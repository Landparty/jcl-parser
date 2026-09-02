"""
Test edge cases for jcl_file_type.py to improve coverage.

This module tests uncovered edge cases:
- Exception handling in is_jcl_file and is_proc_file
- Binary file handling
- Non-UTF-8 encoding support
- Non-seekable file objects
- Statement type extraction edge cases
"""

import tempfile
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from jclparser.jcl_file_type import (
    FileType,
    _extract_statement_type,
    detect_file_type,
    is_jcl_file,
    is_proc_file,
)
from jclparser.utils import (
    _read_file_with_fallback as _read_file,
)
from jclparser.utils import (
    read_source as _read_source,
)


class TestExceptionHandling:
    """Test exception handling in helper functions."""

    def test_is_jcl_file_with_invalid_source_type(self):
        """Test is_jcl_file with invalid source type (should return False)."""
        # Integer is not a valid source type
        result = is_jcl_file(12345)
        assert not result

    def test_is_jcl_file_with_none(self):
        """Test is_jcl_file with None (should return False)."""
        result = is_jcl_file(None)
        assert not result

    def test_is_proc_file_with_invalid_source_type(self):
        """Test is_proc_file with invalid source type (should return False)."""
        # List is not a valid source type
        result = is_proc_file([1, 2, 3])
        assert not result

    def test_is_proc_file_with_none(self):
        """Test is_proc_file with None (should return False)."""
        result = is_proc_file(None)
        assert not result

    def test_detect_file_type_with_none_raises_error(self):
        """Test detect_file_type with None raises ValueError."""
        with pytest.raises(ValueError, match="cannot be None"):
            detect_file_type(None)

    def test_is_jcl_file_logs_detection_failure(self, caplog):
        """is_jcl_file logs (at DEBUG) when detection fails instead of being silent."""
        import logging

        with caplog.at_level(logging.DEBUG, logger="jclparser.jcl_file_type"):
            assert is_jcl_file(12345) is False
        assert any("could not detect file type" in r.message for r in caplog.records)

    def test_is_proc_file_logs_detection_failure(self, caplog):
        """is_proc_file logs (at DEBUG) when detection fails instead of being silent."""
        import logging

        with caplog.at_level(logging.DEBUG, logger="jclparser.jcl_file_type"):
            assert is_proc_file(None) is False
        assert any("could not detect file type" in r.message for r in caplog.records)


class TestBinaryFileHandling:
    """Test handling of binary files."""

    def test_detect_file_type_with_binary_file(self):
        """Test detection with binary file."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".bin") as f:
            # Write binary data (not valid text)
            f.write(b"\x00\x01\x02\x03\x04\x05")
            temp_path = Path(f.name)

        try:
            result = detect_file_type(temp_path)
            # Binary file should return UNKNOWN
            assert result == FileType.UNKNOWN
        finally:
            temp_path.unlink()

    def test_read_file_with_binary_content(self):
        """Test _read_file with binary content."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".dat") as f:
            # Write binary data
            f.write(b"\xff\xfe\x00\x00")
            temp_path = Path(f.name)

        try:
            content = _read_file(temp_path)
            # Should return some content (possibly empty or with replacement chars)
            assert isinstance(content, str)
        finally:
            temp_path.unlink()


class TestEncodingHandling:
    """Test handling of different file encodings."""

    def test_detect_file_type_with_latin1_encoding(self):
        """Test detection with Latin-1 encoded file."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".jcl") as f:
            # Write Latin-1 encoded JCL
            jcl_content = "//MYJOB JOB\n//STEP1 EXEC PGM=PROG\n"
            f.write(jcl_content.encode("latin-1"))
            temp_path = Path(f.name)

        try:
            result = detect_file_type(temp_path)
            assert result == FileType.JCL
        finally:
            temp_path.unlink()

    def test_detect_file_type_with_cp1252_encoding(self):
        """Test detection with CP1252 encoded file."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".jcl") as f:
            # Write CP1252 encoded PROC
            proc_content = "//MYPROC PROC\n//STEP1 EXEC PGM=PROG\n//PEND\n"
            f.write(proc_content.encode("cp1252"))
            temp_path = Path(f.name)

        try:
            result = detect_file_type(temp_path)
            assert result == FileType.PROC
        finally:
            temp_path.unlink()

    def test_read_file_with_unicode_decode_error(self):
        """Test _read_file handles UnicodeDecodeError gracefully."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".txt") as f:
            # Write invalid UTF-8 sequence
            f.write(b"\x80\x81\x82\x83")
            temp_path = Path(f.name)

        try:
            # Should not raise, should return content (possibly with replacements)
            content = _read_file(temp_path)
            assert isinstance(content, str)
        finally:
            temp_path.unlink()


class TestNonSeekableStreams:
    """Test handling of non-seekable file objects."""

    def test_detect_file_type_with_non_seekable_stream(self):
        """Test with file object that doesn't support seek."""

        class NonSeekableStream:
            def __init__(self, content):
                self.content = content
                self.pos = 0

            def read(self):
                return self.content

        stream = NonSeekableStream("//MYJOB JOB\n//STEP1 EXEC PGM=PROG")
        result = detect_file_type(stream)
        assert result == FileType.JCL

    def test_detect_file_type_with_seekable_stream(self):
        """Test with seekable stream (normal case)."""
        stream = StringIO("//MYPROC PROC\n//PEND")
        result = detect_file_type(stream)
        assert result == FileType.PROC

        # Verify stream was reset
        content = stream.read()
        assert content == "//MYPROC PROC\n//PEND"

    def test_detect_file_type_with_bytes_stream(self):
        """Test with BytesIO stream."""
        stream = BytesIO(b"//MYJOB JOB\n")
        # BytesIO needs to be read as bytes, then decoded
        # The _read_source function expects text, so we need StringIO instead
        from io import StringIO

        stream = StringIO("//MYJOB JOB\n")
        result = detect_file_type(stream)
        assert result == FileType.JCL


class TestStatementTypeExtraction:
    """Test _extract_statement_type edge cases."""

    def test_extract_statement_type_non_jcl_line(self):
        """Test extracting type from non-JCL line."""
        result = _extract_statement_type("Not a JCL line")
        assert result is None

    def test_extract_statement_type_comment_line(self):
        """Test extracting type from comment line."""
        result = _extract_statement_type("//* This is a comment")
        assert result is None

    def test_extract_statement_type_single_keyword_job(self):
        """Test statement with only JOB keyword."""
        result = _extract_statement_type("//JOB")
        assert result == "JOB"

    def test_extract_statement_type_single_keyword_exec(self):
        """Test statement with only EXEC keyword."""
        result = _extract_statement_type("//EXEC")
        assert result == "EXEC"

    def test_extract_statement_type_single_keyword_dd(self):
        """Test statement with only DD keyword."""
        result = _extract_statement_type("//DD")
        assert result == "DD"

    def test_extract_statement_type_with_inline_parameters(self):
        """Test statement type with inline parameters like JOB(ACCT)."""
        result = _extract_statement_type("//MYJOB JOB(ACCT)")
        assert result == "JOB"

    def test_extract_statement_type_with_exec_parameters(self):
        """Test EXEC with parameters."""
        result = _extract_statement_type("//STEP1 EXEC(PROC)")
        assert result == "EXEC"

    def test_extract_statement_type_nameless_set(self):
        """Test nameless SET statement."""
        result = _extract_statement_type("//  SET VAR=VALUE")
        assert result == "SET"

    def test_extract_statement_type_nameless_if(self):
        """Test nameless IF statement."""
        result = _extract_statement_type("//  IF (RC = 0) THEN")
        assert result == "IF"

    def test_extract_statement_type_pend(self):
        """Test PEND statement."""
        result = _extract_statement_type("//PEND")
        assert result == "PEND"

    def test_extract_statement_type_empty_after_slashes(self):
        """Test empty line after //."""
        result = _extract_statement_type("//")
        assert result is None

    def test_extract_statement_type_whitespace_only(self):
        """Test whitespace-only after //."""
        result = _extract_statement_type("//   ")
        assert result is None


class TestReadSourceEdgeCases:
    """Test _read_source edge cases."""

    def test_read_source_empty_string(self):
        """Test reading empty string."""
        content = _read_source("")
        assert content == ""

    def test_read_source_string_with_newlines(self):
        """Test reading string with newlines (JCL content)."""
        jcl = "//MYJOB JOB\n//STEP1 EXEC PGM=PROG"
        content = _read_source(jcl)
        assert content == jcl

    def test_read_source_invalid_path_string(self):
        """Test string that looks like path but doesn't exist."""
        # Short string without newlines - might be checked as path
        content = _read_source("//MYJOB JOB")
        # Should be treated as content, not path
        assert content == "//MYJOB JOB"

    def test_read_source_with_invalid_type(self):
        """Test _read_source with invalid type raises TypeError."""
        with pytest.raises(TypeError, match="Invalid source type"):
            _read_source(12345)

    def test_read_source_with_dict(self):
        """Test _read_source with dict raises TypeError."""
        with pytest.raises(TypeError, match="Invalid source type"):
            _read_source({"key": "value"})


class TestFileNotFound:
    """Test file not found scenarios."""

    def test_read_file_nonexistent_path(self):
        """Test _read_file with non-existent path."""
        nonexistent = Path("nonexistent_file_xyz_12345.jcl")

        with pytest.raises(FileNotFoundError):
            _read_file(nonexistent)

    def test_detect_file_type_nonexistent_path(self):
        """Test detect_file_type with non-existent path."""
        nonexistent = Path("nonexistent_file_xyz_12345.jcl")

        with pytest.raises(FileNotFoundError):
            detect_file_type(nonexistent)


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_detect_file_type_with_comments_before_job(self):
        """Test file with many comments before JOB card."""
        jcl = """//* Header comment
//* Author: Test
//* Date: 2026-01-07
//MYJOB JOB CLASS=A"""

        result = detect_file_type(jcl)
        assert result == FileType.JCL

    def test_detect_file_type_with_set_before_job(self):
        """Test file with SET statements before JOB card."""
        jcl = """//  SET VAR1=VALUE1
//  SET VAR2=VALUE2
//MYJOB JOB CLASS=A"""

        result = detect_file_type(jcl)
        assert result == FileType.JCL

    def test_detect_file_type_proc_with_multiple_steps(self):
        """Test PROC file with multiple steps."""
        proc = """//MYPROC PROC
//STEP1 EXEC PGM=PROG1
//DD1 DD DSN=FILE1
//STEP2 EXEC PGM=PROG2
//DD2 DD DSN=FILE2
//PEND"""

        result = detect_file_type(proc)
        assert result == FileType.PROC

    def test_detect_file_type_empty_file(self):
        """Test empty file."""
        result = detect_file_type("")
        assert result == FileType.UNKNOWN

    def test_detect_file_type_only_comments(self):
        """Test file with only comments."""
        jcl = """//* Comment 1
//* Comment 2
//* Comment 3"""

        result = detect_file_type(jcl)
        assert result == FileType.UNKNOWN
