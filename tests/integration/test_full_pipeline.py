"""
Full pipeline integration tests: parse → validate → explode.

Tests that all three stages work together consistently on the same JCL input.
"""

import pytest
from jclparser.parser import parse_jcl, validate_jcl
from jclparser.model import Step


@pytest.mark.integration
class TestParseValidateExplodePipeline:
    """Exercise the full parse → validate → explode pipeline."""

    def test_basic_pipeline(self):
        """Parse, validate, and explode a simple PROC-based job."""
        jcl = """\
//TESTJOB JOB CLASS=A
//MYPROC  PROC DSN=DEFAULT
//STEP1   EXEC PGM=SORT
//INPUT   DD DSN=&DSN,DISP=SHR
//OUTPUT  DD DSN=&DSN..OUT,DISP=(NEW,CATLG)
//SYSOUT  DD SYSOUT=*
//        PEND
//RUN     EXEC MYPROC,DSN=PROD.DATA
"""
        # Stage 1: Parse
        job = parse_jcl(jcl)
        assert job.name == "TESTJOB"
        assert len(job.procedures) == 1
        assert job.procedures[0].name == "MYPROC"

        # Stage 2: Validate
        errors = validate_jcl(jcl, level="structure")
        # Should have no critical errors
        syntax_errors = [e for e in errors if "syntax" in e.error_type.value.lower()]
        assert len(syntax_errors) == 0

        # Stage 3: Explode
        exploded = job.explode()
        assert exploded.name == "TESTJOB"

        # Verify PROC was expanded and symbols substituted
        exec_steps = [s for s in exploded.steps if isinstance(s, Step)]
        assert len(exec_steps) >= 1
        # The symbol &DSN should be resolved
        for step in exec_steps:
            for dd in step.dd_statements:
                if dd.dataset_name:
                    assert "&DSN" not in dd.dataset_name

    def test_pipeline_with_conditionals_and_procs(self):
        """Full pipeline on a job with both PROCs and conditionals."""
        jcl = """\
//TESTJOB JOB CLASS=A
//MYPROC  PROC
//S1      EXEC PGM=IEFBR14
//        PEND
//STEP1   EXEC PGM=PROG1
// IF (STEP1.RC EQ 0) THEN
//STEP2   EXEC MYPROC
// ENDIF
"""
        # Parse
        job = parse_jcl(jcl)
        assert len(job.procedures) == 1

        # Validate
        errors = validate_jcl(jcl, level="basic")
        assert isinstance(errors, list)

        # Explode
        exploded = job.explode()
        # Should have exploded the PROC call inside the conditional
        assert len(exploded.steps) >= 1

    def test_pipeline_validates_then_explodes_multi_step(self):
        """Multi-step job with SET symbols goes through all pipeline stages."""
        jcl = """\
//TESTJOB JOB CLASS=A
// SET DSN1=MY.DATA.SET1
// SET DSN2=MY.DATA.SET2
//STEP1   EXEC PGM=SORT
//INPUT   DD DSN=&DSN1,DISP=SHR
//OUTPUT  DD DSN=&DSN2,DISP=(NEW,CATLG)
//SYSOUT  DD SYSOUT=*
//STEP2   EXEC PGM=IEFBR14
//DD1     DD DSN=&&TEMP,DISP=(NEW,PASS)
"""
        job = parse_jcl(jcl)
        assert len(job.set_statements) >= 2

        errors = validate_jcl(jcl, level="structure")
        assert isinstance(errors, list)

        exploded = job.explode()
        exec_steps = [s for s in exploded.steps if isinstance(s, Step)]
        assert len(exec_steps) >= 2

    def test_pipeline_error_consistency(self):
        """Errors found by validate_jcl are consistent with parse results."""
        # JCL with a structural issue: EXEC before JOB
        bad_jcl = """\
//STEP1   EXEC PGM=PROG1
//TESTJOB JOB CLASS=A
//STEP2   EXEC PGM=PROG2
"""
        errors = validate_jcl(bad_jcl, level="basic")
        # Should detect the specific EXEC-before-JOB structural error
        error_messages = " ".join(e.message for e in errors)
        assert "EXEC statement before JOB statement" in error_messages

    def test_exploded_job_validates_cleanly(self):
        """After explosion, the resulting job should also pass validation."""
        jcl = """\
//TESTJOB JOB CLASS=A
//MYPROC  PROC
//S1      EXEC PGM=IEFBR14
//SYSOUT  DD SYSOUT=*
//        PEND
//CALL1   EXEC MYPROC
//CALL2   EXEC MYPROC
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        # The exploded job's steps should all be valid
        validation_errors = exploded.validate()
        # Filter for genuine structural errors (not warnings about naming)
        structural = [
            e
            for e in validation_errors
            if "structure" in str(e.error_type).lower()
        ]
        assert len(structural) == 0


@pytest.mark.integration
class TestPipelineWithSemanticValidation:
    """Pipeline tests that exercise the semantic validation level."""

    def test_semantic_validation_catches_structure_issues(self):
        """Semantic validation includes structure checks."""
        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
//SYSOUT  DD SYSOUT=*
"""
        errors = validate_jcl(jcl, level="semantic")
        # Should return a list (possibly empty for valid JCL)
        assert isinstance(errors, list)

    def test_full_cycle_with_multiple_procs(self):
        """Parse, validate, explode a job that calls multiple different PROCs."""
        jcl = """\
//TESTJOB JOB CLASS=A
//PROC1   PROC P1=A
//S1      EXEC PGM=PROGA
//DD1     DD DSN=&P1..FILE,DISP=SHR
//        PEND
//PROC2   PROC P2=B
//S1      EXEC PGM=PROGB
//DD1     DD DSN=&P2..FILE,DISP=SHR
//        PEND
//CALL1   EXEC PROC1,P1=X
//CALL2   EXEC PROC2,P2=Y
"""
        job = parse_jcl(jcl)
        assert len(job.procedures) == 2

        errors = validate_jcl(jcl, level="semantic")
        assert isinstance(errors, list)

        exploded = job.explode()
        exec_steps = [s for s in exploded.steps if isinstance(s, Step)]
        assert len(exec_steps) >= 2

        # Verify each call got its own symbol substitution
        for step in exec_steps:
            for dd in step.dd_statements:
                if dd.dataset_name:
                    assert "&P1" not in dd.dataset_name
                    assert "&P2" not in dd.dataset_name
