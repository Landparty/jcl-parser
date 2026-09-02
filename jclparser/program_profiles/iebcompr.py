"""Profile for ``IEBCOMPR`` — sequential/PDS dataset compare utility.

IEBCOMPR performs a record-by-record comparison of two datasets read from
``SYSUT1`` and ``SYSUT2`` — both read-only, so the profile emits
``OPEN_SHARED`` :class:`~jclparser.dataset_lifecycle.DatasetEvent` entries
for both rather than any mutation.  Optional ``SYSUT3``/``SYSUT4`` work
datasets (used internally when comparing large PDSs) carry no useful DD
content to surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..dataset_lifecycle import DatasetEvent
from .base import ProgramAnalysis, ProgramProfile

if TYPE_CHECKING:
    from ..model import Step


class IEBCOMPRProfile(ProgramProfile):
    program_names = frozenset({"IEBCOMPR"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        events: list[DatasetEvent] = []
        notes: list[str] = []

        sysut1 = step.get_dd("SYSUT1")
        sysut2 = step.get_dd("SYSUT2")
        for dd_name, dd in (("SYSUT1", sysut1), ("SYSUT2", sysut2)):
            if dd and dd.dataset_name:
                events.append(
                    DatasetEvent(
                        step_name=step.name or "",
                        dd_name=dd_name,
                        action="OPEN_SHARED",
                        disp_status="SHR",
                        line_number=dd.line_number,
                    )
                )

        if sysut1 and sysut1.dataset_name and sysut2 and sysut2.dataset_name:
            notes.append(f"compares {sysut1.dataset_name} vs {sysut2.dataset_name}")

        summary = (
            "IEBCOMPR: compares SYSUT1 vs SYSUT2"
            if notes
            else "IEBCOMPR with no SYSUT1/SYSUT2"
        )
        return ProgramAnalysis(
            program="IEBCOMPR",
            step_name=step.name or "",
            summary=summary,
            dataset_events=events,
            notes=notes,
        )
