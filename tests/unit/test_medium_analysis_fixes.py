"""Regression tests for the severity:medium analysis fixes.

#101 condition precedence (see test_condition_parser_edge_cases.py),
#108 lifecycle and step COND=, #109 duplicate IF branches,
#110 SORT OUTFIL / JOINKEYS datasets, #111 FTP INPUT DD.
"""

from __future__ import annotations

import pytest

import jclparser as jp
from jclparser.rc_analysis import compute_feasible_paths

pytestmark = pytest.mark.unit


def _duplicates(src: str) -> list[tuple[int, str]]:
    return compute_feasible_paths(jp.parse_jcl(src)).duplicate_if_branches


class TestDuplicateIfBranches:
    """#109: a nested IF repeating its parent's text is not always redundant."""

    def test_unqualified_rc_with_step_between_is_not_duplicate(self):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// IF RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ELSE\n"
            "//S4 EXEC PGM=D\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == []

    @pytest.mark.parametrize("cond", ["ABEND", "NOT RUN", "RC = 0 & S1.RC = 0"])
    def test_other_unqualified_atoms_with_step_between(self, cond):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            f"// IF {cond} THEN\n"
            "//S2 EXEC PGM=B\n"
            f"// IF {cond} THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == []

    def test_unqualified_rc_with_no_step_between_is_duplicate(self):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF RC = 0 THEN\n"
            "// IF RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == [(4, "RC=0")]

    def test_qualified_rc_with_steps_between_is_duplicate(self):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// IF S1.RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == [(5, "S1.RC=0")]

    def test_qualified_step_running_between_is_not_duplicate(self):
        # S2 has not run at the outer IF but has at the inner one.
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF S2.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// IF S2.RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == []

    def test_sibling_ifs_are_not_compared(self):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// ENDIF\n"
            "// IF S1.RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == []


def _lifecycle_warnings(src: str) -> list[tuple[int | None, str]]:
    from jclparser.dataset_lifecycle import validate_dataset_lifecycle

    return [
        (e.line_number, e.message)
        for e in validate_dataset_lifecycle(jp.parse_jcl(src))
    ]


_CREATE = (
    "//J JOB\n"
    "//S1 EXEC PGM=EXTRACT\n"
    "//OUT DD DSN=PROD.DAILY.EXTRACT,DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,"
    "SPACE=(TRK,1)\n"
)
_DELETE_DD = "//DEL DD DSN=PROD.DAILY.EXTRACT,DISP=(OLD,DELETE,DELETE)\n"
_READ = "//S3 EXEC PGM=LOAD\n//IN DD DSN=PROD.DAILY.EXTRACT,DISP=SHR\n"


class TestLifecycleStepCond:
    """#108: a step that COND= can bypass is a THEN branch with no ELSE."""

    def test_cond_only_repro_gives_no_warning(self):
        src = _CREATE + "//S2 EXEC PGM=IEFBR14,COND=ONLY\n" + _DELETE_DD + _READ
        assert _lifecycle_warnings(src) == []

    def test_if_abend_form_agrees(self):
        src = (
            _CREATE
            + "// IF ABEND THEN\n//S2 EXEC PGM=IEFBR14\n"
            + _DELETE_DD
            + "// ENDIF\n"
            + _READ
        )
        assert _lifecycle_warnings(src) == []

    @pytest.mark.parametrize("cond", ["(4,LT)", "((0,NE,S1),EVEN)", "(4,LT,S1)"])
    def test_rc_test_cond_gives_no_warning(self, cond):
        src = _CREATE + f"//S2 EXEC PGM=IEFBR14,COND={cond}\n" + _DELETE_DD + _READ
        assert _lifecycle_warnings(src) == []

    @pytest.mark.parametrize("cond", ["EVEN", "(EVEN)"])
    def test_cond_even_step_always_runs(self, cond):
        src = _CREATE + f"//S2 EXEC PGM=IEFBR14,COND={cond}\n" + _DELETE_DD + _READ
        warnings = _lifecycle_warnings(src)
        assert len(warnings) == 1
        assert "after being uncataloged in step 'S2'" in warnings[0][1]

    def test_no_cond_still_warns(self):
        src = _CREATE + "//S2 EXEC PGM=IEFBR14\n" + _DELETE_DD + _READ
        assert len(_lifecycle_warnings(src)) == 1

    def test_duplicate_catalog_in_cond_step_still_reported(self):
        # The bypassable step may run, so a second NEW,CATLG in it is still
        # a duplicate of the first.
        src = (
            _CREATE
            + "//S2 EXEC PGM=X,COND=(4,LT)\n"
            + "//OUT DD DSN=PROD.DAILY.EXTRACT,DISP=(NEW,CATLG)\n"
        )
        warnings = _lifecycle_warnings(src)
        assert len(warnings) == 1
        assert "already cataloged" in warnings[0][1]
