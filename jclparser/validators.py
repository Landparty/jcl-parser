"""
JCL syntax and structure validation functions.

Contains validation logic for JCL syntax rules, semantic constraints,
and data integrity checks for parsed JCL structures.
"""

import logging
import re

from .errors import ErrorSeverity, ErrorType, ValidationError
from .model import DDStatement, Job, Step, iter_execution_steps
from .parameter_validators import DatasetNameValidator, DISPValidator

logger = logging.getLogger(__name__)

# Precompiled regex patterns for performance
_RE_JCL_ID_VALID = re.compile(r"^[A-Za-z@#$][A-Za-z0-9@#$]*$")

# Shared description used in all JCL name validation error messages
_JCL_NAME_FORMAT = "must be 1-8 characters, alphanumeric + @#$"


def validate_jcl_identifier(name: str) -> bool:
    """
    Validate JCL identifier format.

    JCL identifiers must be 1-8 characters, alphanumeric plus @, #, $

    Args:
        name: Identifier to validate

    Returns:
        True if valid identifier
    """
    if not name or len(name) > 8:
        return False

    return _RE_JCL_ID_VALID.match(name) is not None


def validate_dataset_name(dsn: str) -> bool:
    """
    Validate dataset name format.

    Compatibility wrapper — canonical rules live in
    ``parameter_validators.DatasetNameValidator``.

    Args:
        dsn: Dataset name to validate

    Returns:
        True if valid dataset name
    """
    result = DatasetNameValidator.validate(dsn)
    return result.is_valid


def validate_job_structure(job: Job) -> list[ValidationError]:
    """
    Validate complete job structure and dependencies.

    Args:
        job: Job object to validate

    Returns:
        List of validation errors
    """
    errors = []

    logger.debug("validating structure of job %s", job.name or "(unnamed)")

    # Job name validation
    if not validate_jcl_identifier(job.name):
        errors.append(
            ValidationError(
                f"Invalid job name '{job.name}': {_JCL_NAME_FORMAT}",
                ErrorType.VALIDATION_ERROR,
            )
        )

    # Must have at least one step
    if not job.steps:
        errors.append(
            ValidationError(
                "Job must contain at least one execution step",
                ErrorType.STRUCTURE_ERROR,
            )
        )

    flat_steps = list(iter_execution_steps(job.steps))

    # Validate step name uniqueness
    step_names: set[str] = set()
    for step in flat_steps:
        if step.name:
            if step.name in step_names:
                errors.append(
                    ValidationError(
                        f"Duplicate step name: {step.name}", ErrorType.VALIDATION_ERROR
                    )
                )
            else:
                step_names.add(step.name)

    # Validate each step
    for step in flat_steps:
        errors.extend(validate_step_structure(step))

    # Validate data dependencies (temp dataset creation/use order)
    errors.extend(validate_data_dependencies(job))

    # Validate cross-step permanent dataset lifecycle (duplicate alloc, use-after-uncatalog, etc.)
    from .dataset_lifecycle import validate_dataset_lifecycle

    errors.extend(validate_dataset_lifecycle(job))

    # Validate OUTPUT=*.name back-references (populated by parse_jcl).
    errors.extend(validate_output_references(job))

    logger.debug(
        "validation of job %s produced %d finding(s)",
        job.name or "(unnamed)",
        len(errors),
    )
    return errors


def validate_output_references(job: Job) -> list[ValidationError]:
    """Warn on ``OUTPUT=*.name`` DD references that do not resolve.

    Consumes ``Job.unresolved_output_refs`` which is populated during parsing
    by ``jclparser.parser._resolve_output_refs``.  Issues a WARNING (not an
    ERROR) for each unresolved reference so a malformed name does not cause
    strict-mode parsing to fail outright — the dataset may be intentionally
    resolved by a downstream tool or environment.
    """
    errors: list[ValidationError] = []
    for step_name, ref, line_number in getattr(job, "unresolved_output_refs", []):
        step_label = f" in step '{step_name}'" if step_name else ""
        errors.append(
            ValidationError(
                f"OUTPUT=*.{ref}{step_label} references an undefined OUTPUT statement",
                ErrorType.SEMANTIC_ERROR,
                line_number=line_number,
                severity=ErrorSeverity.WARNING,
            )
        )
    return errors


def validate_step_structure(step: Step) -> list[ValidationError]:
    """
    Validate step structure and constraints.

    Args:
        step: Step object to validate

    Returns:
        List of validation errors
    """
    errors = []

    # Step name validation (if provided)
    if step.name and not validate_jcl_identifier(step.name):
        errors.append(
            ValidationError(
                f"Invalid step name '{step.name}': {_JCL_NAME_FORMAT}",
                ErrorType.VALIDATION_ERROR,
            )
        )

    # Must have program or procedure
    if not step.program and not step.procedure:
        errors.append(
            ValidationError(
                f"Step {step.name or '(unnamed)'} must specify a program (PGM=) or procedure",
                ErrorType.VALIDATION_ERROR,
            )
        )

    # Cannot have both program and procedure
    if step.program and step.procedure:
        errors.append(
            ValidationError(
                f"Step {step.name or '(unnamed)'} cannot specify both program and procedure",
                ErrorType.VALIDATION_ERROR,
            )
        )

    # Validate DD name uniqueness within step (except for empty names used in concatenation)
    dd_names: set[str] = set()
    for dd in step.dd_statements:
        # Empty DD names are allowed for concatenation - skip duplicate check.
        # Duplicate DD names are reported as WARNING (not ERROR) because some
        # JES2 implementations accept them, treating the last definition as
        # authoritative.  They indicate a likely mistake but are not always fatal.
        if dd.name and dd.name in dd_names:
            errors.append(
                ValidationError(
                    f"Duplicate DD name in step {step.name or '(unnamed)'}: {dd.name}",
                    ErrorType.VALIDATION_ERROR,
                    severity=ErrorSeverity.WARNING,
                )
            )
        elif dd.name:  # Only add non-empty names to the set
            dd_names.add(dd.name)

    # Validate each DD statement
    for dd in step.dd_statements:
        errors.extend(validate_dd_statement(dd))

    return errors


# DD parameters other than DSN / SYSOUT / DUMMY / in-stream data that name
# where the DD's data comes from.
_OTHER_DD_SOURCES = ("DDNAME", "PATH", "SUBSYS")


def validate_dd_statement(dd: DDStatement) -> list[ValidationError]:
    """
    Validate DD statement structure and parameters.

    Args:
        dd: DDStatement object to validate

    Returns:
        List of validation errors
    """
    errors = []

    # DD name validation — empty names are valid for DD concatenation statements
    if dd.name and not validate_jcl_identifier(dd.name):
        errors.append(
            ValidationError(
                f"Invalid DD name '{dd.name}': {_JCL_NAME_FORMAT}",
                ErrorType.VALIDATION_ERROR,
            )
        )

    # Dataset name validation (if provided). A name that still holds a symbol
    # (&SYSUID..DATA, kept for explode_job() to resolve) cannot be judged yet;
    # the leading "&&" of a temporary dataset is not a symbol.
    dsn = dd.dataset_name
    unresolved = dsn is not None and "&" in dsn.removeprefix("&&")
    if dsn and not unresolved and not validate_dataset_name(dsn):
        errors.append(
            ValidationError(
                f"Invalid dataset name '{dd.dataset_name}'", ErrorType.VALIDATION_ERROR
            )
        )

    # Validate DISP parameter format
    if dd.disposition and not validate_disposition(dd.disposition):
        errors.append(
            ValidationError(
                f"Invalid DISP parameter '{dd.disposition}' on DD {dd.name}",
                ErrorType.VALIDATION_ERROR,
            )
        )

    # Check for conflicting parameters. DUMMY is stored as the positional
    # operand (``_pos_0``); with DSN= it is legal (the DSN is ignored), so it
    # only counts as a source, never as a conflict.
    params = dd.parameters
    positional = str(params.get("_pos_0", "")).upper()
    has_dsn = dd.dataset_name is not None
    has_sysout = "SYSOUT" in params
    has_dummy = "DUMMY" in params or positional == "DUMMY"
    has_inline = dd.has_inline_data or positional in ("*", "DATA")
    has_other_source = (
        any(key in params for key in _OTHER_DD_SOURCES) or positional == "DYNAM"
    )
    # UNIT= / SPACE= with no DSN allocates a system-named temporary dataset.
    allocates_temporary = any(key in params for key in ("UNIT", "SPACE"))

    conflict_count = sum([has_dsn, has_sysout, has_inline])
    source_count = conflict_count + sum(
        [has_dummy, has_other_source, allocates_temporary]
    )
    if conflict_count > 1:
        errors.append(
            ValidationError(
                f"DD {dd.name} has conflicting data source specifications",
                ErrorType.VALIDATION_ERROR,
            )
        )
    elif source_count == 0:
        errors.append(
            ValidationError(
                f"DD {dd.name} must specify a data source (DSN, SYSOUT, DUMMY, or inline data)",
                ErrorType.VALIDATION_ERROR,
            )
        )

    return errors


def validate_disposition(disp) -> bool:
    """
    Validate DISP parameter format.

    Compatibility wrapper — canonical rules live in
    ``parameter_validators.DISPValidator``.

    Args:
        disp: DISP parameter value to validate (string or list of parts)

    Returns:
        True if valid disposition
    """
    if not disp:
        return False
    # Handle list form — parser may produce ['NEW', 'CATLG', 'DELETE']. An
    # omitted status (DISP=(,CATLG)) is valid and defaults to NEW.
    if isinstance(disp, list):
        disp = "(" + ",".join(str(d) for d in disp) + ")"
    result = DISPValidator.validate(disp)
    return result.is_valid


def validate_data_dependencies(job: Job) -> list[ValidationError]:
    """
    Validate data dependencies between job steps.

    Args:
        job: Job object to validate

    Returns:
        List of validation errors
    """
    errors = []

    # Track temporary datasets created and used
    temp_datasets_created: dict[str, str] = {}  # dataset -> step_name
    temp_datasets_used: dict[str, list[str]] = {}  # dataset -> [step_names]

    flat_steps = list(iter_execution_steps(job.steps))

    for step in flat_steps:
        step_name = step.name or f"Step{len(temp_datasets_created) + 1}"

        for dd in step.dd_statements:
            if dd.dataset_name and dd.dataset_name.startswith("&&"):
                temp_ds = dd.dataset_name

                # Check if this is creating or using the dataset
                if dd.is_output():
                    if temp_ds in temp_datasets_created:
                        errors.append(
                            ValidationError(
                                f"Temporary dataset {temp_ds} created in multiple steps: "
                                f"{temp_datasets_created[temp_ds]} and {step_name}",
                                ErrorType.VALIDATION_ERROR,
                            )
                        )
                    temp_datasets_created[temp_ds] = step_name

                elif dd.is_input():
                    if temp_ds not in temp_datasets_used:
                        temp_datasets_used[temp_ds] = []
                    temp_datasets_used[temp_ds].append(step_name)

    # Check that temporary datasets are created before use.
    # Reported as WARNING rather than ERROR because the validator is flow-blind:
    # the creating step may be inside a conditional branch that the flat step list
    # does not reflect, so a hard ERROR here would produce false positives.
    for temp_ds in temp_datasets_used:
        if temp_ds not in temp_datasets_created:
            errors.append(
                ValidationError(
                    f"Temporary dataset {temp_ds} used but never created",
                    ErrorType.VALIDATION_ERROR,
                    severity=ErrorSeverity.WARNING,
                )
            )

    return errors
