"""
Tests for jclparser.utils module.

Tests the runtime-critical utility functions for JCL syntax handling.
"""

from jclparser.utils import (
    normalize_jcl_line,
    is_continuation_line,
)


class TestNormalizeJCLLine:
    """Test normalize_jcl_line function."""

    def test_removes_trailing_whitespace(self):
        """Test that trailing whitespace is removed."""
        line = "//MYJOB JOB   "
        result = normalize_jcl_line(line)
        assert result == "//MYJOB JOB"

    def test_preserves_leading_whitespace(self):
        """Test that leading whitespace is preserved."""
        line = "   //STEP EXEC PGM=TEST"
        result = normalize_jcl_line(line)
        assert result.startswith("   //")

    def test_converts_tabs_to_spaces(self):
        """Test that tabs are converted to spaces."""
        line = "//MYJOB\tJOB"
        result = normalize_jcl_line(line)
        assert "\t" not in result

    def test_empty_line(self):
        """Test empty line handling."""
        result = normalize_jcl_line("")
        assert result == ""


class TestIsContinuationLine:
    """Test is_continuation_line function."""

    def test_valid_continuation_line(self):
        """Test valid continuation line detection."""
        line = "//  PARM='VALUE'"
        assert is_continuation_line(line)

    def test_not_continuation_regular_statement(self):
        """Test regular statement is not detected as continuation."""
        line = "//STEP1 EXEC PGM=IEBGENER"
        assert not is_continuation_line(line)

    def test_not_continuation_comment(self):
        """Test comment line is not detected as continuation."""
        line = "//* This is a comment"
        assert not is_continuation_line(line)

    def test_continuation_with_leading_spaces(self):
        """Test continuation with leading spaces."""
        line = "   //  DISP=SHR"
        assert is_continuation_line(line)
