"""Regression tests for issue #86.

1. ``compute_feasible_paths`` judged ``NOT S1.RUN`` never true although an
   abend of an earlier step bypasses S1 (the abend-recovery idiom).
2. ``parse_condition`` invented ``RC EQ n`` for a bare number.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.condition_parser import parse_condition
from jclparser.rc_analysis import (
    _collect_optional_steps,
    _tests_run_or_abend,
    compute_feasible_paths,
)

pytestmark = pytest.mark.unit


def _job(condition: str) -> str:
    return (
        "//J1  JOB (A),'X'\n"
        "//S0  EXEC PGM=A\n"
        "//S1  EXEC PGM=A\n"
        f"//IF1 IF {condition} THEN\n"
        "//S2  EXEC PGM=B\n"
        "//    ELSE\n"
        "//S3  EXEC PGM=C\n"
        "//    ENDIF\n"
    )


class TestNotRunAfterPossibleAbend:
    @pytest.mark.parametrize("condition", ["NOT S1.RUN", "S1.RUN = FALSE"])
    def test_negated_run_of_later_step_reachable(self, condition):
        report = compute_feasible_paths(parse_jcl(_job(condition)))
        assert report.unreachable_steps == []
        assert report.contradictory_conditions == []
        assert report.always_skipped == []

    def test_run_of_later_step_else_not_always_skipped(self):
        report = compute_feasible_paths(parse_jcl(_job("S1.RUN")))
        assert report.always_skipped == []

    def test_first_step_always_runs(self):
        report = compute_feasible_paths(parse_jcl(_job("NOT S0.RUN")))
        assert report.unreachable_steps == ["S2"]
        report = compute_feasible_paths(parse_jcl(_job("S0.RUN")))
        assert report.always_skipped == ["S3"]

    def test_rc_contradiction_still_flagged(self):
        report = compute_feasible_paths(parse_jcl(_job("(S1.RC EQ 0 AND S1.RC EQ 4)")))
        assert report.unreachable_steps == ["S2"]

    def test_tautology_on_later_step_no_longer_skips_else(self):
        # S1 may not run (S0 abended); both tests are then false.
        report = compute_feasible_paths(parse_jcl(_job("(S1.RC EQ 0 OR S1.RC NE 0)")))
        assert report.always_skipped == []

    def test_optional_steps_after_abends(self):
        job = parse_jcl(_job("S1.RUN"))
        assert _collect_optional_steps(job) == frozenset({"S2", "S3"})
        assert _collect_optional_steps(job, after_abends=True) == frozenset(
            {"S1", "S2", "S3"}
        )


class TestAbendsNotModelled:
    @pytest.mark.parametrize(
        "condition",
        ["NOT S1.RUN", "S1.RUN = FALSE", "S1.RUN", "S0.ABEND", "ABEND"],
    )
    def test_run_or_abend_test_not_judged(self, condition):
        report = compute_feasible_paths(
            parse_jcl(_job(condition)), include_abends=False
        )
        assert report.unreachable_steps == []
        assert report.always_skipped == []
        assert report.contradictory_conditions == []
        assert len(report.unanalysed_conditions) == 1
        assert "include_abends=False" in report.unanalysed_conditions[0][1]

    def test_rc_only_condition_still_judged(self):
        report = compute_feasible_paths(
            parse_jcl(_job("S1.RC GT 4095")), include_abends=False
        )
        assert report.unreachable_steps == ["S2"]
        assert report.unanalysed_conditions == []

    def test_tests_run_or_abend(self):
        assert _tests_run_or_abend(parse_condition("S1.RC EQ 0 OR NOT S1.RUN"))
        assert _tests_run_or_abend(parse_condition("S1.RC EQ 0 AND ABEND"))
        assert not _tests_run_or_abend(parse_condition("S1.RC EQ 0 OR RC GT 4"))


class TestBareNumberUnparseable:
    @pytest.mark.parametrize("text", ["4", "0", "4 AND RC = 0", "RC = 0 OR 4"])
    def test_bare_number_is_none(self, text):
        assert parse_condition(text) is None

    def test_value_first_comparison_still_parsed(self):
        node = parse_condition("4 LT S1.RC")
        assert node is not None
        assert (node.step_name, node.operator, node.value) == ("S1", "GT", 4)

    def test_block_keeps_raw_condition(self):
        job = parse_jcl(_job("4"))
        block = job.steps[2]
        assert block.condition_ast is None
        assert block.condition.strip() == "4"
