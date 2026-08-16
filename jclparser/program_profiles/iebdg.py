"""Profile for ``IEBDG`` — test data generator.

Control statements are read from ``SYSIN``: ``DSD`` names the output
dataset description, ``FD`` describes a field, and ``CREATE`` requests
record generation (optionally with a ``REPEAT`` count sub-parameter). The
generated output lands on ``SYSUT2``, referenced by DDNAME= on the DSD
statement or the step's SYSUT2 DD.
"""

from __future__ import annotations

import re

from typing import TYPE_CHECKING

from .base import ProgramProfile, ProgramAnalysis, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_DSD = re.compile(
    r"^\s*DSD\b[^\n]*DDNAME=([A-Za-z0-9$#@]+)", re.IGNORECASE | re.MULTILINE
)
_RE_FD = re.compile(
    r"^\s*FD\b[^\n]*NAME=([A-Za-z0-9$#@]+)", re.IGNORECASE | re.MULTILINE
)
_RE_CREATE = re.compile(
    r"^\s*CREATE\b(?:[^\n]*\bREPEAT=(\d+))?", re.IGNORECASE | re.MULTILINE
)


class IEBDGProfile(ProgramProfile):
    program_names = frozenset({"IEBDG"})

    def analyze(self, step: "Step") -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        for m in _RE_DSD.finditer(text):
            notes.append(f"DSD DDNAME={m.group(1)}")
        field_names = [m.group(1) for m in _RE_FD.finditer(text)]
        if field_names:
            notes.append(f"FD fields: {', '.join(field_names)}")
        for m in _RE_CREATE.finditer(text):
            notes.append(f"CREATE REPEAT={m.group(1)}" if m.group(1) else "CREATE")

        summary = (
            f"IEBDG: generates test data ({len(field_names)} field(s))"
            if notes
            else "IEBDG with no recognised control statements"
        )
        return ProgramAnalysis(
            program="IEBDG",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
