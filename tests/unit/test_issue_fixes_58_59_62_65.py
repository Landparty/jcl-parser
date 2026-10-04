"""Regression tests for jcl-parser issues #58, #59, #62 and #65 (items 4, 5).

* #58: a ``//*`` comment inside a continued ``DD *`` / ``DD DATA`` statement
  was read as the first in-stream data record (``DD DATA``) or ended the
  data at once, handing it to a phantom ``SYSIN`` DD (``DD *``).
* #59: an in-stream PROC with no PEND (and an unterminated ``DD DATA`` block
  holding JCL) silently swallowed the rest of the job.
* #62: records were split on form feed / NEL / U+2028 (``str.splitlines``),
  and the cp1252 decode fallback was unreachable behind latin-1.
* #65 item 4: the CLI printed a raw traceback for a directory argument.
* #65 item 5: continuing a quoted string dropped blanks coded through
  column 71 of a card image.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl

pytestmark = pytest.mark.unit


class TestCommentInsideContinuedInstreamDd:
    """Issue #58."""

    def test_dd_star_continued_around_comment_keeps_its_data(self) -> None:
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=X\n"
            "//IN DD *,\n"
            "//* comment\n"
            "//   DCB=BLKSIZE=80\n"
            "REC1\n"
            "REC2\n"
            "/*\n"
        )
        job = parse_jcl(src)
        dds = job.steps[0].dd_statements
        assert [(d.name, d.inline_data) for d in dds] == [("IN", "REC1\nREC2")]
        assert dds[0].parameters.get("DCB") is not None
        assert not any("SYSIN" in w for w in job.warnings)

    def test_dd_data_dlm_continued_around_comment_keeps_comment_out(self) -> None:
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=X\n"
            "//IN DD DATA,\n"
            "//* comment\n"
            "//   DLM=$$\n"
            "REC1\n"
            "//REC2\n"
            "$$\n"
            "//S2 EXEC PGM=Y\n"
        )
        job = parse_jcl(src)
        dds = job.steps[0].dd_statements
        assert [(d.name, d.inline_data) for d in dds] == [("IN", "REC1\n//REC2")]
        assert [s.name for s in job.steps] == ["S1", "S2"]

    def test_comment_line_number_order_is_kept(self) -> None:
        from jclparser.parser import _merge_source_lines

        src = "//J JOB\n//S1 EXEC PGM=X\n//IN DD *,\n//* c\n//   DCB=BLKSIZE=80\nR\n"
        merged = _merge_source_lines(src)[0]
        assert merged[2] == ("//* c", 4)
        assert merged[3][1] == 3
