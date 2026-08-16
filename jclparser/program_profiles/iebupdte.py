"""Profile for ``IEBUPDTE`` — sequential/PDS member update utility.

Control statements in ``SYSIN`` start with ``./`` (a change-control
statement, not a JCL statement) and use ``./ ADD``, ``./ CHANGE``,
``./ REPL``, and ``./ NUMBER``, typically with a ``NAME=member`` operand.
The profile reports the base input (SYSUT1, when present), the output
(SYSUT2), and which member operations the control stream requests.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..dataset_lifecycle import DatasetEvent
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_CTL = re.compile(
    r"^\./\s*(ADD|CHANGE|REPL|NUMBER)\b(?:[^\n]*\bNAME=([A-Za-z0-9$#@]+))?",
    re.IGNORECASE | re.MULTILINE,
)


class IEBUPDTEProfile(ProgramProfile):
    program_names = frozenset({"IEBUPDTE"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        for m in _RE_CTL.finditer(text):
            action = m.group(1).upper()
            member = m.group(2)
            notes.append(f"{action} NAME={member}" if member else action)

        events: list[DatasetEvent] = []
        sysut1 = step.get_dd("SYSUT1")
        sysut2 = step.get_dd("SYSUT2")
        if sysut1 and sysut1.dataset_name:
            events.append(
                DatasetEvent(
                    step_name=step.name or "",
                    dd_name="SYSUT1",
                    action="OPEN_SHARED",
                    disp_status=(sysut1.disposition or "SHR")
                    .split(",")[0]
                    .strip("()")
                    .upper()
                    or "SHR",
                    line_number=sysut1.line_number,
                )
            )
        if sysut2 and sysut2.dataset_name:
            events.append(
                DatasetEvent(
                    step_name=step.name or "",
                    dd_name="SYSUT2",
                    action="ALLOCATE",
                    disp_status="NEW",
                    line_number=sysut2.line_number,
                )
            )

        summary = (
            f"IEBUPDTE: {len(notes)} member operation(s)"
            if notes
            else "IEBUPDTE with no recognised control statements"
        )
        return ProgramAnalysis(
            program="IEBUPDTE",
            step_name=step.name or "",
            summary=summary,
            dataset_events=events,
            notes=notes,
            raw_control=text or None,
        )
