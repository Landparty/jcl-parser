"""
Tests for jclparser.utils module.

Tests the runtime-critical utility functions for JCL syntax handling.
"""

from jclparser.utils import normalize_jcl_line


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
