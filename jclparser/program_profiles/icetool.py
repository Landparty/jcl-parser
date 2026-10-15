"""Profile for ``ICETOOL`` — the DFSORT batch toolkit.

Also matches ``SYNCTOOL``, Syncsort's ICETOOL-compatible batch toolkit,
which reads the same ``TOOLIN`` operator syntax.

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

from ..utils import control_card_text
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

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
# ``FROM(dd)`` / ``TO(dd)`` / ``TO(dd1,dd2,...)``: the group is the DD list.
_RE_FROM = re.compile(r"\bFROM\s*\(([A-Za-z0-9$#@,\s]+)\)", re.IGNORECASE)
_RE_TO = re.compile(r"\bTO\s*\(([A-Za-z0-9$#@,\s]+)\)", re.IGNORECASE)
# A ``*`` in column 1 makes a comment statement.
_RE_COMMENT_LINE = re.compile(r"^\s*\*.*$", re.MULTILINE)
# A trailing ``-`` continues the statement on the next line.
_RE_CONTINUATION = re.compile(r"-[ \t]*\r?\n")


def _normalize_toolin(text: str) -> str:
    """Drop comment statements and join continued lines, so each is whole."""
    text = _RE_COMMENT_LINE.sub("", text)
    return _RE_CONTINUATION.sub(" ", text)


def _dd_names(lists: list[str]) -> list[str]:
    """Flatten the matched ``(dd1,dd2,...)`` lists into DD names."""
    return [
        name.strip() for group in lists for name in group.split(",") if name.strip()
    ]


def _toolin_text(step: Step) -> str:
    dd = step.get_dd("TOOLIN")
    if dd and dd.inline_data:
        return control_card_text(dd.inline_data)
    # Some jobs route TOOLIN through SYSIN instead.
    return _sysin_text(step) or ""


class ICETOOLProfile(ProgramProfile):
    program_names = frozenset({"ICETOOL", "SYNCTOOL"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _toolin_text(step)
        notes: list[str] = []

        for m in _RE_OPERATOR_LINE.finditer(_normalize_toolin(text)):
            operator = m.group(1).upper()
            tail = m.group(2)
            froms = _dd_names(_RE_FROM.findall(tail))
            tos = _dd_names(_RE_TO.findall(tail))
            parts = []
            if froms:
                parts.append(f"FROM({','.join(froms)})")
            if tos:
                parts.append(f"TO({','.join(tos)})")
            detail = f" {' '.join(parts)}" if parts else ""
            notes.append(f"{operator}{detail}")

        program = step.program or "ICETOOL"
        summary = (
            f"{program}: {len(notes)} operator(s)"
            if notes
            else f"{program} with no recognised TOOLIN operators"
        )
        return ProgramAnalysis(
            program=program,
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
