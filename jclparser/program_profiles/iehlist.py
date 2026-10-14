"""Profile for ``IEHLIST`` — VTOC / PDS directory listing utility.

Control statements are read from ``SYSIN``: ``LISTVTOC``, ``LISTPDS``, and
``LISTDG`` (the latter also usable as ``LISTIDG``).  IEHLIST is read-only —
it never mutates a dataset — so the profile only reports which listing
commands ran and, where present, the volume/dataset they target.

The statements are read with the shared utility-statement tokeniser
(:mod:`._control`): an optional label in column 1, the operation, then the
operands up to the first blank outside quotes and parentheses, continued by a
trailing comma or a non-blank column 72.  ``LISTPDS DSNAME=`` takes one name
or a parenthesised list, ``DSNAME=(A.B,'C.D')``; each name is reported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._control import parse_control_statements, split_operands
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_OPERATIONS = frozenset({"LISTVTOC", "LISTPDS", "LISTDG", "LISTIDG"})


def _keywords(operands: str) -> dict[str, str]:
    """``KEY=value`` operands as ``{KEY: value}``; positional ones are dropped."""
    pairs: dict[str, str] = {}
    for operand in split_operands(operands):
        key, sep, value = operand.partition("=")
        if sep:
            pairs.setdefault(key.strip().upper(), value.strip())
    return pairs


def _dataset_names(value: str) -> list[str]:
    """The names of ``DSNAME=A.B`` or ``DSNAME=(A.B,'C.D')``, quotes removed."""
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    return [name.strip("'") for name in split_operands(value) if name.strip("'")]


def _notes(text: str) -> tuple[int, list[str]]:
    """The number of listing statements and their notes, in coded order:
    one note per statement, except one per dataset of a ``LISTPDS`` list."""
    commands = 0
    notes: list[str] = []
    for stmt in parse_control_statements(text, _OPERATIONS):
        if stmt.operation not in _OPERATIONS:
            continue
        commands += 1
        keywords = _keywords(stmt.operands)
        if stmt.operation == "LISTVTOC":
            vol = keywords.get("VOL")
            notes.append(f"LISTVTOC VOL={vol}" if vol else "LISTVTOC")
        elif stmt.operation == "LISTPDS":
            names = _dataset_names(keywords.get("DSNAME", ""))
            notes.extend(f"LISTPDS DSNAME={name}" for name in names)
            if not names:
                notes.append("LISTPDS")
        else:
            notes.append("LISTDG")
    return commands, notes


class IEHLISTProfile(ProgramProfile):
    program_names = frozenset({"IEHLIST"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        commands, notes = _notes(text)

        summary = (
            f"IEHLIST: {commands} listing command(s)"
            if commands
            else "IEHLIST with no recognised commands"
        )
        return ProgramAnalysis(
            program="IEHLIST",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
