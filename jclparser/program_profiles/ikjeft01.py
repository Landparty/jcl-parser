"""Profile for ``IKJEFT01`` / ``IKJEFT1B`` (TSO batch).

These programs run TSO commands from the SYSTSIN DD.  They are very
commonly used to invoke DB2's ``DSN`` command processor for binding
packages or running SQL from a batch job.  The profile reuses
:func:`~jclparser.sql_detector.detect_sql_in_text` to surface any embedded
SQL from SYSTSIN or SYSIN, and recognises common DSN subcommands.
"""

from __future__ import annotations

import re

from ._invoked import collect_control_text, invoked_and_sql_notes
from .base import ProgramAnalysis, ProgramProfile

_RE_DSN = re.compile(r"\bDSN\s+SYSTEM\s*\(\s*([A-Z0-9]+)\s*\)", re.IGNORECASE)
_RE_BIND = re.compile(r"\bBIND\s+(?:PACKAGE|PLAN)\b", re.IGNORECASE)


class IKJEFT01Profile(ProgramProfile):
    program_names = frozenset({"IKJEFT01", "IKJEFT1A", "IKJEFT1B"})

    def analyze(self, step) -> ProgramAnalysis:
        combined = collect_control_text(step)

        notes: list[str] = []
        for m in _RE_DSN.finditer(combined):
            notes.append(f"DSN SYSTEM({m.group(1).upper()})")
        if _RE_BIND.search(combined):
            notes.append("BIND PACKAGE/PLAN")

        # Application programs invoked from the control stream (RUN PROGRAM /
        # CALL) — the real targets hidden behind the IKJEFT01 wrapper — plus any
        # embedded SQL recovered from the same control text.
        invoked, control_notes = invoked_and_sql_notes(combined)
        notes.extend(control_notes)

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
            invoked_programs=[p.name for p in invoked],
        )
