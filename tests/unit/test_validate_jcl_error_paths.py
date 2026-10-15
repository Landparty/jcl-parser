"""
Tests for validate_jcl() error handling paths.

Covers exception handlers, line-by-line validation fallback,
PROC/PEND flag tracking, and DD-before-EXEC handling.
"""

from unittest.mock import patch

import pytest

from jclparser.errors import ErrorSeverity, ErrorType
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
        exec_before_job = [
            e for e in errors if "EXEC" in e.message and "before JOB" in e.message
        ]
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

        with (
            patch("jclparser.parser._parse_jcl_core", side_effect=mock_parse),
            patch("jclparser.parser.read_source", side_effect=mock_read),
        ):
            errors = validate_jcl("some_input", level="basic")

        assert len(errors) >= 1
        assert any(
            "No such file" in e.message or "not found" in e.message.lower()
            for e in errors
        )


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


@pytest.mark.unit
class TestValidateJCLFallbackReportsStrictError:
    """#75: the fallback skips data records and keeps the strict-parse error."""

    @staticmethod
    def _findings(jcl):
        return [(e.line_number, e.message) for e in validate_jcl(jcl)]

    def test_instream_data_not_reported_and_real_cause_kept(self):
        # With a JCLLIB an unknown PROC is an error (issue #116).
        jcl = (
            "//J JOB 1\n// JCLLIB ORDER=MY.PROCLIB\n//S EXEC PGM=SORT\n"
            "//SYSIN DD *\n  SORT FIELDS=COPY\n/*\n//S2 EXEC PROC=XYZ,A=1\n"
        )
        errors = validate_jcl(jcl)
        assert len(errors) == 1
        assert errors[0].line_number == 7
        assert errors[0].message.startswith("Procedure 'XYZ' not found")
        assert errors[0].error_type == ErrorType.SYNTAX_ERROR

    def test_cntl_control_records_not_reported(self):
        jcl = (
            "//J JOB 1\n// JCLLIB ORDER=MY.PROCLIB\n//S EXEC PGM=X\n//C CNTL\n"
            "NOT JCL AT ALL\n// ENDCNTL\n//S2 EXEC NOPROC\n"
        )
        findings = self._findings(jcl)
        assert len(findings) == 1
        assert findings[0][0] == 7
        assert "Procedure 'NOPROC' not found" in findings[0][1]

    def test_positional_exec_of_unknown_proc_reported(self):
        findings = self._findings(
            "//J JOB 1\n// JCLLIB ORDER=MY.PROCLIB\n//S EXEC XYZ\n"
        )
        assert findings and findings[0][0] == 3
        assert "Procedure 'XYZ' not found" in findings[0][1]

    def test_unknown_proc_without_jcllib_is_only_a_warning(self):
        # Issue #116: with no JCLLIB the PROC may be in the JES PROCLIB.
        jcl = "//J JOB 1\n//S EXEC XYZ\n"
        assert validate_jcl(jcl) == []
        (finding,) = validate_jcl(jcl, level="structure")
        assert finding.line_number == 2
        assert finding.severity == ErrorSeverity.WARNING
        assert finding.message.startswith("Procedure 'XYZ' not found")

    def test_malformed_dlm_reported(self):
        findings = self._findings("//J JOB 1\n//S EXEC PGM=X\n//D DD *,DLM=(AB)\n")
        assert (3, "DLM= must be a one- or two-character delimiter, got (AB)") in (
            findings
        )

    def test_member_without_job_reports_no_job(self):
        assert self._findings("//D DD DSN=A.B,DISP=SHR\n") == [
            (0, "No JOB statement found")
        ]

    def test_empty_and_comment_only_input_lenient(self):
        assert validate_jcl("") == []
        assert validate_jcl("//* JUST A COMMENT\n\n") == []

    def test_proc_member_not_flagged_for_missing_job(self):
        jcl = "//P PROC\n//S EXEC PGM=X\n//D DD DSN=(A\n// PEND\n"
        messages = [m for _, m in self._findings(jcl)]
        assert messages and "Unmatched parentheses" in messages[0]
        assert "No JOB statement found" not in messages

    def test_duplicate_findings_reported_once(self):
        findings = self._findings("//J JOB 1\n//S EXEC PGM=X\n//J2 JOB 2\n")
        assert findings == [(3, "Multiple JOB statements found")]
        dd_only = self._findings("//J JOB 1\n//D DD DSN=A.B,DISP=SHR\n")
        assert len(dd_only) == 1
        assert dd_only[0][1].startswith("DD statement found before any EXEC")

    def test_strict_error_inserted_in_line_order(self):
        jcl = "//J JOB 1\n//S EXEC PGM=X\n//D DD *,DLM=(AB)\n/*\n//S2 EXEC\n"
        errors = validate_jcl(jcl)
        assert [e.line_number for e in errors] == [3, 5]
        assert errors[0].message.startswith("DLM= must be")
        assert errors[1].message == "EXEC statement missing program or procedure"

    def test_file_like_source_read_once(self):
        import io

        jcl = "//J JOB 1\n//S EXEC PGM=X\n//SYSIN DD *\nDATA\n/*\n//S2 EXEC XYZ\n"
        assert self._findings(io.StringIO(jcl)) == self._findings(jcl)

    def test_structure_error_type_kept(self):
        errors = validate_jcl("//J JOB 1\n//D DD DSN=A.B,DISP=SHR\n")
        assert errors[0].error_type == ErrorType.STRUCTURE_ERROR
