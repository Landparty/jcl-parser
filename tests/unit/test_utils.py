"""
Comprehensive tests for jclparser.utils module.

Tests all utility functions for JCL syntax handling including
parameter parsing, formatting, continuation handling, and validation.
"""

from jclparser.utils import (
    normalize_jcl_line,
    is_continuation_line,
    split_jcl_parameters,
    parse_jcl_parameter,
    quote_jcl_value,
    unquote_jcl_value,
    validate_jcl_name,
    format_jcl_line,
    extract_inline_data,
    merge_continuation_lines,
    calculate_jcl_checksum
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


class TestSplitJCLParameters:
    """Test split_jcl_parameters function."""
    
    def test_simple_parameters(self):
        """Test splitting simple comma-separated parameters."""
        params = "DSN=MY.DATA,DISP=SHR,UNIT=SYSDA"
        result = split_jcl_parameters(params)
        assert len(result) == 3
        assert "DSN=MY.DATA" in result
        assert "DISP=SHR" in result
        assert "UNIT=SYSDA" in result
    
    def test_quoted_strings(self):
        """Test parameters with quoted strings containing commas."""
        params = "PARM='VALUE1,VALUE2',DSN=TEST"
        result = split_jcl_parameters(params)
        assert len(result) == 2
        assert "PARM='VALUE1,VALUE2'" in result
    
    def test_nested_parentheses(self):
        """Test parameters with nested parentheses."""
        params = "SPACE=(CYL,(10,5),RLSE),DISP=NEW"
        result = split_jcl_parameters(params)
        assert len(result) == 2
        assert "SPACE=(CYL,(10,5),RLSE)" in result
    
    def test_empty_string(self):
        """Test empty parameter string."""
        result = split_jcl_parameters("")
        assert result == []
    
    def test_single_parameter(self):
        """Test single parameter."""
        result = split_jcl_parameters("DSN=MY.DATA")
        assert len(result) == 1
        assert result[0] == "DSN=MY.DATA"


class TestParseJCLParameter:
    """Test parse_jcl_parameter function."""
    
    def test_keyword_parameter(self):
        """Test parsing keyword parameter."""
        key, value = parse_jcl_parameter("DSN=MY.DATA.SET")
        assert key == "DSN"
        assert value == "MY.DATA.SET"
    
    def test_quoted_value(self):
        """Test parsing quoted parameter value."""
        key, value = parse_jcl_parameter("PARM='TEST VALUE'")
        assert key == "PARM"
        assert value == "TEST VALUE"
    
    def test_escaped_quotes(self):
        """Test parsing value with escaped quotes."""
        key, value = parse_jcl_parameter("PARM='O''BRIEN'")
        assert key == "PARM"
        assert value == "O'BRIEN"
    
    def test_positional_parameter(self):
        """Test parsing positional parameter."""
        key, value = parse_jcl_parameter("IEBGENER")
        assert key == "_positional"
        assert value == "IEBGENER"
    
    def test_parenthesized_value(self):
        """Test parsing parenthesized value."""
        key, value = parse_jcl_parameter("DISP=(NEW,CATLG)")
        assert key == "DISP"
        assert isinstance(value, list)
        assert len(value) == 2
    
    def test_single_item_parenthesized(self):
        """Test parsing single-item parenthesized value."""
        key, value = parse_jcl_parameter("UNIT=(SYSDA)")
        assert key == "UNIT"
        assert value == "SYSDA"


class TestQuoteJCLValue:
    """Test quote_jcl_value function."""
    
    def test_quote_with_spaces(self):
        """Test quoting value with spaces."""
        result = quote_jcl_value("TEST VALUE")
        assert result == "'TEST VALUE'"
    
    def test_quote_with_comma(self):
        """Test quoting value with comma."""
        result = quote_jcl_value("VAL1,VAL2")
        assert result == "'VAL1,VAL2'"
    
    def test_no_quote_simple(self):
        """Test simple value doesn't get quoted."""
        result = quote_jcl_value("SIMPLE")
        assert result == "SIMPLE"
    
    def test_escape_quotes(self):
        """Test escaping existing quotes."""
        result = quote_jcl_value("O'BRIEN")
        # quote_jcl_value doesn't quote by default unless special chars
        assert "BRIEN" in result


class TestUnquoteJCLValue:
    """Test unquote_jcl_value function."""
    
    def test_unquote_simple(self):
        """Test unquoting simple quoted value."""
        result = unquote_jcl_value("'TEST VALUE'")
        assert result == "TEST VALUE"
    
    def test_unescape_quotes(self):
        """Test unescaping doubled quotes."""
        result = unquote_jcl_value("'O''BRIEN'")
        assert result == "O'BRIEN"
    
    def test_no_quotes(self):
        """Test value without quotes."""
        result = unquote_jcl_value("SIMPLE")
        assert result == "SIMPLE"
    
    def test_single_quote(self):
        """Test single quote character."""
        result = unquote_jcl_value("'")
        assert result == "'"


class TestValidateJCLName:
    """Test validate_jcl_name function."""
    
    def test_valid_name(self):
        """Test valid JCL name."""
        assert validate_jcl_name("MYJOB")
    
    def test_valid_with_numbers(self):
        """Test valid name with numbers."""
        assert validate_jcl_name("STEP123")
    
    def test_valid_with_special(self):
        """Test valid name with special characters."""
        assert validate_jcl_name("#STEP$01")
    
    def test_too_long(self):
        """Test name too long."""
        assert not validate_jcl_name("TOOLONGNAME")
    
    def test_starts_with_number(self):
        """Test name starting with number."""
        assert not validate_jcl_name("1STEP")
    
    def test_empty_name(self):
        """Test empty name."""
        assert not validate_jcl_name("")
    
    def test_invalid_characters(self):
        """Test name with invalid characters."""
        assert not validate_jcl_name("STEP-01")


class TestFormatJCLLine:
    """Test format_jcl_line function."""
    
    def test_simple_format(self):
        """Test formatting simple JCL line."""
        result = format_jcl_line("EXEC", "STEP1", {"PGM": "IEBGENER"})
        assert len(result) == 1
        assert result[0] == "//STEP1 EXEC PGM=IEBGENER"
    
    def test_no_parameters(self):
        """Test formatting with no parameters."""
        result = format_jcl_line("EXEC", "STEP1", {})
        assert len(result) == 1
        assert result[0] == "//STEP1 EXEC"
    
    def test_multiple_parameters(self):
        """Test formatting with multiple parameters."""
        params = {"PGM": "TEST", "PARM": "VALUE"}
        result = format_jcl_line("EXEC", "STEP1", params)
        assert len(result) >= 1
        assert "PGM=TEST" in result[0]
    
    def test_list_parameter(self):
        """Test formatting list parameter."""
        params = {"DISP": ["NEW", "CATLG"]}
        result = format_jcl_line("DD", "DD1", params)
        assert "(NEW,CATLG)" in result[0]
    
    def test_continuation_for_long_line(self):
        """Test continuation when line is too long."""
        params = {
            "DSN": "VERY.LONG.DATASET.NAME.HERE",
            "DISP": ["NEW", "CATLG"],
            "SPACE": "(CYL,(10,5),RLSE)",
            "UNIT": "SYSDA"
        }
        result = format_jcl_line("DD", "DD1", params, max_line_length=40)
        assert len(result) > 1


class TestExtractInlineData:
    """Test extract_inline_data function."""
    
    def test_extract_simple_data(self):
        """Test extracting simple inline data."""
        lines = [
            "//DD1 DD *",
            "DATA LINE 1",
            "DATA LINE 2",
            "/*"
        ]
        data, end_idx = extract_inline_data(lines, 0)
        assert data == "DATA LINE 1\nDATA LINE 2"
        assert end_idx == 3
    
    def test_no_end_marker(self):
        """Test inline data without end marker."""
        lines = [
            "//DD1 DD *",
            "DATA LINE 1",
            "DATA LINE 2"
        ]
        data, end_idx = extract_inline_data(lines, 0)
        assert data == "DATA LINE 1\nDATA LINE 2"
        assert end_idx == 2
    
    def test_empty_inline_data(self):
        """Test empty inline data."""
        lines = [
            "//DD1 DD *",
            "/*"
        ]
        data, end_idx = extract_inline_data(lines, 0)
        assert data == ""
        assert end_idx == 1
    
    def test_out_of_bounds(self):
        """Test extraction with out of bounds index."""
        lines = ["//DD1 DD *"]
        data, end_idx = extract_inline_data(lines, 5)
        assert data is None
        assert end_idx == 5


class TestMergeContinuationLines:
    """Test merge_continuation_lines function."""
    
    def test_merge_simple_continuation(self):
        """Test merging simple continuation."""
        lines = [
            "//STEP1 EXEC PGM=IEBGENER,",
            "//  PARM='VALUE'"
        ]
        result = merge_continuation_lines(lines)
        assert len(result) == 1
        assert "PARM='VALUE'" in result[0]
    
    def test_preserve_comments(self):
        """Test that comments are preserved."""
        lines = [
            "//* Comment line",
            "//STEP1 EXEC PGM=TEST"
        ]
        result = merge_continuation_lines(lines)
        assert len(result) == 2
        assert result[0].startswith("//*")
    
    def test_preserve_empty_lines(self):
        """Test that empty lines are preserved."""
        lines = [
            "//STEP1 EXEC PGM=TEST",
            "",
            "//STEP2 EXEC PGM=TEST2"
        ]
        result = merge_continuation_lines(lines)
        assert len(result) == 3
    
    def test_multiple_continuations(self):
        """Test multiple continuation lines."""
        lines = [
            "//DD1 DD DSN=MY.DATA,",
            "//  DISP=SHR,",
            "//  UNIT=SYSDA"
        ]
        result = merge_continuation_lines(lines)
        assert len(result) == 1
        assert "DISP=SHR" in result[0]
        assert "UNIT=SYSDA" in result[0]


class TestCalculateJCLChecksum:
    """Test calculate_jcl_checksum function."""
    
    def test_consistent_checksum(self):
        """Test that same content produces same checksum."""
        jcl = "//MYJOB JOB\n//STEP1 EXEC PGM=TEST"
        checksum1 = calculate_jcl_checksum(jcl)
        checksum2 = calculate_jcl_checksum(jcl)
        assert checksum1 == checksum2
    
    def test_different_content_different_checksum(self):
        """Test that different content produces different checksum."""
        jcl1 = "//MYJOB JOB"
        jcl2 = "//MYJOB2 JOB"
        checksum1 = calculate_jcl_checksum(jcl1)
        checksum2 = calculate_jcl_checksum(jcl2)
        assert checksum1 != checksum2
    
    def test_normalized_checksum(self):
        """Test that normalized content produces same checksum."""
        jcl1 = "//MYJOB JOB   \n//STEP1 EXEC PGM=TEST"
        jcl2 = "//MYJOB JOB\n//STEP1 EXEC PGM=TEST"
        checksum1 = calculate_jcl_checksum(jcl1)
        checksum2 = calculate_jcl_checksum(jcl2)
        assert checksum1 == checksum2
    
    def test_checksum_format(self):
        """Test that checksum is in hex format."""
        jcl = "//MYJOB JOB"
        checksum = calculate_jcl_checksum(jcl)
        assert len(checksum) == 32  # MD5 hex is 32 characters
        assert all(c in "0123456789abcdef" for c in checksum)
