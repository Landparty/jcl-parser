"""Regression tests for analysis-layer fixes: RC feasibility, condition
parsing, dataset lifecycle, program profiles, lint and SQL detection."""

from __future__ import annotations

import time

import pytest

from jclparser import parse_jcl
from jclparser.condition_parser import NOT_RUN, parse_condition
from jclparser.dataset_lifecycle import (
    analyze_dataset_lifecycle,
    validate_dataset_lifecycle,
)
from jclparser.lint import LintConfig
from jclparser.lint.rules import HardcodedHLQRule
from jclparser.program_profiles import analyze_job
from jclparser.rc_analysis import _evaluate_over_domain, compute_feasible_paths
from jclparser.sql_detector import detect_sql_in_job

pytestmark = pytest.mark.unit


def _messages(jcl: str) -> list[str]:
    return [e.message for e in validate_dataset_lifecycle(parse_jcl(jcl))]


# ---------------------------------------------------------------------------
# rc_analysis: RC domain
# ---------------------------------------------------------------------------


class TestRcDomain:
    def test_range_between_default_values_is_reachable(self):
        report = compute_feasible_paths(
            parse_jcl(
                "//J JOB 1\n"
                "//S1 EXEC PGM=A\n"
                "// IF (S1.RC GT 4 AND S1.RC LT 8) THEN\n"
                "//S2 EXEC PGM=B\n"
                "// ENDIF\n"
            )
        )
        assert report.unreachable_steps == []

    def test_rc_above_sixteen_is_reachable(self):
        report = compute_feasible_paths(
            parse_jcl(
                "//J JOB 1\n//S1 EXEC PGM=A\n"
                "// IF S1.RC GT 16 THEN\n//S3 EXEC PGM=B\n// ENDIF\n"
            )
        )
        assert report.unreachable_steps == []

    def test_empty_range_still_unreachable(self):
        report = compute_feasible_paths(
            parse_jcl(
                "//J JOB 1\n//S1 EXEC PGM=A\n"
                "// IF (S1.RC GT 5 AND S1.RC LT 6) THEN\n//S2 EXEC PGM=B\n"
                "// ENDIF\n"
            )
        )
        assert report.unreachable_steps == ["S2"]

    def test_above_max_rc_unreachable(self):
        report = compute_feasible_paths(
            parse_jcl(
                "//J JOB 1\n//S1 EXEC PGM=A\n"
                "// IF S1.RC GT 4095 THEN\n//S2 EXEC PGM=B\n// ENDIF\n"
            )
        )
        assert report.unreachable_steps == ["S2"]

    def test_unqualified_rc_range_reachable(self):
        report = compute_feasible_paths(
            parse_jcl(
                "//J JOB 1\n//S1 EXEC PGM=A\n//S2 EXEC PGM=A\n"
                "// IF (RC GT 4 AND RC LT 8) THEN\n//S3 EXEC PGM=B\n// ENDIF\n"
            )
        )
        assert report.unreachable_steps == []

    def test_many_constants_stay_fast(self):
        cond = " AND ".join(f"(S{i}.RC EQ {i * 3 + 1} OR S{i}.ABEND)" for i in range(6))
        ast = parse_condition(cond + " AND S0.RC GT 4095")
        start = time.perf_counter()
        result = _evaluate_over_domain(
            ast, [f"S{i}" for i in range(6)], (0, 4, 8, 12, 16), (False, True)
        )
        assert time.perf_counter() - start < 5
        assert result == (False, True, False)


# ---------------------------------------------------------------------------
# condition_parser / rc_analysis: steps that did not run
# ---------------------------------------------------------------------------


class TestNotRun:
    def test_rc_of_step_not_run_is_false(self):
        assert parse_condition("S2.RC GE 0").evaluate({"S2": NOT_RUN}) is False

    def test_abend_of_step_not_run_is_false(self):
        assert parse_condition("S2.ABEND").evaluate({"S2": NOT_RUN}) is False

    def test_run_of_step_not_run_is_false(self):
        ast = parse_condition("S2.RUN")
        assert ast.evaluate({"S2": NOT_RUN}) is False
        assert parse_condition("NOT S2.RUN").evaluate({"S2": NOT_RUN}) is True

    def test_unknown_step_still_none(self):
        assert parse_condition("S2.RC GE 0").evaluate({}) is None
        assert parse_condition("S2.ABEND").evaluate({}) is None

    def test_unqualified_atoms_ignore_steps_not_run(self):
        results = {"S1": (4, False), "S2": NOT_RUN}
        assert parse_condition("RC EQ 4").evaluate(results) is True
        assert parse_condition("ABEND").evaluate(results) is False
        assert parse_condition("RC EQ 0").evaluate({"S2": NOT_RUN}) is None

    def test_else_of_test_on_optional_step_reachable(self):
        report = compute_feasible_paths(
            parse_jcl(
                "//J JOB 1\n"
                "//S1 EXEC PGM=A\n"
                "// IF S1.RC = 0 THEN\n"
                "//S2 EXEC PGM=B\n"
                "// ENDIF\n"
                "// IF S2.RC GE 0 THEN\n"
                "//S3 EXEC PGM=C\n"
                "// ELSE\n"
                "//S4 EXEC PGM=D\n"
                "// ENDIF\n"
            )
        )
        assert report.always_skipped == []
        assert report.unreachable_steps == []


_PROC_STEP_TESTS = (
    "//J JOB 1\n"
    "//P PROC\n"
    "//PS1 EXEC PGM=X,COND=(4,LT)\n"
    "//PS2 EXEC PGM=Y\n"
    "// PEND\n"
    "//R EXEC P\n"
    "// IF (R.PS1.RUN) THEN\n"
    "//A EXEC PGM=A\n"
    "// ELSE\n"
    "//B EXEC PGM=B\n"
    "// ENDIF\n"
    "// IF (NOT R.PS1.RUN) THEN\n"
    "//C EXEC PGM=C\n"
    "// ENDIF\n"
)


class TestProcStepOnUnexplodedJob:
    """A ``stepname.procstep`` test on an unexploded job: the PROC's steps
    are not in the job, so whether the procstep ran is not known."""

    def test_proc_step_may_not_run(self):
        report = compute_feasible_paths(parse_jcl(_PROC_STEP_TESTS))
        assert report.unreachable_steps == []
        assert report.always_skipped == []
        assert report.contradictory_conditions == []

    def test_exploded_job_still_judged(self):
        from jclparser import explode_job

        # The first step of the exploded job (no COND=) always runs.  PS2
        # is not certain to run: PS1 may abend, which bypasses PS2 (#86).
        jcl = _PROC_STEP_TESTS.replace("PGM=X,COND=(4,LT)", "PGM=X")
        report = compute_feasible_paths(explode_job(parse_jcl(jcl)))
        assert report.unreachable_steps == ["C"]
        assert report.always_skipped == ["B"]
        jcl = _PROC_STEP_TESTS.replace("R.PS1.RUN", "R.PS2.RUN")
        report = compute_feasible_paths(explode_job(parse_jcl(jcl)))
        assert report.unreachable_steps == []
        assert report.always_skipped == []

    def test_program_step_qualifier_unchanged(self):
        report = compute_feasible_paths(
            parse_jcl(
                "//J JOB 1\n"
                "//S1 EXEC PGM=A\n"
                "// IF (NOT S1.RUN) THEN\n"
                "//S2 EXEC PGM=B\n"
                "// ENDIF\n"
            )
        )
        assert report.unreachable_steps == ["S2"]


# ---------------------------------------------------------------------------
# condition_parser: NG / NL
# ---------------------------------------------------------------------------


class TestMnemonicNotOperators:
    def test_ng_is_le(self):
        ast = parse_condition("S1.RC NG 4")
        assert ast is not None
        assert ast.operator == "LE"
        assert ast.evaluate({"S1": (4, False)}) is True
        assert ast.evaluate({"S1": (8, False)}) is False

    def test_nl_is_ge(self):
        ast = parse_condition("S1.RC NL 4")
        assert ast is not None
        assert ast.operator == "GE"
        assert ast.evaluate({"S1": (0, False)}) is False


# ---------------------------------------------------------------------------
# dataset_lifecycle
# ---------------------------------------------------------------------------


class TestLifecycleModCatlg:
    JCL = (
        "//J JOB 1\n"
        "//DEL EXEC PGM=IEFBR14\n"
        "//DD1 DD DSN=A.B.C,DISP=(MOD,DELETE),SPACE=(TRK,0)\n"
        "//S2 EXEC PGM=B\n"
        "//OUT DD DSN=A.B.C,DISP=(MOD,CATLG),SPACE=(TRK,1)\n"
        "//S3 EXEC PGM=C\n"
        "//IN DD DSN=A.B.C,DISP=SHR\n"
    )

    def test_delete_then_mod_catlg_then_read_is_clean(self):
        assert _messages(self.JCL) == []

    def test_old_after_delete_still_warns(self):
        msgs = _messages(
            "//J JOB 1\n"
            "//DEL EXEC PGM=IEFBR14\n"
            "//DD1 DD DSN=A.B.C,DISP=(OLD,DELETE)\n"
            "//S3 EXEC PGM=C\n"
            "//IN DD DSN=A.B.C,DISP=SHR\n"
        )
        assert len(msgs) == 1
        assert "after being uncataloged" in msgs[0]

    def test_mod_catlg_then_new_catlg_is_duplicate(self):
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "//OUT DD DSN=A.B.C,DISP=(MOD,CATLG),SPACE=(TRK,1)\n"
            "//S2 EXEC PGM=B\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG),SPACE=(TRK,1)\n"
        )
        assert len(msgs) == 1
        assert "already cataloged in step 'S1'" in msgs[0]


class TestLifecycleReferbacks:
    JCL = (
        "//J JOB 1\n"
        "//S1 EXEC PGM=A\n"
        "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
        "//S2 EXEC PGM=B\n"
        "//IN DD DSN=*.S1.OUT,DISP=(OLD,DELETE)\n"
        "//S3 EXEC PGM=C\n"
        "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
    )

    def test_referback_recorded_under_target_dataset(self):
        events = analyze_dataset_lifecycle(parse_jcl(self.JCL))
        assert list(events) == ["A.B.C"]
        assert [e.step_name for e in events["A.B.C"]] == ["S1", "S2", "S3"]

    def test_delete_through_referback_allows_recreate(self):
        assert _messages(self.JCL) == []


class TestLifecycleBranches:
    def test_then_and_else_allocating_same_dataset_is_clean(self):
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
            "// ELSE\n"
            "//S3 EXEC PGM=C\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
            "// ENDIF\n"
        )
        assert msgs == []

    def test_allocation_after_endif_still_duplicate(self):
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
            "// ENDIF\n"
            "//S4 EXEC PGM=D\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
        )
        assert len(msgs) == 1
        assert "already cataloged in step 'S2'" in msgs[0]

    def test_duplicate_within_one_branch_still_reported(self):
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
            "//S3 EXEC PGM=C\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
            "// ENDIF\n"
        )
        assert len(msgs) == 1

    def test_open_in_then_not_forward_reference_to_else_allocation(self):
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "//IN DD DSN=A.B.C,DISP=OLD\n"
            "// ELSE\n"
            "//S3 EXEC PGM=C\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
            "// ENDIF\n"
        )
        assert msgs == []

    def test_forward_reference_across_branches_of_different_ifs(self):
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "//IN DD DSN=A.B.C,DISP=OLD\n"
            "// ENDIF\n"
            "// IF S1.RC = 4 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ELSE\n"
            "//S4 EXEC PGM=C\n"
            "//OUT DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,1)\n"
            "// ENDIF\n"
        )
        assert len(msgs) == 1
        assert "before it is allocated in a later step" in msgs[0]

    def test_open_in_else_after_then_allocation_not_forward(self):
        msgs = _messages(
            "//J JOB 1\n"
            "//S0 EXEC PGM=A\n"
            "//X DD DSN=A.B.C,DISP=(NEW,CATLG),SPACE=(TRK,1)\n"
            "// IF S0.RC = 0 THEN\n"
            "//S1 EXEC PGM=B\n"
            "//IN DD DSN=A.B.C,DISP=SHR\n"
            "// ENDIF\n"
        )
        assert msgs == []


# ---------------------------------------------------------------------------
# program profiles
# ---------------------------------------------------------------------------


class TestIcetoolAndSortProfiles:
    JCL = (
        "//J JOB 1\n"
        "//S1 EXEC PGM=ICETOOL\n"
        "//TOOLIN DD *\n"
        "* COPY FROM(X) TO(Y)\n"
        "  COPY FROM(IN) TO(OUT1,OUT2)\n"
        "  SORT FROM(IN) -\n"
        "       TO(OUT3) USING(CTL1)\n"
        "/*\n"
        "//S2 EXEC PGM=SORT\n"
        "//SYSIN DD *\n"
        "* OMIT RECORDS WITH BLANK KEY -- (not used any more)\n"
        "  SORT FIELDS=COPY\n"
        "/*\n"
    )

    def _notes(self) -> dict[str, list[str]]:
        return {r.step_name: r.notes for r in analyze_job(parse_jcl(self.JCL))}

    def test_icetool_to_list_and_continuation(self):
        assert self._notes()["S1"] == [
            "COPY FROM(IN) TO(OUT1,OUT2)",
            "SORT FROM(IN) TO(OUT3)",
        ]

    def test_sort_comment_is_not_a_filter(self):
        assert self._notes()["S2"] == ["SORT FIELDS"]


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


class TestLintHardcodedHlq:
    def test_referback_and_nullfile_not_flagged(self):
        job = parse_jcl(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "//OUT DD DSN=&HLQ..B.C,DISP=(NEW,CATLG),SPACE=(TRK,1)\n"
            "//S2 EXEC PGM=B\n"
            "//IN DD DSN=*.S1.OUT,DISP=SHR\n"
            "//NUL DD DSN=NULLFILE\n"
        )
        assert list(HardcodedHLQRule().check(job, LintConfig())) == []

    def test_literal_still_flagged(self):
        job = parse_jcl("//J JOB 1\n//S1 EXEC PGM=A\n//IN DD DSN=PROD.B.C,DISP=SHR\n")
        assert len(list(HardcodedHLQRule().check(job, LintConfig()))) == 1


# ---------------------------------------------------------------------------
# sql_detector
# ---------------------------------------------------------------------------


class TestSqlDb2Proc:
    def test_exec_dsnuproc_detected(self):
        job = parse_jcl(
            "//J JOB 1\n"
            "//S1 EXEC DSNUPROC,SYSTEM=DB2P,UID='X'\n"
            "//SYSIN DD *\n"
            "  RUNSTATS TABLESPACE DB.TS\n"
            "/*\n"
        )
        results = detect_sql_in_job(job)
        assert [r.step_name for r in results] == ["S1"]
        assert results[0].is_db2_program

    def test_other_proc_not_detected(self):
        job = parse_jcl("//J JOB 1\n//S1 EXEC MYPROC\n")
        assert detect_sql_in_job(job) == []
