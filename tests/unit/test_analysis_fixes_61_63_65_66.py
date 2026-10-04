"""Regression tests for issues #61, #63, #65 (item 3) and #66."""

from __future__ import annotations

import json
import time

import pytest

from jclparser import parse_jcl
from jclparser.cli import main
from jclparser.condition_parser import parse_condition
from jclparser.model import ConditionalBlock
from jclparser.program_profiles import analyze_job
from jclparser.rc_analysis import compute_feasible_paths
from jclparser.sql_detector import detect_sql_in_job

pytestmark = pytest.mark.unit

_NINE = "ABCDEFGHI"


def _nine_step_job(negate: bool = False, *, with_else: bool = False) -> str:
    """Nine steps ASTEP..ISTEP, then an IF naming all nine (issue #61)."""
    src = "//J JOB (A)\n" + "".join(f"//{c}STEP EXEC PGM=X\n" for c in _NINE)
    src += (
        f"// IF {'¬(' if negate else ''}ASTEP.RUN & (BSTEP.RC=0 | CSTEP.RC=0 |\n"
        "//     DSTEP.RC=0 | ESTEP.RC=0 | FSTEP.RC=0 | GSTEP.RC=0 |\n"
        f"//     HSTEP.RC=0 | ISTEP.RC=0){')' if negate else ''} THEN\n"
        "//T EXEC PGM=Y\n"
    )
    if with_else:
        src += "// ELSE\n//E EXEC PGM=Z\n"
    return src + "// ENDIF\n"


# ---------------------------------------------------------------------------
# #61: an IF naming more than 8 steps and testing .RUN
# ---------------------------------------------------------------------------


class TestRunConditionNineSteps:
    def test_run_of_unknown_step_is_unknown(self):
        assert parse_condition("ASTEP.RUN").evaluate({}) is None
        assert parse_condition("NOT ASTEP.RUN").evaluate({}) is None

    def test_unknown_run_combines_three_valued(self):
        ast = parse_condition("ASTEP.RUN & BSTEP.RC=0")
        assert ast.evaluate({"BSTEP": (0, False)}) is None
        assert ast.evaluate({"BSTEP": (4, False)}) is False
        ast = parse_condition("ASTEP.RUN | BSTEP.RC=0")
        assert ast.evaluate({"BSTEP": (0, False)}) is True
        assert ast.evaluate({"BSTEP": (4, False)}) is None

    def test_then_branch_reachable(self):
        report = compute_feasible_paths(parse_jcl(_nine_step_job()))
        assert report.unreachable_steps == []
        assert report.contradictory_conditions == []

    def test_negated_run_else_branch_not_always_skipped(self):
        report = compute_feasible_paths(
            parse_jcl(_nine_step_job(negate=True, with_else=True))
        )
        # ASTEP always runs, so the guard is false whenever some RC is 0:
        # ELSE is reachable, and THEN (every RC non-zero) is too.
        assert report.always_skipped == []
        assert report.unreachable_steps == []


# ---------------------------------------------------------------------------
# #63: the condition tokenizer must not skip unknown characters
# ---------------------------------------------------------------------------


class TestConditionTokenizerStrict:
    @pytest.mark.parametrize(
        "text",
        [
            "S1.RC = -1",
            "S1.RC = 4 * 2",
            "S1.RC = 4 ; S2.RC = 0",
            "S1.RC = 4 AND S2.RC = 0 ?",
            "RC",
            "S1.RC",
            "S1.RC AND S2.RUN",
            "(RC)",
        ],
    )
    def test_unparseable_condition_is_none(self, text):
        assert parse_condition(text) is None

    def test_valid_conditions_still_parse(self):
        assert parse_condition("S1.RC = 1") is not None
        assert parse_condition("RC LE 4") is not None
        assert parse_condition("¬S1.ABEND & (S2.RC<4 | S3.RUN)") is not None

    def test_conditional_block_ast_is_none(self):
        job = parse_jcl(
            "//J JOB 1\n//S1 EXEC PGM=A\n"
            "// IF S1.RC=-1 THEN\n//S2 EXEC PGM=B\n// ENDIF\n"
        )
        (block,) = [b for b in job.steps if isinstance(b, ConditionalBlock)]
        assert block.condition_ast is None
        assert block.condition == "S1.RC=-1"


# ---------------------------------------------------------------------------
# #65 item 3: RC analysis must bound the search, not just the step count
# ---------------------------------------------------------------------------


def _wide_or_job(k: int) -> str:
    src = "//J JOB 1\n" + "".join(f"//S{i} EXEC PGM=A\n" for i in range(1, k + 1))
    groups = [f"(S{i}.RC>4|S{i}.RC<8|S{i}.RC=6)" for i in range(1, k + 1)]
    src += "// IF " + " &\n//    ".join(groups) + " |\n//    ABEND THEN\n"
    return src + "//T EXEC PGM=B\n// ENDIF\n"


class TestRcSearchBound:
    def test_huge_search_is_not_analysed_and_fast(self):
        job = parse_jcl(_wide_or_job(8))
        start = time.perf_counter()
        report = compute_feasible_paths(job)
        # Generous bound: the unbounded search took hours at k=8.
        assert time.perf_counter() - start < 10
        assert report.unreachable_steps == []
        assert report.always_skipped == []
        assert report.contradictory_conditions == []
        assert len(report.unanalysed_conditions) == 1
        condition, reason = report.unanalysed_conditions[0]
        assert condition == job.steps[-1].condition
        assert "combinations" in reason

    def test_small_search_still_analysed(self):
        report = compute_feasible_paths(parse_jcl(_wide_or_job(2)))
        assert report.unanalysed_conditions == []
        assert report.unreachable_steps == []

    def test_more_than_eight_named_steps_still_exact(self):
        # The old 8-step cap dropped ASTEP; with the search bounded by its
        # size instead, a contradiction over nine named steps is still found.
        src = "//J JOB (A)\n" + "".join(f"//{c}STEP EXEC PGM=X\n" for c in _NINE)
        cond = " &\n//    ".join(f"{c}STEP.RC=0" for c in _NINE)
        src += f"// IF {cond} &\n//    ASTEP.RC=4 THEN\n//T EXEC PGM=Y\n// ENDIF\n"
        report = compute_feasible_paths(parse_jcl(src))
        assert report.unreachable_steps == ["T"]
        assert report.unanalysed_conditions == []

    def test_unanalysed_does_not_make_report_non_empty(self):
        report = compute_feasible_paths(parse_jcl(_wide_or_job(8)))
        assert report.is_empty()

    def test_cli_paths_reports_unanalysed(self, tmp_path, capsys):
        path = tmp_path / "wide.jcl"
        path.write_text(_wide_or_job(8))
        assert main([str(path), "paths"]) == 0
        out = capsys.readouterr().out
        assert "(no feasibility issues found)" in out
        assert "Not analysed:" in out
        assert main([str(path), "paths", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data["unanalysed_conditions"]) == 1
        assert data["unreachable_steps"] == []

    def test_cli_paths_unanalysed_after_findings(self, tmp_path, capsys):
        src = _wide_or_job(8) + "// IF S1.RC GT 4095 THEN\n//X EXEC PGM=B\n// ENDIF\n"
        path = tmp_path / "wide.jcl"
        path.write_text(src)
        assert main([str(path), "paths"]) == 0
        out = capsys.readouterr().out
        assert "Unreachable steps:" in out
        assert out.index("Unreachable steps:") < out.index("Not analysed:")


# ---------------------------------------------------------------------------
# #66: TSO DELETE/ALTER commands in SYSTSIN are not embedded SQL
# ---------------------------------------------------------------------------

_TSO_DELETE_ALTER = (
    "//J JOB (A)\n"
    "//S EXEC PGM=IKJEFT01\n"
    "//SYSTSPRT DD SYSOUT=*\n"
    "//SYSTSIN DD *\n"
    " DELETE 'PROD.OLD.FILE'\n"
    " ALTER 'PROD.A' NEWNAME('PROD.B')\n"
    " CALL 'PROD.LOAD(MYPGM)'\n"
    "/*\n"
)


class TestProfileSqlMatchesSqlDetector:
    def test_tso_delete_alter_not_embedded_sql(self):
        job = parse_jcl(_TSO_DELETE_ALTER)
        assert analyze_job(job)[0].notes == ["CALL(MYPGM)"]
        # IKJEFT01 stays flagged as a possible DB2 driver (is_db2_program),
        # but no SQL statement is found -- the two APIs agree.
        (det,) = detect_sql_in_job(job)
        assert det.sql_statements == []

    def test_tso_bind_still_reported(self):
        job = parse_jcl(
            "//J JOB (A)\n//S EXEC PGM=IKJEFT1B\n//SYSTSIN DD *\n"
            " DSN SYSTEM(DB2P)\n BIND PACKAGE(COLL) MEMBER(PGM)\n END\n/*\n"
        )
        notes = analyze_job(job)[0].notes
        assert "embedded SQL: UTILITY" in notes

    def test_sysin_sql_under_ikjeft01_reported(self):
        job = parse_jcl(
            "//J JOB (A)\n//S EXEC PGM=IKJEFT01\n//SYSTSIN DD *\n"
            " DSN SYSTEM(DB2P)\n RUN PROGRAM(DSNTEP2) PLAN(P)\n END\n/*\n"
            "//SYSIN DD *\n DELETE FROM T1 WHERE C = 1;\n/*\n"
        )
        notes = analyze_job(job)[0].notes
        assert "embedded SQL: DML" in notes
        (det,) = detect_sql_in_job(job)
        assert {cat for _, cat, _ in det.sql_statements} == {"DML"}

    def test_dsntep2_sysin_sql_still_reported(self):
        job = parse_jcl(
            "//J JOB (A)\n//S EXEC PGM=DSNTEP2\n//SYSIN DD *\n"
            "  SELECT * FROM T1;\n  ALTER TABLE T1 ADD C INT;\n/*\n"
        )
        assert analyze_job(job)[0].notes == ["embedded SQL: DDL, DML"]
