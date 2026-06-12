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
"""

from __future__ import annotations

from .base import ProgramProfile, ProgramAnalysis


class DFSRRC00Profile(ProgramProfile):
    program_names = frozenset({"DFSRRC00", "DFSRRC02"})

    def analyze(self, step) -> ProgramAnalysis:
        notes: list[str] = []
        parm: str = step.parameters.get("PARM") or ""

        # PARM sub-parameters are comma-separated; quotes are stripped by the
        # parser before they reach us.  Standard layout:
        #   [0] region type  (BMP / MPP / DLI / DBB / IFP / …)
        #   [1] application program
        #   [2] PSB name  (optional)
        parts = [p.strip() for p in parm.split(",")]

        region_type = parts[0].upper() if parts and parts[0] else ""
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
        )
