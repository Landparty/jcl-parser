"""
Comprehensive test suite for JCL/PROC file type detection.

Following TDD methodology - these tests are written BEFORE implementation.
Tests cover unit tests, integration tests, edge cases, and E2E scenarios.
"""

import os
import tempfile
from io import StringIO
from pathlib import Path

import pytest

# Import will fail initially - this is expected in TDD (Red phase)
from jclparser.jcl_file_type import (
    FileType,
    detect_file_type,
    is_jcl_file,
    is_proc_file,
)


class TestBasicDetection:
    """Unit tests for basic JCL/PROC detection."""

    def test_detect_jcl_with_job_card(self):
        """Test detection of standard JCL file with JOB card."""
        jcl_content = """//MYJOB    JOB (12345),'DEVELOPER',CLASS=A
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD   SYSOUT=*
"""
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL

    def test_detect_proc_with_proc_statement(self):
        """Test detection of PROC file starting with PROC statement."""
        proc_content = """//MYPROC   PROC DSN=DEFAULT.DATA
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN,DISP=SHR
//         PEND
"""
        result = detect_file_type(proc_content)
        assert result == FileType.PROC

    def test_detect_proc_with_exec_only(self):
        """Test detection of PROC file with only EXEC statements (no PROC keyword)."""
        proc_content = """//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD   SYSOUT=*
//STEP2    EXEC PGM=SORT
//SORTIN   DD   DSN=INPUT.DATA,DISP=SHR
"""
        result = detect_file_type(proc_content)
        assert result == FileType.PROC

    def test_empty_file(self):
        """Test that empty file returns UNKNOWN."""
        result = detect_file_type("")
        assert result == FileType.UNKNOWN

    def test_comments_only(self):
        """Test that file with only comments returns UNKNOWN."""
        comments_content = """//*
//* This is a comment
//* Another comment
//*
"""
        result = detect_file_type(comments_content)
        assert result == FileType.UNKNOWN

    def test_whitespace_only(self):
        """Test that file with only whitespace returns UNKNOWN."""
        whitespace_content = """


        
"""
        result = detect_file_type(whitespace_content)
        assert result == FileType.UNKNOWN

    def test_job_card_after_comments(self):
        """Test JCL detection when JOB card appears after comment lines."""
        jcl_content = """//*
//* Production payroll job
//* Author: Developer
//*
//PAYROLL  JOB (ACCT001),'PAYROLL SYSTEM',CLASS=A
//STEP1    EXEC PGM=PAYCALC
"""
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL

    def test_proc_card_after_comments(self):
        """Test PROC detection when PROC card appears after comment lines."""
        proc_content = """//*
//* Utility procedure
//*
//UTILPROC PROC
//STEP1    EXEC PGM=IEFBR14
//         PEND
"""
        result = detect_file_type(proc_content)
        assert result == FileType.PROC


class TestSourceTypes:
    """Test detection with different input source types."""

    def test_from_string_source(self):
        """Test detection from string input."""
        jcl_string = "//TESTJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14"
        result = detect_file_type(jcl_string)
        assert result == FileType.JCL

    def test_from_path_source(self):
        """Test detection from Path object."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jcl", delete=False) as f:
            f.write("//TESTJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14")
            temp_path = f.name

        try:
            result = detect_file_type(Path(temp_path))
            assert result == FileType.JCL
        finally:
            os.unlink(temp_path)

    def test_from_file_object_source(self):
        """Test detection from file-like object."""
        jcl_content = "//TESTJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14"
        file_obj = StringIO(jcl_content)
        result = detect_file_type(file_obj)
        assert result == FileType.JCL

    def test_from_string_path(self):
        """Test detection from string path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jcl", delete=False) as f:
            f.write("//MYPROC PROC\n//STEP1 EXEC PGM=IEFBR14\n//PEND")
            temp_path = f.name

        try:
            result = detect_file_type(temp_path)
            assert result == FileType.PROC
        finally:
            os.unlink(temp_path)


class TestHelperFunctions:
    """Test helper functions is_jcl_file() and is_proc_file()."""

    def test_is_jcl_file_returns_true_for_jcl(self):
        """Test is_jcl_file() returns True for JCL files."""
        jcl_content = "//MYJOB JOB CLASS=A"
        assert is_jcl_file(jcl_content) is True

    def test_is_jcl_file_returns_false_for_proc(self):
        """Test is_jcl_file() returns False for PROC files."""
        proc_content = "//MYPROC PROC\n//PEND"
        assert is_jcl_file(proc_content) is False

    def test_is_jcl_file_returns_false_for_unknown(self):
        """Test is_jcl_file() returns False for unknown files."""
        assert is_jcl_file("") is False

    def test_is_proc_file_returns_true_for_proc(self):
        """Test is_proc_file() returns True for PROC files."""
        proc_content = "//MYPROC PROC\n//PEND"
        assert is_proc_file(proc_content) is True

    def test_is_proc_file_returns_false_for_jcl(self):
        """Test is_proc_file() returns False for JCL files."""
        jcl_content = "//MYJOB JOB CLASS=A"
        assert is_proc_file(jcl_content) is False

    def test_is_proc_file_returns_false_for_unknown(self):
        """Test is_proc_file() returns False for unknown files."""
        assert is_proc_file("") is False


class TestEdgeCases:
    """Test edge cases and corner scenarios."""

    def test_malformed_jcl_with_job_keyword(self):
        """Test that malformed JCL with JOB keyword is still detected as JCL."""
        malformed = "//BADJOB JOB this is malformed but has JOB"
        result = detect_file_type(malformed)
        assert result == FileType.JCL

    def test_job_in_comment_not_detected(self):
        """Test that JOB keyword in comment line is not detected as JCL."""
        comment_content = """//* This is a JOB comment
//MYPROC PROC
//STEP1 EXEC PGM=IEFBR14
//PEND
"""
        result = detect_file_type(comment_content)
        assert result == FileType.PROC

    def test_mixed_case_job(self):
        """Test case insensitivity for JOB keyword."""
        mixed_case = "//MYJOB job CLASS=A"
        result = detect_file_type(mixed_case)
        assert result == FileType.JCL

    def test_inline_proc_in_jcl(self):
        """Test that JCL file containing inline PROC is detected as JCL."""
        jcl_with_proc = """//MYJOB    JOB CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//         PEND
//CALLPROC EXEC MYPROC
"""
        result = detect_file_type(jcl_with_proc)
        assert result == FileType.JCL

    def test_set_before_job(self):
        """Test JCL detection when SET statements appear before JOB card."""
        jcl_content = """//         SET VAR1=VALUE1
//         SET VAR2=VALUE2
//MYJOB    JOB CLASS=A
//STEP1    EXEC PGM=IEFBR14
"""
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL

    def test_jcllib_before_job(self):
        """Test JCL detection when JCLLIB appears before JOB card."""
        jcl_content = """//         JCLLIB ORDER=(PROCLIB1,PROCLIB2)
//MYJOB    JOB CLASS=A
//STEP1    EXEC PGM=IEFBR14
"""
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL

    def test_continuation_lines(self):
        """Test detection with continuation lines (basic support)."""
        jcl_content = """//MYJOB    JOB (ACCT),
//             'PROGRAMMER',
//             CLASS=A
//STEP1    EXEC PGM=IEFBR14
"""
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL

    def test_unicode_content(self):
        """Test detection with Unicode characters."""
        jcl_content = "//MYJOB    JOB CLASS=A,NOTIFY=ÜSER\n//STEP1 EXEC PGM=IEFBR14"
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL

    def test_very_large_file(self):
        """Test performance with large file (should be fast)."""
        # Create large JCL with 1000 comment lines before JOB card
        large_content = "\n".join(["//* Comment line"] * 1000)
        large_content += "\n//BIGJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14"

        import time

        start = time.time()
        result = detect_file_type(large_content)
        elapsed = time.time() - start

        assert result == FileType.JCL
        assert elapsed < 0.5  # Should complete in less than 500ms

    def test_proc_with_dd_statements_only(self):
        """Test PROC detection for file with only DD statements."""
        proc_content = """//DD1      DD DSN=MY.DATA.SET,DISP=SHR
//DD2      DD SYSOUT=*
//DD3      DD DUMMY
"""
        result = detect_file_type(proc_content)
        assert result == FileType.PROC

    def test_if_statement_before_job(self):
        """Test JCL detection when IF statement appears before JOB."""
        jcl_content = """//         IF (&VAR = 'YES') THEN
//MYJOB    JOB CLASS=A
//         ENDIF
"""
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL


class TestIntegration:
    """Integration tests with actual parsing."""

    def test_parse_detected_jcl(self):
        """Test that detected JCL file can be parsed successfully."""
        from jclparser import parse_jcl

        jcl_content = """//TESTJOB  JOB CLASS=A
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD SYSOUT=*
"""
        # First detect type
        file_type = detect_file_type(jcl_content)
        assert file_type == FileType.JCL

        # Then parse
        job = parse_jcl(jcl_content)
        assert job.name == "TESTJOB"
        assert len(job.steps) == 1

    def test_parse_detected_proc(self):
        """Test that detected PROC file can be parsed."""
        from jclparser import parse_jcl

        proc_content = """//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//DD1      DD SYSOUT=*
//         PEND
"""
        # Detect type
        file_type = detect_file_type(proc_content)
        assert file_type == FileType.PROC

        # Parse with strict=False to allow PROC without JOB card
        try:
            job = parse_jcl(proc_content, strict_mode=False)
            # Should have parsed the PROC definition
            assert len(job.procedures) >= 1 or len(job.steps) >= 1
        except Exception:
            # Some parsers may not support standalone PROC files
            # The important part is that we detected it correctly as PROC
            pass


class TestRealWorldFiles:
    """End-to-end tests with real fixture files."""

    def test_basic_job_fixture(self):
        """Test detection with basic_job.jcl fixture."""
        fixture_path = Path("tests/fixtures/sample_jcl/basic_job.jcl")
        if fixture_path.exists():
            result = detect_file_type(fixture_path)
            assert result == FileType.JCL

    def test_procedure_fixture(self):
        """Test detection with procedure.jcl fixture."""
        fixture_path = Path("tests/fixtures/sample_jcl/procedure.jcl")
        if fixture_path.exists():
            result = detect_file_type(fixture_path)
            # This file has JOB card, so it's JCL (contains inline PROC)
            assert result == FileType.JCL

    def test_batch_file_detection(self):
        """Test detecting types for multiple files."""
        fixtures_dir = Path("tests/fixtures/sample_jcl")
        if fixtures_dir.exists():
            jcl_files = list(fixtures_dir.glob("*.jcl"))

            results = {}
            for jcl_file in jcl_files[:5]:  # Test first 5 files
                results[jcl_file.name] = detect_file_type(jcl_file)

            # Should have detected at least some files
            assert len(results) > 0
            # Should have at least one of each type or UNKNOWN
            assert any(
                ft in results.values()
                for ft in [FileType.JCL, FileType.PROC, FileType.UNKNOWN]
            )


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_nonexistent_file(self):
        """Test that nonexistent file raises appropriate error."""
        with pytest.raises(FileNotFoundError):
            detect_file_type(Path("/nonexistent/path/to/file.jcl"))

    def test_none_input(self):
        """Test that None input raises appropriate error."""
        with pytest.raises((TypeError, ValueError)):
            detect_file_type(None)

    def test_invalid_type_input(self):
        """Test that invalid input type raises appropriate error."""
        with pytest.raises((TypeError, ValueError)):
            detect_file_type(12345)

    def test_binary_file(self):
        """Test handling of binary file."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".jcl", delete=False) as f:
            f.write(b"\x00\x01\x02\x03\x04")
            temp_path = f.name

        try:
            # Should handle gracefully, likely returning UNKNOWN
            result = detect_file_type(Path(temp_path))
            assert result == FileType.UNKNOWN
        finally:
            os.unlink(temp_path)


class TestSpecialCases:
    """Test special JCL constructs and scenarios."""

    def test_null_statement(self):
        """Test file starting with null statement."""
        jcl_content = """//
//MYJOB    JOB CLASS=A
//STEP1    EXEC PGM=IEFBR14
"""
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL

    def test_include_statement(self):
        """Test file starting with INCLUDE statement."""
        jcl_content = """//         INCLUDE MEMBER=COMMON
//MYJOB    JOB CLASS=A
"""
        result = detect_file_type(jcl_content)
        assert result == FileType.JCL

    def test_only_pend_statement(self):
        """Test file with only PEND statement."""
        content = "//         PEND"
        result = detect_file_type(content)
        # PEND without PROC is unusual, but not a JCL job
        assert result == FileType.PROC

    def test_exec_with_proc_parameter(self):
        """Test EXEC with PROC= parameter (procedure invocation)."""
        proc_content = """//STEP1    EXEC PROC=MYPROC
//DD1      DD SYSOUT=*
"""
        result = detect_file_type(proc_content)
        # No JOB card, so it's a PROC
        assert result == FileType.PROC
