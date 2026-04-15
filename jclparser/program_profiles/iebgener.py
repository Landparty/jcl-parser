"""Profiles for simple IBM copy utilities: ``IEBGENER`` and ``IEBCOPY``.

These programs copy data from one dataset to another.  The profile reports
SYSUT1 (input) and SYSUT2 (output) as the canonical source/destination pair
so downstream consumers can model the data flow without re-interpreting DD
dispositions.
"""

from __future__ import annotations

from .base import ProgramProfile, ProgramAnalysis
from ..dataset_lifecycle import DatasetEvent


def _copy_utility_analysis(step, program: str) -> ProgramAnalysis:
    sysut1 = step.get_dd("SYSUT1")
    sysut2 = step.get_dd("SYSUT2")
    events: list[DatasetEvent] = []
    notes: list[str] = []

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
        notes.append(f"reads {sysut1.dataset_name}")

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
        notes.append(f"writes {sysut2.dataset_name}")

    summary = (
        f"{program}: copy SYSUT1 -> SYSUT2"
        if events
        else f"{program} (no SYSUT1/SYSUT2)"
    )
    return ProgramAnalysis(
        program=program,
        step_name=step.name or "",
        summary=summary,
        dataset_events=events,
        notes=notes,
    )


class IEBGENERProfile(ProgramProfile):
    program_names = frozenset({"IEBGENER"})

    def analyze(self, step) -> ProgramAnalysis:
        return _copy_utility_analysis(step, "IEBGENER")


class IEBCOPYProfile(ProgramProfile):
    program_names = frozenset({"IEBCOPY"})

    def analyze(self, step) -> ProgramAnalysis:
        return _copy_utility_analysis(step, "IEBCOPY")
