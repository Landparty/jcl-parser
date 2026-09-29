"""Regression tests for bug-hunt round 6."""

from __future__ import annotations

import time

import pytest

from jclparser import parse_jcl
from jclparser.dataset_lifecycle import validate_dataset_lifecycle
from jclparser.rc_analysis import compute_feasible_paths
from jclparser.sql_detector import detect_sql_in_step

pytestmark = pytest.mark.unit


class TestJesOperandFieldComment:
    def test_jobparm_comment_not_in_last_value(self):
        job = parse_jcl(
            "//J JOB 1\n/*JOBPARM LINES=100,CARDS=5 SOME COMMENT\n//S1 EXEC PGM=X\n"
        )
        (jobparm,) = job.jes_typed_statements
        assert jobparm.parameters == {"LINES": "100", "CARDS": "5"}
        assert jobparm.raw == "LINES=100,CARDS=5 SOME COMMENT"

    def test_jes3_main_comment_not_in_last_value(self):
        job = parse_jcl("//J JOB 1\n//*MAIN CLASS=A RUN FIRST\n//S1 EXEC PGM=X\n")
        (main,) = job.jes_typed_statements
        assert main.parameters == {"CLASS": "A"}

    def test_jes3_operator_message_kept_whole(self):
        job = parse_jcl("//J JOB 1\n//*OPERATOR MOUNT TAPE NOW\n//S1 EXEC PGM=X\n")
        (op,) = job.jes_typed_statements
        assert op.parameters == {"_pos0": "MOUNT TAPE NOW"}


class TestExecIntegerAccessors:
    def test_unresolved_symbol_returns_none(self):
        job = parse_jcl("//J JOB 1\n//S1 EXEC PGM=X,DYNAMNBR=&N,PERFORM=&P\n")
        step = job.steps[0]
        assert step.dynamnbr is None
        assert step.perform is None

    def test_numeric_values_still_parsed(self):
        job = parse_jcl("//J JOB 1\n//S1 EXEC PGM=X,DYNAMNBR=20,PERFORM=3\n")
        assert job.steps[0].dynamnbr == 20
        assert job.steps[0].perform == 3


class TestRcAnalysis:
    def test_run_of_conditional_step_can_be_false(self):
        job = parse_jcl(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC > 4 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// ENDIF\n"
            "// IF S2.RUN THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ELSE\n"
            "//S4 EXEC PGM=D\n"
            "// ENDIF\n"
        )
        assert compute_feasible_paths(job).always_skipped == []

    def test_run_of_cond_step_can_be_false(self):
        job = parse_jcl(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "//S2 EXEC PGM=B,COND=(4,LT)\n"
            "// IF NOT S2.RUN THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
        )
        assert compute_feasible_paths(job).unreachable_steps == []

    def test_run_of_unconditional_step_still_always_true(self):
        job = parse_jcl(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RUN THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ELSE\n"
            "//S4 EXEC PGM=D\n"
            "// ENDIF\n"
        )
        assert compute_feasible_paths(job).always_skipped == ["S4"]

    def test_many_steps_are_fast_and_still_flag_dead_code(self):
        src = "//J JOB 1\n" + "".join(f"//S{i} EXEC PGM=A\n" for i in range(12))
        src += "// IF S0.RC GT 4095 THEN\n//X EXEC PGM=B\n// ENDIF\n"
        src += "// IF RC GE 0 THEN\n//Y EXEC PGM=B\n// ELSE\n//Z EXEC PGM=B\n// ENDIF\n"
        start = time.perf_counter()
        report = compute_feasible_paths(parse_jcl(src))
        assert time.perf_counter() - start < 5
        assert report.unreachable_steps == ["X"]
        assert report.always_skipped == ["Z"]


class TestLifecycleAbnormalUncatlg:
    SRC = (
        "//J JOB 1\n"
        "//S1 EXEC PGM=A\n"
        "//DD1 DD DSN=MY.DS,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
        "//S2 EXEC PGM=A\n"
        "//DD1 DD DSN=MY.DS,DISP={disp}\n"
        "//S3 EXEC PGM=A\n"
        "//DD1 DD DSN=MY.DS,DISP=SHR\n"
    )

    def test_abnormal_uncatlg_is_not_an_uncatalog(self):
        job = parse_jcl(self.SRC.format(disp="(OLD,KEEP,UNCATLG)"))
        assert validate_dataset_lifecycle(job) == []

    def test_normal_uncatlg_still_warns(self):
        job = parse_jcl(self.SRC.format(disp="(OLD,UNCATLG)"))
        errors = validate_dataset_lifecycle(job)
        assert len(errors) == 1
        assert "after being uncataloged" in str(errors[0])


class TestSystsinConcatenation:
    def test_unnamed_dd_after_systsin_is_tso_input(self):
        job = parse_jcl(
            "//J JOB 1\n"
            "//S1 EXEC PGM=IKJEFT01\n"
            "//SYSTSIN DD *\n"
            " DSN SYSTEM(DB2P)\n"
            "/*\n"
            "//        DD *\n"
            " DELETE 'MY.DATA.SET'\n"
            " BIND PLAN(X)\n"
            "/*\n"
            "//SYSIN DD *\n"
            " DELETE FROM T WHERE A=1;\n"
            "/*\n"
        )
        stmts = detect_sql_in_step(job.steps[0]).sql_statements
        assert stmts == [("BIND", "UTILITY", ""), ("DELETE", "DML", "SYSIN")]
