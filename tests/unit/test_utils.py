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


class TestRestoredParameterHelpers:
    """Lock in helpers that referenced module constants dropped by a refactor.

    Before the constants/imports were restored these functions raised
    NameError as soon as they were called.
    """

    def test_split_jcl_parameters(self):
        from jclparser.utils import split_jcl_parameters

        assert split_jcl_parameters("DSN=A.B,DISP=(NEW,CATLG)") == [
            "DSN=A.B",
            "DISP=(NEW,CATLG)",
        ]
        assert split_jcl_parameters("") == []

    def test_parse_jcl_parameter(self):
        from jclparser.utils import parse_jcl_parameter

        assert parse_jcl_parameter("CLASS=A") == ("CLASS", "A")
        name, value = parse_jcl_parameter("POSITIONAL")
        assert value == "POSITIONAL"

    def test_quote_jcl_value_quotes_special_chars(self):
        from jclparser.utils import quote_jcl_value

        # Contains a space -> must be quoted (uses _RE_SPECIAL_CHARS).
        assert quote_jcl_value("A B") == "'A B'"
        # Plain token -> unchanged.
        assert quote_jcl_value("ABC") == "ABC"

    def test_validate_jcl_name(self):
        from jclparser.utils import validate_jcl_name

        # Exercises _RE_JCL_NAME_START / _RE_JCL_NAME_FULL.
        assert validate_jcl_name("STEP1") is True
        assert validate_jcl_name("1STEP") is False
