"""Regression tests for JobBuilder scope fixes (#102, #103, #130)."""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
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
