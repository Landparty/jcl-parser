"""
Edge case tests for the condition parser.

Covers deeply nested conditions, special operators, quoted strings
in conditions, and malformed expressions.
"""

import pytest

from jclparser.condition_parser import (
    AbendCondition,
    AndCondition,
    NotCondition,
    OrCondition,
    ReturnCodeCondition,
    parse_condition,
)


@pytest.mark.unit
class TestDeeplyNestedConditions:
    """Test parsing of deeply nested conditional expressions."""

    def test_three_level_nesting(self):
        """Parse condition with 3 levels of parenthetical nesting."""
        result = parse_condition("(STEP1.RC EQ 0 AND (STEP2.RC EQ 0 OR STEP3.RC EQ 4))")
        assert result is not None

    def test_not_with_nested_and_or(self):
        """Parse NOT (A AND (B OR C)) pattern."""
        result = parse_condition(
            "NOT (STEP1.RC EQ 0 AND (STEP2.RC EQ 0 OR STEP3.RC EQ 4))"
        )
        assert result is not None

    def test_multiple_or_branches(self):
        """Parse condition with multiple OR branches."""
        result = parse_condition("STEP1.RC EQ 0 OR STEP2.RC EQ 0 OR STEP3.RC EQ 0")
        assert result is not None

    def test_mixed_and_or_precedence(self):
        """AND and OR rank equally, left to right (IBM JCL Reference, #101)."""
        result = parse_condition("S1.RC = 0 | S1.RC = 4 & S2.ABEND")
        assert result == AndCondition(
            OrCondition(
                ReturnCodeCondition("S1", "EQ", 0),
                ReturnCodeCondition("S1", "EQ", 4),
            ),
            AbendCondition("S2"),
        )
        # C-style precedence would read ``RC=0 | (RC=4 & ABEND)`` -> True.
        assert result.evaluate({"S1": (0, False), "S2": (0, False)}) is False

    def test_and_then_or_left_to_right(self):
        """``A & B | C`` is ``(A & B) | C`` -- the same either way, but pinned."""
        result = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0 OR STEP3.RC EQ 4")
        assert isinstance(result, OrCondition)
        assert isinstance(result.left, AndCondition)

    def test_parentheses_still_group(self):
        result = parse_condition("S1.RC = 0 | (S1.RC = 4 & S2.ABEND)")
        assert isinstance(result, OrCondition)
        assert isinstance(result.right, AndCondition)
        assert result.evaluate({"S1": (0, False), "S2": (0, False)}) is True

    def test_deeply_nested_with_not(self):
        """Double-NOT nests two NotCondition nodes."""
        result = parse_condition("NOT NOT STEP1.RC EQ 0")
        assert isinstance(result, NotCondition)
        assert isinstance(result.operand, NotCondition)
        assert result.evaluate({"STEP1": (0, False)}) is True


@pytest.mark.unit
class TestSpecialOperators:
    """Test special/symbolic RC comparison operators."""

    def test_not_equal_caret(self):
        """Parse ^= (not equal) operator."""
        result = parse_condition("STEP1.RC ^= 0")
        assert result is not None

    def test_not_equal_tilde(self):
        """Parse ~= (not equal) operator."""
        result = parse_condition("STEP1.RC ~= 0")
        assert result is not None

    def test_less_than_or_equal(self):
        """Parse <= operator."""
        result = parse_condition("STEP1.RC <= 4")
        assert result is not None

    def test_greater_than_or_equal(self):
        """Parse >= operator."""
        result = parse_condition("STEP1.RC >= 8")
        assert result is not None

    def test_not_equal_angle_brackets(self):
        """Parse <> (not equal) operator."""
        result = parse_condition("STEP1.RC <> 0")
        assert result is not None

    def test_symbolic_eq(self):
        """Parse = (equals) operator."""
        result = parse_condition("STEP1.RC = 0")
        assert result is not None

    def test_symbolic_lt(self):
        """Parse < operator."""
        result = parse_condition("STEP1.RC < 4")
        assert result is not None

    def test_symbolic_gt(self):
        """Parse > operator."""
        result = parse_condition("STEP1.RC > 0")
        assert result is not None


@pytest.mark.unit
class TestQuotedStringsInConditions:
    """Test conditions containing quoted string literals."""

    def test_condition_with_single_quotes(self):
        """A quoted, non-numeric RC value is unparseable (not read as 0)."""
        result = parse_condition("STEP1.RC EQ 'VALUE'")
        assert result is None

    def test_escaped_quote_in_condition(self):
        """Escaped quotes ('') inside a quoted string tokenize without crashing."""
        result = parse_condition("STEP1.RC EQ 'O''BRIEN'")
        assert result is None


@pytest.mark.unit
class TestMalformedConditions:
    """Test that malformed conditions don't crash the parser."""

    def test_empty_condition(self):
        """Empty string returns None."""
        result = parse_condition("")
        assert result is None

    def test_only_whitespace(self):
        """Whitespace-only string returns None."""
        result = parse_condition("   ")
        assert result is None

    def test_unmatched_open_paren(self):
        """Missing close paren is tolerated — parser still produces an AST."""
        result = parse_condition("(STEP1.RC EQ 0")
        assert result is not None

    def test_extra_close_paren(self):
        """Extra close paren at end is tolerated."""
        result = parse_condition("STEP1.RC EQ 0)")
        assert result is not None

    def test_double_operator(self):
        """Two operators in a row are unparseable."""
        result = parse_condition("STEP1.RC EQ GT 0")
        assert result is None

    def test_trailing_and(self):
        """Condition ending with AND keyword."""
        result = parse_condition("STEP1.RC EQ 0 AND")
        assert result is None

    def test_trailing_or(self):
        """Condition ending with OR keyword."""
        result = parse_condition("STEP1.RC EQ 0 OR")
        assert result is None

    def test_leading_and(self):
        """Condition starting with AND keyword returns None."""
        result = parse_condition("AND STEP1.RC EQ 0")
        assert result is None

    def test_just_a_number(self):
        """A bare number tests nothing: unparseable, not ``RC EQ 4`` (#86)."""
        assert parse_condition("4") is None
        assert parse_condition("4 AND RC = 0") is None
        assert parse_condition("S1.4") is None

    def test_nonsense_text(self):
        """Completely invalid text returns None."""
        result = parse_condition("XYZZY PLUGH")
        assert result is None


@pytest.mark.unit
class TestAtomTypes:
    """Test all atom types in conditions."""

    def test_abend_without_step(self):
        """Parse bare ABEND atom."""
        result = parse_condition("ABEND")
        assert result is not None

    def test_abend_with_step(self):
        """Parse STEP1.ABEND atom."""
        result = parse_condition("STEP1.ABEND")
        assert result is not None

    def test_run_without_step(self):
        """Parse bare RUN atom."""
        result = parse_condition("RUN")
        assert result is not None

    def test_run_with_step(self):
        """Parse STEP1.RUN atom."""
        result = parse_condition("STEP1.RUN")
        assert result is not None

    def test_abendcc(self):
        """ABENDCC is currently unsupported and should not parse."""
        result = parse_condition("STEP1.ABENDCC EQ S0C4")
        assert result is None

    def test_rc_without_step_name(self):
        """Parse bare RC comparison (no step prefix)."""
        result = parse_condition("RC EQ 0")
        assert result is not None

    def test_rc_with_step_name(self):
        """Parse STEP.RC comparison."""
        result = parse_condition("STEP1.RC EQ 0")
        assert result is not None

    def test_complex_boolean_with_mixed_atoms(self):
        """Mix RC comparisons, ABEND, and RUN in one expression."""
        result = parse_condition("STEP1.RC EQ 0 AND STEP2.ABEND OR STEP3.RUN")
        assert result is not None


@pytest.mark.unit
class TestConditionEvaluation:
    """Test evaluation of parsed conditions."""

    def test_evaluate_simple_rc_true(self):
        """Evaluate STEP1.RC EQ 0 with RC=0."""
        result = parse_condition("STEP1.RC EQ 0")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (0, False)}) is True

    def test_evaluate_simple_rc_false(self):
        """Evaluate STEP1.RC EQ 0 with RC=4."""
        result = parse_condition("STEP1.RC EQ 0")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (4, False)}) is False

    def test_evaluate_ne_operator(self):
        """Evaluate NE operator."""
        result = parse_condition("STEP1.RC NE 0")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (4, False)}) is True
            assert result.evaluate({"STEP1": (0, False)}) is False

    def test_evaluate_gt_operator(self):
        """Evaluate GT operator."""
        result = parse_condition("STEP1.RC GT 4")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (8, False)}) is True
            assert result.evaluate({"STEP1": (4, False)}) is False

    def test_evaluate_lt_operator(self):
        """Evaluate LT operator."""
        result = parse_condition("STEP1.RC LT 4")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (0, False)}) is True
            assert result.evaluate({"STEP1": (4, False)}) is False

    def test_evaluate_le_operator(self):
        """Evaluate LE operator."""
        result = parse_condition("STEP1.RC LE 4")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (4, False)}) is True
            assert result.evaluate({"STEP1": (8, False)}) is False

    def test_evaluate_ge_operator(self):
        """Evaluate GE operator."""
        result = parse_condition("STEP1.RC GE 4")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (4, False)}) is True
            assert result.evaluate({"STEP1": (0, False)}) is False

    def test_evaluate_and_true(self):
        """Evaluate AND with both sides true."""
        result = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (0, False), "STEP2": (0, False)}) is True

    def test_evaluate_and_false(self):
        """Evaluate AND with one side false."""
        result = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (0, False), "STEP2": (4, False)}) is False

    def test_evaluate_or_true(self):
        """Evaluate OR with one side true."""
        result = parse_condition("STEP1.RC EQ 0 OR STEP2.RC EQ 0")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (4, False), "STEP2": (0, False)}) is True

    def test_evaluate_not(self):
        """Evaluate NOT condition."""
        result = parse_condition("NOT STEP1.RC EQ 0")
        assert result is not None
        if hasattr(result, "evaluate"):
            assert result.evaluate({"STEP1": (4, False)}) is True
            assert result.evaluate({"STEP1": (0, False)}) is False


@pytest.mark.unit
class TestValueFirstComparison:
    """``value op RC``: the operator is mirrored, never kept as written."""

    @pytest.mark.parametrize(
        ("text", "operator"),
        [
            ("4 LT RC", "GT"),
            ("4 GT RC", "LT"),
            ("4 LE RC", "GE"),
            ("4 GE RC", "LE"),
            ("4 EQ RC", "EQ"),
            ("4 NE RC", "NE"),
            ("4 < RC", "GT"),
        ],
    )
    def test_operator_is_mirrored(self, text, operator):
        node = parse_condition(text)
        assert node is not None
        assert (node.step_name, node.operator, node.value) == (None, operator, 4)

    def test_evaluates_like_rc_first_form(self):
        # 4 LT RC is true for RC=8, false for RC=0.
        node = parse_condition("4 LT RC")
        assert node.evaluate({"S1": (8, False)}) is True
        assert node.evaluate({"S1": (0, False)}) is False

    def test_step_qualified_rc(self):
        node = parse_condition("4 LT STEP1.RC")
        assert (node.step_name, node.operator, node.value) == ("STEP1", "GT", 4)
        node = parse_condition("8 GE PS.S1.RC")
        assert (node.step_name, node.operator, node.value) == ("PS.S1", "LE", 8)

    def test_value_op_non_rc_is_unparseable(self):
        assert parse_condition("4 LT X") is None
