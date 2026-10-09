"""A comment may follow a comma that interrupts a parenthesised list."""

import pytest

from jclparser import parse_jcl


@pytest.mark.unit
class TestCommentInParenthesisedList:
    def test_comment_after_comma_inside_parens(self):
        job = parse_jcl(
            "//J JOB 1\n//S EXEC PGM=X\n"
            "//D1 DD DSN=A.B,DISP=(NEW,     COMMENT\n"
            "//             CATLG)\n"
        )
        assert job.steps[0].dd_statements[0].parameters["DISP"] == ["NEW", "CATLG"]

    def test_comment_on_record_continuing_a_paren_list(self):
        job = parse_jcl(
            "//J JOB 1\n//S EXEC PGM=X\n"
            "//D1 DD DSN=A.B,SPACE=(CYL,\n"
            "//             (1,1)),          PRIMARY AND SECONDARY\n"
            "//             UNIT=SYSDA\n"
        )
        params = job.steps[0].dd_statements[0].parameters
        assert params["SPACE"] == ["CYL", "(1,1)"]
        assert params["UNIT"] == "SYSDA"

    def test_jcllib_order_matches_prescan(self):
        job = parse_jcl(
            "//J JOB 1\n//L JCLLIB ORDER=(A.LIB,   FIRST\n//*  NOTE\n"
            "//   B.LIB,\n//   C.LIB)\n//S EXEC PGM=X\n"
        )
        assert job.jcllib_order == ["A.LIB", "B.LIB", "C.LIB"]

    def test_blank_inside_closed_list_still_tolerated(self):
        job = parse_jcl("//J JOB 1\n//S EXEC PGM=X\n//D1 DD DISP=(NEW, CATLG)\n")
        assert job.steps[0].dd_statements[0].parameters["DISP"] == ["NEW", "CATLG"]
