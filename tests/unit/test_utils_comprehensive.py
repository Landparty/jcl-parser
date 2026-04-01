"""
Comprehensive tests for jclparser.utils module.
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
    calculate_jcl_checksum,
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


class TestSplitJCLParameters:
    """Tests for split_jcl_parameters function"""

    def test_simple_parameters(self):
        """Test splitting simple parameters"""
        result = split_jcl_parameters("PARM1=A,PARM2=B,PARM3=C")
        assert result == ["PARM1=A", "PARM2=B", "PARM3=C"]

    def test_quoted_parameters(self):
        """Test parameters with quoted values"""
        result = split_jcl_parameters("DSN='MY.DATA.SET',DISP=SHR")
        assert result == ["DSN='MY.DATA.SET'", "DISP=SHR"]

    def test_quoted_with_comma(self):
        """Test quoted value containing comma"""
        result = split_jcl_parameters("PARM='VALUE,WITH,COMMAS',OTHER=X")
        assert result == ["PARM='VALUE,WITH,COMMAS'", "OTHER=X"]

    def test_parenthesized_parameters(self):
        """Test parameters with parentheses"""
        result = split_jcl_parameters("DISP=(NEW,CATLG,DELETE),DSN=TEST")
        assert result == ["DISP=(NEW,CATLG,DELETE)", "DSN=TEST"]

    def test_nested_parentheses(self):
        """Test nested parentheses"""
        result = split_jcl_parameters("SPACE=(CYL,(10,5),RLSE),UNIT=SYSDA")
        assert result == ["SPACE=(CYL,(10,5),RLSE)", "UNIT=SYSDA"]

    def test_empty_string(self):
        """Test empty parameter string"""
        result = split_jcl_parameters("")
        assert result == []

    def test_whitespace_only(self):
        """Test whitespace-only string"""
        result = split_jcl_parameters("   ")
        assert result == []

    def test_single_parameter(self):
        """Test single parameter"""
        result = split_jcl_parameters("CLASS=A")
        assert result == ["CLASS=A"]


class TestParseJCLParameter:
    """Tests for parse_jcl_parameter function"""

    def test_simple_key_value(self):
        """Test simple key=value parameter"""
        key, value = parse_jcl_parameter("CLASS=A")
        assert key == "CLASS"
        assert value == "A"

    def test_quoted_value(self):
        """Test quoted value parameter"""
        key, value = parse_jcl_parameter("DSN='MY.DATA.SET'")
        assert key == "DSN"
        assert value == "MY.DATA.SET"

    def test_escaped_quotes(self):
        """Test escaped quotes in value"""
        key, value = parse_jcl_parameter("PARM='IT''S HERE'")
        assert key == "PARM"
        assert value == "IT'S HERE"

    def test_positional_parameter(self):
        """Test positional parameter without ="""
        key, value = parse_jcl_parameter("MYPROC")
        assert key == "_positional"
        assert value == "MYPROC"

    def test_parenthesized_single(self):
        """Test parenthesized single value"""
        key, value = parse_jcl_parameter("UNIT=(SYSDA)")
        assert key == "UNIT"
        assert value == "SYSDA"

    def test_parenthesized_multiple(self):
        """Test parenthesized multiple values"""
        key, value = parse_jcl_parameter("DISP=(NEW,CATLG,DELETE)")
        assert key == "DISP"
        assert isinstance(value, list)
        assert value == ["NEW", "CATLG", "DELETE"]

    def test_with_spaces(self):
        """Test parameter with spaces"""
        key, value = parse_jcl_parameter(" CLASS = A ")
        assert key == "CLASS"
        assert value == "A"


class TestQuoteJCLValue:
    """Tests for quote_jcl_value function"""

    def test_simple_value(self):
        """Test simple value needs no quotes"""
        result = quote_jcl_value("SIMPLE")
        assert result == "SIMPLE"

    def test_value_with_space(self):
        """Test value with space needs quotes"""
        result = quote_jcl_value("WITH SPACE")
        assert result == "'WITH SPACE'"

    def test_value_with_comma(self):
        """Test value with comma needs quotes"""
        result = quote_jcl_value("A,B,C")
        assert result == "'A,B,C'"

    def test_value_with_parens(self):
        """Test value with parentheses needs quotes"""
        result = quote_jcl_value("(VALUE)")
        assert result == "'(VALUE)'"

    def test_value_with_equals(self):
        """Test value with equals needs quotes"""
        result = quote_jcl_value("A=B")
        assert result == "'A=B'"

    def test_value_with_quotes(self):
        """Test value with quotes gets escaped"""
        result = quote_jcl_value("IT'S")
        assert result == "'IT''S'"


class TestUnquoteJCLValue:
    """Tests for unquote_jcl_value function"""

    def test_quoted_value(self):
        """Test unquoting quoted value"""
        result = unquote_jcl_value("'MY.DATA.SET'")
        assert result == "MY.DATA.SET"

    def test_escaped_quotes(self):
        """Test unescaping quotes"""
        result = unquote_jcl_value("'IT''S HERE'")
        assert result == "IT'S HERE"

    def test_unquoted_value(self):
        """Test already unquoted value"""
        result = unquote_jcl_value("SIMPLE")
        assert result == "SIMPLE"

    def test_empty_quotes(self):
        """Test empty quoted string"""
        result = unquote_jcl_value("''")
        assert result == ""


class TestValidateJCLName:
    """Tests for validate_jcl_name function"""

    def test_valid_simple(self):
        """Test valid simple name"""
        assert validate_jcl_name("JOBNAME")

    def test_valid_with_numbers(self):
        """Test valid name with numbers"""
        assert validate_jcl_name("JOB123")

    def test_valid_with_specials(self):
        """Test valid name with special characters"""
        assert validate_jcl_name("JOB@#$")

    def test_start_with_at(self):
        """Test name starting with @"""
        assert validate_jcl_name("@JOBNAME")

    def test_start_with_hash(self):
        """Test name starting with #"""
        assert validate_jcl_name("#JOBNAME")

    def test_start_with_dollar(self):
        """Test name starting with $"""
        assert validate_jcl_name("$JOBNAME")

    def test_too_long(self):
        """Test name too long"""
        assert not validate_jcl_name("VERYLONGNAME")

    def test_start_with_number(self):
        """Test invalid name starting with number"""
        assert not validate_jcl_name("1JOBNAME")

    def test_empty_name(self):
        """Test empty name"""
        assert not validate_jcl_name("")

    def test_custom_max_length(self):
        """Test custom max length"""
        assert validate_jcl_name("VERYLONGNAME", max_length=20)
        assert not validate_jcl_name("VERYLONGNAME", max_length=5)


class TestFormatJCLLine:
    """Tests for format_jcl_line function"""

    def test_simple_statement(self):
        """Test simple statement formatting"""
        result = format_jcl_line("JOB", "MYJOB", {"CLASS": "A"})
        assert len(result) == 1
        assert "//MYJOB JOB" in result[0]
        assert "CLASS=A" in result[0]

    def test_no_parameters(self):
        """Test statement with no parameters"""
        result = format_jcl_line("PEND", "MYPROC", {})
        assert len(result) == 1
        assert result[0] == "//MYPROC PEND"

    def test_positional_parameter(self):
        """Test positional parameter"""
        result = format_jcl_line("JOB", "MYJOB", {"_positional_0": "(ACCT)"})
        assert len(result) == 1
        assert "(ACCT)" in result[0]

    def test_list_value(self):
        """Test list value parameter"""
        result = format_jcl_line("DD", "MYDD", {"DISP": ["NEW", "CATLG"]})
        assert len(result) == 1
        assert "DISP=(NEW,CATLG)" in result[0]

    def test_long_line_continuation(self):
        """Test long line gets continued"""
        long_params = {f"PARM{i}": f"VALUE{i}" for i in range(10)}
        result = format_jcl_line("EXEC", "STEP", long_params, max_line_length=40)
        assert len(result) > 1
        for line in result:
            assert len(line) <= 40 or line == result[0]  # First line may exceed


class TestExtractInlineData:
    """Tests for extract_inline_data function"""

    def test_extract_simple_data(self):
        """Test extracting simple inline data"""
        lines = ["//DD1 DD *", "DATA LINE 1", "DATA LINE 2", "/*"]
        data, end_idx = extract_inline_data(lines, 0)
        assert data == "DATA LINE 1\nDATA LINE 2"
        assert end_idx == 3

    def test_no_end_marker(self):
        """Test data without end marker"""
        lines = ["//DD1 DD *", "DATA LINE 1", "DATA LINE 2"]
        data, end_idx = extract_inline_data(lines, 0)
        assert data == "DATA LINE 1\nDATA LINE 2"
        assert end_idx == 2

    def test_empty_inline_data(self):
        """Test empty inline data"""
        lines = ["//DD1 DD *", "/*"]
        data, end_idx = extract_inline_data(lines, 0)
        assert data == ""
        assert end_idx == 1

    def test_out_of_bounds(self):
        """Test start index out of bounds"""
        lines = ["//DD1 DD *"]
        data, end_idx = extract_inline_data(lines, 5)
        assert data is None
        assert end_idx == 5


class TestMergeContinuationLines:
    """Tests for merge_continuation_lines function"""

    def test_no_continuations(self):
        """Test lines without continuations"""
        lines = ["//JOBNAME JOB CLASS=A", "//STEP1 EXEC PGM=PROG"]
        result = merge_continuation_lines(lines)
        assert len(result) == 2

    def test_simple_continuation(self):
        """Test simple continuation"""
        lines = ["//JOBNAME JOB CLASS=A,", "//  MSGCLASS=X"]
        result = merge_continuation_lines(lines)
        assert len(result) == 1
        assert "CLASS=A" in result[0]
        assert "MSGCLASS=X" in result[0]

    def test_multiple_continuations(self):
        """Test multiple continuation lines"""
        lines = ["//JOBNAME JOB CLASS=A,", "//  MSGCLASS=X,", "//  NOTIFY=USER"]
        result = merge_continuation_lines(lines)
        assert len(result) == 1

    def test_preserve_comments(self):
        """Test comment preservation"""
        lines = ["//* This is a comment", "//JOBNAME JOB CLASS=A"]
        result = merge_continuation_lines(lines)
        assert len(result) == 2
        assert result[0].startswith("//*")

    def test_preserve_empty_lines(self):
        """Test empty line preservation"""
        lines = ["//JOBNAME JOB CLASS=A", "", "//STEP1 EXEC PGM=PROG"]
        result = merge_continuation_lines(lines)
        assert len(result) == 3


class TestCalculateJCLChecksum:
    """Tests for calculate_jcl_checksum function"""

    def test_simple_checksum(self):
        """Test checksum calculation"""
        jcl = "//JOBNAME JOB CLASS=A"
        result = calculate_jcl_checksum(jcl)
        assert len(result) == 32  # MD5 hex length
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_checksum(self):
        """Test same content produces same checksum"""
        jcl = "//JOBNAME JOB CLASS=A"
        result1 = calculate_jcl_checksum(jcl)
        result2 = calculate_jcl_checksum(jcl)
        assert result1 == result2

    def test_different_content_different_checksum(self):
        """Test different content produces different checksum"""
        jcl1 = "//JOBNAME JOB CLASS=A"
        jcl2 = "//JOBNAME JOB CLASS=B"
        result1 = calculate_jcl_checksum(jcl1)
        result2 = calculate_jcl_checksum(jcl2)
        assert result1 != result2

    def test_whitespace_normalized(self):
        """Test whitespace normalization"""
        jcl1 = "//JOBNAME JOB CLASS=A"
        jcl2 = "//JOBNAME JOB CLASS=A   "
        result1 = calculate_jcl_checksum(jcl1)
        result2 = calculate_jcl_checksum(jcl2)
        assert result1 == result2
