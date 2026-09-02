"""
Tests for enhanced continuation line handling.
"""

import textwrap

from jclparser import parse_jcl
from jclparser.continuation_handler import (
    ContinuationLineHandler,
    ContinuationContext,
)
from jclparser.utils import normalize_jcl_line


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
        """Test merging continuation lines with interspersed comments.

        Per z/OS, a //* comment does not terminate a statement that has a
        pending continuation (trailing comma): the comment is preserved in
        the output, but the continuation resumes past it so operand data
        is not lost.
        """
        handler = ContinuationLineHandler()

        lines = [
            "//DD1 DD DSN=MY.DATA,",
            "//* This is a comment",
            "//             DISP=SHR,",
            "//             UNIT=SYSDA",
        ]

        merged = handler.merge_continuation_lines(lines)

        # Two results: the comment, and the fully-merged DD statement.
        assert len(merged) == 2

        comment_entries = [m for m in merged if m[0].startswith("//*")]
        assert len(comment_entries) == 1
        assert comment_entries[0][0] == "//* This is a comment"

        dd_entries = [m for m in merged if m[0].startswith("//DD1")]
        assert len(dd_entries) == 1
        assert "DSN=MY.DATA" in dd_entries[0][0]
        assert "DISP=SHR" in dd_entries[0][0]
        assert "UNIT=SYSDA" in dd_entries[0][0]

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


class TestNormalizeLongLines:
    """Regression tests for long-line JCL that must not be truncated."""

    def test_line_between_72_and_80_chars_not_truncated(self):
        """Lines between 73 and 79 chars (modern-editor JCL) must not be truncated."""
        # 74-char line: content runs into what would be the seq-number area on a
        # mainframe record, but here every character is genuine JCL content.
        line = (
            "//DD1     DD DSN=OUTPUT.DATASET.NAME,DCB=(RECFM=FB,LRECL=80,BLKSIZE=23440)"
        )
        assert 72 < len(line) < 80, f"Expected 73-79 chars, got {len(line)}"
        result = normalize_jcl_line(line)
        assert result == line.rstrip()

    def test_80col_mainframe_record_still_truncated(self):
        """Lines of exactly 80 chars (mainframe records) lose cols 73-80."""
        content = "//DD1 DD DSN=MY.DATA,DISP=SHR"
        # Pad to 72, add sequence numbers to reach 80
        padded = content.ljust(72) + "SEQ00001"
        assert len(padded) == 80
        result = normalize_jcl_line(padded)
        assert "SEQ00001" not in result
        assert content in result

    def test_exact_bug_report_single_long_line(self):
        """Regression: DD with all parameters on a 73-79 char line must parse without error.

        Previously, normalize_jcl_line truncated lines > 72 chars, cutting off
        the closing parenthesis of DCB and raising 'Unmatched parentheses'.
        """
        # This DD line is between 73-79 chars — fits in one modern-editor line with
        # all parens closed, but was truncated at char 72 before the fix.
        dd_line = (
            "//DD1     DD DSN=OUTPUT.DATASET.NAME,DCB=(RECFM=FB,LRECL=80,BLKSIZE=23440)"
        )
        assert 72 < len(dd_line) < 80, f"Expected 73-79 chars, got {len(dd_line)}"

        jcl = "//JOBNAME JOB ACCT,NAME\n//STEP1   EXEC PGM=PROG\n" + dd_line + "\n"
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        params = dd.parameters
        assert "DSN" in params
        # Closing paren must not have been lost — DCB must be present with BLKSIZE
        assert "DCB" in params
        dcb_val = str(params["DCB"])
        assert "BLKSIZE" in dcb_val or "23440" in dcb_val

    def test_multiline_dd_aws_m2_carddemo_no_unmatched_parens(self):
        """Regression: multi-param DD with DISP/DCB/SPACE on continuation lines must not
        raise 'Unmatched parentheses'.

        Reported error:
            JCL_PARSE_ERROR: Unmatched parentheses in parameter:
            DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,DCB=(LRECL=80,BLKSIZE=8000,RECFM=FB),
            SPACE=(CYL,(1,1),RLSE), 00,RECFM=FB), ATA.VSAM.KSDSDSN=AWS.M2.CARDDEMO.STATEMNT.PS

        The garbled parameter string shows that a second DD statement's parameters were
        incorrectly merged into the first one because normalize_jcl_line() truncated 73-79
        char continuation lines, leaving DCB's closing parenthesis.
        """
        jcl = textwrap.dedent("""\
            //JOBNAME  JOB ACCT,NAME
            //STEP1    EXEC PGM=PROG
            //SYSUT2   DD  DSN=AWS.M2.CARDDEMO.STATEMNT.PS,
            //             DISP=(NEW,CATLG,DELETE),
            //             UNIT=SYSDA,
            //             DCB=(LRECL=80,BLKSIZE=8000,RECFM=FB),
            //             SPACE=(CYL,(1,1),RLSE)
            """)
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        params = dd.parameters
        assert "DSN" in params
        assert "DISP" in params
        assert "DCB" in params
        assert "SPACE" in params
        # Verify the dataset name is intact
        assert "AWS.M2.CARDDEMO.STATEMNT.PS" in str(params["DSN"])

    def test_creastmt_job_corrupted_line_reports_garbled_text(self):
        """Regression: CREASTMT JCL with a garbled continuation line.

        The STMTFILE DD in STEP040 has garbage text on one continuation line:
            //         SPACE=(CYL,(1,1),RLSE), 00,RECFM=FB), ATA.VSAM.KSDS
        Everything after the blank that follows ``RLSE),`` sits in the record's
        comment field, so z/OS reads the statement as ``SPACE=(CYL,(1,1),RLSE),``
        continued on the next record — and so does this parser.  The clean
        operands must all survive, and because the discarded text looks like
        operands rather than prose it must be reported on ``job.warnings``
        instead of vanishing.
        """
        jcl = textwrap.dedent("""\
            //CREASTMT JOB 'Create Statement',CLASS=A,MSGCLASS=H,MSGLEVEL=(1,1),
            //         NOTIFY=&SYSUID,TIME=1440
            //*
            //STEP040  EXEC PGM=CBSTM03A,COND=(0,NE)
            //STMTFILE DD DISP=(NEW,CATLG,DELETE),
            //         UNIT=SYSDA,
            //         DCB=(LRECL=80,BLKSIZE=8000,RECFM=FB),
            //         SPACE=(CYL,(1,1),RLSE), 00,RECFM=FB), ATA.VSAM.KSDS
            //         DSN=AWS.M2.CARDDEMO.STATEMNT.PS
            """)
        job = parse_jcl(jcl)

        dd = job.steps[0].dd_statements[0]
        assert dd.name == "STMTFILE"
        assert dd.parameters["DSN"] == "AWS.M2.CARDDEMO.STATEMNT.PS"
        assert dd.parameters["UNIT"] == "SYSDA"
        assert "DISP" in dd.parameters and "DCB" in dd.parameters
        assert "SPACE" in dd.parameters
        # The garbled tail is reported, not silently dropped.
        assert any(
            "ATA.VSAM.KSDS" in warning and "line 8" in warning.lower()
            for warning in job.warnings
        ), job.warnings

    def test_creastmt_job_clean_parses_fully(self):
        """Regression: full CREASTMT JCL without the corrupted line must parse cleanly.

        Verifies that parsing the same job with a correct STMTFILE DD (no garbled
        text) produces the expected steps and DD statements.
        """
        jcl = textwrap.dedent("""\
            //CREASTMT JOB 'Create Statement',CLASS=A,MSGCLASS=H,MSGLEVEL=(1,1),
            //         NOTIFY=&SYSUID,TIME=1440
            //*
            //DELDEF01 EXEC PGM=IDCAMS
            //SYSPRINT DD  SYSOUT=*
            //SYSIN    DD  *
              DELETE    AWS.M2.CARDDEMO.TRXFL.SEQ
            /*
            //STEP010  EXEC PGM=SORT
            //SORTIN   DD  DISP=SHR,DSN=AWS.M2.CARDDEMO.TRANSACT.VSAM.KSDS
            //SYSPRINT DD  SYSOUT=*
            //SORTOUT  DD  DSN=AWS.M2.CARDDEMO.TRXFL.SEQ,
            //             DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,
            //             DCB=(LRECL=350,BLKSIZE=3500,RECFM=FB),
            //             SPACE=(CYL,(1,1),RLSE)
            //SYSIN    DD *
              SORT FIELDS=(263,16,CH,A,1,16,CH,A)
            /*
            //STEP040  EXEC PGM=CBSTM03A,COND=(0,NE)
            //STMTFILE DD DISP=(NEW,CATLG,DELETE),
            //         UNIT=SYSDA,
            //         DCB=(LRECL=80,BLKSIZE=8000,RECFM=FB),
            //         SPACE=(CYL,(1,1),RLSE),
            //         DSN=AWS.M2.CARDDEMO.STATEMNT.PS
            //HTMLFILE DD  DISP=(NEW,CATLG,DELETE),
            //         UNIT=SYSDA,
            //         DCB=(LRECL=100,BLKSIZE=800,RECFM=FB),
            //         SPACE=(CYL,(1,1),RLSE),
            //         DSN=AWS.M2.CARDDEMO.STATEMNT.HTML
            """)
        job = parse_jcl(jcl)
        assert job.name == "CREASTMT"
        step_names = [s.name for s in job.steps]
        assert "DELDEF01" in step_names
        assert "STEP010" in step_names
        assert "STEP040" in step_names

        step040 = next(s for s in job.steps if s.name == "STEP040")
        dd_names = [dd.name for dd in step040.dd_statements]
        assert "STMTFILE" in dd_names
        assert "HTMLFILE" in dd_names

        stmtfile = next(dd for dd in step040.dd_statements if dd.name == "STMTFILE")
        assert "DSN" in stmtfile.parameters
        assert "AWS.M2.CARDDEMO.STATEMNT.PS" in str(stmtfile.parameters["DSN"])
        assert "DCB" in stmtfile.parameters
        assert "SPACE" in stmtfile.parameters

    def test_adjacent_dds_not_merged_when_first_ends_with_closed_parens(self):
        """Regression: two adjacent DD statements must remain independent.

        When the first DD's last continuation line is 73-79 chars and ends with a
        closing paren (e.g. SPACE=(CYL,(1,1),RLSE)), the old bug would truncate that
        paren, causing the second DD to be absorbed as a continuation of the first.
        """
        jcl = textwrap.dedent("""\
            //JOBNAME  JOB ACCT,NAME
            //STEP1    EXEC PGM=PROG
            //DD1      DD  DSN=AWS.M2.CARDDEMO.DATA.VSAM.KSDS,
            //             DISP=(NEW,CATLG,DELETE),
            //             UNIT=SYSDA,
            //             DCB=(LRECL=80,BLKSIZE=8000,RECFM=FB),
            //             SPACE=(CYL,(1,1),RLSE)
            //DD2      DD  DSN=AWS.M2.CARDDEMO.STATEMNT.PS,
            //             DISP=SHR
            """)
        job = parse_jcl(jcl)
        assert len(job.steps[0].dd_statements) == 2
        dd1, dd2 = job.steps[0].dd_statements
        assert "AWS.M2.CARDDEMO.DATA.VSAM.KSDS" in str(dd1.parameters.get("DSN", ""))
        assert "AWS.M2.CARDDEMO.STATEMNT.PS" in str(dd2.parameters.get("DSN", ""))
        # DD2 must NOT have DCB or SPACE (those belong to DD1)
        assert "DCB" not in dd2.parameters
        assert "SPACE" not in dd2.parameters
