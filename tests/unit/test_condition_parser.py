"""
Tests for the JCL IF condition parser (condition_parser.py).
"""

from jclparser.condition_parser import (
    AbendCondition,
    AndCondition,
    NotCondition,
    OrCondition,
    ReturnCodeCondition,
    RunCondition,
    parse_condition,
)

# ---------------------------------------------------------------------------
# parse_condition — structural tests
# ---------------------------------------------------------------------------


class TestParseConditionStructure:
    def test_simple_rc_eq(self):
        node = parse_condition("STEP1.RC EQ 0")
        assert isinstance(node, ReturnCodeCondition)
        assert node.step_name == "STEP1"
        assert node.operator == "EQ"
        assert node.value == 0

    def test_simple_rc_gt(self):
        node = parse_condition("STEP2.RC GT 4")
        assert isinstance(node, ReturnCodeCondition)
        assert node.step_name == "STEP2"
        assert node.operator == "GT"
        assert node.value == 4

    def test_rc_without_step_name(self):
        """Omitted step name refers to the last executed step."""
        node = parse_condition("RC LT 8")
        assert isinstance(node, ReturnCodeCondition)
        assert node.step_name is None
        assert node.operator == "LT"
        assert node.value == 8

    def test_abend_with_step(self):
        node = parse_condition("STEP3.ABEND")
        assert isinstance(node, AbendCondition)
        assert node.step_name == "STEP3"

    def test_abend_without_step(self):
        node = parse_condition("ABEND")
        assert isinstance(node, AbendCondition)
        assert node.step_name is None

    def test_run_with_step(self):
        node = parse_condition("MYSTEP.RUN")
        assert isinstance(node, RunCondition)
        assert node.step_name == "MYSTEP"

    def test_not_condition(self):
        node = parse_condition("NOT STEP1.ABEND")
        assert isinstance(node, NotCondition)
        assert isinstance(node.operand, AbendCondition)
        assert node.operand.step_name == "STEP1"

    def test_and_condition(self):
        node = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        assert isinstance(node, AndCondition)
        assert isinstance(node.left, ReturnCodeCondition)
        assert isinstance(node.right, ReturnCodeCondition)

    def test_or_condition(self):
        node = parse_condition("STEP1.ABEND OR STEP2.ABEND")
        assert isinstance(node, OrCondition)
        assert isinstance(node.left, AbendCondition)
        assert isinstance(node.right, AbendCondition)

    def test_compound_and_or(self):
        node = parse_condition("STEP1.RC EQ 0 AND NOT STEP2.ABEND")
        assert isinstance(node, AndCondition)
        assert isinstance(node.left, ReturnCodeCondition)
        assert isinstance(node.right, NotCondition)

    def test_parenthesized_or(self):
        node = parse_condition("(STEP1.RC EQ 0) OR (STEP2.RC EQ 0)")
        assert isinstance(node, OrCondition)

    def test_nested_not_parens(self):
        node = parse_condition("NOT (STEP1.RC EQ 0)")
        assert isinstance(node, NotCondition)
        assert isinstance(node.operand, ReturnCodeCondition)

    def test_unparseable_returns_none(self):
        assert parse_condition("THIS IS GARBAGE @@@@") is None

    def test_empty_returns_none(self):
        assert parse_condition("") is None
        assert parse_condition("   ") is None

    def test_none_input_returns_none(self):
        assert parse_condition(None) is None

    # ── Symbolic operator forms ─────────────────────────────────────────────

    def test_symbol_eq(self):
        node = parse_condition("STEP1.RC = 0")
        assert isinstance(node, ReturnCodeCondition)
        assert node.operator == "EQ"

    def test_symbol_ne_bang(self):
        node = parse_condition("STEP1.RC != 4")
        assert isinstance(node, ReturnCodeCondition)
        assert node.operator == "NE"

    def test_symbol_ne_caret(self):
        node = parse_condition("STEP1.RC ^= 4")
        assert isinstance(node, ReturnCodeCondition)
        assert node.operator == "NE"

    def test_symbol_lt(self):
        node = parse_condition("STEP1.RC < 8")
        assert isinstance(node, ReturnCodeCondition)
        assert node.operator == "LT"

    def test_symbol_le(self):
        node = parse_condition("STEP1.RC <= 4")
        assert isinstance(node, ReturnCodeCondition)
        assert node.operator == "LE"

    def test_symbol_ge(self):
        node = parse_condition("STEP1.RC >= 0")
        assert isinstance(node, ReturnCodeCondition)
        assert node.operator == "GE"


# ---------------------------------------------------------------------------
# evaluate() tests
# ---------------------------------------------------------------------------


class TestConditionEvaluate:
    def test_rc_eq_true(self):
        node = parse_condition("STEP1.RC EQ 0")
        assert node.evaluate({"STEP1": (0, False)}) is True

    def test_rc_eq_false(self):
        node = parse_condition("STEP1.RC EQ 0")
        assert node.evaluate({"STEP1": (4, False)}) is False

    def test_rc_lt(self):
        node = parse_condition("STEP1.RC LT 8")
        assert node.evaluate({"STEP1": (4, False)}) is True
        assert node.evaluate({"STEP1": (8, False)}) is False

    def test_rc_gt(self):
        node = parse_condition("STEP1.RC GT 0")
        assert node.evaluate({"STEP1": (4, False)}) is True
        assert node.evaluate({"STEP1": (0, False)}) is False

    def test_rc_ne(self):
        node = parse_condition("STEP1.RC NE 0")
        assert node.evaluate({"STEP1": (4, False)}) is True
        assert node.evaluate({"STEP1": (0, False)}) is False

    def test_rc_le(self):
        node = parse_condition("STEP1.RC LE 4")
        assert node.evaluate({"STEP1": (4, False)}) is True
        assert node.evaluate({"STEP1": (5, False)}) is False

    def test_rc_ge(self):
        node = parse_condition("STEP1.RC GE 4")
        assert node.evaluate({"STEP1": (4, False)}) is True
        assert node.evaluate({"STEP1": (3, False)}) is False

    def test_abend_true(self):
        node = parse_condition("STEP1.ABEND")
        assert node.evaluate({"STEP1": (0, True)}) is True

    def test_abend_false(self):
        node = parse_condition("STEP1.ABEND")
        assert node.evaluate({"STEP1": (0, False)}) is False

    def test_run_present(self):
        node = parse_condition("STEP1.RUN")
        assert node.evaluate({"STEP1": (0, False)}) is True

    def test_run_absent(self):
        node = parse_condition("STEP1.RUN")
        assert node.evaluate({}) is False

    def test_not_true(self):
        node = parse_condition("NOT STEP1.ABEND")
        assert node.evaluate({"STEP1": (0, False)}) is True
        assert node.evaluate({"STEP1": (0, True)}) is False

    def test_and_both_true(self):
        node = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        assert node.evaluate({"STEP1": (0, False), "STEP2": (0, False)}) is True

    def test_and_one_false(self):
        node = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        assert node.evaluate({"STEP1": (0, False), "STEP2": (4, False)}) is False

    def test_or_one_true(self):
        node = parse_condition("STEP1.ABEND OR STEP2.ABEND")
        assert node.evaluate({"STEP1": (0, True), "STEP2": (0, False)}) is True

    def test_or_both_false(self):
        node = parse_condition("STEP1.ABEND OR STEP2.ABEND")
        assert node.evaluate({"STEP1": (0, False), "STEP2": (0, False)}) is False

    def test_missing_step_returns_none(self):
        node = parse_condition("STEP1.RC EQ 0")
        assert node.evaluate({}) is None

    def test_and_short_circuits_on_false(self):
        """AND returns False even if one side's step is missing."""
        node = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        # STEP1 didn't run (None) but STEP2 clearly failed → still False
        assert node.evaluate({"STEP2": (4, False)}) is False

    def test_or_short_circuits_on_true(self):
        """OR returns True even if one side's step is missing."""
        node = parse_condition("STEP1.ABEND OR STEP2.RC EQ 0")
        assert node.evaluate({"STEP1": (0, True)}) is True

    def test_rc_without_step_uses_last(self):
        node = parse_condition("RC EQ 0")
        assert node.evaluate({"STEP1": (0, False)}) is True
        assert node.evaluate({"STEP1": (4, False)}) is False

    def test_complex_compound(self):
        node = parse_condition("STEP1.RC EQ 0 AND NOT STEP2.ABEND")
        assert node.evaluate({"STEP1": (0, False), "STEP2": (0, False)}) is True
        assert node.evaluate({"STEP1": (0, False), "STEP2": (0, True)}) is False
        assert node.evaluate({"STEP1": (4, False), "STEP2": (0, False)}) is False
