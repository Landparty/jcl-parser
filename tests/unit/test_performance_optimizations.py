"""
Tests for performance optimization additions:

- detect_file_type_from_content() with same inputs as detect_file_type()
- &VAR.SUFFIX and &VAR..SUFFIX symbol substitution cases
- validate_jcl_identifier("1INVALID") must return False
"""

import pytest
from jclparser.jcl_file_type import (
    FileType,
    detect_file_type,
    detect_file_type_from_content,
)
from jclparser.explosion import substitute_symbols, SymbolScope
from jclparser.validators import validate_jcl_identifier


# ---------------------------------------------------------------------------
# detect_file_type_from_content() tests
# ---------------------------------------------------------------------------

class TestDetectFileTypeFromContent:
    """detect_file_type_from_content() mirrors detect_file_type() for string content."""

    def test_jcl_with_job_card(self):
        content = "//MYJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14\n"
        assert detect_file_type_from_content(content) == FileType.JCL

    def test_proc_with_proc_statement(self):
        content = "//MYPROC PROC DSN=DEFAULT.DATA\n//STEP1 EXEC PGM=IEFBR14\n"
        assert detect_file_type_from_content(content) == FileType.PROC

    def test_proc_with_exec_only(self):
        content = "//STEP1 EXEC PGM=IEFBR14\n//SYSPRINT DD SYSOUT=*\n"
        assert detect_file_type_from_content(content) == FileType.PROC

    def test_empty_content_is_unknown(self):
        assert detect_file_type_from_content("") == FileType.UNKNOWN

    def test_comments_only_is_unknown(self):
        content = "//* This is a comment\n//* Another comment\n"
        assert detect_file_type_from_content(content) == FileType.UNKNOWN

    def test_preamble_before_job_still_jcl(self):
        content = "//         SET VAR=VAL\n//MYJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14\n"
        assert detect_file_type_from_content(content) == FileType.JCL

    def test_matches_detect_file_type_for_jcl(self):
        """detect_file_type_from_content should agree with detect_file_type on plain strings."""
        content = "//MYJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14\n"
        assert detect_file_type_from_content(content) == detect_file_type(content)

    def test_matches_detect_file_type_for_proc(self):
        content = "//MYPROC PROC\n//STEP1 EXEC PGM=IEFBR14\n"
        assert detect_file_type_from_content(content) == detect_file_type(content)

    def test_matches_detect_file_type_for_unknown(self):
        content = "//* just a comment\n"
        assert detect_file_type_from_content(content) == detect_file_type(content)


# ---------------------------------------------------------------------------
# Symbol substitution: &VAR.SUFFIX and &VAR..SUFFIX
# ---------------------------------------------------------------------------

class TestSymbolSubstitutionPeriodConcatenation:
    """Tests for trailing-period concatenation in substitute_symbols()."""

    def _scope(self, **kwargs) -> SymbolScope:
        return SymbolScope(set_symbols={k.upper(): v for k, v in kwargs.items()})

    def test_var_dot_suffix_period_consumed(self):
        """&VAR.SUFFIX -> VALUESUFFIX (single period consumed as concatenation op)."""
        scope = self._scope(VAR="VALUE")
        result = substitute_symbols("&VAR.SUFFIX", scope)
        assert result == "VALUESUFFIX"

    def test_var_double_dot_suffix_one_period_remains(self):
        """&VAR..SUFFIX -> VALUE.SUFFIX (one period consumed, second period kept)."""
        scope = self._scope(VAR="VALUE")
        result = substitute_symbols("&VAR..SUFFIX", scope)
        assert result == "VALUE.SUFFIX"

    def test_var_dot_in_dsn(self):
        """Typical DSN pattern: &HLQ..DATA -> HLQ.DATA."""
        scope = self._scope(HLQ="MY.HLQ")
        result = substitute_symbols("&HLQ..DATA", scope)
        assert result == "MY.HLQ.DATA"

    def test_var_dot_qualifier(self):
        """&DSN.QUAL -> DSVAL.QUAL only one period consumed."""
        scope = self._scope(DSN="DSVAL")
        result = substitute_symbols("&DSN.QUAL", scope)
        assert result == "DSVALQUAL"

    def test_escaped_ampersand_not_substituted(self):
        """&& should become a single & and NOT be treated as a symbol reference."""
        scope = self._scope(AMP="SHOULD_NOT_APPEAR")
        result = substitute_symbols("&&AMP", scope)
        assert result == "&AMP"

    def test_undefined_symbol_allow_undefined(self):
        """Undefined symbol with allow_undefined=True should be left as-is."""
        scope = SymbolScope()
        result = substitute_symbols("&UNDEF.SUFFIX", scope, allow_undefined=True)
        assert result == "&UNDEF.SUFFIX"

    def test_undefined_symbol_not_strict(self):
        """Undefined symbol with strict=False (default) should substitute empty string."""
        scope = SymbolScope()
        result = substitute_symbols("PREFIX&UNDEF.SUFFIX", scope, strict=False)
        assert result == "PREFIXSUFFIX"

    def test_multiple_symbols_in_string(self):
        """Multiple symbol substitutions in one string."""
        scope = self._scope(A="HELLO", B="WORLD")
        result = substitute_symbols("&A. &B.", scope)
        assert result == "HELLO WORLD"


# ---------------------------------------------------------------------------
# validate_jcl_identifier edge cases
# ---------------------------------------------------------------------------

class TestValidateJclIdentifierEdgeCases:
    """Ensure edge cases of validate_jcl_identifier work correctly."""

    def test_starts_with_digit_is_invalid(self):
        """Identifier starting with a digit must be rejected."""
        assert validate_jcl_identifier("1INVALID") is False

    def test_starts_with_digit_only_invalid(self):
        assert validate_jcl_identifier("123") is False

    def test_empty_is_invalid(self):
        assert validate_jcl_identifier("") is False

    def test_too_long_is_invalid(self):
        assert validate_jcl_identifier("TOOLONGNAME") is False

    def test_exactly_8_chars_valid(self):
        assert validate_jcl_identifier("ABCDEFGH") is True

    def test_starts_with_at_sign_valid(self):
        assert validate_jcl_identifier("@VALID") is True

    def test_starts_with_hash_valid(self):
        assert validate_jcl_identifier("#VALID") is True

    def test_starts_with_dollar_valid(self):
        assert validate_jcl_identifier("$VALID") is True

    def test_alphanumeric_valid(self):
        assert validate_jcl_identifier("STEP1") is True

    def test_all_special_chars_valid(self):
        assert validate_jcl_identifier("@#$") is True

    def test_hyphen_in_identifier_is_invalid(self):
        """JCL identifiers do NOT allow hyphens."""
        assert validate_jcl_identifier("STEP-1") is False

    def test_space_in_identifier_is_invalid(self):
        assert validate_jcl_identifier("STEP 1") is False
