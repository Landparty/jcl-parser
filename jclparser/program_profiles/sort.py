"""Profile for DFSORT / IBM Sort utilities.

The IBM sort is commonly invoked as ``SORT``, ``ICEMAN``, ``DFSORT``, or
``SORTD``, and the third-party Syncsort product under the compatible name
``SYNCSORT``.  The SYSIN control stream uses ``SORT FIELDS=(…)`` /
``MERGE FIELDS=(…)`` (or ``FIELDS=COPY`` / ``OPTION COPY`` for a copy) with
optional ``INCLUDE``, ``OMIT``, ``INREC``, ``OUTREC``, ``OUTFIL`` statements.
The profile only does a shallow parse — enough to surface the *fact* that
the step sorts, merges or copies, which filters it applies, and which
datasets it reads (SORTIN, SORTIN01-SORTIN99 for a merge, the JOINKEYS
files: SORTJNF1 / SORTJNF2 or the ``F1=`` / ``F2=`` DDs) and writes
(SORTOUT, and each ``OUTFIL``'s ``FNAMES=`` DDs, ``SORTOFx`` for
``FILES=x``, SORTOUT for an ``OUTFIL`` naming neither) — but does not
attempt to validate field specifications.

Each control statement is read as DFSORT reads it: an optional label, the
operation, and the operands up to the first blank outside quotes and
parentheses; the rest of the line is a remark.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ._control import ControlStatement, parse_control_statements, split_operands
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_OPERATIONS = frozenset(
    {
        "SORT",
        "MERGE",
        "OPTION",
        "INCLUDE",
        "OMIT",
        "INREC",
        "OUTREC",
        "OUTFIL",
        "SUM",
        "RECORD",
        "ALTSEQ",
        "DEBUG",
        "END",
        "JOINKEYS",
        "JOIN",
        "REFORMAT",
        "MODS",
    }
)
#: Notes per statement (or ``OUTFIL`` operand) type, in reporting order.
_CLAUSE_NOTES = (
    ("INCLUDE", "INCLUDE filter"),
    ("OMIT", "OMIT filter"),
    ("INREC", "INREC reformat"),
    ("OUTREC", "OUTREC reformat"),
)
#: An input DD: SORTIN, or SORTIN01-SORTIN99 for a MERGE.
_RE_INPUT_DD = re.compile(r"^SORTIN(?:0[1-9]|[1-9][0-9])?$")


def _operand_keys(stmt: ControlStatement) -> set[str]:
    """The upper-cased operands of *stmt*, keyword operands by their key."""
    return {
        operand.partition("=")[0].strip().upper()
        for operand in split_operands(stmt.operands)
    }


def _is_copy_fields(stmt: ControlStatement) -> bool:
    """True for ``FIELDS=COPY`` (or ``FIELDS=(COPY)``) among *stmt*'s operands."""
    return any(
        operand.replace(" ", "").upper() in ("FIELDS=COPY", "FIELDS=(COPY)")
        for operand in split_operands(stmt.operands)
    )


def _kind_notes(statements: list[ControlStatement]) -> list[str]:
    """``SORT FIELDS`` / ``MERGE FIELDS`` / ``COPY``, as the statements ask."""
    notes: list[str] = []
    for stmt in statements:
        if stmt.operation in ("SORT", "MERGE") and _is_copy_fields(stmt):
            note = "COPY"
        elif stmt.operation in ("SORT", "MERGE"):
            note = f"{stmt.operation} FIELDS"
        elif stmt.operation == "OPTION" and "COPY" in _operand_keys(stmt):
            note = "COPY"
        else:
            continue
        if note not in notes:
            notes.append(note)
    return notes


def _clause_notes(statements: list[ControlStatement]) -> list[str]:
    """Filter / reformat notes: from the statements, and from the
    ``INCLUDE=`` / ``OMIT=`` / ``OUTREC=`` operands of ``OUTFIL``."""
    found: set[str] = set()
    for stmt in statements:
        found.add(stmt.operation)
        if stmt.operation == "OUTFIL":
            found |= _operand_keys(stmt)
    return [note for clause, note in _CLAUSE_NOTES if clause in found]


def _keyword_values(stmt: ControlStatement) -> dict[str, list[str]]:
    """*stmt*'s keyword operands: upper-cased key to its value list
    (``FNAMES=(A,B)`` gives ``["A", "B"]``)."""
    values: dict[str, list[str]] = {}
    for operand in split_operands(stmt.operands):
        key, eq, value = operand.partition("=")
        if not eq:
            continue
        value = value.strip()
        if value.startswith("(") and value.endswith(")"):
            value = value[1:-1]
        values[key.strip().upper()] = [
            v.strip().upper() for v in value.split(",") if v.strip()
        ]
    return values


def _outfil_ddnames(stmt: ControlStatement) -> list[str]:
    """The DDs an ``OUTFIL`` writes: ``FNAMES=`` as named, ``FILES=x`` as
    ``SORTOFx``, and ``SORTOUT`` when it names neither."""
    values = _keyword_values(stmt)
    names = values.get("FNAMES", []) + [
        f"SORTOF{suffix}" for suffix in values.get("FILES", [])
    ]
    return names or ["SORTOUT"]


def _joinkeys_ddnames(stmt: ControlStatement) -> list[str]:
    """The DD a ``JOINKEYS`` reads: ``F1=dd`` / ``F2=dd`` as named,
    ``FILE=F1`` / ``FILE=F2`` (or ``FILES=``) as ``SORTJNF1`` / ``SORTJNF2``."""
    values = _keyword_values(stmt)
    names = values.get("F1", []) + values.get("F2", [])
    for key in ("FILE", "FILES"):
        names += [f"SORTJN{f}" for f in values.get(key, []) if f in ("F1", "F2")]
    return names


def _io_ddnames(statements: list[ControlStatement]) -> tuple[set[str], set[str]]:
    """The input and output DD names the control statements name, beyond
    SORTIN / SORTINnn and SORTOUT."""
    inputs: set[str] = set()
    outputs: set[str] = set()
    for stmt in statements:
        if stmt.operation == "OUTFIL":
            outputs.update(_outfil_ddnames(stmt))
        elif stmt.operation == "JOINKEYS":
            inputs.update(_joinkeys_ddnames(stmt))
    return inputs, outputs


def _dataset_notes(step: Step, statements: list[ControlStatement]) -> list[str]:
    """``input:`` for every dataset of SORTIN / SORTINnn and the JOINKEYS
    files (concatenations included), ``output:`` for SORTOUT and the
    ``OUTFIL`` files, in DD order."""
    inputs, outputs = _io_ddnames(statements)
    outputs.add("SORTOUT")
    notes: list[str] = []
    current = ""
    for dd in step.dd_statements:
        if dd.name:
            current = dd.name.upper()
        if not dd.dataset_name:
            continue
        if _RE_INPUT_DD.match(current) or current in inputs:
            notes.append(f"input: {dd.dataset_name}")
        elif current in outputs and dd.name:
            notes.append(f"output: {dd.dataset_name}")
    return notes


class SortProfile(ProgramProfile):
    program_names = frozenset({"SORT", "DFSORT", "ICEMAN", "SORTD", "SYNCSORT"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        raw = _sysin_text(step, card_images=True) or ""
        statements = parse_control_statements(raw, _OPERATIONS)
        kinds = _kind_notes(statements)
        notes = [*kinds, *_clause_notes(statements), *_dataset_notes(step, statements)]

        if not notes:
            summary = f"{step.program} with no recognised control statements"
        elif kinds == ["COPY"]:
            summary = f"{step.program}: copy with {len(notes)} control clauses"
        else:
            summary = f"{step.program}: sort/merge with {len(notes)} control clauses"
        return ProgramAnalysis(
            program=step.program or "SORT",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=raw or None,
        )
