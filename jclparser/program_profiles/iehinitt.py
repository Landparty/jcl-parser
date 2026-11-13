"""Profile for ``IEHINITT`` — magnetic tape volume initialization utility.

Control statements are read from ``SYSIN``. IBM documents one statement::

    ddname   INITT SER=serial[,NUMBTAPE=n][,OWNER='name'][,DISP=REWIND|UNLOAD]...

The name field is the ddname of the DD that allocates the tape unit, so it
is read as the statement's label (through
:func:`~jclparser.program_profiles._control.parse_control_statements`).
``SER=`` gives the first volume serial and ``OWNER=`` the owner ID, usually
quoted. IEHINITT works entirely through tape labels rather than DD dataset
references, so — like :mod:`jclparser.program_profiles.iehlist` — the
profile only reports which volumes were initialized and does not emit
:class:`~jclparser.dataset_lifecycle.DatasetEvent` entries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._control import parse_control_statements, split_operands
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_OPERATIONS = frozenset({"INITT"})


def _keywords(operands: str) -> dict[str, str]:
    """``KEY=value`` operands, keys upper-cased, surrounding quotes dropped.
    ``VOL=SER=x`` (DD syntax, not INITT's) is read as ``SER=x``."""
    found: dict[str, str] = {}
    for part in split_operands(operands):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        key = key.strip().upper()
        value = value.strip()
        if key == "VOL" and value.upper().startswith("SER="):
            key, value = "SER", value[4:]
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1].replace("''", "'")
        found.setdefault(key, value)
    return found


def _initt_note(label: str, keys: dict[str, str]) -> str:
    parts = [f"{name}={keys[name]}" for name in ("SER", "OWNER") if name in keys]
    if "NUMBTAPE" in keys:
        parts.append(f"NUMBTAPE={keys['NUMBTAPE']}")
    note = f"INITT {label}" if label else "INITT"
    return f"{note} ({', '.join(parts)})" if parts else note


class IEHINITTProfile(ProgramProfile):
    program_names = frozenset({"IEHINITT"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes = [
            _initt_note(statement.label.upper(), _keywords(statement.operands))
            for statement in parse_control_statements(text, _OPERATIONS)
            if statement.operation == "INITT"
        ]
        summary = (
            f"IEHINITT: {len(notes)} tape initialization(s)"
            if notes
            else "IEHINITT with no recognised INITT statements"
        )
        return ProgramAnalysis(
            program="IEHINITT",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
