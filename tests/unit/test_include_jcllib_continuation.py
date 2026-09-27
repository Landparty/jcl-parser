"""INCLUDE members are found in libraries named on JCLLIB continuation lines,
and an INCLUDE that cannot be found is reported instead of silently dropped.
"""

import pytest

from jclparser import parse_jcl
from jclparser._statement_parser import _extract_jcllib_order


@pytest.fixture
def libs(tmp_path):
    (tmp_path / "MY.PROCLIB").mkdir()
    other = tmp_path / "OTHER.LIB"
    other.mkdir()
    (other / "MEM2.jcl").write_text("//STEPY    EXEC PGM=FROMOTHR\n")
    return tmp_path


@pytest.mark.unit
class TestIncludeJcllibContinuation:
    @pytest.mark.parametrize(
        ("jcl", "expected"),
        [
            ("//L JCLLIB ORDER=(A.LIB,\n//             B.LIB)\n", ["A.LIB", "B.LIB"]),
            (
                "//L JCLLIB ORDER=(A.LIB,   FIRST\n//*  NOTE\n//   B.LIB,\n//   C.LIB)\n",
                ["A.LIB", "B.LIB", "C.LIB"],
            ),
            ("//L JCLLIB ORDER=(A.LIB,B.LIB)   COMMENT (X)\n", ["A.LIB", "B.LIB"]),
            ("// JCLLIB ORDER=A.LIB\n", ["A.LIB"]),
            ("//L JCLLIB ORDER=(A.LIB,\n//S EXEC PGM=X\n", ["A.LIB"]),
        ],
    )
    def test_prescan_follows_continuations(self, jcl, expected):
        assert _extract_jcllib_order(jcl) == expected

    def test_member_in_continued_library_is_included(self, libs):
        jcl = (
            "//J        JOB (A),'B'\n"
            "//LIBS     JCLLIB ORDER=(MY.PROCLIB,\n"
            "//             OTHER.LIB)\n"
            "//         INCLUDE MEMBER=MEM2\n"
            "//S2       EXEC PGM=X\n"
        )
        job = parse_jcl(jcl, proc_base_path=libs)
        assert [(s.name, s.program) for s in job.steps] == [
            ("STEPY", "FROMOTHR"),
            ("S2", "X"),
        ]
        assert job.includes == ["MEM2"]
        assert not job.warnings

    def test_missing_member_warns(self, libs):
        jcl = "//J        JOB (A),'B'\n//         INCLUDE MEMBER=NOPE\n//S EXEC PGM=X\n"
        job = parse_jcl(jcl, proc_base_path=libs)
        assert job.includes == ["NOPE"]
        assert any("INCLUDE member NOPE not found" in w for w in job.warnings)
