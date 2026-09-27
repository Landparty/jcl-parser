"""
Parameter value validators for JCL parameters.

Provides validation for common JCL parameter values like DISP, dataset names, etc.
"""

import re
from dataclasses import dataclass, field
from typing import ClassVar

# Module-level frozenset for dataset-qualifier character validation
# (avoids per-call set construction).
_VALID_QUALIFIER_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$#@-")


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    errors: list[str]
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def valid(cls, warnings: list[str] | None = None) -> "ValidationResult":
        """Return a passing result, with optional warnings."""
        return cls(is_valid=True, errors=[], warnings=warnings or [])

    @classmethod
    def invalid(
        cls, errors: list[str], warnings: list[str] | None = None
    ) -> "ValidationResult":
        """Return a failing result with the supplied error messages."""
        return cls(is_valid=False, errors=errors, warnings=warnings or [])

    @classmethod
    def from_errors(
        cls, errors: list[str], warnings: list[str] | None = None
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

    VALID_STATUS: ClassVar[set[str]] = {"NEW", "OLD", "SHR", "MOD"}
    VALID_NORMAL_TERM: ClassVar[set[str]] = {
        "DELETE",
        "KEEP",
        "CATLG",
        "UNCATLG",
        "PASS",
    }
    VALID_ABNORMAL_TERM: ClassVar[set[str]] = {"DELETE", "KEEP", "CATLG", "UNCATLG"}

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
        warnings: list[str] = []

        if not disp_value:
            return ValidationResult.valid()

        # Remove outer parentheses if present
        disp_value = disp_value.strip()
        if disp_value.startswith("(") and disp_value.endswith(")"):
            disp_value = disp_value[1:-1]

        # Split by comma (str.split always yields at least one element).
        parts = [p.strip().upper() for p in disp_value.split(",")]

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
            if parts[0] == "NEW" and parts[1] == "PASS":
                warnings.append(
                    "DISP=(NEW,PASS) - consider using CATLG or KEEP for permanent datasets"
                )

        # Validate abnormal termination (third parameter)
        if len(parts) >= 3 and parts[2] and parts[2] not in cls.VALID_ABNORMAL_TERM:
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
    - A PDS member may follow in parentheses: LIB.NAME(MEMBER)
    - A backward reference *.stepname[.procstep].ddname names no dataset
      itself and is accepted as is
    """

    # Pattern for a single qualifier
    QUALIFIER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[A-Z$#@][A-Z0-9$#@-]{0,7}$"
    )

    # Pattern for GDG generation
    GDG_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^\([+-]?\d+\)$")

    # Pattern for a PDS member name in parentheses (1-8 chars, no hyphen)
    MEMBER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^\([A-Z$#@][A-Z0-9$#@]{0,7}\)$"
    )

    # Backward reference to an earlier DD: *.STEP.DD or *.STEP.PROCSTEP.DD
    REFERBACK_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^\*(\.[A-Z$#@][A-Z0-9$#@]{0,7}){1,3}$"
    )

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
        warnings: list[str] = []

        if not dsn:
            errors.append("Dataset name is empty")
            return ValidationResult.invalid(errors)

        original_dsn = dsn
        dsn = dsn.strip().upper()

        if cls.REFERBACK_PATTERN.match(dsn):
            return ValidationResult.valid(warnings)

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
            elif cls.MEMBER_PATTERN.match(gdg_suffix):
                dsn = base_name
            else:
                errors.append(f"Invalid member name or GDG generation: {gdg_suffix}")
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
