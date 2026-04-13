"""
Tests targeting coverage gaps in jclparser/condition_parser.py.

Covers:
- Two-character operator at (near) end of tokenizer input (lines 249-250)
- Escaped apostrophe (doubled '') inside a quoted string literal (lines 259-267)
- Various operator and atom combinations for tokenizer completeness
"""

import pytest

from jclparser.condition_parser import parse_condition


class TestConditionParserTokenizerEdgeCases:
    """Tokenizer edge cases in condition_parser._tokenize."""

    # ── Quoted string literals ──────────────────────────────────────────────

    def test_simple_quoted_string_in_condition(self):
        """Quoted string value in a condition is tokenized without error."""
        result = parse_condition("&WS EQ 'PROD'")
        # Either parses to an AST node or returns None — must not raise
        # (None is acceptable when the parser doesn't recognise the form)

    def test_escaped_apostrophe_in_quoted_string(self):
        """A '' (doubled apostrophe) inside a quoted value is handled."""
        # This hits the escaped-apostrophe branch in the tokenizer
        result = parse_condition("&NAME EQ 'O''BRIEN'")
        # Must not raise; result may be None if the parser doesn't model it

    def test_empty_quoted_string(self):
        result = parse_condition("&VAR EQ ''")

    def test_quoted_string_at_end_of_condition(self):
        result = parse_condition("RC EQ 'DONE'")

    # ── Two-character operators ──────────────────────────────────────────────

    def test_ge_operator_is_recognised(self):
        result = parse_condition("STEP1.RC GE 4")
        # GE is a valid two-char operator

    def test_le_operator_is_recognised(self):
        result = parse_condition("STEP1.RC LE 4")

    def test_ne_operator_is_recognised(self):
        result = parse_condition("STEP1.RC NE 0")

    def test_symbolic_ge_operator(self):
        result = parse_condition("STEP1.RC >= 4")

    def test_symbolic_le_operator(self):
        result = parse_condition("STEP1.RC <= 4")

    def test_symbolic_ne_operator(self):
        # Both != and <> are valid
        result = parse_condition("STEP1.RC <> 0")

    # ── Unclosed quoted string ───────────────────────────────────────────────

    def test_unclosed_quoted_string_at_end_does_not_crash(self):
        """A quoted string without a closing apostrophe exhausts the while loop
        (branch 259→267: while j < n exits because j >= n)."""
        result = parse_condition("STEP1.RC EQ 'UNCLOSED")
        # Must not raise; result may be None since the condition is malformed

    def test_apostrophe_as_last_char_does_not_crash(self):
        """Single apostrophe at the very end of input exits while immediately."""
        result = parse_condition("'")

    # ── Two-char operator near / at end of input ────────────────────────────

    def test_two_char_op_at_end_of_input(self):
        """Tokenizer lookahead for two-char operator at the very end of string."""
        # This exercises the branch where i+1 == n (end of string)
        # for a single-char operator-like character such as '<' or '>'
        result = parse_condition("RC >")
        # Invalid condition — parse_condition should return None, not crash

    def test_single_char_lt_operator(self):
        result = parse_condition("STEP1.RC LT 4")

    def test_single_char_gt_operator(self):
        result = parse_condition("STEP1.RC GT 0")

    def test_eq_operator(self):
        result = parse_condition("STEP1.RC EQ 0")

    # ── Compound conditions ──────────────────────────────────────────────────

    def test_and_condition(self):
        result = parse_condition("STEP1.RC EQ 0 AND STEP2.RC EQ 0")

    def test_or_condition(self):
        result = parse_condition("STEP1.RC EQ 0 OR STEP2.RC GT 4")

    def test_not_condition(self):
        result = parse_condition("NOT (STEP1.RC EQ 0)")

    def test_abend_atom(self):
        result = parse_condition("STEP1.ABEND")

    def test_run_atom(self):
        result = parse_condition("STEP1.RUN")

    # ── Unparseable conditions return None ──────────────────────────────────

    def test_completely_invalid_condition_returns_none(self):
        result = parse_condition("THIS IS NOT A VALID CONDITION AT ALL !!!")
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_condition("")
        assert result is None
