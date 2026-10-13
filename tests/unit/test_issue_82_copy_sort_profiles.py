"""Regression tests for issue #82: the copy and sort program profiles missed
data flow.

1. IEBCOPY ignored its COPY / COPYMOD / COPYGRP control statements.
2. IEBGENER read only the first dataset of a concatenated SYSUT1.
3. SORT reported ``input:`` only for SORTIN, never SORTIN01-SORTIN99.
4. Text after a DFSORT statement's operands (a remark) read as keywords.
5. ``SORT FIELDS=COPY`` / ``OPTION COPY`` were not reported as a copy.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.program_profiles import analyze_job
from jclparser.program_profiles._control import (
    parse_control_statements,
    split_operands,
)
from jclparser.program_profiles.base import ProgramAnalysis

pytestmark = pytest.mark.unit


def _analyse(src: str) -> ProgramAnalysis:
    results = analyze_job(parse_jcl(src))
    assert len(results) == 1
    return results[0]


def _sort(sysin: str, dds: str = "") -> ProgramAnalysis:
    return _analyse(
        "//J JOB 1\n//S1 EXEC PGM=SORT\n" + dds + "//SYSIN DD *\n" + sysin + "/*\n"
    )


class TestControlStatementTokeniser:
    OPS = frozenset({"SORT", "COPY"})

    def test_label_operation_operands_remark(self) -> None:
        (stmt,) = parse_control_statements(
            "LBL SORT FIELDS=(1,5,CH,A) REMARK", self.OPS
        )
        assert (stmt.label, stmt.operation, stmt.operands) == (
            "LBL",
            "SORT",
            "FIELDS=(1,5,CH,A)",
        )

    def test_blank_inside_quotes_and_parens_is_operand(self) -> None:
        (stmt,) = parse_control_statements(
            "  SORT X=(C'A B',( 1 )) rest", frozenset({"SORT"})
        )
        assert stmt.operands == "X=(C'A B',( 1 ))"

    def test_comma_continuation_and_comments(self) -> None:
        stmts = parse_control_statements(
            "* comment\n  SORT FIELDS=(1,5,CH,A),   remark\n        EQUALS\n\n  COPY\n",
            self.OPS,
        )
        assert [(s.operation, s.operands) for s in stmts] == [
            ("SORT", "FIELDS=(1,5,CH,A),EQUALS"),
            ("COPY", ""),
        ]

    def test_column_72_continuation(self) -> None:
        first = "  SORT FIELDS=(1,5,".ljust(71) + "X" + "00000010"
        stmts = parse_control_statements(f"{first}\n               CH,A)\n", self.OPS)
        assert stmts[0].operands == "FIELDS=(1,5,CH,A)"

    def test_operands_only_statement(self) -> None:
        (stmt,) = parse_control_statements("INDD=A", self.OPS)
        assert (stmt.operation, stmt.operands) == ("", "INDD=A")

    def test_split_operands(self) -> None:
        assert split_operands("A=(1,2),B='X,Y',C") == ["A=(1,2)", "B='X,Y'", "C"]


class TestIebcopyControlStatements:
    JCL = (
        "//J JOB 1\n"
        "//S1 EXEC PGM=IEBCOPY\n"
        "//INLIB DD DSN=IN.LIB,DISP=SHR\n"
        "//OUTLIB DD DSN=OUT.LIB,DISP=OLD\n"
        "//SYSUT1 DD DSN=SPILL.X,DISP=(NEW,DELETE)\n"
        "//SYSIN DD *\n"
    )

    def test_copy_uses_indd_outdd_not_spill_file(self) -> None:
        r = _analyse(self.JCL + "  COPY OUTDD=OUTLIB,INDD=INLIB\n/*\n")
        assert r.summary == "IEBCOPY: copy INLIB -> OUTLIB"
        assert r.notes == ["reads IN.LIB", "writes OUT.LIB"]
        assert [(e.dd_name, e.action) for e in r.dataset_events] == [
            ("INLIB", "OPEN_SHARED"),
            ("OUTLIB", "OPEN_EXCLUSIVE"),
        ]
        assert not any("SPILL" in n for n in r.notes)

    def test_abbreviations_lists_and_replace_option(self) -> None:
        src = (
            "//J JOB 1\n"
            "//S1 EXEC PGM=IEBCOPY\n"
            "//A DD DSN=A.LIB,DISP=SHR\n"
            "//B DD DSN=B.LIB,DISP=SHR\n"
            "//  DD DSN=B2.LIB,DISP=SHR\n"
            "//O DD DSN=O.LIB,DISP=OLD\n"
            "//P DD DSN=P.LIB,DISP=OLD\n"
            "//SYSIN DD *\n"
            "STEP1 C O=O,I=((A,R),B)   COPY TWO LIBRARIES\n"
            "  COPYMOD OUTDD=P,\n"
            "          INDD=(A,(B,R))\n"
            "  CG OUTDD=O,INDD=A\n"
            "/*\n"
        )
        r = _analyse(src)
        assert r.summary == ("IEBCOPY: copy A,B -> O; copymod A,B -> P; copygrp A -> O")
        assert r.notes == [
            "reads A.LIB",
            "reads B.LIB",
            "reads B2.LIB",
            "writes O.LIB",
            "writes P.LIB",
        ]

    def test_separate_indd_statement_and_member_lists(self) -> None:
        r = _analyse(
            self.JCL + "  COPY OUTDD=OUTLIB\n"
            "  INDD=INLIB\n"
            "  SELECT MEMBER=(M1,(M2,NEWM2,R))\n"
            "  EXCLUDE M=X1\n"
            "/*\n"
        )
        assert r.summary == "IEBCOPY: copy INLIB -> OUTLIB"
        assert r.notes == [
            "reads IN.LIB",
            "writes OUT.LIB",
            "select members M1,M2",
            "exclude members X1",
        ]

    def test_missing_dds_marked(self) -> None:
        r = _analyse(self.JCL + "  COPY LIST=NO\n/*\n")
        assert r.summary == "IEBCOPY: copy ? -> ?"
        assert r.notes == []

    def test_no_control_statements_copies_sysut1_to_sysut2(self) -> None:
        r = _analyse(
            "//J JOB 1\n"
            "//S1 EXEC PGM=IEBCOPY\n"
            "//SYSUT1 DD DSN=IN.LIB,DISP=SHR\n"
            "//SYSUT2 DD DSN=OUT.LIB,DISP=OLD\n"
        )
        assert r.summary == "IEBCOPY: copy SYSUT1 -> SYSUT2"
        assert r.notes == ["reads IN.LIB", "writes OUT.LIB"]

    def test_only_member_list_falls_back(self) -> None:
        r = _analyse(
            "//J JOB 1\n"
            "//S1 EXEC PGM=IEBCOPY\n"
            "//SYSUT1 DD DSN=IN.LIB,DISP=SHR\n"
            "//SYSUT2 DD DSN=OUT.LIB,DISP=OLD\n"
            "//SYSIN DD *\n"
            "* nothing but a comment\n"
            "  SELECT MEMBER=A\n"
            "/*\n"
        )
        assert r.summary == "IEBCOPY: copy SYSUT1 -> SYSUT2"


class TestIebgenerConcatenation:
    def test_every_sysut1_dataset_reported(self) -> None:
        r = _analyse(
            "//J JOB 1\n"
            "//S1 EXEC PGM=IEBGENER\n"
            "//SYSUT1 DD DSN=A.ONE,DISP=SHR\n"
            "//       DD DSN=A.TWO,DISP=SHR\n"
            "//SYSUT2 DD DSN=B.OUT,DISP=(NEW,CATLG)\n"
            "//SYSIN DD DUMMY\n"
        )
        assert r.notes == ["reads A.ONE", "reads A.TWO", "writes B.OUT"]
        assert [e.dd_name for e in r.dataset_events] == ["SYSUT1", "SYSUT1", "SYSUT2"]


class TestSortInputs:
    def test_merge_inputs_reported(self) -> None:
        r = _sort(
            "  MERGE FIELDS=(1,10,CH,A)\n",
            "//SORTIN01 DD DSN=M.ONE,DISP=SHR\n"
            "//SORTIN02 DD DSN=M.TWO,DISP=SHR\n"
            "//         DD DSN=M.TWO2,DISP=SHR\n"
            "//SORTOUT DD DSN=M.OUT,DISP=(NEW,CATLG)\n",
        )
        assert r.notes == [
            "MERGE FIELDS",
            "input: M.ONE",
            "input: M.TWO",
            "input: M.TWO2",
            "output: M.OUT",
        ]

    def test_sortin_concatenation_and_non_input_dds(self) -> None:
        r = _sort(
            "  SORT FIELDS=(1,5,CH,A)\n",
            "//SORTIN DD DSN=I.ONE,DISP=SHR\n"
            "//       DD DSN=I.TWO,DISP=SHR\n"
            "//SORTIN100 DD DSN=NOT.INPUT,DISP=SHR\n"
            "//SORTWK01 DD UNIT=SYSDA,SPACE=(CYL,1)\n",
        )
        assert r.notes == ["SORT FIELDS", "input: I.ONE", "input: I.TWO"]


class TestSortRemarks:
    def test_remark_is_not_a_keyword(self) -> None:
        r = _sort("  SORT FIELDS=(1,5,CH,A)   OUTREC NOT USED\n")
        assert r.notes == ["SORT FIELDS"]

    def test_continued_statement_remark(self) -> None:
        r = _sort(
            "  SORT FIELDS=(1,5,CH,A),   INCLUDE OMIT\n"
            "       EQUALS               OUTREC\n"
            "  INCLUDE COND=(1,1,CH,EQ,C'X OMIT')\n"
        )
        assert r.notes == ["SORT FIELDS", "INCLUDE filter"]

    def test_outfil_operands_still_reported(self) -> None:
        r = _sort(
            "  SORT FIELDS=(1,5,CH,A)\n"
            "  OUTFIL FNAMES=OUT1,INCLUDE=(1,1,CH,EQ,C'A'),OUTREC=(1,10)\n"
        )
        assert r.notes == ["SORT FIELDS", "INCLUDE filter", "OUTREC reformat"]

    def test_comment_card(self) -> None:
        r = _sort("* OMIT COND=(1,1,CH,EQ,C'X')\n  SORT FIELDS=(1,5,CH,A)\n")
        assert r.notes == ["SORT FIELDS"]


class TestSortCopy:
    @pytest.mark.parametrize(
        "sysin",
        [
            "  SORT FIELDS=COPY\n",
            "  SORT FIELDS=(COPY)\n",
            "  OPTION COPY\n",
            "  OPTION EQUALS,COPY\n",
            "  MERGE FIELDS=COPY\n",
        ],
    )
    def test_copy_reported(self, sysin: str) -> None:
        r = _sort(
            sysin,
            "//SORTIN DD DSN=C.IN,DISP=SHR\n//SORTOUT DD DSN=C.OUT,DISP=OLD\n",
        )
        assert r.notes == ["COPY", "input: C.IN", "output: C.OUT"]
        assert r.summary == "SORT: copy with 3 control clauses"

    def test_option_without_copy_is_not_a_copy(self) -> None:
        r = _sort("  OPTION EQUALS\n  SORT FIELDS=(1,5,CH,A)\n")
        assert r.notes == ["SORT FIELDS"]
        assert r.summary.startswith("SORT: sort/merge")

    def test_no_control_statements(self) -> None:
        r = _sort("")
        assert r.summary == "SORT with no recognised control statements"
