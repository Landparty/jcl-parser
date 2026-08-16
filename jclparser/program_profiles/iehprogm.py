"""Profile for ``IEHPROGM`` — catalog/VTOC maintenance utility.

Control statements are read from ``SYSIN``: ``SCRATCH`` (delete),
``RENAME``, ``CATLG``, ``UNCATLG``, ``BLDG``, and ``CONNECT``.  Unlike the
read-only listing in IEHLIST, several of these commands mutate the catalog,
so — like :mod:`jclparser.program_profiles.idcams` — the profile emits
:class:`~jclparser.dataset_lifecycle.DatasetEvent` entries for
``SCRATCH``/``CATLG``/``UNCATLG``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..dataset_lifecycle import DatasetEvent
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_SCRATCH = re.compile(
    r"^\s*SCRATCH\b[^\n]*DSNAME=([A-Za-z0-9.$#@]+)", re.IGNORECASE | re.MULTILINE
)
_RE_RENAME = re.compile(
    r"^\s*RENAME\b[^\n]*DSNAME=([A-Za-z0-9.$#@]+)", re.IGNORECASE | re.MULTILINE
)
_RE_CATLG = re.compile(
    r"^\s*CATLG\b[^\n]*DSNAME=([A-Za-z0-9.$#@]+)", re.IGNORECASE | re.MULTILINE
)
_RE_UNCATLG = re.compile(
    r"^\s*UNCATLG\b[^\n]*DSNAME=([A-Za-z0-9.$#@]+)", re.IGNORECASE | re.MULTILINE
)
_RE_BLDG = re.compile(r"^\s*BLDG\b", re.IGNORECASE | re.MULTILINE)
_RE_CONNECT = re.compile(r"^\s*CONNECT\b", re.IGNORECASE | re.MULTILINE)


class IEHPROGMProfile(ProgramProfile):
    program_names = frozenset({"IEHPROGM"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        events: list[DatasetEvent] = []
        notes: list[str] = []

        for m in _RE_SCRATCH.finditer(text):
            dsn = m.group(1)
            events.append(
                DatasetEvent(
                    step_name=step.name or "",
                    dd_name="SYSIN",
                    action="DELETE",
                    disp_status="OLD",
                    disp_normal="DELETE",
                    line_number=step.line_number,
                )
            )
            notes.append(f"SCRATCH {dsn}")

        for m in _RE_RENAME.finditer(text):
            notes.append(f"RENAME {m.group(1)}")

        for m in _RE_CATLG.finditer(text):
            dsn = m.group(1)
            events.append(
                DatasetEvent(
                    step_name=step.name or "",
                    dd_name="SYSIN",
                    action="ALLOCATE",
                    disp_status="NEW",
                    disp_normal="CATLG",
                    line_number=step.line_number,
                )
            )
            notes.append(f"CATLG {dsn}")

        for m in _RE_UNCATLG.finditer(text):
            dsn = m.group(1)
            events.append(
                DatasetEvent(
                    step_name=step.name or "",
                    dd_name="SYSIN",
                    action="UNCATALOG",
                    disp_status="OLD",
                    disp_normal="UNCATLG",
                    line_number=step.line_number,
                )
            )
            notes.append(f"UNCATLG {dsn}")

        if _RE_BLDG.search(text):
            notes.append("BLDG (build generation data group index)")
        if _RE_CONNECT.search(text):
            notes.append("CONNECT (add user catalog connection)")

        summary = (
            f"IEHPROGM: {len(events)} dataset mutations, {len(notes)} commands"
            if events or notes
            else "IEHPROGM with no recognised commands"
        )
        return ProgramAnalysis(
            program="IEHPROGM",
            step_name=step.name or "",
            summary=summary,
            dataset_events=events,
            notes=notes,
            raw_control=text or None,
        )
