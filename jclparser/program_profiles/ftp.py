"""Profile for batch ``FTP`` (``PGM=FTP``).

z/OS batch FTP jobs drive the client from ``SYSIN`` subcommands: ``OPEN``
names the remote host, ``USER`` authenticates, ``PUT``/``GET``/``MPUT``/
``MGET`` transfer files, and ``ASCII``/``BINARY`` set transfer mode. The
profile surfaces the host and the file operations without attempting to
resolve remote paths.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_OPEN = re.compile(r"^\s*OPEN\s+(\S+)", re.IGNORECASE | re.MULTILINE)
_RE_USER = re.compile(r"^\s*USER\s+(\S+)", re.IGNORECASE | re.MULTILINE)
_RE_TRANSFER = re.compile(
    r"^\s*(PUT|GET|MPUT|MGET)\s+(\S+)", re.IGNORECASE | re.MULTILINE
)
_RE_MODE = re.compile(r"^\s*(ASCII|BINARY)\b", re.IGNORECASE | re.MULTILINE)


class FTPProfile(ProgramProfile):
    program_names = frozenset({"FTP"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _sysin_text(step) or ""
        notes: list[str] = []

        host_m = _RE_OPEN.search(text)
        if host_m:
            notes.append(f"OPEN {host_m.group(1)}")
        user_m = _RE_USER.search(text)
        if user_m:
            notes.append(f"USER {user_m.group(1)}")
        for m in _RE_TRANSFER.finditer(text):
            notes.append(f"{m.group(1).upper()} {m.group(2)}")
        mode_m = _RE_MODE.search(text)
        if mode_m:
            notes.append(mode_m.group(1).upper())

        summary = (
            f"FTP: {len(notes)} subcommand(s)"
            if notes
            else "FTP with no recognised SYSIN subcommands"
        )
        return ProgramAnalysis(
            program="FTP",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
