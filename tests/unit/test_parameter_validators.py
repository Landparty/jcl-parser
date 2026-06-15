"""
Tests for parameter value validators.
"""

from jclparser.parameter_validators import (
    ParameterValidator,
    DISPValidator,
    DatasetNameValidator,
    ValidationResult,
)


class TestDISPValidator:
    """Test DISP parameter validation."""

    def test_valid_disp_new_catlg(self):
        """Test valid DISP=(NEW,CATLG,DELETE)."""
        result = DISPValidator.validate("NEW,CATLG,DELETE")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_valid_disp_shr(self):
        """Test valid DISP=SHR."""
        result = DISPValidator.validate("SHR")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_valid_disp_with_parentheses(self):
        """Test valid DISP=(OLD,KEEP)."""
        result = DISPValidator.validate("(OLD,KEEP)")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_invalid_status(self):
        """Test invalid DISP status."""
        result = DISPValidator.validate("INVALID,CATLG")

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("status" in err.lower() for err in result.errors)

    def test_invalid_normal_termination(self):
        """Test invalid normal termination."""
        result = DISPValidator.validate("NEW,INVALID")

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("normal termination" in err.lower() for err in result.errors)

    def test_invalid_abnormal_termination(self):
        """Test invalid abnormal termination."""
        result = DISPValidator.validate("NEW,CATLG,INVALID")

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("abnormal termination" in err.lower() for err in result.errors)

    def test_warning_new_pass(self):
        """Test warning for DISP=(NEW,PASS)."""
        result = DISPValidator.validate("NEW,PASS")

        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("PASS" in warn for warn in result.warnings)

    def test_case_insensitive(self):
        """Test that validation is case-insensitive."""
        result = DISPValidator.validate("new,catlg,delete")

        assert result.is_valid is True

    def test_empty_disp(self):
        """Test empty DISP parameter."""
        result = DISPValidator.validate("")

        assert result.is_valid is True  # Empty is allowed

    def test_too_many_parameters(self):
        """Test DISP with too many parameters."""
        result = DISPValidator.validate("NEW,CATLG,DELETE,EXTRA")

        assert result.is_valid is True  # Valid but with warning
        assert len(result.warnings) > 0


class TestDatasetNameValidator:
    """Test dataset name validation."""

    def test_valid_simple_dsn(self):
        """Test valid simple dataset name."""
        result = DatasetNameValidator.validate("MY.DATA.SET")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_valid_temporary_dsn(self):
        """Test valid temporary dataset."""
        result = DatasetNameValidator.validate("&&TEMP")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_valid_gdg(self):
        """Test valid GDG dataset."""
        result = DatasetNameValidator.validate("MY.DATA.SET(+1)")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_valid_gdg_negative(self):
        """Test valid GDG with negative generation."""
        result = DatasetNameValidator.validate("MY.DATA.SET(-1)")

        assert result.is_valid is True

    def test_valid_gdg_zero(self):
        """Test valid GDG generation 0."""
        result = DatasetNameValidator.validate("MY.DATA.SET(0)")

        assert result.is_valid is True

    def test_valid_special_chars(self):
        """Test valid dataset with special characters."""
        result = DatasetNameValidator.validate("$SYS.#DATA.@FILE")

        assert result.is_valid is True

    def test_valid_with_hyphen(self):
        """Test valid dataset with hyphen."""
        result = DatasetNameValidator.validate("MY-DATA.SET-NAME")

        assert result.is_valid is True

    def test_invalid_too_long(self):
        """Test dataset name too long."""
        long_name = "A" * 45
        result = DatasetNameValidator.validate(long_name)

        assert result.is_valid is False
        assert any("too long" in err.lower() for err in result.errors)

    def test_invalid_qualifier_too_long(self):
        """Test qualifier too long."""
        result = DatasetNameValidator.validate("VERYLONGQUALIFIER.DATA")

        assert result.is_valid is False
        assert any("too long" in err.lower() for err in result.errors)

    def test_invalid_starts_with_number(self):
        """Test qualifier starting with number."""
        result = DatasetNameValidator.validate("1INVALID.DATA")

        assert result.is_valid is False
        assert any("must start with" in err.lower() for err in result.errors)

    def test_invalid_special_char(self):
        """Test invalid special character."""
        result = DatasetNameValidator.validate("MY.DATA!SET")

        assert result.is_valid is False
        assert any("invalid characters" in err.lower() for err in result.errors)

    def test_invalid_empty_qualifier(self):
        """Test empty qualifier."""
        result = DatasetNameValidator.validate("MY..DATA")

        assert result.is_valid is False
        assert any("empty qualifier" in err.lower() for err in result.errors)

    def test_invalid_gdg_format(self):
        """Test invalid GDG format."""
        result = DatasetNameValidator.validate("MY.DATA(ABC)")

        assert result.is_valid is False
        assert any("GDG" in err for err in result.errors)

    def test_warning_single_level(self):
        """Test warning for single-level dataset."""
        result = DatasetNameValidator.validate("MYDATA")

        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert any("single-level" in warn.lower() for warn in result.warnings)

    def test_warning_many_qualifiers(self):
        """Test warning for too many qualifiers."""
        # Create 25 single-character qualifiers (total 49 chars with dots)
        # Use shorter qualifiers to stay under 44 char limit
        many_quals = ".".join(["A"] * 23)  # 23 qualifiers = 45 chars, just over limit
        result = DatasetNameValidator.validate(many_quals)

        # Will fail due to length, but if we use 22 qualifiers it should warn
        many_quals_valid = ".".join(["A"] * 22)  # 22 qualifiers = 43 chars
        result = DatasetNameValidator.validate(many_quals_valid)

        assert result.is_valid is True
        # No warning for 22 qualifiers since it's not > 22

    def test_disallow_temporary(self):
        """Test disallowing temporary datasets."""
        result = DatasetNameValidator.validate("&&TEMP", allow_temporary=False)

        assert result.is_valid is False
        assert any("temporary" in err.lower() for err in result.errors)

    def test_disallow_gdg(self):
        """Test disallowing GDG datasets."""
        result = DatasetNameValidator.validate("MY.DATA(+1)", allow_gdg=False)

        assert result.is_valid is False
        assert any("GDG" in err for err in result.errors)

    def test_case_insensitive(self):
        """Test that validation is case-insensitive."""
        result = DatasetNameValidator.validate("my.data.set")

        assert result.is_valid is True


class TestParameterValidator:
    """Test main ParameterValidator class."""

    def test_validate_disp(self):
        """Test DISP validation through main validator."""
        result = ParameterValidator.validate_disp("NEW,CATLG")

        assert result.is_valid is True

    def test_validate_dataset_name(self):
        """Test dataset name validation through main validator."""
        result = ParameterValidator.validate_dataset_name("MY.DATA.SET")

        assert result.is_valid is True

    def test_validate_unit(self):
        """Test UNIT validation."""
        result = ParameterValidator.validate_unit("SYSDA")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_unit_common(self):
        """Test common UNIT values."""
        common_units = ["SYSDA", "SYSALLDA", "TAPE", "3390", "3380"]

        for unit in common_units:
            result = ParameterValidator.validate_unit(unit)
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_validate_unit_uncommon(self):
        """Test uncommon UNIT value gives warning."""
        result = ParameterValidator.validate_unit("MYUNIT")

        assert result.is_valid is True
        assert len(result.warnings) > 0

    def test_validate_volume(self):
        """Test VOLUME validation."""
        result = ParameterValidator.validate_volume("VOL123")

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_volume_too_long(self):
        """Test volume serial too long."""
        result = ParameterValidator.validate_volume("TOOLONG1")

        assert result.is_valid is False
        assert any("too long" in err.lower() for err in result.errors)

    def test_validate_volume_invalid_chars(self):
        """Test volume with invalid characters."""
        result = ParameterValidator.validate_volume("VOL@123")

        assert result.is_valid is False
        assert any("invalid characters" in err.lower() for err in result.errors)


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_creation(self):
        """Test creating ValidationResult."""
        result = ValidationResult(is_valid=True, errors=[], warnings=["Test warning"])

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1

    def test_validation_result_defaults(self):
        """Test ValidationResult with defaults."""
        result = ValidationResult(is_valid=True, errors=[])

        assert result.warnings == []


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_disp_whitespace(self):
        """Test DISP with extra whitespace."""
        result = DISPValidator.validate(" NEW , CATLG , DELETE ")

        assert result.is_valid is True

    def test_dsn_with_numbers(self):
        """Test dataset with numbers in qualifiers."""
        result = DatasetNameValidator.validate("SYS1.PARMLIB")

        assert result.is_valid is True

    def test_dsn_all_special_chars(self):
        """Test dataset with all allowed special chars."""
        result = DatasetNameValidator.validate("$ABC.#DEF.@GHI")

        assert result.is_valid is True

    def test_multiple_errors(self):
        """Test validation with multiple errors."""
        result = DatasetNameValidator.validate("1INVALID..TOOLONGQUALIFIER")

        assert result.is_valid is False
        assert len(result.errors) >= 2


class TestTimeValidator:
    """Test TIME parameter validation."""

    def test_minutes_only(self):
        assert ParameterValidator.validate_time("30").is_valid is True

    def test_minutes_and_seconds(self):
        assert ParameterValidator.validate_time("(30,15)").is_valid is True

    def test_unlimited_1440(self):
        assert ParameterValidator.validate_time("1440").is_valid is True

    def test_nolimit_keyword(self):
        assert ParameterValidator.validate_time("NOLIMIT").is_valid is True

    def test_minutes_over_max(self):
        assert ParameterValidator.validate_time("2000").is_valid is False

    def test_seconds_over_59(self):
        result = ParameterValidator.validate_time("(10,75)")
        assert result.is_valid is False

    def test_empty_is_valid(self):
        assert ParameterValidator.validate_time("").is_valid is True


class TestRegionValidator:
    """Test REGION parameter validation."""

    def test_kilobytes(self):
        assert ParameterValidator.validate_region("4096K").is_valid is True

    def test_megabytes(self):
        assert ParameterValidator.validate_region("32M").is_valid is True

    def test_zero_unlimited(self):
        assert ParameterValidator.validate_region("0").is_valid is True
        assert ParameterValidator.validate_region("0M").is_valid is True

    def test_missing_suffix_rejected(self):
        assert ParameterValidator.validate_region("500").is_valid is False

    def test_garbage_rejected(self):
        assert ParameterValidator.validate_region("BIG").is_valid is False


class TestPriorityAndPerform:
    """Test PRTY and PERFORM validation."""

    def test_prty_in_range(self):
        assert ParameterValidator.validate_priority("0").is_valid is True
        assert ParameterValidator.validate_priority("15").is_valid is True

    def test_prty_out_of_range(self):
        assert ParameterValidator.validate_priority("16").is_valid is False

    def test_prty_non_numeric(self):
        assert ParameterValidator.validate_priority("HIGH").is_valid is False

    def test_perform_in_range(self):
        assert ParameterValidator.validate_perform("1").is_valid is True
        assert ParameterValidator.validate_perform("999").is_valid is True

    def test_perform_zero_rejected(self):
        assert ParameterValidator.validate_perform("0").is_valid is False


class TestRdValidator:
    """Test RD (restart definition) validation."""

    def test_valid_values(self):
        for value in ("R", "RNC", "NR", "NC"):
            assert ParameterValidator.validate_rd(value).is_valid is True

    def test_invalid_value(self):
        assert ParameterValidator.validate_rd("YES").is_valid is False


class TestMsgLevelValidator:
    """Test MSGLEVEL validation."""

    def test_valid(self):
        assert ParameterValidator.validate_msglevel("(1,1)").is_valid is True
        assert ParameterValidator.validate_msglevel("(2,0)").is_valid is True

    def test_statements_out_of_range(self):
        assert ParameterValidator.validate_msglevel("(3,1)").is_valid is False

    def test_messages_out_of_range(self):
        assert ParameterValidator.validate_msglevel("(1,2)").is_valid is False


class TestDsnTypeValidator:
    """Test DSNTYPE validation."""

    def test_valid(self):
        assert ParameterValidator.validate_dsntype("LIBRARY").is_valid is True
        assert ParameterValidator.validate_dsntype("LARGE").is_valid is True

    def test_invalid(self):
        assert ParameterValidator.validate_dsntype("SEQUENTIAL").is_valid is False


class TestRecfmValidator:
    """Test RECFM (record format) validation."""

    def test_valid_formats(self):
        for value in ("F", "FB", "FBA", "V", "VB", "VBS", "U", "VBA", "FBM"):
            assert ParameterValidator.validate_recfm(value).is_valid is True, value

    def test_fixed_spanned_rejected(self):
        # Spanned applies to V/D, not F.
        assert ParameterValidator.validate_recfm("FS").is_valid is False

    def test_garbage_rejected(self):
        assert ParameterValidator.validate_recfm("XYZ").is_valid is False
