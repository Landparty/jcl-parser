"""Profile for ``IKJEFT01`` / ``IKJEFT1B`` (TSO batch).

These programs run TSO commands from the SYSTSIN DD.  They are very
commonly used to invoke DB2's ``DSN`` command processor for binding
packages or running SQL from a batch job.  The profile reuses
:func:`~jclparser.sql_detector.detect_sql_in_text` to surface any embedded
SQL from SYSTSIN or SYSIN, and recognises common DSN subcommands.
"""

from __future__ import annotations

import re

from .base import ProgramProfile, ProgramAnalysis
from ..sql_detector import detect_sql_in_text

_RE_DSN = re.compile(r"\bDSN\s+SYSTEM\s*\(\s*([A-Z0-9]+)\s*\)", re.IGNORECASE)
_RE_BIND = re.compile(r"\bBIND\s+(?:PACKAGE|PLAN)\b", re.IGNORECASE)
_RE_RUN_PROG = re.compile(r"\bRUN\s+PROGRAM\s*\(\s*([A-Z0-9]+)\s*\)", re.IGNORECASE)


class IKJEFT01Profile(ProgramProfile):
    program_names = frozenset({"IKJEFT01", "IKJEFT1A", "IKJEFT1B"})

    def analyze(self, step) -> ProgramAnalysis:
        notes: list[str] = []
        texts: list[str] = []

        for dd_name in ("SYSTSIN", "SYSIN"):
            dd = step.get_dd(dd_name)
            if dd and dd.inline_data:
                texts.append(dd.inline_data)

        combined = "\n".join(texts)

        for m in _RE_DSN.finditer(combined):
            notes.append(f"DSN SYSTEM({m.group(1).upper()})")
        if _RE_BIND.search(combined):
            notes.append("BIND PACKAGE/PLAN")
        for m in _RE_RUN_PROG.finditer(combined):
            notes.append(f"RUN PROGRAM({m.group(1).upper()})")

        sql_hits = detect_sql_in_text(combined) if combined else []
        if sql_hits:
            categories = sorted({cat for _, cat in sql_hits})
            notes.append(f"embedded SQL: {', '.join(categories)}")

        summary = (
            f"{step.program}: {len(notes)} TSO/DSN commands"
            if notes
            else f"{step.program} with no recognised TSO commands"
        )
        return ProgramAnalysis(
            program=step.program or "IKJEFT01",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=combined or None,
        )
