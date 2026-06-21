"""Tests for the homemade-PROC alias catalog (proc_aliases.py).

Covers:
- The default catalog resolving to real ``PGM=`` steps.
- ``extra`` overrides taking precedence over shipped defaults.
- End-to-end explosion + program-profile analysis (IMSBATCH -> DFSRRC00).
"""

import pytest

from jclparser import build_alias_loader, explode_job, parse_jcl
from jclparser.proc_aliases import DEFAULT_PROC_ALIASES
from jclparser.program_profiles import analyze_step


pytestmark = pytest.mark.unit


class TestDefaultCatalog:
    def test_imsbatch_present(self):
        assert "IMSBATCH" in DEFAULT_PROC_ALIASES
        assert "DLIBATCH" in DEFAULT_PROC_ALIASES

    def test_build_alias_loader_resolves_imsbatch(self):
        loader = build_alias_loader()
        proc = loader.load_procedure("IMSBATCH")
        assert proc is not None
        assert any(step.program == "DFSRRC00" for step in proc.steps)

    def test_lookup_is_case_insensitive(self):
        loader = build_alias_loader()
        assert loader.load_procedure("imsbatch") is not None

    def test_unknown_proc_returns_none(self):
        loader = build_alias_loader()
        assert loader.load_procedure("NOSUCHPROC") is None


class TestOverrides:
    def test_extra_overrides_default(self):
        custom = "//IMSBATCH PROC MBR=,PSB=\n//G  EXEC PGM=CUSTOMIMS\n//   PEND\n"
        loader = build_alias_loader(extra={"IMSBATCH": custom})
        proc = loader.load_procedure("IMSBATCH")
        assert proc is not None
        assert any(step.program == "CUSTOMIMS" for step in proc.steps)

    def test_extra_adds_new_alias(self):
        custom = (
            "//MYIMS PROC MBR=,PSB=\n"
            "//G  EXEC PGM=DFSRRC00,PARM='BMP,&MBR,&PSB'\n"
            "//   PEND\n"
        )
        loader = build_alias_loader(extra={"MYIMS": custom})
        # Default still resolvable...
        assert loader.load_procedure("IMSBATCH") is not None
        # ...and the new one too.
        assert loader.load_procedure("MYIMS") is not None


class TestEndToEndExpansion:
    def test_imsbatch_explodes_to_dfsrrc00_with_parm(self):
        jcl = "//MYJOB JOB\n//S1 EXEC IMSBATCH,MBR=MYPROG,PSB=MYPSB\n"
        job = parse_jcl(jcl, strict_mode=False)

        assert job.steps[0].procedure == "IMSBATCH"
        assert job.steps[0].program is None

        exploded = explode_job(job, proc_loader=build_alias_loader())

        dfs_steps = [s for s in exploded.steps if s.program == "DFSRRC00"]
        assert len(dfs_steps) == 1
        step = dfs_steps[0]
        assert step.is_exploded is True
        assert step.parameters.get("PARM") == "BMP,MYPROG,MYPSB"

    def test_exploded_step_matches_dfsrrc00_profile(self):
        jcl = "//MYJOB JOB\n//S1 EXEC IMSBATCH,MBR=MYPROG,PSB=MYPSB\n"
        job = parse_jcl(jcl, strict_mode=False)
        exploded = explode_job(job, proc_loader=build_alias_loader())

        step = next(s for s in exploded.steps if s.program == "DFSRRC00")
        analysis = analyze_step(step)

        assert analysis is not None
        assert "MYPROG" in analysis.summary
        assert any("BMP" in note for note in analysis.notes)
        assert any("MYPSB" in note for note in analysis.notes)

    def test_dlibatch_uses_dli_region_type(self):
        jcl = "//MYJOB JOB\n//S1 EXEC DLIBATCH,MBR=BATCHPGM,PSB=BATCHPSB\n"
        job = parse_jcl(jcl, strict_mode=False)
        exploded = explode_job(job, proc_loader=build_alias_loader())

        step = next(s for s in exploded.steps if s.program == "DFSRRC00")
        assert step.parameters.get("PARM") == "DLI,BATCHPGM,BATCHPSB"
