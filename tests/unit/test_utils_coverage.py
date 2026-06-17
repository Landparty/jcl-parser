"""
Coverage-focused tests for the deprecated/compatibility helpers in
``jclparser.utils``.

These functions are no longer on the main parse path (they were superseded
by ``parameter_ast``, ``continuation_handler`` and the core parser) but remain
part of the module's public surface, so their behaviour is pinned here.
"""

import hashlib

from pathlib import Path

import pytest

from jclparser.utils import (
    calculate_jcl_checksum,
    extract_inline_data,
    format_jcl_line,
    merge_continuation_lines,
    parse_jcl_parameter,
    quote_jcl_value,
    read_source,
    unquote_jcl_value,
    validate_jcl_name,
)


class TestReadSource:
    """Tests for read_source path/string/file-like resolution."""

    def test_path_object_reads_file(self, tmp_path: Path):
        f = tmp_path / "job.jcl"
        f.write_text("//J JOB\n")
        assert read_source(f) == "//J JOB\n"

    def test_path_object_missing_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_source(tmp_path / "nope.jcl")

    def test_string_with_jcl_extension_reads_file(self, tmp_path: Path):
        f = tmp_path / "job.jcl"
        f.write_text("//J JOB\n")
        assert read_source(str(f)) == "//J JOB\n"

    def test_plain_string_naming_existing_file_is_read(self, tmp_path: Path):
        # No extension and no separator in the name, but it exists on disk.
        f = tmp_path / "PROCMEMB"
        f.write_text("//STEP EXEC PGM=X\n")
        # Pass just the file name while cwd is tmp_path so there is no separator.
        import os

        old = os.getcwd()
        try:
            os.chdir(tmp_path)
            assert read_source("PROCMEMB") == "//STEP EXEC PGM=X\n"
        finally:
            os.chdir(old)

    def test_plain_jcl_content_returned_as_is(self):
        content = "//J JOB\n//S EXEC PGM=X\n"
        assert read_source(content) == content

    def test_file_like_object(self):
        import io

        stream = io.StringIO("//J JOB\n")
        assert read_source(stream) == "//J JOB\n"
        # seek(0) is best-effort; the stream should be rewound for reuse.
        assert stream.tell() == 0

    def test_invalid_source_type_raises(self):
        with pytest.raises(TypeError):
            read_source(12345)


class TestParseJclParameter:
    """Tests for the deprecated parse_jcl_parameter helper."""

    def test_positional(self):
        assert parse_jcl_parameter("PROG") == ("_positional", "PROG")

    def test_keyword(self):
        assert parse_jcl_parameter("CLASS=A") == ("CLASS", "A")

    def test_quoted_value_with_escaped_quotes(self):
        key, value = parse_jcl_parameter("PARM='IT''S'")
        assert key == "PARM"
        assert value == "IT'S"

    def test_parenthesized_single_subparam(self):
        key, value = parse_jcl_parameter("UNIT=(SYSDA)")
        assert key == "UNIT"
        assert value == "SYSDA"

    def test_parenthesized_multiple_subparams(self):
        key, value = parse_jcl_parameter("DISP=(NEW,CATLG,DELETE)")
        assert key == "DISP"
        assert value == ["NEW", "CATLG", "DELETE"]


class TestQuoteUnquote:
    """Tests for quote_jcl_value / unquote_jcl_value."""

    def test_quote_special_chars(self):
        assert quote_jcl_value("HELLO WORLD") == "'HELLO WORLD'"

    def test_quote_escapes_apostrophes(self):
        assert quote_jcl_value("IT'S") == "'IT''S'"

    def test_quote_plain_value_unchanged(self):
        assert quote_jcl_value("ABC123") == "ABC123"

    def test_unquote_quoted(self):
        assert unquote_jcl_value("'HELLO WORLD'") == "HELLO WORLD"

    def test_unquote_unescapes_doubled_quotes(self):
        assert unquote_jcl_value("'IT''S'") == "IT'S"

    def test_unquote_plain_value_unchanged(self):
        assert unquote_jcl_value("ABC") == "ABC"


class TestValidateJclName:
    """Tests for validate_jcl_name."""

    def test_valid(self):
        assert validate_jcl_name("STEP1") is True

    def test_national_chars(self):
        assert validate_jcl_name("@A$#") is True

    def test_empty(self):
        assert validate_jcl_name("") is False

    def test_too_long(self):
        assert validate_jcl_name("ABCDEFGHI") is False

    def test_bad_start_char(self):
        assert validate_jcl_name("1ABC") is False

    def test_bad_inner_char(self):
        assert validate_jcl_name("AB-CD") is False


class TestFormatJclLine:
    """Tests for format_jcl_line including continuation wrapping."""

    def test_no_parameters(self):
        assert format_jcl_line("JOB", "MYJOB", {}) == ["//MYJOB JOB"]

    def test_single_line(self):
        lines = format_jcl_line("EXEC", "S1", {"PGM": "IEFBR14"})
        assert lines == ["//S1 EXEC PGM=IEFBR14"]

    def test_positional_parameter(self):
        lines = format_jcl_line("EXEC", "S1", {"_positional": "MYPROC"})
        assert lines == ["//S1 EXEC MYPROC"]

    def test_list_value_rendered_as_parenthesized(self):
        lines = format_jcl_line("DD", "D1", {"DISP": ["NEW", "CATLG"]})
        assert lines == ["//D1 DD DISP=(NEW,CATLG)"]

    def test_value_with_space_is_quoted(self):
        lines = format_jcl_line("DD", "D1", {"PARM": "A B"})
        assert lines == ["//D1 DD PARM='A B'"]

    def test_continuation_when_too_long(self):
        params = {f"K{i}": f"VALUE{i}" for i in range(12)}
        lines = format_jcl_line("DD", "LONGDD", params)
        assert len(lines) > 1
        assert lines[0] == "//LONGDD DD"
        # Every line stays within the JCL line-length budget.
        assert all(len(line) <= 71 for line in lines)


class TestExtractInlineData:
    """Tests for the deprecated extract_inline_data helper."""

    def test_extracts_until_delimiter(self):
        lines = ["//SYSIN DD *", "DATA LINE 1", "DATA LINE 2", "/*", "//NEXT DD"]
        data, end = extract_inline_data(lines, 0)
        assert data == "DATA LINE 1\nDATA LINE 2"
        assert lines[end] == "/*"

    def test_start_index_past_end(self):
        assert extract_inline_data(["//A"], 5) == (None, 5)

    def test_no_delimiter_consumes_rest(self):
        lines = ["//SYSIN DD *", "ONE", "TWO"]
        data, end = extract_inline_data(lines, 0)
        assert data == "ONE\nTWO"
        assert end == len(lines) - 1


class TestMergeContinuationLines:
    """Tests for the deprecated merge_continuation_lines wrapper."""

    def test_merges_continuations(self):
        lines = [
            "//STEP EXEC PGM=IEBGENER,",
            "//      PARM='A'",
        ]
        merged = merge_continuation_lines(lines)
        assert len(merged) == 1
        assert "PARM='A'" in merged[0]


class TestCalculateChecksum:
    """Tests for calculate_jcl_checksum."""

    def test_deterministic(self):
        content = "//J JOB\n//S EXEC PGM=X\n"
        assert calculate_jcl_checksum(content) == calculate_jcl_checksum(content)

    def test_ignores_blank_lines_and_surrounding_whitespace(self):
        a = "//J JOB\n//S EXEC PGM=X\n"
        b = "  //J JOB  \n\n   //S EXEC PGM=X\n\n"
        assert calculate_jcl_checksum(a) == calculate_jcl_checksum(b)

    def test_matches_manual_md5_of_normalized(self):
        content = "//J JOB\n\n//S EXEC PGM=X\n"
        normalized = "//J JOB\n//S EXEC PGM=X"
        expected = hashlib.md5(normalized.encode("utf-8")).hexdigest()
        assert calculate_jcl_checksum(content) == expected
