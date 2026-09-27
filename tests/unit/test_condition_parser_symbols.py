"""IF conditions with symbolic operators and TRUE/FALSE tests parse completely.

The parser used to stop at the first token it did not understand and return
the prefix, so ``&`` / ``|`` clauses vanished and a lone ``¬`` was dropped.
"""

import pytest

from jclparser import parse_jcl
from jclparser.condition_parser import (
    AbendCondition,
    AndCondition,
    NotCondition,
    OrCondition,
    ReturnCodeCondition,
    RunCondition,
    parse_condition,
)


@pytest.mark.unit
class TestSymbolicOperators:
    def test_ampersand_is_and(self):
        node = parse_condition("STEP1.RC = 0 & STEP2.RC = 0")
        assert isinstance(node, AndCondition)
        assert node.evaluate({"STEP1": (0, False), "STEP2": (4, False)}) is False

    def test_bar_is_or(self):
        node = parse_condition("RC > 4 | RC < 0")
        assert isinstance(node, OrCondition)
        assert isinstance(node.right, ReturnCodeCondition)
        assert node.right.operator == "LT"

    @pytest.mark.parametrize("sym", ["¬", "^", "~"])
    def test_lone_not_symbol_negates(self, sym):
        node = parse_condition(f"{sym}STEP1.RUN")
        assert node == NotCondition(RunCondition(step_name="STEP1"))
        assert node.evaluate({"STEP1": (0, False)}) is False

    def test_not_equal_operator_still_a_comparison(self):
        node = parse_condition("RC ¬= 0")
        assert node == ReturnCodeCondition(step_name=None, operator="NE", value=0)


@pytest.mark.unit
class TestTrueFalseTests:
    def test_abend_false_is_negated_abend(self):
        node = parse_condition("(RC <= 4 & ABEND = FALSE)")
        assert isinstance(node, AndCondition)
        assert node.right == NotCondition(AbendCondition(step_name=None))

    def test_run_true_is_plain_run(self):
        assert parse_condition("STEP1.RUN = TRUE") == RunCondition(step_name="STEP1")

    def test_abend_ne_true_is_negated(self):
        node = parse_condition("STEP1.ABEND ¬= TRUE")
        assert node == NotCondition(AbendCondition(step_name="STEP1"))

    def test_abend_eq_garbage_is_unparseable(self):
        assert parse_condition("ABEND = MAYBE") is None


@pytest.mark.unit
class TestNoSilentTruncation:
    @pytest.mark.parametrize(
        "cond",
        [
            "STEP1.ABENDCC = U0100",
            "RC GT &MAXRC",
            "STEP1.RC EQ 0 STEP2.RC EQ 0",
            "(RC = 0) RC = 4",
            "(RC = 0 RC = 4",
        ],
    )
    def test_unparseable_returns_none(self, cond):
        assert parse_condition(cond) is None

    def test_conditional_block_keeps_full_ast(self):
        jcl = (
            "//J        JOB (ACCT),'T'\n"
            "//S1       EXEC PGM=A\n"
            "//         IF (S1.RC <= 4 & ¬S1.ABEND) THEN\n"
            "//S2       EXEC PGM=B\n"
            "//         ENDIF\n"
        )
        block = parse_jcl(jcl).conditionals[0]
        assert isinstance(block.condition_ast, AndCondition)
        assert block.condition_ast.right == NotCondition(AbendCondition("S1"))


@pytest.mark.unit
class TestStepLessEvaluation:
    def test_rc_is_highest_prior_rc(self):
        node = parse_condition("RC <= 4")
        assert node.evaluate({"S1": (8, False), "S2": (0, False)}) is False

    def test_abend_is_any_prior_abend(self):
        node = parse_condition("ABEND")
        assert node.evaluate({"S1": (0, True), "S2": (0, False)}) is True
