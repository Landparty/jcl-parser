"""Profile for ``IEBPTPCH`` — sequential/PDS print & punch utility.

Control statements are read from ``SYSIN``: ``PRINT`` or ``PUNCH`` selects
the mode, ``TITLE`` supplies a report heading, ``MEMBER`` selects a PDS
member, and ``RECORD`` narrows the field range printed/punched.  Input
comes from ``SYSUT1``; output goes to ``SYSUT2``.  Any statement may carry
a name field in column 1 (issue #204), so the statements are read through
:func:`~jclparser.program_profiles._control.parse_control_statements`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._control import parse_control_statements, split_operands
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_OPERATIONS = frozenset({"PRINT", "PUNCH", "TITLE", "MEMBER", "RECORD", "LABELS"})


def _keyword(operands: str, key: str) -> str | None:
    """The value of ``KEY=value`` among *operands*, or ``None``."""
    prefix = f"{key}="
    for part in split_operands(operands):
        if part.upper().startswith(prefix):
            return part[len(prefix) :]
    return None


class IEBPTPCHProfile(ProgramProfile):
    program_names = frozenset({"IEBPTPCH"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []
        statements = parse_control_statements(text, _OPERATIONS)

        mode = next(
            (s.operation for s in statements if s.operation in ("PRINT", "PUNCH")),
            None,
        )
        if mode:
            notes.append(mode)
        for statement in statements:
            if statement.operation == "MEMBER":
                name = _keyword(statement.operands, "NAME")
                if name:
                    notes.append(f"MEMBER {name}")
        if any(s.operation == "TITLE" for s in statements):
            notes.append("TITLE")
        if any(s.operation == "RECORD" for s in statements):
            notes.append("RECORD (field selection)")

        sysut1 = step.get_dd("SYSUT1")
        if sysut1 and sysut1.dataset_name:
            notes.append(f"reads {sysut1.dataset_name}")

        summary = (
            f"IEBPTPCH: {len(notes)} control clause(s)"
            if notes
            else "IEBPTPCH with no recognised control statements"
        )
        return ProgramAnalysis(
            program="IEBPTPCH",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
