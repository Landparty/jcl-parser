"""Regression tests for #80: column 72 of a 72-character continued record.

A fixed-format card whose sequence field was trimmed is 72 characters long
and carries its continuation indicator in column 72. When column 71 holds
operand text (a trailing comma, or a quoted string still open), that
indicator used to be kept as statement text. It is now dropped when the
next record is a continuation; an editor line of 72 characters that is not
continued keeps every character.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.utils import (
    is_continued_card_image,
    normalize_jcl_line,
    normalize_jcl_lines,
)


def _parm_record() -> str:
    head = "//S1 EXEC PGM=IEFBR14,PARM='ABC"
    record = head + "D" * (69 - len(head)) + "FG" + "X"
    assert len(record) == 72 and record[70] == "G"
    return record


def _dd_record() -> str:
    head = "//DD1 DD DISP=SHR,UNIT=SYSDA,DSN=A.B.C"
    record = head + "C" * (70 - len(head)) + ",X"
    assert len(record) == 72 and record[70] == ","
    return record


@pytest.mark.unit
class TestTrimmedCardContinuation:
    def test_open_quote_through_column_71(self):
        job = parse_jcl("//J JOB\n" + _parm_record() + "\n//             MORE'\n")
        parm = job.steps[0].parameters["PARM"]
        assert parm.endswith("DFGMORE")
        # Same as the full 80-column card image.
        padded = parse_jcl(
            "//J JOB\n" + _parm_record() + "00000010\n//             MORE'\n"
        )
        assert padded.steps[0].parameters["PARM"] == parm

    def test_comma_in_column_71(self):
        src = (
            "//J JOB\n//S EXEC PGM=X\n" + _dd_record() + "\n//         VOL=SER=VOL001\n"
        )
        params = parse_jcl(src).steps[0].dd_statements[0].parameters
        assert params["VOL"] == "SER=VOL001"
        assert "XVOL" not in params
        assert params["DISP"] == "SHR"


@pytest.mark.unit
class TestEditorLinesKeepTheirLastCharacter:
    def test_72_char_line_ending_in_content(self):
        head = "//DD1 DD DSN=A.B.C"
        record = head + "C" * (63 - len(head)) + ",DISP=SHR"
        assert len(record) == 72 and record.endswith("DISP=SHR")
        src = "//J JOB\n//S EXEC PGM=X\n" + record + "\n//DD2 DD DUMMY\n"
        assert parse_jcl(src).steps[0].dd_statements[0].parameters["DISP"] == "SHR"

    def test_open_operand_without_continuation_record_is_kept(self):
        # Column 71 a comma, but the next record starts a new statement.
        assert normalize_jcl_line(_dd_record(), "//DD2 DD DUMMY") == _dd_record()
        assert normalize_jcl_line(_dd_record(), None) == _dd_record()
        assert normalize_jcl_line(_dd_record(), "// ") == _dd_record()

    def test_comment_record_is_never_trimmed(self):
        comment = "//*" + "'" + "C" * 66 + ",X"
        assert len(comment) == 72
        assert normalize_jcl_line(comment, "//         A=B") == comment

    def test_closed_quote_without_comma_is_kept(self):
        head = "//S1 EXEC PGM=X,PARM='AB'"
        record = head + "," + "R" * (71 - len(head) - 1)
        record = record[:71] + "Z"
        assert len(record) == 72 and record[70] != ","
        assert normalize_jcl_line(record, "//         A=B") == record


@pytest.mark.unit
class TestHelpers:
    def test_normalize_jcl_lines_looks_ahead(self):
        lines = normalize_jcl_lines([_dd_record(), "//         VOL=SER=VOL001"])
        assert lines[0] == _dd_record()[:71]
        assert lines[1] == "//         VOL=SER=VOL001"

    def test_is_continued_card_image_with_lookahead(self):
        assert is_continued_card_image(_dd_record(), "//         VOL=SER=A")
        assert not is_continued_card_image(_dd_record())
        assert not is_continued_card_image(_dd_record()[:71] + " ", "//  A=B")
