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
  then referenced in step M (M > N).

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
from .model import Job, iter_execution_steps

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


def _parse_disp_tokens(disposition) -> tuple[str, str, str]:
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
# Public API
# ---------------------------------------------------------------------------


def analyze_dataset_lifecycle(job: Job) -> dict[str, list[DatasetEvent]]:
    """Build a per-dataset event log for *job*.

    Iterates all steps in execution order (flattening conditional branches)
    and records every DISP interaction with each named dataset.

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

    for step in iter_execution_steps(job.steps):
        step_name = step.name or "(unnamed)"
        for dd in step.dd_statements:
            dsn = dd.dataset_name
            if not dsn:
                continue

            dsn_key = dsn.upper()
            status, normal, abnormal = _parse_disp_tokens(dd.disposition)
            if not status:
                continue

            action = _action_from_disp(status)
            event = DatasetEvent(
                step_name=step_name,
                dd_name=dd.name or "",
                action=action,
                disp_status=status,
                disp_normal=normal,
                disp_abnormal=abnormal,
                line_number=dd.line_number,
            )

            if dsn_key not in lifecycle:
                lifecycle[dsn_key] = []
            lifecycle[dsn_key].append(event)

    return lifecycle


def validate_dataset_lifecycle(job: Job) -> list[ValidationError]:
    """Validate cross-step dataset lifecycle consistency.

    Checks for:

    * **Duplicate allocation** — ``DISP=NEW`` with a cataloging normal
      disposition (``CATLG`` / ``CATALOG``) appearing more than once for the
      same dataset name without an intervening deletion.
    * **Use after uncatalog** — a step opens a dataset that was explicitly
      uncataloged by an earlier step.
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
    errors: list[ValidationError] = []
    lifecycle = analyze_dataset_lifecycle(job)

    for dsn, events in lifecycle.items():
        # Skip temporary datasets — handled by validate_data_dependencies
        if dsn.startswith("&&"):
            continue

        # Catalog state as the steps run: the event that cataloged the
        # dataset (None while it is not known to be cataloged by this job)
        # and the event that last deleted / uncataloged it.  A state, not a
        # count: a delete of a pre-existing dataset (the IEFBR14
        # DISP=(MOD,DELETE) idiom) followed by a re-create must leave the
        # dataset cataloged, not at "zero catalogs".
        cataloged_by: DatasetEvent | None = None
        uncataloged_by: DatasetEvent | None = None
        _first_alloc_pos: int | None = None

        for pos, evt in enumerate(events):
            is_catlg = (
                evt.disp_normal in _CATLG_VALUES or evt.disp_abnormal in _CATLG_VALUES
            )
            # Only a normal-termination CATLG leaves the dataset cataloged for
            # the steps that follow: an abnormal one (DISP=(NEW,PASS,CATLG),
            # DISP=(NEW,KEEP,CATLG)) takes effect only if the step abends,
            # and the later steps are then normally bypassed with it.
            catalogs_for_later_steps = evt.disp_normal in _CATLG_VALUES

            if evt.action == "ALLOCATE":
                if _first_alloc_pos is None:
                    _first_alloc_pos = pos
                if is_catlg:
                    # Check for duplicate cataloging: already cataloged and not
                    # subsequently deleted/uncataloged
                    if cataloged_by is not None:
                        first_catlg_evt = cataloged_by
                        errors.append(
                            ValidationError(
                                f"Dataset '{dsn}' allocated with DISP=NEW,CATLG in step "
                                f"'{evt.step_name}' (DD {evt.dd_name}) but was already "
                                f"cataloged in step '{first_catlg_evt.step_name}' without "
                                f"an intervening DELETE or UNCATLG",
                                ErrorType.VALIDATION_ERROR,
                                severity=ErrorSeverity.WARNING,
                                line_number=evt.line_number,
                            )
                        )
                    if catalogs_for_later_steps and cataloged_by is None:
                        cataloged_by = evt
                        uncataloged_by = None

            elif evt.action in ("OPEN_EXCLUSIVE", "OPEN_SHARED", "EXTEND"):
                # Check for use after uncatalog
                if uncataloged_by is not None and cataloged_by is None:
                    last_uncatlg_evt = uncataloged_by
                    errors.append(
                        ValidationError(
                            f"Dataset '{dsn}' opened in step '{evt.step_name}' "
                            f"(DD {evt.dd_name}) after being uncataloged in step "
                            f"'{last_uncatlg_evt.step_name}'",
                            ErrorType.VALIDATION_ERROR,
                            severity=ErrorSeverity.WARNING,
                            line_number=evt.line_number,
                        )
                    )

                # Forward-reference check: dataset opened (OLD or SHR) before
                # it is allocated anywhere in the job — heuristic warning because
                # the dataset may already exist in the catalog from a prior run.
                if (
                    evt.action in ("OPEN_EXCLUSIVE", "OPEN_SHARED")
                    and _first_alloc_pos is None
                ):
                    has_later_alloc = any(
                        e.action == "ALLOCATE" for e in events[pos + 1 :]
                    )
                    if has_later_alloc:
                        disp_label = (
                            "DISP=OLD" if evt.action == "OPEN_EXCLUSIVE" else "DISP=SHR"
                        )
                        errors.append(
                            ValidationError(
                                f"Dataset '{dsn}' opened {disp_label} in step "
                                f"'{evt.step_name}' (DD {evt.dd_name}) before it "
                                f"is allocated in a later step — verify the dataset "
                                f"exists in the catalog",
                                ErrorType.VALIDATION_ERROR,
                                severity=ErrorSeverity.WARNING,
                                line_number=evt.line_number,
                            )
                        )

            # Track uncatalog dispositions.  Only the normal disposition
            # counts: an abnormal one (DISP=(OLD,KEEP,UNCATLG)) takes effect
            # only if the step abends, and the later steps that would then
            # see the dataset uncataloged are normally bypassed with it.
            if evt.disp_normal in _UNCATLG_VALUES or evt.disp_normal in _DELETE_VALUES:
                # DELETE removes the catalog entry along with the dataset.
                cataloged_by = None
                uncataloged_by = evt

    return errors
