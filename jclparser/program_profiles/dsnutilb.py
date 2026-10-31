"""Profile for ``DSNUTILB`` — the DB2 stand-alone (batch) utility driver.

Control statements are read from ``SYSIN``: one or more utility statements,
each starting at a utility verb at the start of a line (``LOAD``, ``UNLOAD``,
``REORG``, ``RUNSTATS``, ``COPY``, ``COPYTOCOPY``, ``MERGECOPY``,
``RECOVER``, ``REBUILD``, ``CHECK``, ``STOSPACE``, ``REPAIR``, ``REPORT``,
``MODIFY``, ``CATMAINT``, ``DIAGNOSE``, ``QUIESCE``, ``TEMPLATE``,
``LISTDEF``, ``OPTIONS``, ``EXEC SQL``, ``BACKUP SYSTEM``, ``RESTORE
SYSTEM``), optionally after a short label, and running over the option lines
after it to the next statement. The note names the first ``TABLESPACE``,
``TABLE`` or ``INDEX`` object anywhere in the statement. This profile does a shallow parse —
enough to surface which utility ran against which object — without
validating the full utility control-statement grammar.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..utils import split_source_lines
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_UTILITY_VERBS = (
    "BACKUP SYSTEM",
    "CATMAINT",
    "CHECK",
    "COPY",
    "COPYTOCOPY",
    "DIAGNOSE",
    "EXEC SQL",
    "LISTDEF",
    "LOAD",
    "MERGECOPY",
    "MODIFY",
    "OPTIONS",
    "QUIESCE",
    "REBUILD",
    "RECOVER",
    "REORG",
    "REPAIR",
    "REPORT",
    "RESTORE SYSTEM",
    "RUNSTATS",
    "STOSPACE",
    "TEMPLATE",
    "UNLOAD",
)
_VERB_ALTERNATION = "|".join(
    v.replace(" ", r"\s+") for v in sorted(_UTILITY_VERBS, key=len, reverse=True)
)
# A statement starts at a verb at the start of a line, optionally after a
# short label.
_RE_UTILITY_STMT = re.compile(
    r"^\s*(?:[A-Za-z0-9$#@]{1,8}\s+)?(" + _VERB_ALTERNATION + r")\b(.*)$",
    re.IGNORECASE,
)
# Option lines that look like a verb but continue the statement before them:
# REORG's ``UNLOAD CONTINUE|PAUSE|ONLY|EXTERNAL|NONE`` and RUNSTATS / REORG /
# LOAD's ``REPORT YES|NO``. The REPORT utility is ``REPORT RECOVERY`` or
# ``REPORT TABLESPACESET``.
_RE_UNLOAD_OPTION = re.compile(
    r"^UNLOAD\s+(?:CONTINUE|PAUSE|ONLY|EXTERNAL|NONE)\b", re.IGNORECASE
)
_RE_REPORT_UTILITY = re.compile(
    r"^REPORT\s+(?:RECOVERY|TABLESPACESET)\b", re.IGNORECASE
)
_RE_ENDEXEC = re.compile(r"\bENDEXEC\b", re.IGNORECASE)
# The object a statement works on, wherever in the statement it is coded:
# ``TABLESPACE db.ts``, ``[INTO] TABLE x``, ``INDEX x`` / ``INDEX (x, ...)``.
_RE_TARGET = re.compile(
    r"\b(TABLESPACE|TABLE|INDEX)\s*\(?\s*([A-Za-z0-9$#@.]+)", re.IGNORECASE
)


def _strip_comment(line: str) -> str:
    """Drop a ``--`` comment (outside quotes) from a control record."""
    quoted = False
    for i, ch in enumerate(line):
        if ch == "'":
            quoted = not quoted
        elif not quoted and line.startswith("--", i):
            return line[:i]
    return line


def _statement_start(line: str, current: str | None) -> tuple[str, str] | None:
    """(verb, statement text) when *line* starts a new utility statement
    after one whose verb is *current*."""
    match = _RE_UTILITY_STMT.match(line)
    if match is None:
        return None
    verb = " ".join(match.group(1).upper().split())
    rest = line[match.start(1) :]
    if verb == "UNLOAD" and current == "REORG" and _RE_UNLOAD_OPTION.match(rest):
        return None
    if verb == "REPORT" and not _RE_REPORT_UTILITY.match(rest):
        return None
    return verb, rest


def _split_statements(text: str) -> list[tuple[str, str]]:
    """(verb, whole statement text) for each utility statement in *text*.

    A statement runs from a line starting with a verb to the next such
    line; an option line that only looks like one (``UNLOAD CONTINUE`` in a
    REORG, ``REPORT YES``) and anything inside ``EXEC SQL ... ENDEXEC``
    continue the current statement.
    """
    statements: list[tuple[str, list[str]]] = []
    in_sql = False
    for raw in split_source_lines(text):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        current = statements[-1][0] if statements else None
        start = None if in_sql else _statement_start(line, current)
        if start is not None:
            statements.append((start[0], [start[1]]))
            in_sql = start[0] == "EXEC SQL"
        elif statements:
            statements[-1][1].append(line)
        if in_sql and _RE_ENDEXEC.search(line):
            in_sql = False
    return [(verb, " ".join(lines)) for verb, lines in statements]


def _target(verb: str, statement: str) -> str | None:
    if verb == "EXEC SQL":
        return None
    for m in _RE_TARGET.finditer(statement):
        if m.group(2).upper() != "ALL":
            return f"{m.group(1).upper()} {m.group(2).upper()}"
    return None


class DSNUTILBProfile(ProgramProfile):
    program_names = frozenset({"DSNUTILB"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        for verb, statement in _split_statements(text):
            target = _target(verb, statement)
            notes.append(f"{verb} {target}" if target else verb)

        summary = (
            f"DSNUTILB: {len(notes)} DB2 utility statement(s)"
            if notes
            else "DSNUTILB with no recognised utility statements"
        )
        return ProgramAnalysis(
            program="DSNUTILB",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
