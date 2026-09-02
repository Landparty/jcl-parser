"""Profile for ``DSNUTILB`` — the DB2 stand-alone (batch) utility driver.

Control statements are read from ``SYSIN``: one or more utility statements,
each naming a utility verb (``LOAD``, ``UNLOAD``, ``REORG``, ``RUNSTATS``,
``COPY``, ``RECOVER``, ``REBUILD``, ``CHECK``, ``STOSPACE``, ``REPAIR``,
``MODIFY``, ``MERGE``, ``CATMAINT``, ``DIAGNOSE``, ``QUIESCE``, ``TEMPLATE``,
``LISTDEF``), optionally preceded by a short utility-ID label and followed
by a ``TABLESPACE``/``TABLE`` target. This profile does a shallow parse —
enough to surface which utility ran against which object — without
validating the full utility control-statement grammar.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_UTILITY_VERBS = (
    "LOAD",
    "UNLOAD",
    "REORG",
    "RUNSTATS",
    "COPY",
    "RECOVER",
    "REBUILD",
    "CHECK",
    "STOSPACE",
    "REPAIR",
    "MODIFY",
    "MERGE",
    "CATMAINT",
    "DIAGNOSE",
    "QUIESCE",
    "TEMPLATE",
    "LISTDEF",
)
_RE_UTILITY_STMT = re.compile(
    r"^\s*(?:[A-Za-z0-9$#@]{1,8}\s+)?(" + "|".join(_UTILITY_VERBS) + r")\b",
    re.IGNORECASE | re.MULTILINE,
)
_RE_TABLESPACE = re.compile(r"\bTABLESPACE\s+([A-Za-z0-9$#@.]+)", re.IGNORECASE)
_RE_TABLE = re.compile(r"\bTABLE\s+([A-Za-z0-9$#@.]+)", re.IGNORECASE)


class DSNUTILBProfile(ProgramProfile):
    program_names = frozenset({"DSNUTILB"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        for m in _RE_UTILITY_STMT.finditer(text):
            verb = m.group(1).upper()
            line_end = text.find("\n", m.end())
            line_tail = text[m.end() : line_end if line_end != -1 else len(text)]
            target_m = _RE_TABLESPACE.search(line_tail) or _RE_TABLE.search(line_tail)
            if target_m:
                notes.append(f"{verb} {target_m.group(0).upper()}")
            else:
                notes.append(verb)

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
