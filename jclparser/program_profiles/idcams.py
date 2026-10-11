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
_ENTRY_NAME = r"'[^']*'|[A-Z0-9.@#$&\-]+(?:\([A-Z0-9@#$+\-]+\))?"
_RE_ENTRY_NAME = re.compile(_ENTRY_NAME, re.IGNORECASE)
# ``DELETE`` (or its abbreviation ``DEL``) names one entry, or a list of
# them in parentheses: ``DELETE (A.B C.D) PURGE``.
_RE_DELETE = re.compile(
    r"^\s*DEL(?:ETE)?\b\s*(\((?:[^()]|\([^()]*\))*\)|" + _ENTRY_NAME + ")",
    re.IGNORECASE | re.MULTILINE,
)
# ``DEFINE`` and its object keywords have IDCAMS abbreviations (``DEF CL``,
# ``DEF NVSAM``, ...); each is reported under its full keyword.
_DEFINE_KINDS = {
    "CLUSTER": "CLUSTER",
    "CL": "CLUSTER",
    "GENERATIONDATAGROUP": "GDG",
    "GDG": "GDG",
    "ALTERNATEINDEX": "AIX",
    "AIX": "AIX",
    "PATH": "PATH",
    "NONVSAM": "NONVSAM",
    "NVSAM": "NONVSAM",
    "USERCATALOG": "USERCATALOG",
    "UCAT": "USERCATALOG",
}
_RE_DEFINE = re.compile(
    r"^\s*DEF(?:INE)?\s+("
    + "|".join(sorted(_DEFINE_KINDS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE | re.MULTILINE,
)
# ``NAME(entry)``: the entry may be quoted, carry a member or a relative GDG
# generation (``NAME(A.B(+1))``) or a JCL symbol (``NAME(&HLQ..BASE)``).
_RE_NAME_PARAM = re.compile(
    r"NAME\s*\(\s*('[^']*'|[A-Z0-9.@#$&\-]+(?:\([A-Z0-9@#$+\-]+\))?)\s*\)",
    re.IGNORECASE,
)
_RE_REPRO = re.compile(r"^\s*REPRO\b", re.IGNORECASE | re.MULTILINE)
_RE_ALTER = re.compile(r"^\s*ALTER\s+([A-Z0-9.@#$\-']+)", re.IGNORECASE | re.MULTILINE)
_RE_LISTCAT = re.compile(r"^\s*LISTCAT\b", re.IGNORECASE | re.MULTILINE)
# A command also starts after ``THEN`` / ``ELSE`` (``IF LASTCC = 0 THEN
# DELETE X``) and after a ``;`` terminator (``DELETE A; DELETE B``).  Not
# inside a name: ``MY.THEN.FILE`` is no keyword.
_RE_COMMAND_START = re.compile(
    r"(?:(?<![^\s)])(THEN|ELSE)(?=\s|$)|;)", re.IGNORECASE | re.MULTILINE
)


def _one_command_per_line(text: str) -> str:
    """Put each command of normalized control text on a line of its own."""
    return _RE_COMMAND_START.sub(lambda m: (m.group(1) or "") + "\n", text)


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
        text = _one_command_per_line(_normalize_control_text(raw))
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
            define_kind = _DEFINE_KINDS[m.group(1).upper()]
            # Search for NAME(...) in this command only: continuations are
            # joined and commands split, so the command ends at the end of
            # its line, and a
            # DEFINE with no NAME must not take the next command's.
            end = text.find("\n", m.end())
            tail = text[m.end() : end if end != -1 else len(text)]
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
