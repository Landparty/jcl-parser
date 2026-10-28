"""Profile for ``IEHPROGM`` — catalog/VTOC maintenance utility.

Control statements are read from ``SYSIN``: ``SCRATCH`` (delete),
``RENAME``, ``CATLG``, ``UNCATLG``, ``BLDG``, and ``CONNECT``.  Unlike the
read-only listing in IEHLIST, several of these commands mutate the catalog,
so — like :mod:`jclparser.program_profiles.idcams` — the profile emits
:class:`~jclparser.dataset_lifecycle.DatasetEvent` entries for
``SCRATCH``/``CATLG``/``UNCATLG``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..dataset_lifecycle import DatasetEvent
from ._control import ControlStatement, parse_control_statements, split_operands
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_OPERATIONS = frozenset({"SCRATCH", "RENAME", "CATLG", "UNCATLG", "BLDG", "CONNECT"})

#: The DatasetEvent each mutating command records:
#: (action, disp_status, disp_normal).
_EVENTS: dict[str, tuple[str, str, str]] = {
    "SCRATCH": ("DELETE", "OLD", "DELETE"),
    "CATLG": ("ALLOCATE", "NEW", "CATLG"),
    "UNCATLG": ("UNCATALOG", "OLD", "UNCATLG"),
}

_NOTES = {
    "BLDG": "BLDG (build generation data group index)",
    "CONNECT": "CONNECT (add user catalog connection)",
}


def _dsname(statement: ControlStatement) -> str | None:
    """The ``DSNAME=`` operand of *statement*, continuations joined."""
    for operand in split_operands(statement.operands):
        key, _, value = operand.partition("=")
        if key.strip().upper() in ("DSNAME", "DSN") and value:
            return value.strip()
    return None


class IEHPROGMProfile(ProgramProfile):
    program_names = frozenset({"IEHPROGM"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        # Card images whole: a DSNAME= on a column-72 continuation card
        # belongs to the statement above it (issue #113).
        text = _sysin_text(step, card_images=True) or ""
        events: list[DatasetEvent] = []
        notes: list[str] = []
        seen_notes: set[str] = set()

        for statement in parse_control_statements(text, _OPERATIONS):
            operation = statement.operation
            if operation in _NOTES:
                if operation not in seen_notes:
                    seen_notes.add(operation)
                    notes.append(_NOTES[operation])
                continue
            dsn = _dsname(statement)
            if operation not in _OPERATIONS or dsn is None:
                continue
            if operation in _EVENTS:
                action, status, normal = _EVENTS[operation]
                events.append(
                    DatasetEvent(
                        step_name=step.name or "",
                        dd_name="SYSIN",
                        action=action,
                        disp_status=status,
                        disp_normal=normal,
                        line_number=step.line_number,
                    )
                )
            notes.append(f"{operation} {dsn}")

        summary = (
            f"IEHPROGM: {len(events)} dataset mutations, {len(notes)} commands"
            if events or notes
            else "IEHPROGM with no recognised commands"
        )
        return ProgramAnalysis(
            program="IEHPROGM",
            step_name=step.name or "",
            summary=summary,
            dataset_events=events,
            notes=notes,
            raw_control=_sysin_text(step),
        )
