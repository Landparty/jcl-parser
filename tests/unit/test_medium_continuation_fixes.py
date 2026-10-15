"""Regression tests for the continuation / comment-field / XMIT medium fixes.

Covers issues #122 (backslash is not an escape), #123 (a record continues a
statement only after a trailing comma), #120 (a comment starting with ``(``
or ``'`` after a trailing comma) and #117 (XMIT ``DLM=`` and JES2 ``/*XMIT``).
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
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
