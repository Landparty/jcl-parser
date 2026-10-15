"""
JCL syntax and structure validation functions.

Contains validation logic for JCL syntax rules, semantic constraints,
and data integrity checks for parsed JCL structures.
"""

import logging
import re

from .errors import ErrorSeverity, ErrorType, ValidationError
from .model import (
    ConditionalBlock,
    DDStatement,
    Job,
    Step,
    _dataset_dds,
    iter_execution_steps,
)
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


def validate_step_name(name: str) -> bool:
    """
    Validate a step name, allowing the qualified form of an exploded step.

    ``explode_job()`` names each PROC step ``<callingstep>.<procstep>``
    (e.g. ``S1.PS1``); each dot-separated component must itself be a valid
    JCL identifier.

    Args:
        name: Step name to validate

    Returns:
        True if every component is a valid JCL identifier
    """
    if not name:
        return False
    return all(validate_jcl_identifier(part) for part in name.split("."))


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

    # A JOB-less PROC member has no JOB statement and keeps its steps in
    # job.procedures; the job-name and "at least one step" rules are about
    # a JOB statement and do not apply to it.
    if not job.is_procedure_member and not validate_jcl_identifier(job.name):
        errors.append(
            ValidationError(
                f"Invalid job name '{job.name}': {_JCL_NAME_FORMAT}",
                ErrorType.VALIDATION_ERROR,
                line_number=job.line_number,
            )
        )

    # Must have at least one step
    if not job.steps and not job.is_procedure_member:
        errors.append(
            ValidationError(
                "Job must contain at least one execution step",
                ErrorType.STRUCTURE_ERROR,
                line_number=job.line_number,
            )
        )

    flat_steps = list(iter_execution_steps(job.steps))

    # Validate step name uniqueness
    step_names: set[str] = set()
    for step in flat_steps:
        # An exploded step called from an unnamed EXEC carries a placeholder
        # qualifier (``PROC.PS1``), so two unnamed calls of one PROC share a
        # name without either being a coding error.
        if step.is_exploded and not step.original_proc_call:
            continue
        if step.name:
            if step.name in step_names:
                errors.append(
                    ValidationError(
                        f"Duplicate step name: {step.name}",
                        ErrorType.VALIDATION_ERROR,
                        line_number=step.line_number,
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

    errors.extend(validate_procedure_references(job))

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


def validate_procedure_references(job: Job) -> list[ValidationError]:
    """Warn on ``EXEC procname`` calls whose PROC was not found.

    :func:`jclparser.parse_jcl` adds every PROC it can load (in-stream,
    JCLLIB / system PROCLIB under the base path, built-in) to
    ``job.procedures``.  A call to any other PROC cannot be checked or
    expanded here, but the PROC may well exist in the JES PROCLIB, so it is
    a WARNING, not an ERROR (issue #116).  A strict parse of a job with a
    ``JCLLIB ORDER`` still fails on it before this runs.
    """
    errors: list[ValidationError] = []
    for step in iter_execution_steps(job.steps):
        if step.procedure and not job.get_procedure(step.procedure):
            errors.append(
                ValidationError(
                    f"Procedure '{step.procedure}' not found in-stream or in "
                    "any configured PROC library; step "
                    f"'{step.name or ''}' cannot be checked or expanded",
                    ErrorType.SEMANTIC_ERROR,
                    line_number=step.line_number,
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
    if step.name and not validate_step_name(step.name):
        errors.append(
            ValidationError(
                f"Invalid step name '{step.name}': {_JCL_NAME_FORMAT}",
                ErrorType.VALIDATION_ERROR,
                line_number=step.line_number,
            )
        )

    # Must have program or procedure
    if not step.program and not step.procedure:
        errors.append(
            ValidationError(
                f"Step {step.name or '(unnamed)'} must specify a program (PGM=) or procedure",
                ErrorType.VALIDATION_ERROR,
                line_number=step.line_number,
            )
        )

    # Cannot have both program and procedure
    if step.program and step.procedure:
        errors.append(
            ValidationError(
                f"Step {step.name or '(unnamed)'} cannot specify both program and procedure",
                ErrorType.VALIDATION_ERROR,
                line_number=step.line_number,
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
                    line_number=dd.line_number,
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

# DD parameters that, with no DSN, allocate a system-named temporary dataset.
_TEMP_ALLOCATION_KEYS = (
    "UNIT",
    "SPACE",
    "DATACLAS",
    "STORCLAS",
    "MGMTCLAS",
    "LIKE",
    "REFDD",
    "AVGREC",
)


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
                line_number=dd.line_number,
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
                f"Invalid dataset name '{dd.dataset_name}'",
                ErrorType.VALIDATION_ERROR,
                line_number=dd.line_number,
            )
        )

    # Validate DISP parameter format
    if dd.disposition and not validate_disposition(dd.disposition):
        errors.append(
            ValidationError(
                f"Invalid DISP parameter '{dd.disposition}' on DD {dd.name}",
                ErrorType.VALIDATION_ERROR,
                line_number=dd.line_number,
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
    # UNIT= / SPACE= (or SMS classes / LIKE= / REFDD= / AVGREC= supplying the
    # allocation attributes) with no DSN allocates a system-named temporary
    # dataset.
    allocates_temporary = any(key in params for key in _TEMP_ALLOCATION_KEYS)

    conflict_count = sum([has_dsn, has_sysout, has_inline])
    source_count = conflict_count + sum(
        [has_dummy, has_other_source, allocates_temporary]
    )
    if conflict_count > 1:
        errors.append(
            ValidationError(
                f"DD {dd.name} has conflicting data source specifications",
                ErrorType.VALIDATION_ERROR,
                line_number=dd.line_number,
            )
        )
    elif source_count == 0:
        errors.append(
            ValidationError(
                f"DD {dd.name} must specify a data source (DSN, SYSOUT, DUMMY, or inline data)",
                ErrorType.VALIDATION_ERROR,
                line_number=dd.line_number,
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
    tracker = _TempDatasetTracker()
    tracker.walk(job.steps, {})
    return tracker.findings()


class _TempDatasetTracker:
    """Creation / use of temporary (``&&name``) datasets, in execution order."""

    def __init__(self) -> None:
        self.errors: list[ValidationError] = []
        #: dataset -> name of the step that (last) created it
        self.created: dict[str, str] = {}
        #: dataset -> line of the first DD that reads or extends it
        self.first_use: dict[str, int] = {}

    def walk(
        self, items: list[Step | ConditionalBlock], active: dict[str, str]
    ) -> dict[str, str]:
        """Walk *items* in execution order; return the temporaries left.

        The THEN and ELSE branches of an IF are mutually exclusive, so each
        starts from the state before the IF (#60: the same ``&&T`` created
        in both is not a duplicate), and after ENDIF a temporary exists when
        either branch left it.
        """
        for item in items:
            if isinstance(item, Step):
                self.check_step(item, active)
            elif isinstance(item, ConditionalBlock):
                then_active = self.walk(item.then_steps, dict(active))
                else_active = self.walk(item.else_steps, dict(active))
                active = {**else_active, **then_active}
        return active

    def check_step(self, step: Step, active: dict[str, str]) -> None:
        """Check one step's temporary DDs against *active*, updating it.

        *active* maps each temporary dataset that still exists (created and
        not yet deleted by an explicit or defaulted DELETE) to the step that
        created it.  DISP=MOD on one of them extends it (the classic way to
        collect several compiles' object decks in &&LOADSET) rather than
        creating it a second time.
        """
        step_name = step.name or f"Step{len(self.created) + 1}"
        for dd in _dataset_dds(step):
            if dd.dataset_name and dd.dataset_name.startswith("&&"):
                self._check_dd(dd, step_name, active)

    def _check_dd(
        self, dd: DDStatement, step_name: str, active: dict[str, str]
    ) -> None:
        # &&GOSET(GO) names a member of &&GOSET: key on the dataset.
        temp_ds = (dd.dataset_name or "").split("(", 1)[0]
        tokens = dd._disp_tokens() if dd.disposition else []
        extends_existing = bool(tokens) and tokens[0] == "MOD" and temp_ds in active

        # Check if this is creating or using the dataset
        if dd.is_output() and not extends_existing:
            if temp_ds in active:
                self.errors.append(
                    ValidationError(
                        f"Temporary dataset {temp_ds} created in multiple steps: "
                        f"{active[temp_ds]} and {step_name}",
                        ErrorType.VALIDATION_ERROR,
                        line_number=dd.line_number,
                    )
                )
            self.created[temp_ds] = step_name
            active[temp_ds] = step_name
        elif dd.is_input() or extends_existing:
            self.first_use.setdefault(temp_ds, dd.line_number)

        normal_disp = tokens[1] if len(tokens) >= 2 else ""
        if normal_disp == "DELETE" or (
            tokens and tokens[0] == "NEW" and not normal_disp
        ):
            # Deleted at the end of this step (an omitted normal disposition
            # on a NEW dataset defaults to DELETE): a later step may create
            # one of the same name again.
            active.pop(temp_ds, None)

    def findings(self) -> list[ValidationError]:
        """The duplicate-creation errors, then the used-but-never-created ones.

        The latter are reported as WARNING rather than ERROR because the
        validator is flow-blind: the creating step may be inside a
        conditional branch that the flat step list does not reflect, so a
        hard ERROR here would produce false positives.
        """
        errors = list(self.errors)
        for temp_ds, line_number in self.first_use.items():
            if temp_ds not in self.created:
                errors.append(
                    ValidationError(
                        f"Temporary dataset {temp_ds} used but never created",
                        ErrorType.VALIDATION_ERROR,
                        line_number=line_number,
                        severity=ErrorSeverity.WARNING,
                    )
                )
        return errors
