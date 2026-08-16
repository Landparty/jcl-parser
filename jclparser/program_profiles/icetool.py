"""Profile for ``ICETOOL`` — the DFSORT batch toolkit.

ICETOOL reads a sequence of operator statements from ``TOOLIN`` (one
operator per logical statement), each naming its input/output DDs via
``FROM(ddname)`` / ``TO(ddname)`` / ``USING(member)``.  Common operators:
``COPY``, ``SORT``, ``MERGE``, ``COUNT``, ``STATS``, ``SELECT``, ``SPLICE``,
``UNIQUE``, ``OCCUR``, ``DISPLAY``, ``DEFAULTS``, ``MODE``, ``RESIZE``,
``VERIFY``, ``WHENSAME``, ``WHENDIFF``, ``DEDUP``, ``RANGE``, ``CORR``.

Like :mod:`jclparser.program_profiles.sort`, this is a shallow parse: it
surfaces which operators ran and which DDs they touched without validating
field specifications.
"""

from __future__ import annotations

import re

from typing import TYPE_CHECKING

from .base import ProgramProfile, ProgramAnalysis, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_OPERATORS = (
    "COPY",
    "SORT",
    "MERGE",
    "COUNT",
    "STATS",
    "SELECT",
    "SPLICE",
    "UNIQUE",
    "OCCUR",
    "DISPLAY",
    "DEFAULTS",
    "MODE",
    "RESIZE",
    "VERIFY",
    "WHENSAME",
    "WHENDIFF",
    "DEDUP",
    "RANGE",
    "CORR",
)
_RE_OPERATOR_LINE = re.compile(
    r"^\s*(" + "|".join(_OPERATORS) + r")\b(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_RE_FROM = re.compile(r"\bFROM\s*\(\s*([A-Za-z0-9$#@]+)\s*\)", re.IGNORECASE)
_RE_TO = re.compile(r"\bTO\s*\(\s*([A-Za-z0-9$#@]+)\s*\)", re.IGNORECASE)


def _toolin_text(step: "Step") -> str:
    dd = step.get_dd("TOOLIN")
    if dd and dd.inline_data:
        return dd.inline_data
    # Some jobs route TOOLIN through SYSIN instead.
    return _sysin_text(step) or ""


class ICETOOLProfile(ProgramProfile):
    program_names = frozenset({"ICETOOL"})

    def analyze(self, step: "Step") -> ProgramAnalysis:
        text = _toolin_text(step)
        notes: list[str] = []

        for m in _RE_OPERATOR_LINE.finditer(text):
            operator = m.group(1).upper()
            tail = m.group(2)
            froms = _RE_FROM.findall(tail)
            tos = _RE_TO.findall(tail)
            parts = []
            if froms:
                parts.append(f"FROM({','.join(froms)})")
            if tos:
                parts.append(f"TO({','.join(tos)})")
            detail = f" {' '.join(parts)}" if parts else ""
            notes.append(f"{operator}{detail}")

        summary = (
            f"ICETOOL: {len(notes)} operator(s)"
            if notes
            else "ICETOOL with no recognised TOOLIN operators"
        )
        return ProgramAnalysis(
            program="ICETOOL",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
