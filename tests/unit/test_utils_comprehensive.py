"""
Comprehensive tests for jclparser.utils module.
"""

from jclparser.utils import (
    normalize_jcl_line,
    is_continuation_line,
)


class TestNormalizeJCLLine:
    """Tests for normalize_jcl_line function"""

    def test_remove_trailing_whitespace(self):
        """Test removal of trailing whitespace"""
        result = normalize_jcl_line("//JOBNAME JOB   ")
        assert result == "//JOBNAME JOB"

    def test_preserve_leading_whitespace(self):
        """Test preservation of leading whitespace"""
        result = normalize_jcl_line("  //COMMENT")
        assert result == "  //COMMENT"

    def test_convert_tabs(self):
        """Test tab to space conversion"""
        result = normalize_jcl_line("//JOB\tNAME\tJOB")
        assert "\t" not in result
        # expandtabs(4) converts tabs to 4 spaces
        assert result == "//JOB   NAME    JOB"

    def test_empty_line(self):
        """Test empty line handling"""
        result = normalize_jcl_line("")
        assert result == ""


class TestIsContinuationLine:
    """Tests for is_continuation_line function"""

    def test_valid_continuation(self):
        """Test valid continuation line detection"""
        assert is_continuation_line("//  PARM=VALUE")

    def test_regular_statement(self):
        """Test regular statement is not continuation"""
        assert not is_continuation_line("//STEPNAME EXEC PGM=PROG")

    def test_comment_line(self):
        """Test comment line is not continuation"""
        assert not is_continuation_line("//* This is a comment")

    def test_empty_line(self):
        """Test empty line is not continuation"""
        assert not is_continuation_line("")

    def test_with_leading_spaces(self):
        """Test continuation with leading spaces"""
        assert is_continuation_line("   //  PARM=VALUE")
