"""Profile for ``BPXBATCH`` — the z/OS UNIX System Services batch runner.

BPXBATCH runs either a compiled program or a shell command, selected by the
first token of ``PARM``: ``PGM <path-or-name> <args>`` runs a program (an
HFS path such as ``/bin/prog`` or a load-module name), and
``SH <command>`` runs a command line through the z/OS UNIX shell. Both
forms name the *real* program/command BPXBATCH invokes on behalf of the
step, which ``EXEC PGM=BPXBATCH`` alone hides — this profile recovers it
the same way :mod:`jclparser.program_profiles.irxjcl` recovers a REXX exec
name from PARM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile

if TYPE_CHECKING:
    from ..model import Step


class BPXBATCHProfile(ProgramProfile):
    program_names = frozenset({"BPXBATCH"})

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

        parts = parm.split(None, 2)
        mode = parts[0].upper() if parts else ""
        target = parts[1] if len(parts) > 1 else ""
        args = parts[2] if len(parts) > 2 else ""

        invoked: list[str] = []
        if mode == "PGM" and target:
            notes.append(f"PGM {target}")
            invoked.append(target.rsplit("/", 1)[-1].upper())
            if args:
                notes.append(f"args: {args}")
        elif mode == "SH" and target:
            notes.append(f"SH {' '.join(p for p in (target, args) if p)}")
        elif parm:
            notes.append(parm)

        if mode and target:
            summary = f"BPXBATCH: {mode} {target}"
        elif mode:
            summary = f"BPXBATCH: {mode}"
        else:
            summary = "BPXBATCH with no PARM"

        return ProgramAnalysis(
            program="BPXBATCH",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=parm or None,
            invoked_programs=invoked,
        )
