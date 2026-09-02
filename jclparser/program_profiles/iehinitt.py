"""Profile for ``IEHINITT`` — magnetic tape volume initialization utility.

Control statements are read from ``SYSIN``: each ``INITT`` statement writes
a standard label to initialize one or more tape volumes, optionally naming
a volume serial (``VOL=SER=``) and owner ID (``OWNER=``).  IEHINITT works
entirely through tape labels rather than DD dataset references, so — like
:mod:`jclparser.program_profiles.iehlist` — the profile only reports which
volumes were initialized and does not emit
:class:`~jclparser.dataset_lifecycle.DatasetEvent` entries.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_INITT = re.compile(r"^\s*INITT\b", re.IGNORECASE | re.MULTILINE)
_RE_VOL = re.compile(r"\bVOL=SER=([A-Za-z0-9]+)", re.IGNORECASE)
_RE_OWNER = re.compile(r"\bOWNER=([A-Za-z0-9]+)", re.IGNORECASE)


class IEHINITTProfile(ProgramProfile):
    program_names = frozenset({"IEHINITT"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        for m in _RE_INITT.finditer(text):
            line_end = text.find("\n", m.end())
            line_tail = text[m.end() : line_end if line_end != -1 else len(text)]
            vol_m = _RE_VOL.search(line_tail)
            owner_m = _RE_OWNER.search(line_tail)
            detail_parts = []
            if vol_m:
                detail_parts.append(f"VOL={vol_m.group(1)}")
            if owner_m:
                detail_parts.append(f"OWNER={owner_m.group(1)}")
            detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
            notes.append(f"INITT{detail}")

        summary = (
            f"IEHINITT: {len(notes)} tape initialization(s)"
            if notes
            else "IEHINITT with no recognised INITT statements"
        )
        return ProgramAnalysis(
            program="IEHINITT",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
