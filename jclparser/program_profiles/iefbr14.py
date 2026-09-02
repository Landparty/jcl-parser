"""Profile for ``IEFBR14`` — the "do nothing" utility.

IEFBR14 is a one-instruction program used purely for its side-effects on
DD dispositions: datasets with ``DISP=(NEW,CATLG,...)`` get allocated, and
``DISP=(OLD,DELETE)`` get deleted.  The DatasetEvents we emit here are
effectively the same as ``analyze_dataset_lifecycle`` produces, included
for consistency with other profiles.
"""

from __future__ import annotations

from ..dataset_lifecycle import DatasetEvent, _action_from_disp, _parse_disp_tokens
from .base import ProgramAnalysis, ProgramProfile


class IEFBR14Profile(ProgramProfile):
    program_names = frozenset({"IEFBR14"})

    def analyze(self, step) -> ProgramAnalysis:
        events: list[DatasetEvent] = []
        notes: list[str] = []
        for dd in step.dd_statements:
            if not dd.dataset_name:
                continue
            status, normal, abnormal = _parse_disp_tokens(dd.disposition)
            if not status:
                continue
            events.append(
                DatasetEvent(
                    step_name=step.name or "",
                    dd_name=dd.name or "",
                    action=_action_from_disp(status),
                    disp_status=status,
                    disp_normal=normal,
                    disp_abnormal=abnormal,
                    line_number=dd.line_number,
                )
            )
            if normal == "DELETE" and status == "OLD":
                notes.append(f"deletes {dd.dataset_name}")
            elif normal in ("CATLG", "CATALOG") and status == "NEW":
                notes.append(f"allocates {dd.dataset_name}")
        summary = (
            f"IEFBR14: {len(events)} DD dispositions applied"
            if events
            else "IEFBR14 with no DD allocations"
        )
        return ProgramAnalysis(
            program="IEFBR14",
            step_name=step.name or "",
            summary=summary,
            dataset_events=events,
            notes=notes,
        )
