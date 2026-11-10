"""Regression tests for validation / explosion issues #57, #60, #64 and #65."""

from __future__ import annotations

import pytest

from jclparser import ErrorSeverity, parse_jcl, validate_jcl
from jclparser.cli import main

DUP_STEP_JCL = "//J JOB\n//S1 EXEC PGM=A\n//S1 EXEC PGM=B\n"


@pytest.mark.unit
class TestValidateJclReportsStructuralErrors:
    """#57: validate_jcl() must not swallow job.validate() ERROR findings."""

    @pytest.mark.parametrize("level", ["basic", "structure", "semantic"])
    def test_duplicate_step_name_reported_at_every_level(self, level):
        errors = validate_jcl(DUP_STEP_JCL, level=level)
        dup = [e for e in errors if "Duplicate step name: S1" in e.message]
        if level == "basic":
            # A WARNING: z/OS runs the job (JCL Reference, "Rules for names"),
            # and the basic level reports only what fails a strict parse.
            assert dup == []
            return
        assert len(dup) == 1
        assert dup[0].severity == ErrorSeverity.WARNING

    def test_structure_level_matches_job_validate(self):
        expected = [e.message for e in parse_jcl(DUP_STEP_JCL).validate()]
        got = [e.message for e in validate_jcl(DUP_STEP_JCL, level="structure")]
        assert got == expected

    def test_basic_level_omits_warnings(self):
        # Duplicate DD names are a WARNING finding: only the structure and
        # semantic levels report it; basic reports what fails a strict parse.
        src = "//J JOB\n//S1 EXEC PGM=A\n//D DD DUMMY\n//D DD DUMMY\n"
        structure = validate_jcl(src, level="structure")
        assert any(e.severity == ErrorSeverity.WARNING for e in structure)
        assert validate_jcl(src, level="basic") == []

    def test_cli_validate_exits_nonzero(self, tmp_path, capsys):
        jcl = tmp_path / "dup.jcl"
        jcl.write_text(DUP_STEP_JCL)
        rc = main([str(jcl), "--validate"])
        out = capsys.readouterr().out
        assert rc == 1
        assert "Duplicate step name: S1" in out
        assert "OK - no errors found." not in out


BRANCH_TEMP_JCL = """\
//J JOB
//S1 EXEC PGM=A
// IF S1.RC = 0 THEN
//S2 EXEC PGM=B
//O DD DSN=&&T,DISP=(NEW,PASS)
// ELSE
//S3 EXEC PGM=C
//O DD DSN=&&T,DISP=(NEW,PASS)
// ENDIF
//S4 EXEC PGM=D
//I DD DSN=&&T,DISP=(OLD,DELETE)
"""


def _temp_errors(job):
    from jclparser.validators import validate_data_dependencies

    return [
        e for e in validate_data_dependencies(job) if e.severity == ErrorSeverity.ERROR
    ]


@pytest.mark.unit
class TestTempDatasetInIfBranches:
    """#60: THEN and ELSE are mutually exclusive for temporary datasets."""

    def test_creation_in_then_and_else_is_not_a_duplicate(self):
        assert _temp_errors(parse_jcl(BRANCH_TEMP_JCL)) == []

    def test_strict_parse_accepts_it(self):
        job = parse_jcl(BRANCH_TEMP_JCL, strict_mode=True)
        assert job.name == "J"

    def test_sequential_duplicate_still_error(self):
        src = (
            "//J JOB\n//S1 EXEC PGM=A\n//O DD DSN=&&T,DISP=(NEW,PASS)\n"
            "//S2 EXEC PGM=B\n//O DD DSN=&&T,DISP=(NEW,PASS)\n"
        )
        errors = _temp_errors(parse_jcl(src))
        assert [e.message for e in errors] == [
            "Temporary dataset &&T created in multiple steps: S1 and S2"
        ]

    def test_duplicate_within_one_branch_still_error(self):
        src = (
            "//J JOB\n//S1 EXEC PGM=A\n// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n//O DD DSN=&&T,DISP=(NEW,PASS)\n"
            "//S3 EXEC PGM=C\n//O DD DSN=&&T,DISP=(NEW,PASS)\n// ENDIF\n"
        )
        errors = _temp_errors(parse_jcl(src))
        assert [e.message for e in errors] == [
            "Temporary dataset &&T created in multiple steps: S2 and S3"
        ]

    def test_creation_in_branch_then_again_after_endif_is_error(self):
        src = (
            "//J JOB\n//S1 EXEC PGM=A\n// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n//O DD DSN=&&T,DISP=(NEW,PASS)\n// ENDIF\n"
            "//S3 EXEC PGM=C\n//O DD DSN=&&T,DISP=(NEW,PASS)\n"
        )
        errors = _temp_errors(parse_jcl(src))
        assert [e.message for e in errors] == [
            "Temporary dataset &&T created in multiple steps: S2 and S3"
        ]


@pytest.mark.unit
class TestDdOverrideNamingNoProcstep:
    """#64: a qualified DD override that matches no step is reported."""

    def test_unknown_procstep_warns_once(self):
        from jclparser import explode_job

        src = (
            "//J JOB\n//P PROC\n//S EXEC PGM=X\n// PEND\n"
            "//R EXEC P\n//NOPE.D DD DSN=A,DISP=SHR\n"
        )
        job = parse_jcl(src)
        exploded = explode_job(job)
        new = [w for w in exploded.warnings if w not in job.warnings]
        assert new == ["DD override NOPE.D names no step in PROC P"]
        assert [(s.name, s.dd_statements) for s in exploded.steps] == [("R.S", [])]

    def test_matching_procstep_does_not_warn(self):
        from jclparser import explode_job

        src = (
            "//J JOB\n//P PROC\n//S EXEC PGM=X\n// PEND\n"
            "//R EXEC P\n//S.D DD DSN=A,DISP=SHR\n"
        )
        exploded = explode_job(parse_jcl(src))
        assert not [w for w in exploded.warnings if "DD override" in w]
        assert [d.name for d in exploded.steps[0].dd_statements] == ["D"]

    def test_three_part_unknown_outer_step_warns(self):
        from jclparser import explode_job

        src = (
            "//J JOB\n//IN PROC\n//I EXEC PGM=Y\n// PEND\n"
            "//P PROC\n//S EXEC IN\n// PEND\n"
            "//R EXEC P\n//NOPE.I.D DD DSN=A,DISP=SHR\n"
        )
        exploded = explode_job(parse_jcl(src))
        assert [w for w in exploded.warnings if "DD override" in w] == [
            "DD override NOPE.I.D names no step in PROC P"
        ]

    def test_three_part_unknown_inner_step_warns(self):
        from jclparser import explode_job

        src = (
            "//J JOB\n//IN PROC\n//I EXEC PGM=Y\n// PEND\n"
            "//P PROC\n//S EXEC IN\n// PEND\n"
            "//R EXEC P\n//S.NOPE.D DD DSN=A,DISP=SHR\n"
        )
        exploded = explode_job(parse_jcl(src))
        assert [w for w in exploded.warnings if "DD override" in w] == [
            "DD override NOPE.D names no step in PROC IN"
        ]

    def test_three_part_through_a_pgm_step_warns(self):
        from jclparser import explode_job

        src = (
            "//J JOB\n//P PROC\n//S EXEC PGM=X\n// PEND\n"
            "//R EXEC P\n//S.I.D DD DSN=A,DISP=SHR\n"
        )
        exploded = explode_job(parse_jcl(src))
        assert [w for w in exploded.warnings if "DD override" in w] == [
            "DD override S.I.D names no step in PROC P"
        ]
        assert exploded.steps[0].dd_overrides == {}

    def test_four_part_name_warns(self):
        from jclparser import explode_job

        src = (
            "//J JOB\n//P PROC\n//S EXEC PGM=X\n// PEND\n"
            "//R EXEC P\n//A.B.C.D DD DSN=A,DISP=SHR\n"
        )
        exploded = explode_job(parse_jcl(src))
        assert [w for w in exploded.warnings if "DD override" in w] == [
            "DD override A.B.C.D names no step in PROC P"
        ]

    def test_qualified_dd_under_pgm_step_warns_at_parse_time(self):
        src = "//J JOB\n//S EXEC PGM=X\n//A.B DD DSN=A,DISP=SHR\n"
        job = parse_jcl(src)
        assert job.warnings == [
            (
                "DD override A.B names no step in PROC: step S runs PGM=X, "
                "not a procedure; override ignored"
            )
        ]


@pytest.mark.unit
class TestSpaceZeroPrimary:
    """#65 item 1: SPACE=(TRK,0) is the IEFBR14 delete idiom, not an error."""

    def _space(self, value):
        src = f"//J JOB\n//S EXEC PGM=IEFBR14\n//D DD DSN=A.B,DISP=(MOD,DELETE),SPACE={value}\n"
        return parse_jcl(src).steps[0].dd_statements[0].space

    def test_zero_primary_is_valid(self):
        assert self._space("(TRK,0)").validate() == []

    def test_negative_primary_still_rejected(self):
        errors = self._space("(TRK,-1)").validate()
        assert errors == ["Primary space cannot be negative: -1"]


def _lifecycle_messages(src):
    from jclparser import validate_dataset_lifecycle

    return [e.message for e in validate_dataset_lifecycle(parse_jcl(src))]


@pytest.mark.unit
class TestLifecycleDispositionAtStepEnd:
    """#65 item 2: dispositions take effect at step end, not per DD."""

    def test_delete_then_use_in_same_step_is_clean(self):
        src = (
            "//J JOB\n//S3 EXEC PGM=X\n"
            "//D3 DD DSN=PROD.B,DISP=(OLD,DELETE)\n"
            "//D4 DD DSN=PROD.B,DISP=SHR\n"
        )
        assert _lifecycle_messages(src) == []

    def test_delete_then_use_in_next_step_still_warns(self):
        src = (
            "//J JOB\n//S3 EXEC PGM=X\n"
            "//D3 DD DSN=PROD.B,DISP=(OLD,DELETE)\n"
            "//S4 EXEC PGM=Y\n"
            "//D4 DD DSN=PROD.B,DISP=SHR\n"
        )
        assert _lifecycle_messages(src) == [
            (
                "Dataset 'PROD.B' opened in step 'S4' (DD D4) after being "
                "uncataloged in step 'S3'"
            )
        ]

    def test_delete_and_recatalog_in_one_step_leaves_it_cataloged(self):
        # D1 deletes, D2 re-catalogs: at step end the dataset is cataloged,
        # so S2 reading it is clean and a later NEW,CATLG is a duplicate.
        src = (
            "//J JOB\n//S1 EXEC PGM=X\n"
            "//D1 DD DSN=PROD.B,DISP=(OLD,DELETE)\n"
            "//D2 DD DSN=PROD.B,DISP=(MOD,CATLG)\n"
            "//S2 EXEC PGM=Y\n//D DD DSN=PROD.B,DISP=SHR\n"
            "//S3 EXEC PGM=Z\n//D DD DSN=PROD.B,DISP=(NEW,CATLG)\n"
        )
        messages = _lifecycle_messages(src)
        assert not [m for m in messages if "after being uncataloged" in m]
        dup = [m for m in messages if "already cataloged" in m]
        assert len(dup) == 1
        assert "in step 'S3'" in dup[0]
        assert "already cataloged in step 'S1'" in dup[0]
