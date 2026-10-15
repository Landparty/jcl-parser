"""Regression tests for JobBuilder scope fixes (#102, #103, #130)."""

from __future__ import annotations

import pytest

from jclparser import explode_job, parse_jcl
from jclparser.model import ConditionalBlock, Step

pytestmark = pytest.mark.unit


def _names(items: list[Step | ConditionalBlock]) -> list[str]:
    return [i.name if isinstance(i, Step) else "IF" for i in items]


class TestUnclosedIfInProc:
    """#102: PEND closes the PROC scope, including IF blocks opened in it."""

    SRC = (
        "//J JOB\n"
        "//P PROC\n"
        "//PS1 EXEC PGM=A\n"
        "// IF (PS1.RC = 0) THEN\n"
        "//PS2 EXEC PGM=B\n"
        "// PEND\n"
        "//S1 EXEC P\n"
        "//S2 EXEC PGM=X\n"
    )

    def test_later_steps_are_job_steps(self) -> None:
        job = parse_jcl(self.SRC)
        assert _names(job.steps) == ["S1", "S2"]

    def test_unclosed_if_stays_in_procedure(self) -> None:
        job = parse_jcl(self.SRC)
        proc = job.procedures[0]
        assert _names(proc.steps) == ["PS1", "IF"]
        cond = proc.steps[1]
        assert isinstance(cond, ConditionalBlock)
        assert _names(cond.then_steps) == ["PS2"]

    def test_single_warning_names_the_proc(self) -> None:
        job = parse_jcl(self.SRC)
        if_warnings = [w for w in job.warnings if "ENDIF" in w]
        assert if_warnings == [
            "Line 4: IF block in PROC P has no matching ENDIF; closed at PEND (line 6)"
        ]

    def test_nested_unclosed_ifs_each_warned(self) -> None:
        src = (
            "//J JOB\n"
            "//P PROC\n"
            "//PS1 EXEC PGM=A\n"
            "// IF (PS1.RC = 0) THEN\n"
            "// IF (PS1.RC = 4) THEN\n"
            "//PS2 EXEC PGM=B\n"
            "// PEND\n"
            "//S1 EXEC PGM=X\n"
        )
        job = parse_jcl(src)
        assert _names(job.steps) == ["S1"]
        assert sum("closed at PEND" in w for w in job.warnings) == 2
        assert not any("IF block has no matching ENDIF" in w for w in job.warnings)

    def test_job_if_open_around_proc_is_not_used_by_proc(self) -> None:
        src = (
            "//J JOB\n"
            "//S0 EXEC PGM=Z\n"
            "// IF (S0.RC = 0) THEN\n"
            "//P PROC\n"
            "//PS1 EXEC PGM=A\n"
            "// ENDIF\n"
            "// PEND\n"
            "//S1 EXEC P\n"
            "// ELSE\n"
            "//S2 EXEC PGM=X\n"
            "// ENDIF\n"
        )
        job = parse_jcl(src)
        proc = job.procedures[0]
        # The procedure's step is the procedure's, not the job IF's.
        assert _names(proc.steps) == ["PS1"]
        # ENDIF inside the PROC cannot close the job's IF.
        assert any("Line 6: ENDIF with no matching IF" in w for w in job.warnings)
        cond = job.steps[1]
        assert isinstance(cond, ConditionalBlock)
        assert _names(cond.then_steps) == ["S1"]
        assert _names(cond.else_steps) == ["S2"]
        assert not any("no matching ENDIF" in w for w in job.warnings)

    def test_else_in_proc_without_proc_if_warns(self) -> None:
        src = (
            "//J JOB\n"
            "//S0 EXEC PGM=Z\n"
            "// IF (S0.RC = 0) THEN\n"
            "//P PROC\n"
            "// ELSE\n"
            "//PS1 EXEC PGM=A\n"
            "// PEND\n"
            "// ENDIF\n"
        )
        job = parse_jcl(src)
        assert any("Line 5: ELSE with no matching IF" in w for w in job.warnings)
        cond = job.steps[1]
        assert isinstance(cond, ConditionalBlock)
        assert cond.then_steps == []

    def test_closed_if_in_proc_unchanged(self) -> None:
        src = (
            "//J JOB\n"
            "//P PROC\n"
            "//PS1 EXEC PGM=A\n"
            "// IF (PS1.RC = 0) THEN\n"
            "//PS2 EXEC PGM=B\n"
            "// ELSE\n"
            "//PS3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// PEND\n"
            "//S1 EXEC P\n"
        )
        job = parse_jcl(src)
        assert job.warnings == []
        assert _names(job.steps) == ["S1"]
        cond = job.procedures[0].steps[1]
        assert isinstance(cond, ConditionalBlock)
        assert _names(cond.then_steps) == ["PS2"]
        assert _names(cond.else_steps) == ["PS3"]

    def test_pend_without_proc_is_harmless(self) -> None:
        src = (
            "//J JOB\n"
            "//S0 EXEC PGM=Z\n"
            "// IF (S0.RC = 0) THEN\n"
            "// PEND\n"
            "//S1 EXEC PGM=X\n"
            "// ENDIF\n"
        )
        job = parse_jcl(src)
        cond = job.steps[1]
        assert isinstance(cond, ConditionalBlock)
        assert _names(cond.then_steps) == ["S1"]


def _dd_names(step: Step | ConditionalBlock) -> list[str]:
    assert isinstance(step, Step)
    return [dd.name for dd in step.dd_statements]


class TestJobLevelDdBeforeInstreamProc:
    """#103: a job-level DD before an in-stream PROC is not moved into it."""

    SRC = (
        "//J JOB\n"
        "//JOBLIB DD DSN=A.LOAD,DISP=SHR\n"
        "//SYSCHK DD DSN=CHK.DS,DISP=OLD\n"
        "//P PROC\n"
        "//PS1 EXEC PGM=A\n"
        "// PEND\n"
        "//S1 EXEC P\n"
        "//S2 EXEC P\n"
    )

    def test_procedure_definition_untouched(self) -> None:
        job = parse_jcl(self.SRC)
        assert _dd_names(job.procedures[0].steps[0]) == []

    def test_dd_attaches_to_first_job_level_step(self) -> None:
        job = parse_jcl(self.SRC)
        assert [dd.name for dd in job.joblib_dds] == ["JOBLIB"]
        assert _dd_names(job.steps[0]) == ["SYSCHK"]
        assert _dd_names(job.steps[1]) == []
        assert job.warnings == []

    def test_same_as_without_the_proc_in_between(self) -> None:
        plain = parse_jcl(
            "//J JOB\n"
            "//JOBLIB DD DSN=A.LOAD,DISP=SHR\n"
            "//SYSCHK DD DSN=CHK.DS,DISP=OLD\n"
            "//S1 EXEC PGM=X\n"
        )
        assert _dd_names(plain.steps[0]) == _dd_names(parse_jcl(self.SRC).steps[0])

    def test_not_copied_into_every_expansion(self) -> None:
        exploded = explode_job(parse_jcl(self.SRC))
        by_name = {s.name: _dd_names(s) for s in exploded.steps}
        assert by_name["S2.PS1"] == []

    def test_dd_before_first_proc_exec_stays_in_proc(self) -> None:
        job = parse_jcl(
            "//J JOB\n"
            "//SYSCHK DD DSN=CHK.DS,DISP=OLD\n"
            "//P PROC\n"
            "//PDD DD DSN=P.DS,DISP=SHR\n"
            "//PS1 EXEC PGM=A\n"
            "// PEND\n"
            "//S1 EXEC P\n"
        )
        assert _dd_names(job.procedures[0].steps[0]) == ["PDD"]
        assert _dd_names(job.steps[0]) == ["SYSCHK"]

    def test_proc_dd_with_no_proc_step_is_warned(self) -> None:
        job = parse_jcl(
            "//J JOB\n//P PROC\n//PDD DD DSN=P.DS,DISP=SHR\n// PEND\n//S1 EXEC PGM=X\n"
        )
        assert _dd_names(job.steps[0]) == []
        assert any(
            "PROC P has DD statement(s) but no EXEC step" in w and "PDD" in w
            for w in job.warnings
        )

    def test_job_dd_with_no_job_step_still_warned(self) -> None:
        job = parse_jcl(
            "//J JOB\n"
            "//SYSCHK DD DSN=CHK.DS,DISP=OLD\n"
            "//P PROC\n"
            "//PS1 EXEC PGM=A\n"
            "// PEND\n"
        )
        assert _dd_names(job.procedures[0].steps[0]) == []
        assert any("no EXEC step" in w and "SYSCHK" in w for w in job.warnings)
