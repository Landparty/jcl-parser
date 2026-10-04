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


class TestUnterminatedBlocksWarn:
    """Issue #59."""

    def test_instream_proc_without_pend_warns(self) -> None:
        src = (
            "//J JOB\n"
            "//P PROC\n"
            "//S EXEC PGM=X\n"
            "//D DD DSN=A,DISP=SHR\n"
            "//R EXEC P\n"
            "//R2 EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(src)
        assert job.steps == []
        assert (
            "Line 2: PROC P has no PEND; the statements after it were read as "
            "part of the procedure"
        ) in job.warnings

    def test_cataloged_proc_member_without_pend_is_silent(self) -> None:
        src = "//P PROC\n//S EXEC PGM=X\n//D DD DSN=A,DISP=SHR\n"
        job = parse_jcl(src)
        assert job.name == ""
        assert [p.name for p in job.procedures] == ["P"]
        assert job.warnings == []

    def test_proc_with_pend_is_silent(self) -> None:
        src = "//J JOB\n//P PROC\n//S EXEC PGM=X\n// PEND\n//R EXEC P\n"
        job = parse_jcl(src)
        assert not any("PEND" in w for w in job.warnings)

    def test_unterminated_dd_data_swallowing_jcl_warns(self) -> None:
        src = "//J JOB\n//S1 EXEC PGM=X\n//IN DD DATA,DLM=$$\nREC1\n//S2 EXEC PGM=Y\n"
        job = parse_jcl(src)
        assert [s.name for s in job.steps] == ["S1"]
        assert job.steps[0].dd_statements[0].inline_data == "REC1\n//S2 EXEC PGM=Y"
        assert any(
            "Line 3:" in w and "never closed" in w and "S2" in w for w in job.warnings
        ), job.warnings

    def test_unterminated_ordinary_data_is_silent(self) -> None:
        src = "//J JOB\n//S1 EXEC PGM=X\n//IN DD DATA\nREC1\nREC2\n"
        job = parse_jcl(src)
        assert job.steps[0].dd_statements[0].inline_data == "REC1\nREC2"
        assert job.warnings == []

    def test_unterminated_job_level_xmit_swallowing_jcl_warns(self) -> None:
        job = parse_jcl("//J JOB\n//X XMIT DEST=A\nDATA\n//S1 EXEC PGM=X\n")
        assert job.steps == []
        assert any(
            w.startswith("In-stream data was never closed") and "S1" in w
            for w in job.warnings
        ), job.warnings


class TestRecordsBreakOnlyOnNewlines:
    """Issue #62."""

    SRC = "//J JOB\n//S1 EXEC PGM=X\n//IN DD *\nREC1\x0cMORE\n/*\n//S2 EXEC PGM=Y\n"

    def test_form_feed_inside_a_record_is_data(self) -> None:
        job = parse_jcl(self.SRC)
        assert job.steps[0].dd_statements[0].inline_data == "REC1\x0cMORE"
        assert [s.line_number for s in job.steps] == [2, 6]

    @pytest.mark.parametrize("char", ["\x0b", "\x1c", "\x1d", "\x1e", "\x85", " "])
    def test_other_unicode_line_breaks_are_data(self, char: str) -> None:
        job = parse_jcl(self.SRC.replace("\x0c", char))
        assert job.steps[0].dd_statements[0].inline_data == f"REC1{char}MORE"
        assert [s.line_number for s in job.steps] == [2, 6]

    @pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
    def test_real_line_ends_still_split(self, newline: str) -> None:
        job = parse_jcl(self.SRC.replace("\n", newline))
        assert job.steps[0].dd_statements[0].inline_data == "REC1\x0cMORE"
        assert [s.line_number for s in job.steps] == [2, 6]

    def test_split_source_lines_helper(self) -> None:
        from jclparser.utils import split_source_lines

        assert split_source_lines("") == []
        assert split_source_lines("a\x0cb\r\nc\rd\ne\n") == ["a\x0cb", "c", "d", "e"]
        assert split_source_lines("a\n\n") == ["a", ""]
        assert split_source_lines("a b") == ["a b"]
        assert split_source_lines("a\r\nb\rc", keepends=True) == ["a\r\n", "b\r", "c"]
        assert split_source_lines("a\n", keepends=True) == ["a\n"]

    def test_include_expansion_keeps_form_feed_records(self) -> None:
        from jclparser.include_loader import resolve_includes

        class _Loader:
            def load_member(self, member, libraries=None):
                return "//INC DD DSN=INC.DS,DISP=SHR\n" if member == "M" else None

        src = "//J JOB\n//S1 EXEC PGM=X\n//IN DD *\nA\x0cB\n/*\n// INCLUDE MEMBER=M\n"
        out = resolve_includes(src, loader=_Loader())
        assert "A\x0cB\n" in out
        assert "//INC DD DSN=INC.DS" in out

    def test_strict_dd_scan_and_jcllib_prescan_use_records(self) -> None:
        from jclparser._statement_parser import _extract_jcllib_order

        assert _extract_jcllib_order("//J JOB\x0c\n//L JCLLIB ORDER=A.B\n") == ["A.B"]

    def test_cp1252_file_decodes_before_latin1(self, tmp_path) -> None:
        path = tmp_path / "w.jcl"
        path.write_bytes(b"//J JOB\n//S1 EXEC PGM=X,PARM='WAIT\x85DONE'\n")
        job = parse_jcl(path)
        assert "WAIT…DONE" in job.steps[0].parameters["PARM"]

    def test_undefined_cp1252_bytes_fall_back_to_latin1(self, tmp_path) -> None:
        from jclparser.utils import _read_file_with_fallback

        path = tmp_path / "u.jcl"
        path.write_bytes(b"//J JOB \x81\n")
        assert _read_file_with_fallback(path) == "//J JOB \x81\n"


class TestCliOsErrors:
    """Issue #65 item 4."""

    @pytest.mark.parametrize(
        "extra", [[], ["steps"], ["--validate"], ["detect"], ["--json"]]
    )
    def test_directory_argument_is_a_clean_error(self, tmp_path, capsys, extra):
        from jclparser.cli import main

        assert main([str(tmp_path), *extra]) == 1
        err = capsys.readouterr().err
        assert err.startswith("Error: ")
        assert "Traceback" not in err

    def test_unreadable_file_is_a_clean_error(self, tmp_path, capsys, monkeypatch):
        from jclparser import cli

        path = tmp_path / "job.jcl"
        path.write_text("//J JOB\n")

        def _denied(*args, **kwargs):
            raise PermissionError(13, "Permission denied", str(path))

        monkeypatch.setattr(cli, "parse_jcl", _denied)
        assert cli.main([str(path)]) == 1
        assert "Permission denied" in capsys.readouterr().err


def _card(content: str, indicator: str = "X", seq: str = "00000010") -> str:
    """An 80-column card image: columns 1-71, column 72, columns 73-80."""
    assert len(content) <= 71
    return content.ljust(71) + indicator + seq


class TestQuotedContinuationKeepsBlanks:
    """Issue #65 item 5: a quoted string is coded through column 71 and
    resumes in column 16 of the next record."""

    PREFIX = "//S1 EXEC PGM=X,PARM='"

    def _parm(self, *records: str) -> str:
        job = parse_jcl("//J JOB\n" + "\n".join(records) + "\n")
        return job.steps[0].parameters["PARM"]

    def test_blank_in_column_71_inside_quotes_is_kept(self) -> None:
        a_run = "A" * (70 - len(self.PREFIX))
        first = _card(self.PREFIX + a_run + " ")
        assert first[70] == " " and first[71] == "X"
        assert self._parm(first, "//" + " " * 13 + "BCD'") == a_run + " BCD"

    def test_several_trailing_blanks_through_column_71_are_kept(self) -> None:
        first = _card(self.PREFIX + "AB")  # columns 25-71 blank
        expected = "AB" + " " * (71 - len(self.PREFIX) - 2) + "CD"
        assert self._parm(first, "//" + " " * 13 + "CD'") == expected

    def test_text_resumes_in_column_16_with_its_leading_blanks(self) -> None:
        a_run = "A" * (71 - len(self.PREFIX))
        first = _card(self.PREFIX + a_run)
        # Column 16 blank, text from column 17: the blank is part of the value.
        assert self._parm(first, "//" + " " * 14 + "X'") == a_run + " X"

    def test_three_records(self) -> None:
        first = _card(self.PREFIX + "ONE")
        middle = _card("//" + " " * 13 + "TWO", seq="00000020")
        value = self._parm(first, middle, "//" + " " * 13 + "THREE'")
        gap1 = " " * (71 - len(self.PREFIX) - 3)
        gap2 = " " * (71 - 15 - 3)
        assert value == "ONE" + gap1 + "TWO" + gap2 + "THREE"

    def test_72_column_record_with_indicator_counts_as_a_card(self) -> None:
        a_run = "A" * (70 - len(self.PREFIX))
        first = (self.PREFIX + a_run + " ").ljust(71) + "X"  # sequence trimmed
        assert len(first) == 72
        assert self._parm(first, "//" + " " * 13 + "BCD'") == a_run + " BCD"

    def test_short_editor_lines_keep_current_behaviour(self) -> None:
        value = self._parm(self.PREFIX + "AAA ", "//             BCD'")
        assert value == "AAABCD"

    def test_continuation_starting_before_column_16_is_lstripped(self) -> None:
        a_run = "A" * (71 - len(self.PREFIX))
        first = _card(self.PREFIX + a_run)
        assert self._parm(first, "//   BCD'") == a_run + "BCD"

    def test_unquoted_card_continuation_is_unchanged(self) -> None:
        first = _card("//S1 EXEC PGM=X,")
        job = parse_jcl("//J JOB\n" + first + "\n//             REGION=4M\n")
        assert job.steps[0].parameters["REGION"] == "4M"
        assert job.steps[0].program == "X"
