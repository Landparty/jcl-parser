"""Profiles for simple IBM copy utilities: ``IEBGENER``, ``IEBCOPY``, and
``ICEGENER`` (the DFSORT-based drop-in replacement for IEBGENER).

These programs copy data from one dataset to another.  IEBGENER and
ICEGENER always copy SYSUT1 (every dataset of its concatenation) to SYSUT2,
and the profile reports that pair so downstream consumers can model the data
flow without re-interpreting DD dispositions.

IEBCOPY copies between the DDs its SYSIN control statements name
(``COPY OUTDD=OUT,INDD=(IN1,IN2)``); SYSUT1 / SYSUT2 are its defaults only
when there are no control statements, and SYSUT3 / SYSUT4 are spill files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..dataset_lifecycle import DatasetEvent
from ._control import ControlStatement, parse_control_statements, split_operands
from .base import ProgramAnalysis, ProgramProfile, _concatenation, _dd_event

if TYPE_CHECKING:
    from ..model import Step


class _Flow:
    """The dataset events and notes of a copy, one DD at a time."""

    def __init__(self, step: Step) -> None:
        self.step = step
        self.events: list[DatasetEvent] = []
        self.notes: list[str] = []
        self._seen: set[tuple[str, str]] = set()

    def add(self, dd_name: str, verb: str, default_status: str) -> None:
        """Record every dataset of the DD (concatenation) *dd_name*."""
        if (dd_name, verb) in self._seen:
            return
        self._seen.add((dd_name, verb))
        for dd in _concatenation(self.step, dd_name):
            if not dd.dataset_name:
                continue
            self.events.append(
                _dd_event(self.step, dd_name, dd, default_status=default_status)
            )
            self.notes.append(f"{verb} {dd.dataset_name}")


def _copy_utility_analysis(step: Step, program: str) -> ProgramAnalysis:
    flow = _Flow(step)
    flow.add("SYSUT1", "reads", "SHR")
    flow.add("SYSUT2", "writes", "NEW")
    summary = (
        f"{program}: copy SYSUT1 -> SYSUT2"
        if flow.events
        else f"{program} (no SYSUT1/SYSUT2)"
    )
    return ProgramAnalysis(
        program=program,
        step_name=step.name or "",
        summary=summary,
        dataset_events=flow.events,
        notes=flow.notes,
    )


class IEBGENERProfile(ProgramProfile):
    program_names = frozenset({"IEBGENER"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        return _copy_utility_analysis(step, "IEBGENER")


# ---------------------------------------------------------------------------
# IEBCOPY
# ---------------------------------------------------------------------------

#: IEBCOPY operation names (and abbreviations) -> the name reported.
_IEBCOPY_COPIES = {
    "COPY": "copy",
    "C": "copy",
    "COPYMOD": "copymod",
    "CM": "copymod",
    "COPYGRP": "copygrp",
    "CG": "copygrp",
}
_IEBCOPY_MEMBER_LISTS = {"SELECT": "select", "S": "select"}
_IEBCOPY_MEMBER_LISTS.update({"EXCLUDE": "exclude", "E": "exclude"})
_IEBCOPY_OPERATIONS = frozenset(
    {*_IEBCOPY_COPIES, *_IEBCOPY_MEMBER_LISTS, "ALTERMOD", "AM"}
)


@dataclass
class _CopyOperation:
    """One IEBCOPY copy: its operation, DDs and member lists."""

    operation: str
    indd: list[str] = field(default_factory=list)
    outdd: str = ""
    members: list[str] = field(default_factory=list)


def _keyword_operands(operands: str) -> list[tuple[str, str]]:
    """``KEY=value`` operands of *operands* as upper-cased ``(KEY, value)``."""
    pairs = []
    for operand in split_operands(operands):
        key, _, value = operand.partition("=")
        pairs.append((key.strip().upper(), value.strip()))
    return pairs


def _first_names(value: str) -> list[str]:
    """The names of a ``(A,(B,R),(C,NEWC))`` list: the first item of each
    entry (an ``INDD`` replace option or a ``MEMBER`` rename is dropped)."""
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    names = []
    for entry in split_operands(value):
        entry = entry.strip("()")
        name = entry.split(",", 1)[0].strip()
        if name:
            names.append(name.upper())
    return names


def _apply_operands(copy: _CopyOperation, operands: str) -> None:
    for key, value in _keyword_operands(operands):
        if key in ("INDD", "I"):
            copy.indd.extend(_first_names(value))
        elif key in ("OUTDD", "O"):
            copy.outdd = value.upper()


def _iebcopy_operations(statements: list[ControlStatement]) -> list[_CopyOperation]:
    """The copy operations of *statements*, with the INDD statements and
    SELECT / EXCLUDE lists that follow each attached to it."""
    copies: list[_CopyOperation] = []
    for stmt in statements:
        if stmt.operation in _IEBCOPY_COPIES:
            copies.append(_CopyOperation(_IEBCOPY_COPIES[stmt.operation]))
            _apply_operands(copies[-1], stmt.operands)
        elif not copies:
            continue
        elif stmt.operation in _IEBCOPY_MEMBER_LISTS:
            verb = _IEBCOPY_MEMBER_LISTS[stmt.operation]
            for key, value in _keyword_operands(stmt.operands):
                if key in ("MEMBER", "M"):
                    names = ",".join(_first_names(value))
                    copies[-1].members.append(f"{verb} members {names}")
        elif not stmt.operation:
            # A separate ``INDD=`` statement continues the copy before it.
            _apply_operands(copies[-1], stmt.operands)
    return copies


def _iebcopy_analysis(step: Step, copies: list[_CopyOperation]) -> ProgramAnalysis:
    flow = _Flow(step)
    descriptions = []
    for copy in copies:
        for dd_name in copy.indd:
            flow.add(dd_name, "reads", "SHR")
        if copy.outdd:
            flow.add(copy.outdd, "writes", "NEW")
        flow.notes.extend(copy.members)
        source = ",".join(copy.indd) or "?"
        descriptions.append(f"{copy.operation} {source} -> {copy.outdd or '?'}")
    return ProgramAnalysis(
        program="IEBCOPY",
        step_name=step.name or "",
        summary=f"IEBCOPY: {'; '.join(descriptions)}",
        dataset_events=flow.events,
        notes=flow.notes,
    )


class IEBCOPYProfile(ProgramProfile):
    program_names = frozenset({"IEBCOPY"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        sysin = step.get_dd("SYSIN")
        text = sysin.inline_data if sysin is not None else None
        copies = _iebcopy_operations(
            parse_control_statements(text or "", _IEBCOPY_OPERATIONS)
        )
        if copies:
            return _iebcopy_analysis(step, copies)
        # No control statements: IEBCOPY copies SYSUT1 to SYSUT2.
        return _copy_utility_analysis(step, "IEBCOPY")


class ICEGENERProfile(ProgramProfile):
    program_names = frozenset({"ICEGENER"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        return _copy_utility_analysis(step, "ICEGENER")
