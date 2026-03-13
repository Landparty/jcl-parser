"""
Tests for enhanced continuation line handling.
"""

import pytest
from jclparser.continuation_handler import (
    ContinuationLineHandler,
    ContinuationContext,
    merge_continuation_lines,
)


class TestContinuationContext:
    """Test ContinuationContext dataclass."""

    def test_default_context(self):
        """Test default context initialization."""
        ctx = ContinuationContext()

        assert ctx.in_quotes is False
        assert ctx.paren_depth == 0
        assert ctx.bracket_depth == 0
        assert ctx.last_char == ""
        assert ctx.is_complete is False


class TestContinuationLineHandler:
    """Test the ContinuationLineHandler class."""

    def test_standard_continuation_detection(self):
        """Test detection of standard continuation lines."""
        handler = ContinuationLineHandler()

        # Standard continuation (2-14 spaces - columns 4-16)
        assert handler.is_continuation_line("//" + " " * 13 + "PARM=VALUE")

        # Continuation at column 16 (14 spaces)
        assert handler.is_continuation_line("//" + " " * 14 + "PARM=VALUE")

        # Continuation at column 4 (2 spaces) - minimum
        assert handler.is_continuation_line("//" + " " * 2 + "PARM=VALUE")

        # Not a continuation (1 space = column 3)
        assert not handler.is_continuation_line("//" + " " * 1 + "PARM=VALUE")

        # Not a continuation (16+ spaces = column 17+)
        assert not handler.is_continuation_line("//" + " " * 16 + "PARM=VALUE")

        # Not a continuation (statement start)
        assert not handler.is_continuation_line("//STEP1 EXEC PGM=PROG")

    def test_empty_continuation_content(self):
        """Test continuation with empty content after spaces."""
        handler = ContinuationLineHandler()

        # With comma context - empty continuation should be detected
        previous = "//DD1 DD DSN=MY.DATA,"
        current = "//             "  # 13 spaces, no content
        assert handler.is_continuation_line(current, previous)

        # Without context - empty content should NOT be a continuation
        assert not handler.is_continuation_line("//             ")

    def test_alternative_continuation_detection(self):
        """Test detection of alternative continuation formats."""
        handler = ContinuationLineHandler()

        # Alternative continuation (// ,param)
        assert handler.is_continuation_line("// ,PARM=VALUE")

        # With more spaces
        assert handler.is_continuation_line("//  ,UNIT=SYSDA")

    def test_implicit_continuation_comma(self):
        """Test implicit continuation when previous line ends with comma."""
        handler = ContinuationLineHandler()

        previous = "//DD1 DD DSN=MY.DATA,"
        current = "//             DISP=SHR"

        assert handler.is_continuation_line(current, previous)

    def test_unclosed_parentheses_continuation(self):
        """Test continuation detection for unclosed parentheses."""
        handler = ContinuationLineHandler()

        previous = "//DD1 DD SPACE=(CYL,(10,5),"
        current = "//             RLSE)"

        # Note: This test depends on _analyze_line_context working correctly
        # The current line should be detected as continuation due to unclosed paren
        assert handler.is_continuation_line(current, previous)

    def test_comment_not_continuation(self):
        """Test that comments are not treated as continuations."""
        handler = ContinuationLineHandler()

        assert not handler.is_continuation_line("//* This is a comment")

    def test_empty_line_not_continuation(self):
        """Test that empty lines are not continuations."""
        handler = ContinuationLineHandler()

        assert not handler.is_continuation_line("")
        assert not handler.is_continuation_line("   ")

    def test_merge_simple_continuation(self):
        """Test merging simple continuation lines."""
        handler = ContinuationLineHandler()

        lines = ["//STEP1 EXEC PGM=MYPROG,", "//             PARM='VALUE1,VALUE2'"]

        merged = handler.merge_continuation_lines(lines)

        assert len(merged) == 1
        assert "PARM='VALUE1,VALUE2'" in merged[0][0]
        assert merged[0][1] == 1  # Original line number

    def test_merge_complex_dcb_parameters(self):
        """Test merging complex DCB parameters across multiple lines."""
        handler = ContinuationLineHandler()

        lines = [
            "//DD1 DD DSN=MY.DATA,",
            "//             DISP=(NEW,CATLG,DELETE),",
            "//             UNIT=SYSDA,",
            "//             SPACE=(CYL,(100,10),RLSE),",
            "//             DCB=(RECFM=FB,LRECL=80,",
            "//                  BLKSIZE=27920)",
        ]

        merged = handler.merge_continuation_lines(lines)

        assert len(merged) == 1
        merged_line = merged[0][0]

        assert "DSN=MY.DATA" in merged_line
        assert "DISP=(NEW,CATLG,DELETE)" in merged_line
        assert "DCB=(RECFM=FB,LRECL=80" in merged_line
        assert "BLKSIZE=27920)" in merged_line

    def test_merge_with_comments(self):
        """Test merging continuation lines with interspersed comments."""
        handler = ContinuationLineHandler()

        lines = [
            "//DD1 DD DSN=MY.DATA,",
            "//* This is a comment",
            "//             DISP=SHR,",
            "//             UNIT=SYSDA",
        ]

        merged = handler.merge_continuation_lines(lines)

        # Should have 3 results: DD1 (stopped at comment), comment, and new DD continuation
        assert len(merged) == 3

        # First is DD1 with just DSN (comment broke the continuation)
        assert "DSN=MY.DATA" in merged[0][0]
        assert "DISP" not in merged[0][0]  # Comment broke continuation

        # Second is the comment
        assert merged[1][0].startswith("//*")

        # Third is the continuation lines after comment (merged together)
        assert "DISP=SHR" in merged[2][0]
        assert "UNIT=SYSDA" in merged[2][0]

    def test_merge_alternative_continuation_format(self):
        """Test merging alternative continuation format (// ,param)."""
        handler = ContinuationLineHandler()

        lines = ["//DD1 DD DSN=MY.DATA", "// ,DISP=SHR", "// ,UNIT=SYSDA"]

        merged = handler.merge_continuation_lines(lines)

        assert len(merged) == 1
        merged_line = merged[0][0]

        assert "DSN=MY.DATA" in merged_line
        assert "DISP=SHR" in merged_line
        assert "UNIT=SYSDA" in merged_line

    def test_merge_preserves_non_jcl_lines(self):
        """Test that non-JCL lines are preserved as-is."""
        handler = ContinuationLineHandler()

        lines = ["//DD1 DD *", "This is inline data", "More inline data", "/*"]

        merged = handler.merge_continuation_lines(lines)

        # DD statement merged, inline data preserved
        assert len(merged) == 4
        assert merged[0][0].startswith("//DD1")
        assert merged[1][0] == "This is inline data"
        assert merged[2][0] == "More inline data"
        assert merged[3][0] == "/*"

    def test_extract_continuation_content(self):
        """Test extraction of continuation content."""
        handler = ContinuationLineHandler()

        # Standard continuation
        content = handler._extract_continuation_content("//               PARM=VALUE")
        assert content == "PARM=VALUE"

        # Alternative continuation
        content = handler._extract_continuation_content("// ,UNIT=SYSDA")
        assert content == "UNIT=SYSDA"

    def test_analyze_line_context_balanced(self):
        """Test context analysis for balanced line."""
        handler = ContinuationLineHandler()

        ctx = handler._analyze_line_context("//DD1 DD DCB=(RECFM=FB,LRECL=80)")

        assert ctx.paren_depth == 0
        assert ctx.in_quotes is False
        assert ctx.is_complete is True

    def test_analyze_line_context_unclosed_paren(self):
        """Test context analysis for unclosed parenthesis."""
        handler = ContinuationLineHandler()

        ctx = handler._analyze_line_context("//DD1 DD DCB=(RECFM=FB,LRECL=80,")

        assert ctx.paren_depth == 1
        assert ctx.is_complete is False

    def test_analyze_line_context_unclosed_quote(self):
        """Test context analysis for unclosed quote."""
        handler = ContinuationLineHandler()

        ctx = handler._analyze_line_context("//DD1 DD PARM='VALUE1,VALUE2,")

        assert ctx.in_quotes is True
        assert ctx.is_complete is False

    def test_analyze_line_context_escaped_quote(self):
        """Test context analysis with escaped quotes."""
        handler = ContinuationLineHandler()

        ctx = handler._analyze_line_context("//DD1 DD PARM='O''BRIEN'")

        # Should be balanced (escaped quote doesn't toggle state)
        assert ctx.in_quotes is False
        assert ctx.is_complete is True


class TestConvenienceFunction:
    """Test the convenience function."""

    def test_merge_continuation_lines_function(self):
        """Test the module-level convenience function."""
        lines = ["//STEP1 EXEC PGM=MYPROG,", "//             PARM='VALUE'"]

        merged = merge_continuation_lines(lines)

        assert len(merged) == 1
        assert "PARM='VALUE'" in merged[0][0]


class TestContinuationEdgeCases:
    """Test edge cases in continuation handling."""

    def test_continuation_with_quoted_comma(self):
        """Test continuation with comma inside quotes."""
        handler = ContinuationLineHandler()

        lines = [
            "//STEP1 EXEC PGM=MYPROG,",
            "//         PARM='VALUE1,VALUE2,",
            "//               VALUE3'",
        ]

        merged = handler.merge_continuation_lines(lines)

        assert len(merged) == 1
        merged_line = merged[0][0]

        # Should preserve comma inside quotes
        assert "VALUE1,VALUE2" in merged_line
        assert "VALUE3" in merged_line

    def test_multiple_statements_with_continuation(self):
        """Test multiple statements each with continuation."""
        handler = ContinuationLineHandler()

        lines = [
            "//STEP1 EXEC PGM=PROG1,",
            "//         PARM='VALUE1'",
            "//DD1   DD DSN=DATA1,",
            "//         DISP=SHR",
            "//STEP2 EXEC PGM=PROG2,",
            "//         PARM='VALUE2'",
            "//DD2   DD DSN=DATA2,",
            "//         DISP=SHR",
        ]

        merged = handler.merge_continuation_lines(lines)

        # Should have 4 merged statements
        assert len(merged) == 4

        # Verify each statement
        assert "STEP1" in merged[0][0] and "PARM='VALUE1'" in merged[0][0]
        assert "DD1" in merged[1][0] and "DISP=SHR" in merged[1][0]
        assert "STEP2" in merged[2][0] and "PARM='VALUE2'" in merged[2][0]
        assert "DD2" in merged[3][0] and "DISP=SHR" in merged[3][0]

    def test_continuation_line_numbers_preserved(self):
        """Test that original line numbers are preserved."""
        handler = ContinuationLineHandler()

        lines = [
            "//* Comment line 1",
            "//STEP1 EXEC PGM=PROG,",  # Line 2
            "//         PARM='VALUE'",  # Line 3 (continuation)
            "//* Comment line 4",
            "//DD1 DD DSN=DATA",  # Line 5
        ]

        merged = handler.merge_continuation_lines(lines)

        # Check line numbers
        assert merged[0][1] == 1  # Comment
        assert merged[1][1] == 2  # EXEC (merged from lines 2-3)
        assert merged[2][1] == 4  # Comment
        assert merged[3][1] == 5  # DD

    def test_deeply_nested_parentheses(self):
        """Test handling of deeply nested parentheses."""
        handler = ContinuationLineHandler()

        lines = ["//DD1 DD PARM='((A,B),(C,(D,E)))',", "//         UNIT=SYSDA"]

        merged = handler.merge_continuation_lines(lines)

        assert len(merged) == 1
        assert "((A,B),(C,(D,E)))" in merged[0][0]
        assert "UNIT=SYSDA" in merged[0][0]
