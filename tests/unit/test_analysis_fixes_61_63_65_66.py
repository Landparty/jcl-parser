"""Regression tests for issues #61, #63, #65 (item 3) and #66."""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.condition_parser import parse_condition
from jclparser.rc_analysis import compute_feasible_paths

pytestmark = pytest.mark.unit

_NINE = "ABCDEFGHI"


def _nine_step_job(negate: bool = False, *, with_else: bool = False) -> str:
    """Nine steps ASTEP..ISTEP, then an IF naming all nine (issue #61)."""
    src = "//J JOB (A)\n" + "".join(f"//{c}STEP EXEC PGM=X\n" for c in _NINE)
    src += (
        f"// IF {'¬(' if negate else ''}ASTEP.RUN & (BSTEP.RC=0 | CSTEP.RC=0 |\n"
        "//     DSTEP.RC=0 | ESTEP.RC=0 | FSTEP.RC=0 | GSTEP.RC=0 |\n"
        f"//     HSTEP.RC=0 | ISTEP.RC=0){')' if negate else ''} THEN\n"
        "//T EXEC PGM=Y\n"
    )
    if with_else:
        src += "// ELSE\n//E EXEC PGM=Z\n"
    return src + "// ENDIF\n"


# ---------------------------------------------------------------------------
# #61: an IF naming more than 8 steps and testing .RUN
# ---------------------------------------------------------------------------


class TestRunConditionNineSteps:
    def test_run_of_unknown_step_is_unknown(self):
        assert parse_condition("ASTEP.RUN").evaluate({}) is None
        assert parse_condition("NOT ASTEP.RUN").evaluate({}) is None

    def test_unknown_run_combines_three_valued(self):
        ast = parse_condition("ASTEP.RUN & BSTEP.RC=0")
        assert ast.evaluate({"BSTEP": (0, False)}) is None
        assert ast.evaluate({"BSTEP": (4, False)}) is False
        ast = parse_condition("ASTEP.RUN | BSTEP.RC=0")
        assert ast.evaluate({"BSTEP": (0, False)}) is True
        assert ast.evaluate({"BSTEP": (4, False)}) is None

    def test_then_branch_reachable(self):
        report = compute_feasible_paths(parse_jcl(_nine_step_job()))
        assert report.unreachable_steps == []
        assert report.contradictory_conditions == []

    def test_negated_run_else_branch_not_always_skipped(self):
        report = compute_feasible_paths(
            parse_jcl(_nine_step_job(negate=True, with_else=True))
        )
        # ASTEP always runs, so the guard is false whenever some RC is 0:
        # ELSE is reachable, and THEN (every RC non-zero) is too.
        assert report.always_skipped == []
        assert report.unreachable_steps == []
