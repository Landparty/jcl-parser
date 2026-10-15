"""Regression tests for JobBuilder scope fixes (#102, #103, #130)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from jclparser import explode_job, parse_jcl, parse_statement
from jclparser._job_builder import JobBuilder
from jclparser.model import ConditionalBlock, Statement, Step
from jclparser.plugins import ParserConfig, StatementPlugin, get_plugin_registry

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


class _MyOpPlugin(StatementPlugin):
    def can_parse(self, line: str) -> bool:
        return " MYOP " in line

    def parse_statement(self, line: str, line_number: int) -> Statement:
        name = line[2:].split(" ", 1)[0]
        return Statement(
            type="MYOP",
            name=name,
            parameters={"_raw": line.split(" MYOP ", 1)[1].strip()},
            line_number=line_number,
        )

    @property
    def statement_types(self) -> list[str]:
        return ["MYOP"]


@pytest.fixture
def myop_plugin() -> Iterator[None]:
    registry = get_plugin_registry()
    plugin = _MyOpPlugin()
    registry.register_statement_plugin(plugin)
    try:
        yield
    finally:
        registry.unregister_plugin(plugin)


class TestCustomPluginStatements:
    """#130: a plugin statement of a custom type is kept on the job."""

    SRC = "//J JOB\n//OP1 MYOP FIRST\n//S1 EXEC PGM=X\n//OP2 MYOP SECOND\n"
    CONFIG = ParserConfig(enabled_plugins=["_MyOpPlugin"])

    @pytest.mark.usefixtures("myop_plugin")
    def test_custom_statements_kept_in_source_order(self) -> None:
        job = parse_jcl(self.SRC, config=self.CONFIG)
        assert [(s.type, s.name) for s in job.custom_statements] == [
            ("MYOP", "OP1"),
            ("MYOP", "OP2"),
        ]
        assert job.custom_statements[0].parameters["_raw"] == "FIRST"
        assert _names(job.steps) == ["S1"]

    @pytest.mark.usefixtures("myop_plugin")
    def test_custom_statement_before_job_card_kept_first(self) -> None:
        job = parse_jcl("//OP0 MYOP ZERO\n" + self.SRC, config=self.CONFIG)
        assert [s.name for s in job.custom_statements] == ["OP0", "OP1", "OP2"]

    @pytest.mark.usefixtures("myop_plugin")
    def test_custom_statements_survive_explosion(self) -> None:
        job = parse_jcl(self.SRC, config=self.CONFIG)
        exploded = explode_job(job)
        assert [s.name for s in exploded.custom_statements] == ["OP1", "OP2"]
        assert exploded.custom_statements is not job.custom_statements

    def test_default_is_empty(self) -> None:
        assert parse_jcl("//J JOB\n//S1 EXEC PGM=X\n").custom_statements == []

    def test_builder_routes_unhandled_type(self) -> None:
        builder = JobBuilder()
        stmt = Statement(type="WHATEVER", name="X", parameters={}, line_number=1)
        assert "WHATEVER" not in JobBuilder._HANDLERS
        builder.handle_statement(stmt, 1)
        builder.handle_statement(parse_statement("//J JOB", 2), 2)
        assert builder.finish().custom_statements == [stmt]
