"""Profile for DFSORT / IBM Sort utilities.

The IBM sort is commonly invoked as ``SORT``, ``ICEMAN``, ``DFSORT``, or
``SORTD``, and the third-party Syncsort product under the compatible name
``SYNCSORT``.  The SYSIN control stream uses ``SORT FIELDS=(…)`` with optional
``INCLUDE``, ``OMIT``, ``INREC``, ``OUTREC`` statements.  The profile only
does a shallow parse — enough to surface the *fact* that the step sorts
and which filters it applies — but does not attempt to validate field
specifications.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_SORT_FIELDS = re.compile(r"\bSORT\s+FIELDS\s*=", re.IGNORECASE)
_RE_INCLUDE = re.compile(r"\bINCLUDE\b", re.IGNORECASE)
_RE_OMIT = re.compile(r"\bOMIT\b", re.IGNORECASE)
_RE_INREC = re.compile(r"\bINREC\b", re.IGNORECASE)
_RE_OUTREC = re.compile(r"\bOUTREC\b", re.IGNORECASE)
_RE_MERGE = re.compile(r"\bMERGE\s+FIELDS\s*=", re.IGNORECASE)
# A ``*`` in column 1 makes a DFSORT comment statement.
_RE_COMMENT_LINE = re.compile(r"^\s*\*.*$", re.MULTILINE)


class SortProfile(ProgramProfile):
    program_names = frozenset({"SORT", "DFSORT", "ICEMAN", "SORTD", "SYNCSORT"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        raw = _sysin_text(step) or ""
        # Comment statements are not control statements: ``* OMIT ...`` must
        # not read as an OMIT filter.
        text = _RE_COMMENT_LINE.sub("", raw)
        notes: list[str] = []

        if _RE_SORT_FIELDS.search(text):
            notes.append("SORT FIELDS")
        if _RE_MERGE.search(text):
            notes.append("MERGE FIELDS")
        if _RE_INCLUDE.search(text):
            notes.append("INCLUDE filter")
        if _RE_OMIT.search(text):
            notes.append("OMIT filter")
        if _RE_INREC.search(text):
            notes.append("INREC reformat")
        if _RE_OUTREC.search(text):
            notes.append("OUTREC reformat")

        sortin = step.get_dd("SORTIN")
        sortout = step.get_dd("SORTOUT")
        if sortin and sortin.dataset_name:
            notes.append(f"input: {sortin.dataset_name}")
        if sortout and sortout.dataset_name:
            notes.append(f"output: {sortout.dataset_name}")

        summary = (
            f"{step.program}: sort/merge with {len(notes)} control clauses"
            if notes
            else f"{step.program} with no recognised control statements"
        )
        return ProgramAnalysis(
            program=step.program or "SORT",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=raw or None,
        )
