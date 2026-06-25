"""
Comprehensive tests for jclparser.utils module.
"""

from jclparser.utils import normalize_jcl_line


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
