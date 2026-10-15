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
both run) and their catalog state is merged at ``ENDIF``.  A step whose
``COND=`` can bypass it is analysed as such a THEN branch with an empty ELSE;
``COND=EVEN`` alone does not bypass a step on the normal path.  Backward references
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

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .errors import ErrorSeverity, ErrorType, ValidationError
from .metrics import _counted_dataset_name
from .model import ConditionalBlock, Job, Step, _dataset_dds

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

#: The IF branches a step sits in, outermost first: ``(IF id, is THEN)``.
_Path = tuple[tuple[int, bool], ...]


@dataclass
class _StepEvents:
    """The events of one step, in DD order.

    Kept together because dispositions take effect at the *end* of the
    step: every DD of the step sees the catalog state from before it (#65).
    """

    events: list[_Event]
    path: _Path = ()


def _on_one_path(a: _Path, b: _Path) -> bool:
    """True unless *a* and *b* sit in opposite branches of the same IF."""
    for (a_if, a_then), (b_if, b_then) in zip(a, b, strict=False):
        if a_if != b_if:
            return True
        if a_then != b_then:
            return False
    return True


def _iter_step_events(nodes: list[_Node]) -> Iterator[_StepEvents]:
    """Every :class:`_StepEvents` under *nodes*, in flattened order."""
    for node in nodes:
        if isinstance(node, _Branch):
            yield from _iter_step_events(node.then_nodes)
            yield from _iter_step_events(node.else_nodes)
        else:
            yield node


#: One step's events, or the two branches of an ``IF``.
_Node = _StepEvents | _Branch


def _cond_may_bypass(step: Step) -> bool:
    """True when *step*'s ``COND=`` can bypass it on the normal path.

    ``COND=ONLY`` runs the step only after an abend, and any RC test
    (``COND=(4,LT)``, ``COND=((0,NE,S1),EVEN)``) bypasses it when the test
    is true; an unresolved ``COND=&C`` may be either.  ``COND=EVEN`` alone
    runs the step whether or not an earlier step abended, so it always runs
    on the normal path.
    """
    cond = step.parameters.get("COND")
    if not cond:
        return False
    raw = ",".join(cond) if isinstance(cond, list) else str(cond)
    tokens = [t.strip().upper() for t in re.split(r"[(),]", raw) if t.strip()]
    return any(token != "EVEN" for token in tokens)


def _step_events(
    step: Step,
    lifecycle: dict[str, list[DatasetEvent]],
    by_dd: dict[str, str],
    path: _Path,
) -> _StepEvents | None:
    """Record *step*'s events into *lifecycle*; ``None`` when it has none."""
    step_name = step.name or ""
    step_events: list[_Event] = []
    for dd in _dataset_dds(step):
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
            step_name=step.name or "(unnamed)",
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
    return _StepEvents(step_events, path) if step_events else None


def _collect_events(
    items: list[Step | ConditionalBlock],
    lifecycle: dict[str, list[DatasetEvent]],
    by_dd: dict[str, str],
    path: _Path = (),
) -> list[_Node]:
    """Record the events of *items* into *lifecycle*, keeping their IF shape.

    Events are appended to *lifecycle* in flattened execution order (THEN
    before ELSE, as :func:`~jclparser.model.iter_execution_steps` yields
    them); the returned nodes keep each ``IF``'s branches apart so catalog
    state can be run through them separately.  *by_dd* maps ``"STEP.DD"`` to
    the dataset seen so far, to resolve ``DSN=*.STEP.DD`` backward references.
    *path* is the IF branches *items* sit in.

    A step whose ``COND=`` can bypass it (:func:`_cond_may_bypass`) is a
    THEN branch with an empty ELSE, like ``// IF ... THEN`` around it
    (issue #108).
    """
    nodes: list[_Node] = []
    for item in items:
        if isinstance(item, ConditionalBlock):
            branch = id(item)
            nodes.append(
                _Branch(
                    _collect_events(
                        item.then_steps, lifecycle, by_dd, path + ((branch, True),)
                    ),
                    _collect_events(
                        item.else_steps, lifecycle, by_dd, path + ((branch, False),)
                    ),
                )
            )
            continue
        if not isinstance(item, Step):
            continue
        bypassable = _cond_may_bypass(item)
        step_path = path + ((id(item), True),) if bypassable else path
        node = _step_events(item, lifecycle, by_dd, step_path)
        if node is None:
            continue
        nodes.append(_Branch([node], []) if bypassable else node)
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


#: A parenthesised suffix at the end of a dataset name: a PDS member
#: (``LIB(MEM)``) or a relative GDG generation (``GDG(+1)``).
_RE_PAREN_SUFFIX = re.compile(r"^(?P<base>[^()]*)\((?P<inner>[^()]*)\)$")
#: A relative generation number: a signed or unsigned integer.
_RE_GENERATION = re.compile(r"^(?P<sign>[+-]?)(?P<number>\d+)$")


def _library_key(dsn: str) -> str:
    """The dataset *dsn* allocates, for catalog-state purposes.

    A DISP applies to a whole library, not to the member named with it, so
    ``P.L(M1)`` and ``P.L(M2)`` are both ``P.L`` (a temporary
    ``&&TEMP(MEM)`` is ``&&TEMP``).  A relative GDG generation names a
    dataset of its own and is kept, with its number spelled one way:
    ``G.H(+01)`` is ``G.H(+1)`` and ``G.H(00)`` / ``G.H(-0)`` are
    ``G.H(0)``.  What is in the parentheses decides which it is: an integer
    is a generation, anything else (a member name, a symbol) a member.
    """
    match = _RE_PAREN_SUFFIX.match(dsn)
    if match is None:
        return dsn
    base = match.group("base")
    generation = _RE_GENERATION.match(match.group("inner").strip())
    if generation is None:
        return base
    number = int(generation.group("number"))
    if number == 0:
        return f"{base}(0)"
    return f"{base}({generation.group('sign')}{number})"


def _group_by_library(nodes: list[_Node], counts: dict[str, int]) -> list[_Node]:
    """*nodes* with every event keyed by :func:`_library_key`.

    Events of the names that share a key are renumbered in flattened order
    (the order :func:`_collect_events` recorded them in), so positions stay
    comparable within the merged group.  *counts* collects the number of
    events per key, in order of first appearance.
    """
    grouped: list[_Node] = []
    for node in nodes:
        if isinstance(node, _Branch):
            grouped.append(
                _Branch(
                    _group_by_library(node.then_nodes, counts),
                    _group_by_library(node.else_nodes, counts),
                )
            )
            continue
        events: list[_Event] = []
        for dsn, _pos, evt in node.events:
            key = _library_key(dsn)
            pos = counts.get(key, 0)
            counts[key] = pos + 1
            events.append((key, pos, evt))
        grouped.append(_StepEvents(events, node.path))
    return grouped


class _LifecycleChecker:
    """Runs the catalog state of every dataset through a job's events."""

    def __init__(self, nodes: list[_Node]) -> None:
        self.nodes = nodes
        # Each dataset's allocations (position in flattened order, IF
        # branches), for the forward-reference heuristic.
        self.allocations: dict[str, list[tuple[int, _Path]]] = {}
        for step in _iter_step_events(nodes):
            for dsn, pos, evt in step.events:
                if evt.action == "ALLOCATE":
                    self.allocations.setdefault(dsn, []).append((pos, step.path))
        # Errors per dataset, keyed by event position, so they come out
        # grouped by dataset in event order however the branches are walked.
        self.found: dict[str, list[tuple[int, ValidationError]]] = {}

    def errors(self, order: Iterable[str]) -> list[ValidationError]:
        """Run the job and return its findings, grouped by dataset in *order*."""
        self._run(self.nodes, {})
        errors: list[ValidationError] = []
        for dsn in order:
            errors.extend(
                err for _pos, err in sorted(self.found.get(dsn, []), key=lambda f: f[0])
            )
        return errors

    def _allocated_only_later(self, dsn: str, pos: int, path: _Path) -> bool:
        """True when *dsn* is allocated after *pos*, and not before it, on a
        path through the job that also runs the event at *pos*: the THEN
        and ELSE branches of one IF never both run."""
        on_path = [
            p for p, alloc in self.allocations.get(dsn, []) if _on_one_path(path, alloc)
        ]
        return bool(on_path) and min(on_path) > pos

    def _report(self, dsn: str, pos: int, message: str, evt: DatasetEvent) -> None:
        self.found.setdefault(dsn, []).append(
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
        self, dsn: str, pos: int, evt: DatasetEvent, state: _CatalogState, path: _Path
    ) -> _CatalogState:
        cataloged_by = state[0]
        is_catlg = (
            evt.disp_normal in _CATLG_VALUES or evt.disp_abnormal in _CATLG_VALUES
        )
        if evt.action == "ALLOCATE" and is_catlg and cataloged_by is not None:
            # Already cataloged and not subsequently deleted/uncataloged.
            self._report(
                dsn,
                pos,
                f"Dataset '{dsn}' allocated with DISP=NEW,CATLG in step "
                f"'{evt.step_name}' (DD {evt.dd_name}) but was already "
                f"cataloged in step '{cataloged_by.step_name}' without "
                f"an intervening DELETE or UNCATLG",
                evt,
            )

        if evt.action in ("OPEN_EXCLUSIVE", "OPEN_SHARED"):
            self._check_open(dsn, pos, evt, state, path)

        # Only a normal-termination CATLG leaves the dataset cataloged for
        # the steps that follow: an abnormal one (DISP=(NEW,PASS,CATLG),
        # DISP=(NEW,KEEP,CATLG)) takes effect only if the step abends, and
        # the later steps are then normally bypassed with it.  A cataloging
        # allocation counts at once, so a second NEW,CATLG of the dataset
        # later in the same step is still a duplicate; the full disposition
        # is applied at step end by _dispose.
        if evt.disp_normal in _CATLG_VALUES and cataloged_by is None:
            return (evt, None)
        return state

    def _check_open(
        self, dsn: str, pos: int, evt: DatasetEvent, state: _CatalogState, path: _Path
    ) -> None:
        """Checks for an OLD / SHR open.  Not for MOD (EXTEND): it creates the
        dataset when it is not there, as in the IEFBR14
        delete-then-DISP=(MOD,CATLG) idiom."""
        cataloged_by, uncataloged_by = state
        if uncataloged_by is not None and cataloged_by is None:
            self._report(
                dsn,
                pos,
                f"Dataset '{dsn}' opened in step '{evt.step_name}' "
                f"(DD {evt.dd_name}) after being uncataloged in step "
                f"'{uncataloged_by.step_name}'",
                evt,
            )

        # Forward-reference check: dataset opened (OLD or SHR) before it is
        # allocated anywhere in the job — heuristic warning because the
        # dataset may already exist in the catalog from a prior run.
        if self._allocated_only_later(dsn, pos, path):
            disp_label = "DISP=OLD" if evt.action == "OPEN_EXCLUSIVE" else "DISP=SHR"
            self._report(
                dsn,
                pos,
                f"Dataset '{dsn}' opened {disp_label} in step "
                f"'{evt.step_name}' (DD {evt.dd_name}) before it "
                f"is allocated in a later step — verify the dataset "
                f"exists in the catalog",
                evt,
            )

    @staticmethod
    def _dispose(evt: DatasetEvent, state: _CatalogState) -> _CatalogState:
        """Apply *evt*'s normal disposition: the catalog state after the step."""
        # Track uncatalog dispositions.  Only the normal disposition counts:
        # an abnormal one (DISP=(OLD,KEEP,UNCATLG)) takes effect only if the
        # step abends, and the later steps that would then see the dataset
        # uncataloged are normally bypassed with it.  DELETE removes the
        # catalog entry along with the dataset.
        if evt.disp_normal in _UNCATLG_VALUES or evt.disp_normal in _DELETE_VALUES:
            return (None, evt)
        # Any disposition that catalogs -- DISP=(NEW,CATLG), but also
        # DISP=(MOD,CATLG) creating the dataset afresh -- leaves it cataloged.
        if evt.disp_normal in _CATLG_VALUES and state[0] is None:
            return (evt, None)
        return state

    def _run(
        self, seq: list[_Node], state: dict[str, _CatalogState]
    ) -> dict[str, _CatalogState]:
        for node in seq:
            if isinstance(node, _Branch):
                # THEN and ELSE never both run: each starts from the state
                # before the IF, and they meet again at ENDIF.
                state = _merge_states(
                    self._run(node.then_nodes, dict(state)),
                    self._run(node.else_nodes, dict(state)),
                )
                continue
            # Skip temporary datasets — handled by validate_data_dependencies
            events = [e for e in node.events if not e[0].startswith("&&")]
            # Dispositions take effect when the step ends, so a DD that
            # follows DISP=(OLD,DELETE) of the same dataset in the same step
            # still finds it there: check every DD first ...
            for dsn, pos, evt in events:
                state[dsn] = self._check(
                    dsn, pos, evt, state.get(dsn, (None, None)), node.path
                )
            # ... then apply the dispositions, in DD order.
            for dsn, _pos, evt in events:
                state[dsn] = self._dispose(evt, state[dsn])
        return state


def validate_dataset_lifecycle(job: Job) -> list[ValidationError]:
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

    A DISP applies to a whole library, so the members of one PDS
    (``P.L(M1)``, ``P.L(M2)``) and the library itself are checked as one
    dataset, reported under the library name; relative GDG generations
    (``G.H(0)``, ``G.H(+1)``) stay separate datasets, ``G.H(+01)`` being the
    same as ``G.H(+1)``.  :func:`analyze_dataset_lifecycle` still keys its
    log by the name as coded.

    Temporary datasets (``&&name``) are handled by the existing check in
    :func:`~jclparser.validators.validate_data_dependencies`; this function
    focuses on permanent (cataloged) datasets only.

    Args:
        job: Parsed job to validate.

    Returns:
        List of :class:`~jclparser.errors.ValidationError` objects.
    """
    counts: dict[str, int] = {}
    nodes = _group_by_library(_collect_events(job.steps, {}, {}), counts)
    return _LifecycleChecker(nodes).errors(counts)
