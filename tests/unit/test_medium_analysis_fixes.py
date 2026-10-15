"""Regression tests for the severity:medium analysis fixes.

#101 condition precedence (see test_condition_parser_edge_cases.py),
#108 lifecycle and step COND=, #109 duplicate IF branches,
#110 SORT OUTFIL / JOINKEYS datasets, #111 FTP INPUT DD.
"""

from __future__ import annotations

import pytest

import jclparser as jp
from jclparser.rc_analysis import compute_feasible_paths

pytestmark = pytest.mark.unit


def _duplicates(src: str) -> list[tuple[int, str]]:
    return compute_feasible_paths(jp.parse_jcl(src)).duplicate_if_branches


class TestDuplicateIfBranches:
    """#109: a nested IF repeating its parent's text is not always redundant."""

    def test_unqualified_rc_with_step_between_is_not_duplicate(self):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// IF RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ELSE\n"
            "//S4 EXEC PGM=D\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == []

    @pytest.mark.parametrize("cond", ["ABEND", "NOT RUN", "RC = 0 & S1.RC = 0"])
    def test_other_unqualified_atoms_with_step_between(self, cond):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            f"// IF {cond} THEN\n"
            "//S2 EXEC PGM=B\n"
            f"// IF {cond} THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == []

    def test_unqualified_rc_with_no_step_between_is_duplicate(self):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF RC = 0 THEN\n"
            "// IF RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == [(4, "RC=0")]

    def test_qualified_rc_with_steps_between_is_duplicate(self):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// IF S1.RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == [(5, "S1.RC=0")]

    def test_qualified_step_running_between_is_not_duplicate(self):
        # S2 has not run at the outer IF but has at the inner one.
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF S2.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// IF S2.RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == []

    def test_sibling_ifs_are_not_compared(self):
        src = (
            "//J JOB\n"
            "//S1 EXEC PGM=A\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// ENDIF\n"
            "// IF S1.RC = 0 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
        )
        assert _duplicates(src) == []
