"""Profile for DB2 batch SQL processors (``DSNTEP2`` / ``DSNTEP4`` / ``DSNTIAD``).

These programs are usually driven by the DSN command processor and read their
work from ``SYSIN`` (dynamic SQL) — and occasionally name an application
program via ``RUN PROGRAM(...)`` or a ``CALL``.  Like
:class:`~jclparser.program_profiles.ikjeft01.IKJEFT01Profile`, this profile
surfaces embedded SQL and any invoked application program so dependency
analysis does not stop at the DB2 driver.
"""

from __future__ import annotations

from .base import ProgramProfile, ProgramAnalysis
from ._invoked import extract_invoked_programs
from ..sql_detector import detect_sql_in_text


class DB2BatchProfile(ProgramProfile):
    program_names = frozenset({"DSNTEP2", "DSNTEP4", "DSNTIAD"})

    def analyze(self, step) -> ProgramAnalysis:
        notes: list[str] = []
        texts: list[str] = []

        for dd_name in ("SYSTSIN", "SYSIN"):
            dd = step.get_dd(dd_name)
            if dd and dd.inline_data:
                texts.append(dd.inline_data)

        combined = "\n".join(texts)

        invoked = extract_invoked_programs(combined)
        for prog in invoked:
            notes.append(f"{prog.via}({prog.name})")

        sql_hits = detect_sql_in_text(combined) if combined else []
        if sql_hits:
            categories = sorted({cat for _, cat in sql_hits})
            notes.append(f"embedded SQL: {', '.join(categories)}")

        summary = (
            f"{step.program}: {len(notes)} DB2 batch operations"
            if notes
            else f"{step.program} with no recognised SYSIN content"
        )
        return ProgramAnalysis(
            program=step.program or "DSNTEP2",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=combined or None,
            invoked_programs=[p.name for p in invoked],
        )
