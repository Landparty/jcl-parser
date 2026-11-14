"""Profile for ``DFSRRC00`` / ``DFSRRC02`` (IMS region controller).

DFSRRC00 is the IMS region entry point used for BMP, MPP, DLI, DBB, and IFP
region types.  The actual application program is passed as the *second*
comma-delimited sub-parameter of PARM:

    EXEC PGM=DFSRRC00,PARM='BMP,MYPROG,MYPGMSB'
                              ^^^  ^^^^^^  ^^^^^^^
                              |    |       PSB name
                              |    application program
                              IMS region type

The profile extracts the application program and PSB name from PARM so that
``analyze_step``/``analyze_job`` can report what application is actually
running, not just the region controller.

That layout holds only for the batch regions (BMP, DLI, DBB). A message
processing region codes ``PARM=(MSG,&CL1&CL2&CL3&CL4,...)``: PARM[1] is the
four three-digit transaction classes it serves and it names no program. For
MSG, IFP and any other region type, only the region type (and, for MSG, the
classes) is reported (issue #173).
"""

from __future__ import annotations

from ..model import Step
from .base import ProgramAnalysis, ProgramProfile

#: Region types whose PARM[1] / PARM[2] are the application program and PSB.
_BATCH_REGION_TYPES = frozenset({"BMP", "DLI", "DBB"})


def _transaction_classes(field: str) -> list[str]:
    """Split an MPP's ``&CL1&CL2&CL3&CL4`` field into its three-digit classes."""
    if not field.isdigit() or len(field) % 3:
        return []
    return [field[i : i + 3] for i in range(0, len(field), 3)]


class DFSRRC00Profile(ProgramProfile):
    program_names = frozenset({"DFSRRC00", "DFSRRC02"})

    def analyze(self, step) -> ProgramAnalysis:
        notes: list[str] = []
        raw_parm = step.parameters.get("PARM")

        # PARM sub-parameters are comma-separated; quotes are stripped by the
        # parser before they reach us.  ``PARM='BMP,PROG,PSB'`` arrives as one
        # string, the equally common unquoted ``PARM=(BMP,PROG,PSB)`` (the
        # IBM-supplied DLIBATCH/IMSBATCH procedures code it that way) as a
        # list of sub-parameters.  Standard layout:
        #   [0] region type  (BMP / MPP / DLI / DBB / IFP / …)
        #   [1] application program
        #   [2] PSB name  (optional)
        if isinstance(raw_parm, list):
            parm = ",".join(str(p) for p in raw_parm)
        else:
            parm = str(raw_parm) if raw_parm else ""
        parts = [p.strip() for p in parm.split(",")]

        region_type = parts[0].upper() if parts and parts[0] else ""
        if region_type and region_type not in _BATCH_REGION_TYPES:
            return _online_region_analysis(step, region_type, parts, parm)

        app_program = parts[1].upper() if len(parts) > 1 and parts[1] else ""
        psb_name = parts[2].upper() if len(parts) > 2 and parts[2] else ""

        if region_type:
            notes.append(f"IMS region type: {region_type}")
        if app_program:
            notes.append(f"application program: {app_program}")
        if psb_name:
            notes.append(f"PSB: {psb_name}")

        if app_program:
            summary = f"IMS {region_type} step running {app_program}"
        elif region_type:
            summary = f"IMS {region_type} region ({step.program}) with no application program in PARM"
        else:
            summary = f"IMS region controller ({step.program}) with unparseable PARM"

        return ProgramAnalysis(
            program=step.program or "DFSRRC00",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=parm or None,
            invoked_programs=[app_program] if app_program else [],
        )


def _online_region_analysis(
    step: Step, region_type: str, parts: list[str], parm: str
) -> ProgramAnalysis:
    """A region whose PARM names no program (MSG, IFP, ...): issue #173."""
    notes = [f"IMS region type: {region_type}"]
    classes = (
        _transaction_classes(parts[1])
        if region_type == "MSG" and len(parts) > 1
        else []
    )
    summary = f"IMS {region_type} region ({step.program})"
    if classes:
        summary += f", classes {' '.join(classes)}"
        notes.append(f"transaction classes: {' '.join(classes)}")
    notes.append(
        f"an IMS {region_type} region runs the transactions scheduled to it; "
        "its PARM names no application program"
    )
    return ProgramAnalysis(
        program=step.program or "DFSRRC00",
        step_name=step.name or "",
        summary=summary,
        dataset_events=[],
        notes=notes,
        raw_control=parm or None,
    )
