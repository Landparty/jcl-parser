"""Profile for ``IDCAMS`` — Access Method Services.

Parses the step's SYSIN inline data for common commands:

* ``DELETE`` — flags the named dataset as deleted.
* ``DEFINE CLUSTER``, ``DEFINE GDG`` — flags the named dataset as allocated.
* ``REPRO`` — copy INFILE -> OUTFILE.
* ``ALTER``, ``LISTCAT``, ``PRINT`` — noted but not event-producing.

The parser is deliberately tolerant: IDCAMS control statements span
multiple lines with flexible continuation rules, and we only extract
simple ``COMMAND OBJECT`` forms.  Unrecognised commands land in
:attr:`ProgramAnalysis.notes` for downstream consumers.
"""

from __future__ import annotations

import re

from ..dataset_lifecycle import DatasetEvent
from ._invoked import _normalize_control_text
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

# One catalog entry name: a dataset name, optionally quoted or with a member.
_ENTRY_NAME = r"'[^']*'|[A-Z0-9.@#$\-]+(?:\([A-Z0-9@#$+\-]+\))?"
_RE_ENTRY_NAME = re.compile(_ENTRY_NAME, re.IGNORECASE)
# ``DELETE`` (or its abbreviation ``DEL``) names one entry, or a list of
# them in parentheses: ``DELETE (A.B C.D) PURGE``.
_RE_DELETE = re.compile(
    r"^\s*DEL(?:ETE)?\b\s*(\((?:[^()]|\([^()]*\))*\)|" + _ENTRY_NAME + ")",
    re.IGNORECASE | re.MULTILINE,
)
_RE_DEFINE = re.compile(
    r"^\s*DEFINE\s+(CLUSTER|GDG|AIX|PATH|NONVSAM|USERCATALOG)\b",
    re.IGNORECASE | re.MULTILINE,
)
_RE_NAME_PARAM = re.compile(r"NAME\s*\(\s*([A-Z0-9.@#$\-']+)\s*\)", re.IGNORECASE)
_RE_REPRO = re.compile(r"^\s*REPRO\b", re.IGNORECASE | re.MULTILINE)
_RE_ALTER = re.compile(r"^\s*ALTER\s+([A-Z0-9.@#$\-']+)", re.IGNORECASE | re.MULTILINE)
_RE_LISTCAT = re.compile(r"^\s*LISTCAT\b", re.IGNORECASE | re.MULTILINE)


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    return s


class IDCAMSProfile(ProgramProfile):
    program_names = frozenset({"IDCAMS"})

    def analyze(self, step) -> ProgramAnalysis:
        raw = _sysin_text(step) or ""
        # IDCAMS continues a command with a trailing ``-`` (or ``+``) and
        # comments with ``/* ... */``.  Join and strip them first, or
        # ``DELETE -`` / next line ``MY.DSN`` reads the ``-`` as the name.
        text = _normalize_control_text(raw)
        events: list[DatasetEvent] = []
        notes: list[str] = []

        for m in _RE_DELETE.finditer(text):
            operand = m.group(1)
            if operand.startswith("("):
                names = _RE_ENTRY_NAME.findall(operand[1:-1])
            else:
                names = [operand]
            for dsn in (_strip_quotes(n) for n in names):
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
                notes.append(f"IDCAMS DELETE {dsn}")

        # DEFINE CLUSTER / GDG / ... — pair with the nearest NAME(...) parameter
        for m in _RE_DEFINE.finditer(text):
            define_kind = m.group(1).upper()
            # Search for NAME(...) starting at the DEFINE position.
            tail = text[m.end() :]
            name_m = _RE_NAME_PARAM.search(tail)
            dsn = _strip_quotes(name_m.group(1)) if name_m else "(unknown)"
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
            notes.append(f"IDCAMS DEFINE {define_kind} {dsn}")

        if _RE_REPRO.search(text):
            notes.append("IDCAMS REPRO (copy INFILE -> OUTFILE)")

        for m in _RE_ALTER.finditer(text):
            notes.append(f"IDCAMS ALTER {_strip_quotes(m.group(1))}")

        if _RE_LISTCAT.search(text):
            notes.append("IDCAMS LISTCAT")

        summary = (
            f"IDCAMS: {len(events)} dataset mutations, {len(notes)} commands"
            if events or notes
            else "IDCAMS with no recognised commands"
        )
        return ProgramAnalysis(
            program="IDCAMS",
            step_name=step.name or "",
            summary=summary,
            dataset_events=events,
            notes=notes,
            raw_control=raw or None,
        )
