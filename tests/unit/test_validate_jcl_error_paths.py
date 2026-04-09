"""
Tests for validate_jcl() error handling paths.

Covers exception handlers, line-by-line validation fallback,
PROC/PEND flag tracking, and DD-before-EXEC handling.
"""

import pytest
from unittest.mock import patch
from jclparser.parser import validate_jcl


@pytest.mark.unit
class TestValidateJCLLineLevelFallback:
    """Test the line-by-line validation path triggered when parse_jcl fails."""

    def test_multiple_job_statements_detected(self):
        """Line-by-line validation catches multiple JOB statements."""
        jcl = """\
//JOB1    JOB CLASS=A
//STEP1   EXEC PGM=PROG1
//JOB2    JOB CLASS=B
//STEP2   EXEC PGM=PROG2
"""
        errors = validate_jcl(jcl, level="basic")
        messages = " ".join(e.message for e in errors)
        assert "Multiple JOB statements found" in messages

    def test_exec_before_job_detected(self):
        """Line-by-line validation catches EXEC before JOB."""
        jcl = """\
//STEP1   EXEC PGM=PROG1
//MYJOB   JOB CLASS=A
"""
        errors = validate_jcl(jcl, level="basic")
        messages = " ".join(e.message for e in errors)
        assert "EXEC statement before JOB statement" in messages

    def test_exec_missing_program_detected(self):
        """Line-by-line validation catches EXEC with no PGM or PROC."""
        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=PROG1
//STEP2   EXEC
"""
        errors = validate_jcl(jcl, level="basic")
        messages = " ".join(e.message for e in errors)
        assert "EXEC statement missing program or procedure" in messages

    def test_proc_pend_tracking_in_validation(self):
        """PROC/PEND toggle the in_proc flag so EXEC inside PROC is not flagged."""
        jcl = """\
//TESTJOB JOB CLASS=A
//MYPROC  PROC
//STEP1   EXEC PGM=SORT
//        PEND
//RUN     EXEC MYPROC
"""
        errors = validate_jcl(jcl, level="basic")
        # Should not flag EXEC inside PROC as "EXEC before JOB"
        exec_before_job = [e for e in errors if "EXEC" in e.message and "before JOB" in e.message]
        assert len(exec_before_job) == 0

    def test_dd_before_exec_allowed(self):
        """DD statements before any EXEC should not crash validation."""
        # This is unusual but the validator should handle it gracefully
        jcl = """\
//TESTJOB JOB CLASS=A
//DD1     DD DUMMY
//STEP1   EXEC PGM=PROG1
"""
        errors = validate_jcl(jcl, level="basic")
        # Should not crash; may or may not flag an error
        assert isinstance(errors, list)

    def test_comments_and_empty_lines_skipped(self):
        """Comments and blank lines are ignored in validation."""
        jcl = """\
//TESTJOB JOB CLASS=A
//*
//* THIS IS A COMMENT
//*
//STEP1   EXEC PGM=IEFBR14
"""
        errors = validate_jcl(jcl, level="basic")
        assert isinstance(errors, list)


@pytest.mark.unit
class TestValidateJCLFileNotFound:
    """Test FileNotFoundError handling in validate_jcl."""

    def test_file_not_found_when_source_is_bad_path(self):
        """When the line-by-line path gets FileNotFoundError, it returns error."""
        # We simulate this by patching read_source to raise FileNotFoundError
        # only on the second call (the line-by-line fallback path).
        from jclparser.errors import JCLSyntaxError

        def mock_parse(*args, **kwargs):
            raise JCLSyntaxError("forced failure")

        def mock_read(source):
            raise FileNotFoundError("No such file: /nonexistent/test.jcl")

        with patch("jclparser.parser.parse_jcl", side_effect=mock_parse):
            with patch("jclparser.parser.read_source", side_effect=mock_read):
                errors = validate_jcl("some_input", level="basic")

        assert len(errors) >= 1
        assert any("No such file" in e.message or "not found" in e.message.lower() for e in errors)


@pytest.mark.unit
class TestValidateJCLStructureLevel:
    """Test the structure validation level which calls job.validate()."""

    def test_structure_level_returns_errors_list(self):
        """Structure-level validation returns a list of ParseError objects."""
        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=PROG1
//DD1     DD DSN=DATA.SET1,DISP=SHR
//STEP2   EXEC PGM=PROG2
//DD2     DD DSN=DATA.SET2,DISP=SHR
"""
        errors = validate_jcl(jcl, level="structure")
        assert isinstance(errors, list)

    def test_structure_level_on_valid_job(self):
        """Structure validation returns no errors for valid JCL."""
        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=PROG1
//DD1     DD DSN=DATA.SET1,DISP=SHR
//SYSOUT  DD SYSOUT=*
"""
        errors = validate_jcl(jcl, level="structure")
        assert errors == []


@pytest.mark.unit
class TestValidateJCLSyntaxError:
    """Test that JCLSyntaxError during line-by-line validation is captured."""

    def test_syntax_error_collected(self):
        """parse_statement raising JCLSyntaxError is collected as ParseError."""
        # A line that is not valid JCL (no // prefix)
        # The initial parse_jcl will fail, then line-by-line will catch individual errors
        jcl = """\
//TESTJOB JOB CLASS=A
INVALID LINE WITHOUT SLASHES
//STEP1   EXEC PGM=PROG1
"""
        errors = validate_jcl(jcl, level="basic")
        # The "INVALID LINE" should produce a syntax error
        assert isinstance(errors, list)
        assert len(errors) >= 1
