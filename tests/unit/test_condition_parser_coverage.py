"""
Tests targeting uncovered lines in condition_parser.py.

Covers: anonymous ABEND/RUN evaluation, None-propagation in AND/OR,
tokenizer edge cases (single-char ops, quoted strings, stray chars),
parser edge cases (RC-no-op, RC-op-no-value, bare numerics, unrecognized atoms).
"""

import pytest

from jclparser.condition_parser import (
    AbendCondition,
    AndCondition,
    NotCondition,
    OrCondition,
    ReturnCodeCondition,
    RunCondition,
    _tokenize,
    parse_condition,
)

# ---------------------------------------------------------------------------
# Anonymous (no step name) evaluate paths — lines 107-111, 123
# ---------------------------------------------------------------------------


class TestAnonymousEvaluate:
    """Evaluate conditions that omit the step name (use last step)."""

    def test_abend_anonymous_with_results(self):
        """Anonymous ABEND uses last step's abend flag (line 111)."""
        node = parse_condition("ABEND")
        assert isinstance(node, AbendCondition)
        assert node.step_name is None
        # Last step abended
        assert node.evaluate({"S1": (0, True)}) is True
        # Last step did not abend
        assert node.evaluate({"S1": (0, False)}) is False

    def test_abend_anonymous_empty_results(self):
        """Anonymous ABEND with no results returns None (lines 109-110)."""
        node = parse_condition("ABEND")
        assert node.evaluate({}) is None

    def test_abend_named_missing_step(self):
        """Named ABEND for a step not in results returns None (lines 106-107)."""
        node = parse_condition("MISSING.ABEND")
        assert node.evaluate({"OTHER": (0, False)}) is None

    def test_run_anonymous_with_results(self):
        """Anonymous RUN returns True if any step ran (line 123)."""
        node = parse_condition("RUN")
        assert isinstance(node, RunCondition)
        assert node.step_name is None
        assert node.evaluate({"S1": (0, False)}) is True

    def test_run_anonymous_empty_results(self):
        """Anonymous RUN returns False if no steps ran (line 123)."""
        node = parse_condition("RUN")
        assert node.evaluate({}) is False

    def test_rc_anonymous_empty_results(self):
        """Anonymous RC with no results returns None (lines 77-78)."""
        node = parse_condition("RC EQ 0")
        assert node.evaluate({}) is None


# ---------------------------------------------------------------------------
# None-propagation in AND / OR — lines 150, 167
# ---------------------------------------------------------------------------


class TestNonePropagation:
    """Test that None (unknown step) propagates correctly through AND/OR."""

    def test_and_both_none(self):
        """AND with both sides None returns None (line 150)."""
        node = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        # Neither step ran
        assert node.evaluate({}) is None

    def test_and_left_true_right_none(self):
        """AND: True AND None → None (line 150)."""
        node = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        assert node.evaluate({"STEP1": (0, False)}) is None

    def test_and_left_none_right_true(self):
        """AND: None AND True → None (line 150)."""
        node = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")
        assert node.evaluate({"STEP2": (0, False)}) is None

    def test_or_both_none(self):
        """OR with both sides None returns None (line 167)."""
        node = parse_condition("STEP1.ABEND OR STEP2.ABEND")
        assert node.evaluate({}) is None

    def test_or_left_false_right_none(self):
        """OR: False OR None → None (line 167)."""
        node = parse_condition("STEP1.ABEND OR STEP2.ABEND")
        assert node.evaluate({"STEP1": (0, False)}) is None

    def test_or_left_none_right_false(self):
        """OR: None OR False → None (line 167)."""
        node = parse_condition("STEP1.ABEND OR STEP2.ABEND")
        assert node.evaluate({"STEP2": (0, False)}) is None

    def test_not_with_none(self):
        """NOT None → None."""
        node = parse_condition("NOT STEP1.RC EQ 0")
        assert node.evaluate({}) is None


# ---------------------------------------------------------------------------
# ReturnCodeCondition.evaluate fallback — line 94
# ---------------------------------------------------------------------------


class TestReturnCodeFallback:
    """RC evaluate returns None for an unrecognized operator (line 94)."""

    def test_unrecognized_operator_returns_none(self):
        """Directly construct a node with a bad operator."""
        node = ReturnCodeCondition(step_name="S1", operator="XX", value=0)
        assert node.evaluate({"S1": (0, False)}) is None


# ---------------------------------------------------------------------------
# Tokenizer edge cases — lines 248-249, 258-260
# ---------------------------------------------------------------------------


class TestTokenizer:
    """Test _tokenize() edge cases."""

    def test_single_char_equals(self):
        """Bare '=' should be tokenized (line 251)."""
        tokens = _tokenize("RC = 0")
        assert "=" in tokens

    def test_single_char_lt(self):
        """Bare '<' should be tokenized (line 251)."""
        tokens = _tokenize("RC < 8")
        assert "<" in tokens

    def test_single_char_gt(self):
        """Bare '>' should be tokenized (line 251)."""
        tokens = _tokenize("RC > 4")
        assert ">" in tokens

    def test_two_char_le(self):
        """'<=' tokenized as a single token via _TWO_CHAR_OP_STARTS (lines 237-241)."""
        tokens = _tokenize("RC <= 4")
        assert "<=" in tokens

    def test_two_char_ge(self):
        """'>=' tokenized as a single token via _TWO_CHAR_OP_STARTS (lines 237-241)."""
        tokens = _tokenize("RC >= 4")
        assert ">=" in tokens

    def test_two_char_ne_diamond(self):
        """'<>' should be tokenized as a single token."""
        tokens = _tokenize("RC <> 0")
        assert "<>" in tokens

    def test_quoted_string(self):
        """Quoted string preserved as single token (lines 258-266)."""
        tokens = _tokenize("'PRODUCTION'")
        assert "'PRODUCTION'" in tokens

    def test_quoted_string_with_escaped_apostrophe(self):
        """Escaped apostrophe '' inside quotes (lines 259-260)."""
        tokens = _tokenize("'DON''T'")
        assert "'DON''T'" in tokens

    def test_stray_characters_rejected(self):
        """Unrecognized characters are an error, not silently skipped (#63)."""
        with pytest.raises(ValueError, match="Unexpected character"):
            _tokenize("RC ; 0")
        assert parse_condition("RC ; 0") is None

    def test_not_equal_tilde(self):
        """'~=' (tilde-equals) is tokenized as NE operator."""
        tokens = _tokenize("RC ~= 4")
        assert "~=" in tokens

    def test_not_equal_not_sign(self):
        """'¬=' (not-sign equals) is tokenized as NE operator."""
        tokens = _tokenize("RC ¬= 4")
        assert "¬=" in tokens

    def test_not_less_than(self):
        """'¬<' is tokenized (maps to GE)."""
        tokens = _tokenize("RC ¬< 4")
        assert "¬<" in tokens

    def test_not_greater_than(self):
        """'^>' is tokenized (maps to LE)."""
        tokens = _tokenize("RC ^> 4")
        assert "^>" in tokens


# ---------------------------------------------------------------------------
# Parser edge cases — lines 343, 348, 373, 378, 389, 393-405, 438
# ---------------------------------------------------------------------------


class TestParserEdgeCases:
    """Test _Parser edge cases in _parse_primary()."""

    def test_rc_with_no_operator_after(self):
        """A bare RC is unparseable, not an invented RC EQ 0 (#63)."""
        assert parse_condition("STEP1.RC") is None

    def test_rc_with_operator_but_no_value(self):
        """RC GT with no number is unparseable, not an invented RC GT 0."""
        assert parse_condition("STEP1.RC GT") is None

    def test_rc_with_operator_and_non_numeric(self):
        """RC GT followed by a non-numeric token is unparseable."""
        assert parse_condition("STEP1.RC GT AND STEP2.ABEND") is None

    def test_rc_with_unrecognized_next_token(self):
        """Leftover tokens make the condition unparseable instead of dropped."""
        assert parse_condition("STEP1.RC STEP2.ABEND") is None

    def test_bare_number_condition(self):
        """A bare number like '0' is unparseable; it used to become RC EQ 0."""
        assert parse_condition("0") is None

    def test_bare_number_with_operator_and_rc(self):
        """Reversed form: '4 GT RC' means RC LT 4 (operator mirrored)."""
        node = parse_condition("4 GT RC")
        assert isinstance(node, ReturnCodeCondition)
        assert node.value == 4
        assert node.operator == "LT"

    def test_bare_number_with_operator_no_rc(self):
        """Bare number with operator but no 'RC' after it is unparseable.

        Dropping the operator and reading '4 GT' as 'RC EQ 4' would invent
        a different condition, so the caller falls back to the raw string.
        """
        assert parse_condition("4 GT") is None

    def test_unrecognized_atom_returns_none(self):
        """Unrecognized atom raises ValueError (line 409) caught by parse_condition (line 441)."""
        result = parse_condition("FOOBAR")
        # "FOOBAR" is not RC/ABEND/RUN/digit → ValueError → caught → None
        assert result is None

    def test_missing_close_paren_tolerance(self):
        """Parenthesized expression missing ')' still parses (line 348 branch-not-taken)."""
        node = parse_condition("(STEP1.RC EQ 0")
        # Should not crash; missing ')' is tolerated
        assert isinstance(node, ReturnCodeCondition)

    def test_empty_whitespace_returns_none(self):
        """Whitespace-only input returns None via early check (line 433)."""
        result = parse_condition("   ")
        assert result is None

    def test_stray_chars_only_produces_empty_tokens(self):
        """Input with only stray chars produces empty token list → None (line 438)."""
        result = parse_condition(";")
        assert result is None

    def test_unexpected_end_of_expression(self):
        """Trailing AND with no right operand raises ValueError (line 343) → None."""
        result = parse_condition("STEP1.RC EQ 0 AND")
        # After consuming AND, _parse_not → _parse_primary finds no tokens → ValueError
        assert result is None

    def test_trailing_or_returns_none(self):
        """Trailing OR with no right operand → None."""
        result = parse_condition("STEP1.ABEND OR")
        assert result is None

    def test_trailing_not_returns_none(self):
        """Trailing NOT with no operand → None."""
        result = parse_condition("NOT")
        assert result is None

    def test_nested_parens_with_and_or(self):
        """Complex nested expression with parens."""
        node = parse_condition("(STEP1.RC EQ 0 OR STEP2.RC EQ 4) AND NOT STEP3.ABEND")
        assert isinstance(node, AndCondition)
        assert isinstance(node.left, OrCondition)
        assert isinstance(node.right, NotCondition)
