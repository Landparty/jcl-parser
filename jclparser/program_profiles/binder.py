"""Profile for ``IEWL`` / ``HEWL`` — the Binder / Linkage Editor.

Control statements are read from ``SYSIN`` (or, when absent, ``SYSLIN``):
``INCLUDE`` pulls in an object/load module, ``ENTRY`` sets the entry point,
``NAME`` names the output load module member, and ``LIBRARY``/``ALIAS``
add search libraries and alternate names.  Output lands on ``SYSLMOD``.

Also matches ``IEWBLINK`` (the modern Binder entry point) and the
load-and-go Program Loader — ``IEWLDRGO``/``HEWLDRGO``, commonly invoked
under the alias ``LOADER`` — which accepts the same INCLUDE/LIBRARY/ENTRY
control statements but loads and executes the module directly instead of
producing a permanent ``SYSLMOD`` member.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..utils import control_card_text
from ._control import split_operands
from .base import ProgramAnalysis, ProgramProfile

if TYPE_CHECKING:
    from ..model import Step

# The whole operand field: ``ddname``, ``ddname(mem1,mem2,...)`` or several
# of those separated by commas.
_RE_INCLUDE = re.compile(r"^\s*INCLUDE\s+(\S+)", re.IGNORECASE | re.MULTILINE)
_RE_ENTRY = re.compile(r"^\s*ENTRY\s+([A-Za-z0-9$#@]+)", re.IGNORECASE | re.MULTILINE)
_RE_NAME = re.compile(r"^\s*NAME\s+([A-Za-z0-9$#@]+)", re.IGNORECASE | re.MULTILINE)
_RE_LIBRARY = re.compile(
    r"^\s*LIBRARY\s+([A-Za-z0-9$#@,()]+)", re.IGNORECASE | re.MULTILINE
)
_RE_ALIAS = re.compile(r"^\s*ALIAS\s+([A-Za-z0-9$#@]+)", re.IGNORECASE | re.MULTILINE)


def _module_count(include_operands: str) -> int:
    """How many modules one INCLUDE statement names (issue #112).

    ``ddname(m1,m2,m3)`` names one module per member; a bare ``ddname``
    (a sequential object dataset or a whole member) counts as one.
    """
    count = 0
    for operand in split_operands(include_operands):
        _, paren, members = operand.partition("(")
        if paren:
            count += max(len(split_operands(members.rstrip(")"))), 1)
        else:
            count += 1
    return count


def _control_text(step: Step) -> str:
    for dd_name in ("SYSIN", "SYSLIN"):
        dd = step.get_dd(dd_name)
        if dd and dd.inline_data:
            return control_card_text(dd.inline_data)
    return ""


class BinderProfile(ProgramProfile):
    program_names = frozenset(
        {"IEWL", "HEWL", "IEWBLINK", "IEWLDRGO", "HEWLDRGO", "LOADER"}
    )

    def analyze(self, step: Step) -> ProgramAnalysis:
        text = _control_text(step)
        notes: list[str] = []

        includes = [m.group(1) for m in _RE_INCLUDE.finditer(text)]
        modules = sum(_module_count(operands) for operands in includes)
        if includes:
            notes.append(f"INCLUDE {', '.join(includes)}")
        for m in _RE_ENTRY.finditer(text):
            notes.append(f"ENTRY {m.group(1)}")
        for m in _RE_NAME.finditer(text):
            notes.append(f"NAME {m.group(1)}")
        for m in _RE_LIBRARY.finditer(text):
            notes.append(f"LIBRARY {m.group(1)}")
        for m in _RE_ALIAS.finditer(text):
            notes.append(f"ALIAS {m.group(1)}")

        syslmod = step.get_dd("SYSLMOD")
        if syslmod and syslmod.dataset_name:
            notes.append(f"output module: {syslmod.dataset_name}")

        summary = (
            f"{step.program}: link-edits {modules} object module(s)"
            if notes
            else f"{step.program} with no recognised control statements"
        )
        return ProgramAnalysis(
            program=step.program or "IEWL",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
