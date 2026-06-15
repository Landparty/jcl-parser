"""
Parameter value validators for JCL parameters.

Provides validation for common JCL parameter values like DISP, dataset names, etc.
"""

import re
from typing import ClassVar, List, Set
from dataclasses import dataclass, field

# Module-level frozensets for character validation (avoids per-call set construction)
_VALID_QUALIFIER_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$#@-")
_VALID_VOLUME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

# Enumerated keyword values for the JOB/EXEC/DD parameters validated below.
_VALID_RD_VALUES = frozenset({"R", "RNC", "NR", "NC"})
_VALID_DSNTYPE_VALUES = frozenset(
    {"LIBRARY", "PDS", "HFS", "PIPE", "LARGE", "BASIC", "EXTREQ", "EXTPREF"}
)
# RECFM: format (F/V/U/D), optional Blocked, optional Spanned (V/D only),
# optional ANSI/Machine carriage control. U takes neither B nor S.
_RECFM_PATTERN = re.compile(r"^(FB?|VB?S?|U|DB?)[AM]?$")
# TIME keywords that stand in for "no limit".
_TIME_UNLIMITED = frozenset({"NOLIMIT", "MAXIMUM"})
# REGION: digits with an optional K/M suffix.
_REGION_PATTERN = re.compile(r"^(\d+)([KM]?)$")


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    errors: List[str]
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def valid(cls, warnings: List[str] | None = None) -> "ValidationResult":
        """Return a passing result, with optional warnings."""
        return cls(is_valid=True, errors=[], warnings=warnings or [])

    @classmethod
    def invalid(
        cls, errors: List[str], warnings: List[str] | None = None
    ) -> "ValidationResult":
        """Return a failing result with the supplied error messages."""
        return cls(is_valid=False, errors=errors, warnings=warnings or [])

    @classmethod
    def from_errors(
        cls, errors: List[str], warnings: List[str] | None = None
    ) -> "ValidationResult":
        """Return valid when *errors* is empty, invalid otherwise."""
        return cls(is_valid=len(errors) == 0, errors=errors, warnings=warnings or [])


class DISPValidator:
    """
    Validator for DISP (disposition) parameters.

    DISP format: (status,normal-termination,abnormal-termination)
    - status: NEW, OLD, SHR, MOD
    - normal-termination: DELETE, KEEP, CATLG, UNCATLG, PASS
    - abnormal-termination: DELETE, KEEP, CATLG, UNCATLG
    """

    VALID_STATUS: ClassVar[Set[str]] = {"NEW", "OLD", "SHR", "MOD"}
    VALID_NORMAL_TERM: ClassVar[Set[str]] = {
        "DELETE",
        "KEEP",
        "CATLG",
        "UNCATLG",
        "PASS",
    }
    VALID_ABNORMAL_TERM: ClassVar[Set[str]] = {"DELETE", "KEEP", "CATLG", "UNCATLG"}

    # Precomputed sorted join strings (built once at class definition time)
    _VALID_STATUS_STR: ClassVar[str] = ", ".join(sorted(VALID_STATUS))
    _VALID_NORMAL_TERM_STR: ClassVar[str] = ", ".join(sorted(VALID_NORMAL_TERM))
    _VALID_ABNORMAL_TERM_STR: ClassVar[str] = ", ".join(sorted(VALID_ABNORMAL_TERM))

    @classmethod
    def validate(cls, disp_value: str) -> ValidationResult:
        """
        Validate DISP parameter value.

        Args:
            disp_value: DISP parameter value (e.g., "NEW,CATLG,DELETE" or "(SHR)")

        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings: List[str] = []

        if not disp_value:
            return ValidationResult.valid()

        # Remove outer parentheses if present
        disp_value = disp_value.strip()
        if disp_value.startswith("(") and disp_value.endswith(")"):
            disp_value = disp_value[1:-1]

        # Split by comma
        parts = [p.strip().upper() for p in disp_value.split(",")]

        if len(parts) == 0:
            errors.append("DISP parameter is empty")
            return ValidationResult.invalid(errors, warnings)

        # Validate status (first parameter)
        if parts[0] and parts[0] not in cls.VALID_STATUS:
            errors.append(
                f"Invalid DISP status: {parts[0]}. Valid values: {cls._VALID_STATUS_STR}"
            )

        # Validate normal termination (second parameter)
        if len(parts) >= 2 and parts[1]:
            if parts[1] not in cls.VALID_NORMAL_TERM:
                errors.append(
                    f"Invalid DISP normal termination: {parts[1]}. Valid values: {cls._VALID_NORMAL_TERM_STR}"
                )

            # Warning: PASS with NEW should usually be CATLG or KEEP
            if len(parts) >= 1 and parts[0] == "NEW" and parts[1] == "PASS":
                warnings.append(
                    "DISP=(NEW,PASS) - consider using CATLG or KEEP for permanent datasets"
                )

        # Validate abnormal termination (third parameter)
        if len(parts) >= 3 and parts[2]:
            if parts[2] not in cls.VALID_ABNORMAL_TERM:
                errors.append(
                    f"Invalid DISP abnormal termination: {parts[2]}. Valid values: {cls._VALID_ABNORMAL_TERM_STR}"
                )

        # Too many parameters
        if len(parts) > 3:
            warnings.append(
                f"DISP has {len(parts)} parameters, expected 1-3. Extra parameters will be ignored."
            )

        return ValidationResult.from_errors(errors, warnings)


class DatasetNameValidator:
    """
    Validator for dataset names (DSN).

    Rules:
    - 1-44 characters total
    - Qualifiers separated by periods
    - Each qualifier: 1-8 characters
    - First character: A-Z, $, #, @
    - Other characters: A-Z, 0-9, $, #, @, -
    - Temporary datasets start with &&
    - GDG datasets end with (+n) or (-n) or (0)
    """

    # Pattern for a single qualifier
    QUALIFIER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[A-Z$#@][A-Z0-9$#@-]{0,7}$"
    )

    # Pattern for GDG generation
    GDG_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^\([+-]?\d+\)$")

    @classmethod
    def validate(
        cls, dsn: str, allow_temporary: bool = True, allow_gdg: bool = True
    ) -> ValidationResult:
        """
        Validate dataset name.

        Args:
            dsn: Dataset name to validate
            allow_temporary: Allow temporary datasets (&&name)
            allow_gdg: Allow GDG datasets (name(+1))

        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings: List[str] = []

        if not dsn:
            errors.append("Dataset name is empty")
            return ValidationResult.invalid(errors)

        original_dsn = dsn
        dsn = dsn.strip().upper()

        # Check for temporary dataset
        is_temporary = dsn.startswith("&&")
        if is_temporary:
            if not allow_temporary:
                errors.append(f"Temporary datasets (&&) not allowed: {original_dsn}")
                return ValidationResult.invalid(errors)
            dsn = dsn[2:]  # Remove &&

        # Check for GDG
        gdg_suffix = None
        if "(" in dsn:
            base_name, gdg_part = dsn.rsplit("(", 1)
            gdg_suffix = "(" + gdg_part

            if cls.GDG_PATTERN.match(gdg_suffix):
                if not allow_gdg:
                    errors.append(f"GDG datasets not allowed: {original_dsn}")
                    return ValidationResult.invalid(errors)
                dsn = base_name
            else:
                errors.append(f"Invalid GDG generation: {gdg_suffix}")
                return ValidationResult.invalid(errors)

        # Check total length (excluding && and GDG)
        if len(dsn) > 44:
            errors.append(f"Dataset name too long: {len(dsn)} characters (max 44)")

        if len(dsn) == 0:
            errors.append("Dataset name has no qualifiers")
            return ValidationResult.invalid(errors)

        # Split into qualifiers
        qualifiers = dsn.split(".")

        # Validate each qualifier
        for i, qualifier in enumerate(qualifiers):
            if not qualifier:
                errors.append(f"Empty qualifier at position {i + 1}")
                continue

            if len(qualifier) > 8:
                errors.append(
                    f"Qualifier '{qualifier}' too long: {len(qualifier)} characters (max 8)"
                )

            if not cls.QUALIFIER_PATTERN.match(qualifier):
                # Check specific issues
                if not qualifier[0].isalpha() and qualifier[0] not in "$#@":
                    errors.append(
                        f"Qualifier '{qualifier}' must start with A-Z, $, #, or @"
                    )
                else:
                    invalid_chars = set(qualifier) - _VALID_QUALIFIER_CHARS
                    if invalid_chars:
                        errors.append(
                            f"Qualifier '{qualifier}' contains invalid characters: {', '.join(sorted(invalid_chars))}"
                        )

        # Warnings
        if len(qualifiers) == 1 and not is_temporary:
            warnings.append(
                f"Single-level dataset name: {original_dsn}. Consider using multi-level names."
            )

        if len(qualifiers) > 22:
            warnings.append(
                f"Dataset has {len(qualifiers)} qualifiers. This is unusual (typical: 2-5)."
            )

        return ValidationResult.from_errors(errors, warnings)


class ParameterValidator:
    """Main validator class for all parameter types."""

    @staticmethod
    def validate_disp(disp_value: str) -> ValidationResult:
        """Validate DISP parameter."""
        return DISPValidator.validate(disp_value)

    @staticmethod
    def validate_dataset_name(dsn: str, **kwargs) -> ValidationResult:
        """Validate dataset name."""
        return DatasetNameValidator.validate(dsn, **kwargs)

    @staticmethod
    def validate_unit(unit: str) -> ValidationResult:
        """
        Validate UNIT parameter.

        Common values: SYSDA, SYSALLDA, 3390, 3380, TAPE, etc.
        """
        errors = []
        warnings: List[str] = []

        if not unit:
            errors.append("UNIT parameter is empty")
            return ValidationResult.invalid(errors)

        unit = unit.strip().upper()

        # Common valid units
        common_units = {
            "SYSDA",
            "SYSALLDA",
            "TAPE",
            "CART",
            "3390",
            "3380",
            "3350",
            "3375",
            "3330",
            "2400",
            "3400",
            "3480",
            "3490",
            "3590",
        }

        # If it's not a common unit, give a warning
        if unit not in common_units and not unit.startswith("("):
            warnings.append(
                f"Uncommon UNIT value: {unit}. Verify this is correct for your system."
            )

        return ValidationResult.valid(warnings)

    @staticmethod
    def validate_volume(volume: str) -> ValidationResult:
        """
        Validate VOLUME parameter.

        Volume serial: 1-6 characters, alphanumeric
        """
        errors = []
        warnings: List[str] = []

        if not volume:
            return ValidationResult.valid()

        volume = volume.strip().upper()

        # Remove VOL=SER= prefix if present
        if volume.startswith("SER="):
            volume = volume[4:]

        # Check length
        if len(volume) > 6:
            errors.append(f"Volume serial too long: {len(volume)} characters (max 6)")

        # Check characters (alphanumeric)
        if not volume.isalnum():
            invalid_chars = set(volume) - _VALID_VOLUME_CHARS
            errors.append(
                f"Volume serial contains invalid characters: {', '.join(sorted(invalid_chars))}"
            )

        return ValidationResult.from_errors(errors, warnings)

    @staticmethod
    def _strip_parens(value: str) -> str:
        """Remove one layer of surrounding parentheses, if present."""
        value = value.strip()
        if value.startswith("(") and value.endswith(")"):
            return value[1:-1].strip()
        return value

    @staticmethod
    def validate_time(time_value: str) -> ValidationResult:
        """
        Validate a TIME parameter.

        Accepts ``TIME=minutes``, ``TIME=(minutes,seconds)``, ``TIME=1440``,
        ``TIME=NOLIMIT`` and ``TIME=MAXIMUM``. Minutes are 0-1440 (1440 means
        unlimited); seconds are 0-59.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not time_value:
            return ValidationResult.valid()

        value = ParameterValidator._strip_parens(time_value.strip().upper())
        if value in _TIME_UNLIMITED:
            return ValidationResult.valid()

        parts = [p.strip() for p in value.split(",")]
        if len(parts) > 2:
            errors.append(
                f"TIME has {len(parts)} subparameters, expected (minutes[,seconds])"
            )

        minutes = parts[0] if parts else ""
        if minutes and minutes not in _TIME_UNLIMITED:
            if minutes.isdigit():
                if int(minutes) > 1440:
                    errors.append(f"TIME minutes {minutes} exceeds the maximum of 1440")
            else:
                errors.append(f"Invalid TIME minutes: {minutes}")

        seconds = parts[1] if len(parts) > 1 else ""
        if seconds:
            if seconds.isdigit():
                if int(seconds) > 59:
                    errors.append(f"TIME seconds {seconds} must be 0-59")
            else:
                errors.append(f"Invalid TIME seconds: {seconds}")

        return ValidationResult.from_errors(errors, warnings)

    @staticmethod
    def validate_region(region_value: str) -> ValidationResult:
        """
        Validate a REGION parameter.

        Accepts a value size with an optional ``K`` or ``M`` suffix
        (``REGION=4096K``, ``REGION=32M``). ``REGION=0``/``0K``/``0M`` requests
        all available storage. A bare number with no suffix is flagged.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not region_value:
            return ValidationResult.valid()

        value = ParameterValidator._strip_parens(region_value.strip().upper())
        match = _REGION_PATTERN.match(value)
        if not match:
            errors.append(
                f"Invalid REGION value: {region_value}. "
                "Expected a number with an optional K or M suffix."
            )
            return ValidationResult.invalid(errors, warnings)

        number = int(match.group(1))
        suffix = match.group(2)
        if not suffix and number != 0:
            errors.append(f"REGION value {region_value} must end with K or M (or be 0)")
        if suffix == "K" and number % 4 != 0 and number != 0:
            warnings.append("REGION in K is rounded up to a 4K multiple by the system")

        return ValidationResult.from_errors(errors, warnings)

    @staticmethod
    def validate_priority(prty_value: str) -> ValidationResult:
        """Validate a PRTY (job priority) parameter: an integer 0-15."""
        errors: List[str] = []
        if not prty_value:
            return ValidationResult.valid()
        value = prty_value.strip()
        if not value.isdigit() or not (0 <= int(value) <= 15):
            errors.append(f"Invalid PRTY value: {prty_value}. Must be an integer 0-15.")
        return ValidationResult.from_errors(errors)

    @staticmethod
    def validate_perform(perform_value: str) -> ValidationResult:
        """Validate a PERFORM (performance group) parameter: an integer 1-999."""
        errors: List[str] = []
        if not perform_value:
            return ValidationResult.valid()
        value = perform_value.strip()
        if not value.isdigit() or not (1 <= int(value) <= 999):
            errors.append(
                f"Invalid PERFORM value: {perform_value}. Must be an integer 1-999."
            )
        return ValidationResult.from_errors(errors)

    @staticmethod
    def validate_rd(rd_value: str) -> ValidationResult:
        """Validate an RD (restart definition) parameter: R, RNC, NR or NC."""
        errors: List[str] = []
        if not rd_value:
            return ValidationResult.valid()
        value = ParameterValidator._strip_parens(rd_value.strip().upper())
        if value not in _VALID_RD_VALUES:
            errors.append(
                f"Invalid RD value: {rd_value}. "
                f"Valid values: {', '.join(sorted(_VALID_RD_VALUES))}"
            )
        return ValidationResult.from_errors(errors)

    @staticmethod
    def validate_msglevel(msglevel_value: str) -> ValidationResult:
        """
        Validate a MSGLEVEL parameter of the form ``(statements,messages)``.

        ``statements`` is 0, 1 or 2; ``messages`` is 0 or 1. Either subparameter
        may be omitted.
        """
        errors: List[str] = []
        if not msglevel_value:
            return ValidationResult.valid()

        value = ParameterValidator._strip_parens(msglevel_value.strip())
        parts = [p.strip() for p in value.split(",")]
        if len(parts) > 2:
            errors.append(
                f"MSGLEVEL has {len(parts)} subparameters, expected (statements,messages)"
            )

        statements = parts[0] if parts else ""
        if statements and (
            not statements.isdigit() or int(statements) not in (0, 1, 2)
        ):
            errors.append(f"MSGLEVEL statements value {statements} must be 0, 1 or 2")

        messages = parts[1] if len(parts) > 1 else ""
        if messages and (not messages.isdigit() or int(messages) not in (0, 1)):
            errors.append(f"MSGLEVEL messages value {messages} must be 0 or 1")

        return ValidationResult.from_errors(errors)

    @staticmethod
    def validate_dsntype(dsntype_value: str) -> ValidationResult:
        """Validate a DSNTYPE parameter (LIBRARY, PDS, HFS, LARGE, ...)."""
        errors: List[str] = []
        if not dsntype_value:
            return ValidationResult.valid()
        value = ParameterValidator._strip_parens(dsntype_value.strip().upper())
        if value not in _VALID_DSNTYPE_VALUES:
            errors.append(
                f"Invalid DSNTYPE value: {dsntype_value}. "
                f"Valid values: {', '.join(sorted(_VALID_DSNTYPE_VALUES))}"
            )
        return ValidationResult.from_errors(errors)

    @staticmethod
    def validate_recfm(recfm_value: str) -> ValidationResult:
        """
        Validate a RECFM (record format) parameter.

        Accepts the standard combinations: a format letter (F, V, U or D),
        optional ``B`` (blocked), optional ``S`` (spanned; V/D only), and an
        optional ``A``/``M`` carriage-control character (e.g. F, FB, FBA, V, VB,
        VBS, U, VBA).
        """
        errors: List[str] = []
        if not recfm_value:
            return ValidationResult.valid()
        value = ParameterValidator._strip_parens(recfm_value.strip().upper())
        if not _RECFM_PATTERN.match(value):
            errors.append(
                f"Invalid RECFM value: {recfm_value}. "
                "Expected a format (F/V/U/D) with optional B, S and A/M."
            )
        return ValidationResult.from_errors(errors)
