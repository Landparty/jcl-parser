"""Profile for ``BPXBATCH`` — the z/OS UNIX System Services batch runner.

BPXBATCH runs either a compiled program or a shell command, selected by the
first token of ``PARM``: ``PGM <path-or-name> <args>`` runs a program (an
HFS path such as ``/bin/prog`` or a load-module name), and
``SH <command>`` runs a command line through the z/OS UNIX shell. Both
forms name the *real* program/command BPXBATCH invokes on behalf of the
step, which ``EXEC PGM=BPXBATCH`` alone hides — this profile recovers it
the same way :mod:`jclparser.program_profiles.irxjcl` recovers a REXX exec
name from PARM.

A ``//STDPARM`` DD supplies the same parameter string and overrides
``PARM=`` when both are coded (the usual way past PARM's 100 characters).
Its in-stream records are read with trailing blanks dropped and joined by
a blank; a STDPARM naming a dataset or z/OS UNIX file is noted, its
content being unknown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile

if TYPE_CHECKING:
    from ..model import Step


def _parm_text(step: Step) -> str:
    """The step's ``PARM=`` as one string."""
    raw_parm = step.parameters.get("PARM")
    # PARM=(subparm,...) is parsed into a list of strings; PARM=value or
    # PARM='value text' stays a plain string. Normalise both to a string
    # before splitting so a parenthesised PARM can't crash this profile.
    if isinstance(raw_parm, list):
        return " ".join(str(p) for p in raw_parm)
    return str(raw_parm) if raw_parm else ""


def _stdparm(step: Step) -> tuple[str | None, str | None]:
    """``(text, source)`` of the step's ``//STDPARM`` DD.

    *text* is the in-stream parameter string (empty for an empty or DUMMY
    STDPARM); *source* names the dataset or z/OS UNIX file the parameters
    are read from instead. Both are ``None`` without a STDPARM DD.
    """
    dd = step.get_dd("STDPARM")
    if dd is None:
        return None, None
    if dd.inline_data:
        records = (line.rstrip() for line in dd.inline_data.splitlines())
        return " ".join(r for r in records if r).strip(), None
    path = dd.parameters.get("PATH")
    source = dd.dataset_name or (str(path).strip("'") if path else None)
    return ("", None) if source is None else (None, source)


class BPXBATCHProfile(ProgramProfile):
    program_names = frozenset({"BPXBATCH"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        notes: list[str] = []
        stdparm_text, stdparm_source = _stdparm(step)
        if stdparm_source is not None:
            return self._from_stdparm_file(step, stdparm_source)
        parm = stdparm_text if stdparm_text is not None else _parm_text(step)

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
        elif stdparm_text is not None:
            summary = "BPXBATCH with an empty STDPARM"
        else:
            summary = "BPXBATCH with no PARM"
        if stdparm_text is not None:
            notes.append("parameters from STDPARM")

        return ProgramAnalysis(
            program="BPXBATCH",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=parm or None,
            invoked_programs=invoked,
        )

    @staticmethod
    def _from_stdparm_file(step: Step, source: str) -> ProgramAnalysis:
        """The analysis of a step whose STDPARM names a dataset or file."""
        return ProgramAnalysis(
            program="BPXBATCH",
            step_name=step.name or "",
            summary=f"BPXBATCH: parameters from STDPARM {source}",
            dataset_events=[],
            notes=[f"parameters from STDPARM: {source} (content not read)"],
            raw_control=None,
            invoked_programs=[],
        )
