"""
Cross-step dataset lifecycle analysis for JCL jobs.

Tracks how permanent (cataloged) and temporary datasets are created, opened,
and disposed of across all steps in a job.  The analysis produces a structured
:class:`DatasetEvent` log and a set of :class:`~jclparser.errors.ValidationError`
diagnostics for common lifecycle problems.

Detected issues
---------------
* **Duplicate creation** — a dataset is allocated ``DISP=(NEW,CATLG)`` in two
  or more steps without an intervening delete/uncatalog.
* **Forward reference** — step N opens a dataset ``DISP=OLD`` that is first
  *created* in a later step M (M > N).  Reported as a warning because the
  dataset may already exist in the catalog before the job runs.
* **Uncatalog before use** — a dataset is explicitly uncataloged in step N and
  then opened ``OLD`` / ``SHR`` in step M (M > N).

The THEN and ELSE branches of an ``IF`` are analysed separately (they never
both run) and their catalog state is merged at ``ENDIF``.  Backward references
(``DSN=*.STEP.DD``) count as the dataset they point at.

Note: temporary datasets (``&&name``) are intentionally skipped here — they
are handled by :func:`~jclparser.validators.validate_data_dependencies`.

Usage::

    from jclparser.dataset_lifecycle import analyze_dataset_lifecycle
    events = analyze_dataset_lifecycle(job)
    for dsn, evts in events.items():
        for e in evts:
            print(f"  step {e.step_name}: {e.action} ({e.disp_status})")
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ErrorSeverity, ErrorType, ValidationError
from .metrics import _counted_dataset_name
from .model import ConditionalBlock, Job, Step

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class DatasetEvent:
    """A single dataset action recorded for one DD statement in one step.

    Attributes:
        step_name: Name of the step that contains this DD statement.
        dd_name: Name of the DD statement (e.g. ``"INPUT"``).
        action: High-level action keyword (see below).
        disp_status: Opening status token: ``NEW``, ``OLD``, ``SHR``, ``MOD``.
        disp_normal: Normal termination disposition: ``CATLG``, ``KEEP``,
            ``DELETE``, ``UNCATLG``, or ``""`` if omitted.
        disp_abnormal: Abnormal termination disposition (same set as normal),
            or ``""`` if omitted.
        line_number: Source line number of the DD statement.
    """

    step_name: str
    dd_name: str
    action: str  # "ALLOCATE", "OPEN_EXCLUSIVE", "OPEN_SHARED", "EXTEND", "UNCATALOG", "DELETE"
    disp_status: str
    disp_normal: str = ""
    disp_abnormal: str = ""
    line_number: int = 0


# ---------------------------------------------------------------------------
# DISP parsing helpers
# ---------------------------------------------------------------------------

_CATLG_VALUES = frozenset({"CATLG", "CATALOG"})
_DELETE_VALUES = frozenset({"DELETE"})
_UNCATLG_VALUES = frozenset({"UNCATLG"})


def _parse_disp_tokens(disposition: object) -> tuple[str, str, str]:
    """Return (status, normal, abnormal) from a raw DISP value.

    Handles string form ``"(NEW,CATLG,DELETE)"``, list form
    ``["NEW", "CATLG", "DELETE"]``, and bare string ``"SHR"``.

    A coded DISP whose status is omitted (``DISP=(,CATLG,DELETE)``) has
    status ``NEW``, the JCL default. A DD with no DISP at all returns an empty
    status so callers can tell "not stated" apart.
    """
    if not disposition:
        return ("", "", "")

    if isinstance(disposition, list):
        tokens = [str(t).upper().strip() for t in disposition]
    else:
        raw = str(disposition).strip()
        if raw.startswith("(") and raw.endswith(")"):
            raw = raw[1:-1]
        tokens = [t.strip().upper() for t in raw.split(",")]

    # Pad to three elements
    while len(tokens) < 3:
        tokens.append("")

    if not tokens[0]:
        tokens[0] = "NEW"

    return (tokens[0], tokens[1], tokens[2])


def _action_from_disp(status: str) -> str:
    """Map DISP status token to a human-readable action keyword."""
    return {
        "NEW": "ALLOCATE",
        "OLD": "OPEN_EXCLUSIVE",
        "SHR": "OPEN_SHARED",
        "MOD": "EXTEND",
    }.get(status, "UNKNOWN")


# ---------------------------------------------------------------------------
# Structural walk
# ---------------------------------------------------------------------------


@dataclass
class _Branch:
    """The THEN and ELSE event sequences of one ``IF`` construct."""

    then_nodes: list[_Node]
    else_nodes: list[_Node]


#: ``(dataset key, position in that dataset's event list, event)``.
_Event = tuple[str, int, DatasetEvent]


@dataclass
class _StepEvents:
    """The events of one step, in DD order.

    Kept together because dispositions take effect at the *end* of the
    step: every DD of the step sees the catalog state from before it (#65).
    """

    events: list[_Event]


#: One step's events, or the two branches of an ``IF``.
_Node = _StepEvents | _Branch


def _collect_events(
    items: list[Step | ConditionalBlock],
    lifecycle: dict[str, list[DatasetEvent]],
    by_dd: dict[str, str],
) -> list[_Node]:
    """Record the events of *items* into *lifecycle*, keeping their IF shape.

    Events are appended to *lifecycle* in flattened execution order (THEN
    before ELSE, as :func:`~jclparser.model.iter_execution_steps` yields
    them); the returned nodes keep each ``IF``'s branches apart so catalog
    state can be run through them separately.  *by_dd* maps ``"STEP.DD"`` to
    the dataset seen so far, to resolve ``DSN=*.STEP.DD`` backward references.
    """
    nodes: list[_Node] = []
    for item in items:
        if isinstance(item, ConditionalBlock):
            nodes.append(
                _Branch(
                    _collect_events(item.then_steps, lifecycle, by_dd),
                    _collect_events(item.else_steps, lifecycle, by_dd),
                )
            )
            continue
        if not isinstance(item, Step):
            continue
        step_name = item.name or ""
        step_events: list[_Event] = []
        for dd in item.dd_statements:
            if not dd.dataset_name:
                continue
            # A backward reference names the dataset of the DD it points at;
            # NULLFILE and an unresolvable reference name none.
            dsn_key = _counted_dataset_name(dd.dataset_name, step_name, by_dd)
            if dsn_key is None:
                continue
            if dd.name:
                by_dd[f"{step_name}.{dd.name}".upper()] = dsn_key
            status, normal, abnormal = _parse_disp_tokens(dd.disposition)
            if not status:
                continue

            event = DatasetEvent(
                step_name=item.name or "(unnamed)",
                dd_name=dd.name or "",
                action=_action_from_disp(status),
                disp_status=status,
                disp_normal=normal,
                disp_abnormal=abnormal,
                line_number=dd.line_number,
            )
            events = lifecycle.setdefault(dsn_key, [])
            step_events.append((dsn_key, len(events), event))
            events.append(event)
        if step_events:
            nodes.append(_StepEvents(step_events))
    return nodes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_dataset_lifecycle(job: Job) -> dict[str, list[DatasetEvent]]:
    """Build a per-dataset event log for *job*.

    Iterates all steps in execution order (flattening conditional branches)
    and records every DISP interaction with each named dataset.  A backward
    reference (``DSN=*.STEP.DD``) is recorded under the dataset it resolves
    to; ``DSN=NULLFILE`` is not a dataset and is skipped.

    Args:
        job: Parsed job to analyse.

    Returns:
        Dictionary mapping **uppercased dataset name** to an ordered list of
        :class:`DatasetEvent` objects, one per DD reference.

    Example::

        events = analyze_dataset_lifecycle(job)
        for dsn, evts in sorted(events.items()):
            print(dsn, [e.action for e in evts])
    """
    lifecycle: dict[str, list[DatasetEvent]] = {}
    _collect_events(job.steps, lifecycle, {})
    return lifecycle


#: Catalog state of one dataset as the steps run: the event that cataloged it
#: (None while it is not known to be cataloged by this job) and the event that
#: last deleted / uncataloged it.  A state, not a count: a delete of a
#: pre-existing dataset (the IEFBR14 DISP=(MOD,DELETE) idiom) followed by a
#: re-create must leave the dataset cataloged, not at "zero catalogs".
_CatalogState = tuple[DatasetEvent | None, DatasetEvent | None]


def _merge_states(
    then_state: dict[str, _CatalogState], else_state: dict[str, _CatalogState]
) -> dict[str, _CatalogState]:
    """Catalog state after ENDIF: what either branch may have left behind.

    Either branch may have run, so the dataset counts as cataloged (or
    uncataloged) when one of them left it so -- the same verdicts the steps
    after ENDIF got before branches were told apart, so no warning about
    them is lost.
    """
    merged: dict[str, _CatalogState] = {}
    # dict.fromkeys, not ``keys() | keys()``: keeps a stable order, and the
    # set union of two key views crashes Cython's OptimizeBuiltinCalls pass
    # if the module is ever compiled.
    for dsn in dict.fromkeys([*then_state, *else_state]):
        t_cat, t_uncat = then_state.get(dsn, (None, None))
        e_cat, e_uncat = else_state.get(dsn, (None, None))
        merged[dsn] = (t_cat or e_cat, t_uncat or e_uncat)
    return merged


def validate_dataset_lifecycle(job: Job) -> list[ValidationError]:  # noqa: C901 -- complexity baseline, split when touched
    """Validate cross-step dataset lifecycle consistency.

    Checks for:

    * **Duplicate allocation** — ``DISP=NEW`` with a cataloging normal
      disposition (``CATLG`` / ``CATALOG``) appearing more than once for the
      same dataset name without an intervening deletion.  The THEN and ELSE
      branches of an ``IF`` are mutually exclusive, so each allocating the
      same dataset is not a duplicate.
    * **Use after uncatalog** — a step opens (``OLD`` / ``SHR``) a dataset
      that was explicitly uncataloged by an earlier step.  ``MOD`` is exempt:
      it creates the dataset when it does not exist.
    * **Forward reference** — a step opens a permanent dataset exclusively
      (``OLD``) whose *first* lifecycle event is an allocation in a *later*
      step (heuristic; reported as WARNING because the dataset may be
      pre-existing).

    Temporary datasets (``&&name``) are handled by the existing check in
    :func:`~jclparser.validators.validate_data_dependencies`; this function
    focuses on permanent (cataloged) datasets only.

    Args:
        job: Parsed job to validate.

    Returns:
        List of :class:`~jclparser.errors.ValidationError` objects.
    """
    lifecycle: dict[str, list[DatasetEvent]] = {}
    nodes = _collect_events(job.steps, lifecycle, {})
    # Position (in flattened order) of each dataset's first allocation, for
    # the forward-reference heuristic.
    first_alloc: dict[str, int] = {}
    for dsn, events in lifecycle.items():
        for pos, evt in enumerate(events):
            if evt.action == "ALLOCATE":
                first_alloc[dsn] = pos
                break
    # Errors per dataset, keyed by event position, so they come out grouped by
    # dataset in event order however the branches are walked.
    found: dict[str, list[tuple[int, ValidationError]]] = {}

    def _report(dsn: str, pos: int, message: str, evt: DatasetEvent) -> None:
        found.setdefault(dsn, []).append(
            (
                pos,
                ValidationError(
                    message,
                    ErrorType.VALIDATION_ERROR,
                    severity=ErrorSeverity.WARNING,
                    line_number=evt.line_number,
                ),
            )
        )

    def _check(
        dsn: str, pos: int, evt: DatasetEvent, state: _CatalogState
    ) -> _CatalogState:
        cataloged_by, uncataloged_by = state
        is_catlg = (
            evt.disp_normal in _CATLG_VALUES or evt.disp_abnormal in _CATLG_VALUES
        )
        # Only a normal-termination CATLG leaves the dataset cataloged for
        # the steps that follow: an abnormal one (DISP=(NEW,PASS,CATLG),
        # DISP=(NEW,KEEP,CATLG)) takes effect only if the step abends, and
        # the later steps are then normally bypassed with it.
        catalogs_for_later_steps = evt.disp_normal in _CATLG_VALUES

        if evt.action == "ALLOCATE" and is_catlg and cataloged_by is not None:
            # Already cataloged and not subsequently deleted/uncataloged.
            _report(
                dsn,
                pos,
                f"Dataset '{dsn}' allocated with DISP=NEW,CATLG in step "
                f"'{evt.step_name}' (DD {evt.dd_name}) but was already "
                f"cataloged in step '{cataloged_by.step_name}' without "
                f"an intervening DELETE or UNCATLG",
                evt,
            )

        if evt.action in ("OPEN_EXCLUSIVE", "OPEN_SHARED"):
            # Use after uncatalog.  Not for MOD (EXTEND): it creates the
            # dataset when it is not there, as in the IEFBR14
            # delete-then-DISP=(MOD,CATLG) idiom.
            if uncataloged_by is not None and cataloged_by is None:
                _report(
                    dsn,
                    pos,
                    f"Dataset '{dsn}' opened in step '{evt.step_name}' "
                    f"(DD {evt.dd_name}) after being uncataloged in step "
                    f"'{uncataloged_by.step_name}'",
                    evt,
                )

            # Forward-reference check: dataset opened (OLD or SHR) before it
            # is allocated anywhere in the job — heuristic warning because
            # the dataset may already exist in the catalog from a prior run.
            if first_alloc.get(dsn, -1) > pos:
                disp_label = (
                    "DISP=OLD" if evt.action == "OPEN_EXCLUSIVE" else "DISP=SHR"
                )
                _report(
                    dsn,
                    pos,
                    f"Dataset '{dsn}' opened {disp_label} in step "
                    f"'{evt.step_name}' (DD {evt.dd_name}) before it "
                    f"is allocated in a later step — verify the dataset "
                    f"exists in the catalog",
                    evt,
                )

        # A cataloging allocation counts at once, so a second NEW,CATLG of
        # the dataset later in the same step is still a duplicate; the full
        # disposition is applied at step end by _dispose.
        if catalogs_for_later_steps and cataloged_by is None:
            cataloged_by, uncataloged_by = evt, None
        return (cataloged_by, uncataloged_by)

    def _dispose(evt: DatasetEvent, state: _CatalogState) -> _CatalogState:
        """Apply *evt*'s normal disposition: the catalog state after the step."""
        cataloged_by, uncataloged_by = state
        # Any disposition that catalogs -- DISP=(NEW,CATLG), but also
        # DISP=(MOD,CATLG) creating the dataset afresh -- leaves it cataloged.
        if evt.disp_normal in _CATLG_VALUES and cataloged_by is None:
            cataloged_by, uncataloged_by = evt, None

        # Track uncatalog dispositions.  Only the normal disposition counts:
        # an abnormal one (DISP=(OLD,KEEP,UNCATLG)) takes effect only if the
        # step abends, and the later steps that would then see the dataset
        # uncataloged are normally bypassed with it.
        if evt.disp_normal in _UNCATLG_VALUES or evt.disp_normal in _DELETE_VALUES:
            # DELETE removes the catalog entry along with the dataset.
            cataloged_by, uncataloged_by = None, evt
        return (cataloged_by, uncataloged_by)

    def _run(
        seq: list[_Node], state: dict[str, _CatalogState]
    ) -> dict[str, _CatalogState]:
        for node in seq:
            if isinstance(node, _Branch):
                # THEN and ELSE never both run: each starts from the state
                # before the IF, and they meet again at ENDIF.
                state = _merge_states(
                    _run(node.then_nodes, dict(state)),
                    _run(node.else_nodes, dict(state)),
                )
                continue
            # Skip temporary datasets — handled by validate_data_dependencies
            events = [e for e in node.events if not e[0].startswith("&&")]
            # Dispositions take effect when the step ends, so a DD that
            # follows DISP=(OLD,DELETE) of the same dataset in the same step
            # still finds it there: check every DD first ...
            for dsn, pos, evt in events:
                state[dsn] = _check(dsn, pos, evt, state.get(dsn, (None, None)))
            # ... then apply the dispositions, in DD order.
            for dsn, _pos, evt in events:
                state[dsn] = _dispose(evt, state[dsn])
        return state

    _run(nodes, {})

    errors: list[ValidationError] = []
    for dsn in lifecycle:
        errors.extend(
            err for _pos, err in sorted(found.get(dsn, []), key=lambda f: f[0])
        )
    return errors
