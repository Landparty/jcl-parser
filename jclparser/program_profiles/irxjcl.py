"""Profile for ``IRXJCL`` — batch REXX exec runner.

IRXJCL runs a single REXX exec named as the first token of ``PARM``; any
remaining PARM text is passed as the exec's argument string. The exec
source itself is read from ``SYSEXEC`` (a concatenation of PDS
exec libraries) rather than SYSIN.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile

if TYPE_CHECKING:
    from ..model import Step


class IRXJCLProfile(ProgramProfile):
    program_names = frozenset({"IRXJCL"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        notes: list[str] = []
        raw_parm = step.parameters.get("PARM")
        # PARM=(subparm,...) is parsed into a list of strings; PARM=value or
        # PARM='value text' stays a plain string. Normalise both to a string
        # before splitting so a parenthesised PARM can't crash this profile.
        if isinstance(raw_parm, list):
            parm = " ".join(str(p) for p in raw_parm)
        else:
            parm = str(raw_parm) if raw_parm else ""
        parts = parm.split(None, 1)
        exec_name = parts[0].upper() if parts else ""
        exec_args = parts[1] if len(parts) > 1 else ""

        if exec_name:
            notes.append(f"exec: {exec_name}")
        if exec_args:
            notes.append(f"args: {exec_args}")

        sysexec = step.get_dd("SYSEXEC")
        if sysexec and sysexec.dataset_name:
            notes.append(f"SYSEXEC library: {sysexec.dataset_name}")

        summary = (
            f"IRXJCL: runs REXX exec {exec_name}"
            if exec_name
            else "IRXJCL with no exec name in PARM"
        )
        return ProgramAnalysis(
            program="IRXJCL",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=parm or None,
            invoked_programs=[exec_name] if exec_name else [],
        )
