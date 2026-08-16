"""Profile for ``IEHLIST`` — VTOC / PDS directory listing utility.

Control statements are read from ``SYSIN``: ``LISTVTOC``, ``LISTPDS``, and
``LISTDG`` (the latter also usable as ``LISTIDG``).  IEHLIST is read-only —
it never mutates a dataset — so the profile only reports which listing
commands ran and, where present, the volume/dataset they target.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_LISTVTOC = re.compile(
    r"^\s*LISTVTOC\b[^\n]*VOL=([A-Za-z0-9,=]+)", re.IGNORECASE | re.MULTILINE
)
_RE_LISTPDS = re.compile(
    r"^\s*LISTPDS\b[^\n]*DSNAME=([A-Za-z0-9.$#@]+)", re.IGNORECASE | re.MULTILINE
)
_RE_LISTDG = re.compile(r"^\s*LIST(?:I)?DG\b", re.IGNORECASE | re.MULTILINE)


class IEHLISTProfile(ProgramProfile):
    program_names = frozenset({"IEHLIST"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        for m in _RE_LISTVTOC.finditer(text):
            notes.append(f"LISTVTOC VOL={m.group(1)}")
        for m in _RE_LISTPDS.finditer(text):
            notes.append(f"LISTPDS DSNAME={m.group(1)}")
        for _ in _RE_LISTDG.finditer(text):
            notes.append("LISTDG")

        summary = (
            f"IEHLIST: {len(notes)} listing command(s)"
            if notes
            else "IEHLIST with no recognised commands"
        )
        return ProgramAnalysis(
            program="IEHLIST",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
