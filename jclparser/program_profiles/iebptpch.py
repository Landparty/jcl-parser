"""Profile for ``IEBPTPCH`` — sequential/PDS print & punch utility.

Control statements are read from ``SYSIN``: ``PRINT`` or ``PUNCH`` selects
the mode, ``TITLE`` supplies a report heading, ``MEMBER`` selects a PDS
member, and ``RECORD`` narrows the field range printed/punched.  Input
comes from ``SYSUT1``; output goes to ``SYSUT2``.
"""

from __future__ import annotations

import re

from typing import TYPE_CHECKING

from .base import ProgramProfile, ProgramAnalysis, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_MODE = re.compile(r"^\s*(PRINT|PUNCH)\b", re.IGNORECASE | re.MULTILINE)
_RE_MEMBER = re.compile(
    r"^\s*MEMBER\s+NAME=([A-Za-z0-9$#@]+)", re.IGNORECASE | re.MULTILINE
)
_RE_TITLE = re.compile(r"^\s*TITLE\b", re.IGNORECASE | re.MULTILINE)
_RE_RECORD = re.compile(r"^\s*RECORD\b", re.IGNORECASE | re.MULTILINE)


class IEBPTPCHProfile(ProgramProfile):
    program_names = frozenset({"IEBPTPCH"})

    def analyze(self, step: "Step") -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        mode_m = _RE_MODE.search(text)
        if mode_m:
            notes.append(mode_m.group(1).upper())
        for m in _RE_MEMBER.finditer(text):
            notes.append(f"MEMBER {m.group(1)}")
        if _RE_TITLE.search(text):
            notes.append("TITLE")
        if _RE_RECORD.search(text):
            notes.append("RECORD (field selection)")

        sysut1 = step.get_dd("SYSUT1")
        if sysut1 and sysut1.dataset_name:
            notes.append(f"reads {sysut1.dataset_name}")

        summary = (
            f"IEBPTPCH: {len(notes)} control clause(s)"
            if notes
            else "IEBPTPCH with no recognised control statements"
        )
        return ProgramAnalysis(
            program="IEBPTPCH",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
