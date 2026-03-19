"""
JCL syntax and structure validation functions.

Contains validation logic for JCL syntax rules, semantic constraints,
and data integrity checks for parsed JCL structures.
"""

import re
from typing import List, Set, Dict, Any, Optional
from .model import Job, Step, DDStatement, ConditionalBlock, iter_execution_steps
from .errors import ValidationError, ErrorType
from .parameter_validators import DatasetNameValidator, DISPValidator

# Precompiled regex patterns for performance
_RE_JCL_ID_START = re.compile(r'^[A-Za-z@#$]')
_RE_JCL_ID_FULL = re.compile(r'^[A-Za-z0-9@#$]+$')
_RE_PARAM_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9]*$')


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
    
    # Must start with letter or @, #, $
    if not _RE_JCL_ID_START.match(name):
        return False

    # Remaining characters can be alphanumeric or @, #, $
    return _RE_JCL_ID_FULL.match(name) is not None


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


def validate_job_structure(job: Job) -> List[ValidationError]:
    """
    Validate complete job structure and dependencies.
    
    Args:
        job: Job object to validate
        
    Returns:
        List of validation errors
    """
    errors = []
    
    # Job name validation
    if not validate_jcl_identifier(job.name):
        errors.append(ValidationError(
            f"Invalid job name '{job.name}': must be 1-8 characters, alphanumeric + @#$",
            ErrorType.VALIDATION_ERROR
        ))
    
    # Must have at least one step
    if not job.steps:
        errors.append(ValidationError(
            "Job must contain at least one execution step",
            ErrorType.STRUCTURE_ERROR
        ))
    
    flat_steps = list(iter_execution_steps(job.steps))

    # Validate step name uniqueness
    step_names: Set[str] = set()
    for step in flat_steps:
        if step.name:
            if step.name in step_names:
                errors.append(ValidationError(
                    f"Duplicate step name: {step.name}",
                    ErrorType.VALIDATION_ERROR
                ))
            else:
                step_names.add(step.name)
    
    # Validate each step
    for step in flat_steps:
        errors.extend(validate_step_structure(step))
    
    # Validate data dependencies
    errors.extend(validate_data_dependencies(job))
    
    return errors


def validate_step_structure(step: Step) -> List[ValidationError]:
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
        errors.append(ValidationError(
            f"Invalid step name '{step.name}': must be 1-8 characters, alphanumeric + @#$",
            ErrorType.VALIDATION_ERROR
        ))
    
    # Must have program or procedure
    if not step.program and not step.procedure:
        errors.append(ValidationError(
            f"Step {step.name or '(unnamed)'} must specify a program (PGM=) or procedure",
            ErrorType.VALIDATION_ERROR
        ))
    
    # Cannot have both program and procedure
    if step.program and step.procedure:
        errors.append(ValidationError(
            f"Step {step.name or '(unnamed)'} cannot specify both program and procedure",
            ErrorType.VALIDATION_ERROR
        ))
    
    # Validate DD name uniqueness within step (except for empty names used in concatenation)
    dd_names: Set[str] = set()
    for dd in step.dd_statements:
        # Empty DD names are allowed for concatenation - skip duplicate check
        if dd.name and dd.name in dd_names:
            errors.append(ValidationError(
                f"Duplicate DD name in step {step.name or '(unnamed)'}: {dd.name}",
                ErrorType.VALIDATION_ERROR
            ))
        elif dd.name:  # Only add non-empty names to the set
            dd_names.add(dd.name)
    
    # Validate each DD statement
    for dd in step.dd_statements:
        errors.extend(validate_dd_statement(dd))
    
    return errors


def validate_dd_statement(dd: DDStatement) -> List[ValidationError]:
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
        errors.append(ValidationError(
            f"Invalid DD name '{dd.name}': must be 1-8 characters, alphanumeric + @#$",
            ErrorType.VALIDATION_ERROR
        ))
    
    # Dataset name validation (if provided)
    if dd.dataset_name and not validate_dataset_name(dd.dataset_name):
        errors.append(ValidationError(
            f"Invalid dataset name '{dd.dataset_name}'",
            ErrorType.VALIDATION_ERROR
        ))
    
    # Validate DISP parameter format
    if dd.disposition and not validate_disposition(dd.disposition):
        errors.append(ValidationError(
            f"Invalid DISP parameter '{dd.disposition}' on DD {dd.name}",
            ErrorType.VALIDATION_ERROR
        ))
    
    # Check for conflicting parameters
    has_dsn = dd.dataset_name is not None
    has_sysout = "SYSOUT" in dd.parameters
    has_dummy = "DUMMY" in dd.parameters
    has_inline = dd.has_inline_data
    
    conflict_count = sum([has_dsn, has_sysout, has_dummy, has_inline])
    if conflict_count > 1:
        errors.append(ValidationError(
            f"DD {dd.name} has conflicting data source specifications",
            ErrorType.VALIDATION_ERROR
        ))
    elif conflict_count == 0:
        errors.append(ValidationError(
            f"DD {dd.name} must specify a data source (DSN, SYSOUT, DUMMY, or inline data)",
            ErrorType.VALIDATION_ERROR
        ))
    
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
    # Handle list form — parser may produce ['NEW', 'CATLG', 'DELETE']
    if isinstance(disp, list):
        if not disp or not disp[0]:
            return False
        disp = '(' + ','.join(str(d) for d in disp) + ')'
    # For parenthesized forms, status must be non-empty
    stripped = disp.strip()
    if stripped.startswith('(') and stripped.endswith(')'):
        inner = stripped[1:-1]
        parts = [p.strip() for p in inner.split(',')]
        if not parts[0]:
            return False
    result = DISPValidator.validate(disp)
    return result.is_valid


def validate_data_dependencies(job: Job) -> List[ValidationError]:
    """
    Validate data dependencies between job steps.
    
    Args:
        job: Job object to validate
        
    Returns:
        List of validation errors
    """
    errors = []
    
    # Track temporary datasets created and used
    temp_datasets_created: Dict[str, str] = {}  # dataset -> step_name
    temp_datasets_used: Dict[str, List[str]] = {}  # dataset -> [step_names]
    
    flat_steps = list(iter_execution_steps(job.steps))
    
    for step in flat_steps:
        step_name = step.name or f"Step{len(temp_datasets_created) + 1}"
        
        for dd in step.dd_statements:
            if dd.dataset_name and dd.dataset_name.startswith("&&"):
                temp_ds = dd.dataset_name
                
                # Check if this is creating or using the dataset
                if dd.is_output():
                    if temp_ds in temp_datasets_created:
                        errors.append(ValidationError(
                            f"Temporary dataset {temp_ds} created in multiple steps: "
                            f"{temp_datasets_created[temp_ds]} and {step_name}",
                            ErrorType.VALIDATION_ERROR
                        ))
                    temp_datasets_created[temp_ds] = step_name
                
                elif dd.is_input():
                    if temp_ds not in temp_datasets_used:
                        temp_datasets_used[temp_ds] = []
                    temp_datasets_used[temp_ds].append(step_name)
    
    # Check that temporary datasets are created before use
    for temp_ds, using_steps in temp_datasets_used.items():
        if temp_ds not in temp_datasets_created:
            errors.append(ValidationError(
                f"Temporary dataset {temp_ds} used but never created",
                ErrorType.VALIDATION_ERROR
            ))
    
    return errors


def validate_parameter_syntax(param_name: str, param_value: Any) -> List[ValidationError]:
    """
    Validate individual parameter syntax.
    
    Args:
        param_name: Parameter name
        param_value: Parameter value
        
    Returns:
        List of validation errors
    """
    errors = []
    
    # Parameter name validation
    if not _RE_PARAM_NAME.match(param_name):
        errors.append(ValidationError(
            f"Invalid parameter name '{param_name}': must start with letter, alphanumeric only",
            ErrorType.VALIDATION_ERROR
        ))
    
    # Value validation depends on type
    if isinstance(param_value, str):
        # Check for unmatched quotes
        if param_value.count("'") % 2 != 0:
            errors.append(ValidationError(
                f"Unmatched quotes in parameter {param_name}: {param_value}",
                ErrorType.SYNTAX_ERROR
            ))
    
    return errors