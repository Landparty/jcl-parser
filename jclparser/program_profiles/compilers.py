"""Profile for language-translator (compiler) steps.

Covers the common z/OS compilers invoked directly via ``EXEC PGM=``:
COBOL (``IGYCRCTL``, and the legacy OS/VS COBOL ``IKFCBL00``), PL/I
(``IEL1CL``, ``IBMZPLI``), Assembler (``ASMA90`` High Level Assembler and
the older Assembler H ``IEV90``), and the z/OS XL C/C++ compiler driver
(``CCNDRVR``).  These programs do not read a command-language
control stream the way utilities do — the "control" is the source itself
on ``SYSIN`` plus copybook/include libraries on ``SYSLIB``.  The profile
reports which of those DDs are present and where the compiled object
lands (``SYSLIN``/``SYSPUNCH``), which is enough to model a compile step's
dataset dependencies without parsing the source language.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ProgramAnalysis, ProgramProfile

if TYPE_CHECKING:
    from ..model import Step

_COMPILER_LABELS = {
    "IGYCRCTL": "COBOL",
    "IKFCBL00": "COBOL",
    "IEL1CL": "PL/I",
    "IBMZPLI": "PL/I",
    "ASMA90": "Assembler",
    "IEV90": "Assembler",
    "CCNDRVR": "C/C++",
}


class CompilerProfile(ProgramProfile):
    program_names = frozenset(_COMPILER_LABELS)

    def analyze(self, step: Step) -> ProgramAnalysis:
        program = step.program or ""
        language = _COMPILER_LABELS.get(program.upper(), "")
        notes: list[str] = []

        sysin = step.get_dd("SYSIN")
        if sysin and sysin.dataset_name:
            notes.append(f"source: {sysin.dataset_name}")
        elif sysin and sysin.inline_data:
            notes.append("source: in-stream SYSIN")

        syslib = step.get_dd("SYSLIB")
        if syslib and syslib.dataset_name:
            notes.append(f"copy/include library: {syslib.dataset_name}")

        for out_dd in ("SYSLIN", "SYSPUNCH"):
            dd = step.get_dd(out_dd)
            if dd and dd.dataset_name:
                notes.append(f"object output ({out_dd}): {dd.dataset_name}")

        summary = (
            f"{language} compile ({program})" if language else f"compile ({program})"
        )
        if notes:
            summary += f": {len(notes)} relevant DD(s)"
        else:
            summary += " with no recognised SYSIN/SYSLIB/SYSLIN DDs"

        return ProgramAnalysis(
            program=program or "COMPILER",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
        )
