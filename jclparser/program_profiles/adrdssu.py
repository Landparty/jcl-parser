"""Profile for ``ADRDSSU`` — DFSMSdss batch (DUMP/RESTORE/COPY).

Control statements are read from ``SYSIN`` and use a keyword-command form,
e.g. ``DUMP DATASET(INCLUDE(...)) OUTDDNAME(...)``.  This is a shallow
parse: it recognises the leading command keyword and, where present, the
``DATASET(INCLUDE(...))`` dataset list, without validating the full
DFSMSdss grammar (which spans many optional sub-parameters).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_COMMANDS = (
    "DUMP",
    "RESTORE",
    "COPY",
    "RELEASE",
    "COMPRESS",
    "DEFRAG",
    "CONVERTV",
    "PRINT",
)
_RE_COMMAND = re.compile(
    r"^\s*(" + "|".join(_COMMANDS) + r")\b", re.IGNORECASE | re.MULTILINE
)
_RE_DATASET_INCLUDE = re.compile(
    r"DATASET\s*\(\s*INCLUDE\s*\(\s*([^)]*)\)", re.IGNORECASE
)


class ADRDSSUProfile(ProgramProfile):
    program_names = frozenset({"ADRDSSU"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        matches = list(_RE_COMMAND.finditer(text))
        for i, m in enumerate(matches):
            command = m.group(1).upper()
            # Scope the INCLUDE search to this command's own statement —
            # up to the next command keyword (or end of text) — so a later
            # command's DATASET(INCLUDE(...)) can't be misattributed here.
            segment_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            segment = text[m.end() : segment_end]
            ds_m = _RE_DATASET_INCLUDE.search(segment)
            if ds_m:
                names = [n.strip() for n in ds_m.group(1).split() if n.strip()]
                notes.append(f"{command} DATASET(INCLUDE({' '.join(names)}))")
            else:
                notes.append(command)

        summary = (
            f"ADRDSSU: {len(notes)} command(s)"
            if notes
            else "ADRDSSU with no recognised commands"
        )
        return ProgramAnalysis(
            program="ADRDSSU",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
