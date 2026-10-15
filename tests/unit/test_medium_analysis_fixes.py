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


def _profile_notes(src: str) -> list[str]:
    from jclparser.program_profiles import analyze_job

    results = analyze_job(jp.parse_jcl(src))
    assert len(results) == 1
    return results[0].notes


class TestSortOutfilJoinkeysDatasets:
    """#110: OUTFIL FNAMES=/FILES= outputs and JOINKEYS inputs are reported."""

    def test_outfil_fnames_outputs(self):
        src = (
            "//J JOB\n"
            "//S EXEC PGM=SORT\n"
            "//SORTIN DD DSN=A.IN,DISP=SHR\n"
            "//OUT1 DD DSN=A.OUT1,DISP=(NEW,CATLG)\n"
            "//OUT2 DD DSN=A.OUT2,DISP=(NEW,CATLG)\n"
            "//OTHER DD DSN=A.OTHER,DISP=SHR\n"
            "//SYSIN DD *\n"
            "  SORT FIELDS=COPY\n"
            "  OUTFIL FNAMES=OUT1,\n"
            "    INCLUDE=(1,1,CH,EQ,C'A')\n"
            "  OUTFIL FNAMES=OUT2,SAVE\n"
            "/*\n"
        )
        notes = _profile_notes(src)
        assert "input: A.IN" in notes
        assert "output: A.OUT1" in notes
        assert "output: A.OUT2" in notes
        assert not any("A.OTHER" in n for n in notes)

    def test_outfil_fnames_list_files_and_default(self):
        src = (
            "//J JOB\n"
            "//S EXEC PGM=SORT\n"
            "//SORTIN DD DSN=A.IN,DISP=SHR\n"
            "//SORTOUT DD DSN=A.MAIN,DISP=(NEW,CATLG)\n"
            "//SORTOF1 DD DSN=A.OF1,DISP=(NEW,CATLG)\n"
            "//SORTOFAB DD DSN=A.OFAB,DISP=(NEW,CATLG)\n"
            "//X DD DSN=A.X,DISP=(NEW,CATLG)\n"
            "//Y DD DSN=A.Y,DISP=(NEW,CATLG)\n"
            "//SYSIN DD *\n"
            "  SORT FIELDS=(1,4,CH,A)\n"
            "  OUTFIL FILES=(1,AB)\n"
            "  OUTFIL FNAMES=(X,Y)\n"
            "  OUTFIL INCLUDE=(1,1,CH,EQ,C'B')\n"
            "/*\n"
        )
        notes = _profile_notes(src)
        for dsn in ("A.MAIN", "A.OF1", "A.OFAB", "A.X", "A.Y"):
            assert f"output: {dsn}" in notes

    def test_joinkeys_default_ddnames(self):
        src = (
            "//J JOB\n"
            "//S EXEC PGM=SORT\n"
            "//SORTJNF1 DD DSN=A.LEFT,DISP=SHR\n"
            "//SORTJNF2 DD DSN=A.RIGHT,DISP=SHR\n"
            "//SORTOUT DD DSN=A.JOINED,DISP=(NEW,CATLG)\n"
            "//SYSIN DD *\n"
            "  JOINKEYS FILE=F1,FIELDS=(1,10,A)\n"
            "  JOINKEYS FILE=F2,FIELDS=(1,10,A)\n"
            "  REFORMAT FIELDS=(F1:1,80,F2:11,20)\n"
            "  SORT FIELDS=COPY\n"
            "/*\n"
        )
        notes = _profile_notes(src)
        assert "input: A.LEFT" in notes
        assert "input: A.RIGHT" in notes
        assert "output: A.JOINED" in notes

    def test_joinkeys_named_ddnames(self):
        src = (
            "//J JOB\n"
            "//S EXEC PGM=SORT\n"
            "//LEFT DD DSN=A.LEFT,DISP=SHR\n"
            "//RIGHT DD DSN=A.RIGHT,DISP=SHR\n"
            "//SORTOUT DD DSN=A.JOINED,DISP=(NEW,CATLG)\n"
            "//SYSIN DD *\n"
            "  JOINKEYS F1=LEFT,FIELDS=(1,10,A)\n"
            "  JOINKEYS F2=RIGHT,\n"
            "    FIELDS=(1,10,A)\n"
            "  SORT FIELDS=COPY\n"
            "/*\n"
        )
        notes = _profile_notes(src)
        assert "input: A.LEFT" in notes
        assert "input: A.RIGHT" in notes
