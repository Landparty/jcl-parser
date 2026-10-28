"""Profile for ``ADRDSSU`` — DFSMSdss batch (DUMP/RESTORE/COPY).

Control statements are read from ``SYSIN`` and use a keyword-command form,
e.g. ``DUMP DATASET(INCLUDE(...)) OUTDDNAME(...)``.  This is a shallow
parse: it recognises the leading command keyword and, where present, the
``DATASET(INCLUDE(...))`` dataset list, without validating the full
DFSMSdss grammar (which spans many optional sub-parameters).

A statement is continued by a hyphen or plus sign as its last non-blank
character (the plus also drops the next line's leading blanks, so a name
split across lines is rejoined), ``/* ... */`` comments are ignored, and the
keyword abbreviations ``DS`` (``DATASET``) and ``INCL`` (``INCLUDE``) are
read.  Only the first word of a statement names its command, so a keyword
that shares a command's name on a continuation line (``DUMP ... -`` then
``COMPRESS``) is not a command of its own.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_COMMANDS = frozenset(
    {
        "DUMP",
        "RESTORE",
        "COPY",
        "RELEASE",
        "COMPRESS",
        "DEFRAG",
        "CONVERTV",
        "PRINT",
    }
)
_RE_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_RE_DATASET = re.compile(r"\b(?:DATASET|DS)\s*\(", re.IGNORECASE)
_RE_INCLUDE = re.compile(r"\b(?:INCLUDE|INCL)\s*\(([^)]*)\)", re.IGNORECASE)


def _blank_comment(match: re.Match[str]) -> str:
    """A comment replaced by blanks, keeping its line breaks."""
    return re.sub(r"[^\n]", " ", match.group())


def _statements(text: str) -> list[str]:
    """The logical statements of *text*: comments removed, continuations
    joined.  *text* is already cut to columns 1-71 for a card image
    (:func:`~jclparser.program_profiles.base._sysin_text`)."""
    statements: list[str] = []
    continued = False
    joiner = " "
    for raw in _RE_COMMENT.sub(_blank_comment, text).split("\n"):
        line = raw.rstrip()
        mark = line[-1:] if line[-1:] in ("-", "+") else ""
        body = line[:-1].rstrip() if mark else line
        if continued:
            statements[-1] += joiner + (body.lstrip() if joiner == "" else body)
        elif body.strip():
            statements.append(body.strip())
        else:
            continue
        continued = bool(mark)
        joiner = "" if mark == "+" else " "
    return statements


def _include_names(statement: str) -> list[str] | None:
    """The ``INCLUDE`` names of the statement's ``DATASET(...)`` filter."""
    match = _RE_DATASET.search(statement)
    if match is None:
        return None
    depth, end = 1, match.end()
    while end < len(statement) and depth:
        depth += {"(": 1, ")": -1}.get(statement[end], 0)
        end += 1
    include = _RE_INCLUDE.search(statement, match.end(), end)
    if include is None:
        return None
    return [n for n in re.split(r"[\s,]+", include.group(1)) if n]


class ADRDSSUProfile(ProgramProfile):
    program_names = frozenset({"ADRDSSU"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        for statement in _statements(text):
            command = statement.split(None, 1)[0].upper()
            if command not in _COMMANDS:
                continue
            names = _include_names(statement)
            if names:
                notes.append(f"{command} DATASET(INCLUDE({' '.join(names)}))")
            else:
                notes.append(command)

        summary = (
            f"ADRDSSU: {len(notes)} command(s)"
            if notes
            else "ADRDSSU with no recognised commands"
        )
        return ProgramAnalysis(
            program="ADRDSSU",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
