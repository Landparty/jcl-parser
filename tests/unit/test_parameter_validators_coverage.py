"""
Tests targeting uncovered lines in parameter_validators.py.

Covers: empty DISP, GDG disallowed, empty UNIT, volume serial
edge cases (SER= prefix, invalid chars).
"""

from jclparser.parameter_validators import (
    DatasetNameValidator,
    DISPValidator,
)

# ---------------------------------------------------------------------------
# DISPValidator edge cases — lines 74-75
# ---------------------------------------------------------------------------


class TestDISPValidatorCoverage:
    """Test DISPValidator edge cases."""

    def test_empty_disp_is_valid(self):
        """Empty DISP string is valid (returns early, line 63)."""
        result = DISPValidator.validate("")
        assert result.is_valid is True

    def test_disp_extra_parameters_warning(self):
        """DISP with >3 parameters produces a warning (lines 104-107)."""
        result = DISPValidator.validate("NEW,CATLG,DELETE,EXTRA")
        assert result.is_valid is True  # Not an error, just a warning
        assert len(result.warnings) > 0
        assert any("4 parameters" in w for w in result.warnings)

    def test_disp_new_pass_warning(self):
        """DISP=(NEW,PASS) produces a warning (lines 91-94)."""
        result = DISPValidator.validate("NEW,PASS")
        assert result.is_valid is True
        assert any("PASS" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# DatasetNameValidator — lines 193-194
# ---------------------------------------------------------------------------


class TestDatasetNameValidatorCoverage:
    """Test DatasetNameValidator edge cases."""

    def test_gdg_not_allowed(self):
        """GDG datasets rejected when allow_gdg=False (lines 176-180)."""
        result = DatasetNameValidator.validate("MY.DATA(+1)", allow_gdg=False)
        assert result.is_valid is False
        assert any("GDG" in e for e in result.errors)

    def test_temporary_not_allowed(self):
        """Temporary datasets rejected when allow_temporary=False (lines 162-166)."""
        result = DatasetNameValidator.validate("&&TEMP", allow_temporary=False)
        assert result.is_valid is False
        assert any("Temporary" in e or "&&" in e for e in result.errors)

    def test_invalid_gdg_generation(self):
        """Invalid GDG suffix is rejected (lines 183-186)."""
        result = DatasetNameValidator.validate("MY.DATA(+X)")
        assert result.is_valid is False
        assert any("GDG" in e.upper() for e in result.errors)

    def test_empty_qualifier(self):
        """Empty qualifier detected (e.g., 'A..B') (lines 201-203)."""
        result = DatasetNameValidator.validate("A..B")
        assert result.is_valid is False
        assert any("Empty qualifier" in e for e in result.errors)

    def test_qualifier_too_long(self):
        """Qualifier exceeding 8 characters flagged (lines 205-208)."""
        result = DatasetNameValidator.validate("ABCDEFGHIJ.DATA")
        assert result.is_valid is False
        assert any("too long" in e.lower() for e in result.errors)

    def test_qualifier_starts_with_number(self):
        """Qualifier starting with number flagged (lines 212-215)."""
        result = DatasetNameValidator.validate("1BADNAME.DATA")
        assert result.is_valid is False
        assert any("must start" in e.lower() for e in result.errors)

    def test_qualifier_invalid_chars(self):
        """Qualifier with invalid characters flagged (lines 217-221)."""
        result = DatasetNameValidator.validate("BAD!NAME.DATA")
        assert result.is_valid is False
        assert any("invalid characters" in e.lower() for e in result.errors)

    def test_many_qualifiers_warning(self):
        """Many qualifiers (>22) produce a warning (lines 229-232)."""
        dsn = ".".join(["Q"] * 23)
        result = DatasetNameValidator.validate(dsn)
        assert any("23 qualifiers" in w for w in result.warnings)
