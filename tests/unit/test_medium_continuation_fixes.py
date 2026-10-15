"""Regression tests for the continuation / comment-field / XMIT medium fixes.

Covers issues #122 (backslash is not an escape), #123 (a record continues a
statement only after a trailing comma), #120 (a comment starting with ``(``
or ``'`` after a trailing comma) and #117 (XMIT ``DLM=`` and JES2 ``/*XMIT``).
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser._statement_parser import split_comment_field
from jclparser.continuation_handler import ContinuationLineHandler

pytestmark = pytest.mark.unit


class TestBackslashIsNotAnEscape:
    """#122: JCL has no backslash escape; only ``''`` escapes a quote."""

    def test_backslash_before_closing_quote_ends_the_string(self):
        job = parse_jcl(
            "//J1 JOB (A),'X'\n// SET DIR='C:\\'\n// SET HLQ=PROD\n//S1 EXEC PGM=X\n"
        )
        assert job.set_statements == {"DIR": "C:\\", "HLQ": "PROD"}

    def test_context_scan_closes_quote_after_backslash(self):
        ctx = ContinuationLineHandler()._analyze_line_context("// SET DIR='C:\\'")
        assert not ctx.in_quotes
        assert ctx.is_complete

    def test_doubled_apostrophe_is_still_an_escape(self):
        ctx = ContinuationLineHandler()._analyze_line_context("//S EXEC PARM='IT''S'")
        assert not ctx.in_quotes


def _dd_params(source: str) -> dict:
    return parse_jcl(source).steps[0].dd_statements[0].parameters


class TestCommentAfterTrailingComma:
    """#120: a comment starting with ``(`` or ``'`` after a trailing comma."""

    def test_parenthesised_comment_is_not_an_operand(self):
        params = _dd_params(
            "//J1 JOB (A),'X'\n//S1 EXEC PGM=A\n"
            "//IN DD DSN=PROD.CUST.MASTER,   (CUSTOMER MASTER FILE)\n"
            "//      DISP=SHR\n"
        )
        assert params == {"DSN": "PROD.CUST.MASTER", "DISP": "SHR"}

    def test_quoted_word_then_prose_is_a_comment(self):
        params = _dd_params(
            "//J1 JOB (A),'X'\n//S1 EXEC PGM=A\n"
            "//IN DD DSN=PROD.CUST.MASTER,   'CUSTOMER' MASTER\n"
            "//      DISP=SHR\n"
        )
        assert params == {"DSN": "PROD.CUST.MASTER", "DISP": "SHR"}

    def test_job_programmer_name_after_blank_ending_the_record(self):
        # Illegal blank before a quoted string, deliberately tolerated.
        job = parse_jcl("//J1 JOB (ACCT), 'PGMR'\n//S1 EXEC PGM=A\n")
        assert job.accounting_info == "ACCT"
        assert job.parameters == {"_pos_1": "PGMR"}

    def test_job_programmer_name_followed_by_comma_keeps_operands(self):
        job = parse_jcl("//J1 JOB (ACCT), 'PGMR',CLASS=A\n//S1 EXEC PGM=A\n")
        assert job.parameters == {"_pos_1": "PGMR", "CLASS": "A"}

    @pytest.mark.parametrize(
        ("record", "expected"),
        [
            # A blank inside quotes within the group is still operand text.
            ("//IN DD DSN=A.B,   ('X Y',Z)", ("//IN DD DSN=A.B,   ('X Y',Z)", "")),
            ("//IN DD DSN=A.B,   (X Y)", ("//IN DD DSN=A.B,", "(X Y)")),
            ("//IN DD DSN=A.B,   'IT''S',", ("//IN DD DSN=A.B,   'IT''S',", "")),
            ("//IN DD DSN=A.B,   'OPEN", ("//IN DD DSN=A.B,", "'OPEN")),
            ("//IN DD DSN=A.B,   (A,(B", ("//IN DD DSN=A.B,", "(A,(B")),
            ("//IN DD DSN=A.B,   ('OPEN", ("//IN DD DSN=A.B,", "('OPEN")),
            (
                "//IN DD DSN=A.B,   (A,(B,C)),X=1  CMT",
                ("//IN DD DSN=A.B,   (A,(B,C)),X=1", "CMT"),
            ),
        ],
    )
    def test_split_comment_field(self, record, expected):
        assert split_comment_field(record) == expected


class TestMissingCommaDoesNotMerge:
    """#123: a record continues a statement only after a trailing comma."""

    def test_missing_comma_keeps_dsn_and_warns(self):
        job = parse_jcl(
            "//J1 JOB (A),'X'\n//S1 EXEC PGM=A\n"
            "//IN DD DSN=PROD.MASTER\n//      DISP=SHR\n"
        )
        assert job.steps[0].dd_statements[0].parameters == {"DSN": "PROD.MASTER"}
        assert len(job.warnings) == 1
        assert job.warnings[0].startswith("Line 4: continuation record ignored")
        assert "DISP=SHR" in job.warnings[0]

    def test_stray_group_is_reported_once_and_next_statement_survives(self):
        job = parse_jcl(
            "//J1 JOB (A),'X'\n//S1 EXEC PGM=A\n"
            "//IN DD DSN=PROD.MASTER\n//      DISP=SHR,\n//      UNIT=SYSDA\n"
            "//OUT DD DUMMY\n"
        )
        dds = job.steps[0].dd_statements
        assert [dd.name for dd in dds] == ["IN", "OUT"]
        assert dds[0].parameters == {"DSN": "PROD.MASTER"}
        assert len(job.warnings) == 1

    def test_comma_continuation_still_merges(self):
        params = _dd_params(
            "//J1 JOB (A),'X'\n//S1 EXEC PGM=A\n"
            "//IN DD DSN=PROD.MASTER,\n//      DISP=SHR\n"
        )
        assert params == {"DSN": "PROD.MASTER", "DISP": "SHR"}

    def test_open_quote_still_continues_without_comma(self):
        handler = ContinuationLineHandler()
        assert handler.is_continuation_line("//         B'", "//S EXEC PARM='A")

    def test_leading_comma_record_after_complete_statement_continues(self):
        handler = ContinuationLineHandler()
        assert handler.is_continuation_line("//   ,DISP=SHR", "//IN DD DSN=A")

    def test_stray_record_classification(self):
        handler = ContinuationLineHandler()
        assert handler.is_stray_continuation_record("//      DISP=SHR")
        assert handler.is_stray_continuation_record("// ,DISP=SHR")
        assert not handler.is_stray_continuation_record("//S2 EXEC PGM=X")
        assert not handler.is_stray_continuation_record("//   STEP2 EXEC PGM=X")
        assert not handler.is_stray_continuation_record("//  DD DUMMY")
        assert not handler.is_stray_continuation_record("// DISP=SHR")
        assert not handler.is_stray_continuation_record("//")

    def test_unnamed_notify_is_its_own_statement(self):
        job = parse_jcl(
            "//J1 JOB (A),'X'\n// NOTIFY EMAIL='a@b.com'\n"
            "//N2 NOTIFY USER=IBMUSER\n//S1 EXEC PGM=A\n"
        )
        assert job.parameters == {"_pos_1": "X"}
        assert [(c.type, c.name, c.parameters) for c in job.control_statements] == [
            ("NOTIFY", "", {"EMAIL": "a@b.com"}),
            ("NOTIFY", "N2", {"USER": "IBMUSER"}),
        ]
        assert job.warnings == []
        assert [s.name for s in job.steps] == ["S1"]
