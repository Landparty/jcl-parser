"""Profile for ``IEBDG`` — test data generator.

Control statements are read from ``SYSIN``: ``DSD`` names the output data
set with ``OUTPUT=(ddname)`` (and inputs with ``INPUT=(...)``), ``FD``
describes a field, and ``CREATE`` requests record generation (optionally
with a ``REPEAT`` count sub-parameter).  Any statement may carry a name
field in column 1 (issue #204), so the statements are read through
:func:`~jclparser.program_profiles._control.parse_control_statements`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._control import parse_control_statements, split_operands
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_OPERATIONS = frozenset({"DSD", "FD", "CREATE", "REPEAT", "END"})


def _keywords(operands: str) -> dict[str, str]:
    """``KEY=value`` operands, keys upper-cased, outer parentheses dropped."""
    found: dict[str, str] = {}
    for part in split_operands(operands):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        value = value.strip()
        if value.startswith("(") and value.endswith(")"):
            value = value[1:-1]
        found.setdefault(key.strip().upper(), value)
    return found


class IEBDGProfile(ProgramProfile):
    program_names = frozenset({"IEBDG"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []
        field_names: list[str] = []

        for statement in parse_control_statements(text, _OPERATIONS):
            keys = _keywords(statement.operands)
            if statement.operation == "DSD":
                note = "DSD"
                if "OUTPUT" in keys:
                    note += f" OUTPUT={keys['OUTPUT']}"
                if "INPUT" in keys:
                    note += f" INPUT={keys['INPUT']}"
                notes.append(note)
            elif statement.operation == "FD" and "NAME" in keys:
                field_names.append(keys["NAME"])
            elif statement.operation == "CREATE":
                repeat = keys.get("REPEAT")
                notes.append(f"CREATE REPEAT={repeat}" if repeat else "CREATE")
        if field_names:
            fd_note = f"FD fields: {', '.join(field_names)}"
            first_create = next(
                (i for i, n in enumerate(notes) if n.startswith("CREATE")),
                len(notes),
            )
            notes.insert(first_create, fd_note)

        summary = (
            f"IEBDG: generates test data ({len(field_names)} field(s))"
            if notes
            else "IEBDG with no recognised control statements"
        )
        return ProgramAnalysis(
            program="IEBDG",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
