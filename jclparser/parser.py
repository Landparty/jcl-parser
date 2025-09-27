"""
Core JCL parsing logic.

This module contains the main parsing functions for converting JCL scripts
into structured Python objects with full support for syntax validation
and plugin extensibility.
"""

import re
from pathlib import Path
from typing import Union, List, Optional, Dict, Any, IO
from .model import Job, Step, DDStatement, Statement, Parameter
from .errors import (
    JCLSyntaxError, JCLValidationError, ParseError, 
    ErrorType, ErrorSeverity
)
from .plugins import get_plugin_registry, ParserConfig


def parse_jcl(source: Union[str, Path, IO], strict_mode: bool = False, 
              config: Optional[ParserConfig] = None) -> Job:
    """
    Parse JCL script from various input sources into structured Job object.
    
    Args:
        source: JCL script content as string, file path, or file-like object
        strict_mode: Enable strict parsing mode
        config: Optional parser configuration
        
    Returns:
        Job object representing parsed JCL structure
        
    Raises:
        JCLSyntaxError: Invalid JCL syntax encountered
        JCLValidationError: Valid syntax but semantic errors
        FileNotFoundError: When source is path to non-existent file
    """
    # Handle different input source types
    if isinstance(source, Path):
        # Definitely a file path
        if not source.exists():
            raise FileNotFoundError(f"JCL file not found: {source}")
        with open(source, 'r', encoding='utf-8') as file:
            content = file.read()
    elif isinstance(source, str):
        # Check if it's likely a file path vs JCL content
        if (source.endswith('.jcl') or 
            (('/' in source or '\\' in source) and not source.strip().startswith('//'))):
            # Treat as file path
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"JCL file not found: {path}")
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
        else:
            # Treat as JCL content string
            content = source
    else:
        # Treat as file-like object
        content = source.read()
        if hasattr(source, 'seek'):
            source.seek(0)  # Reset for potential reuse
    
    # Parse the content
    lines = content.splitlines()
    
    # First pass: merge continuation lines
    merged_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        original_line_num = i + 1
        
        # Check if this is a JCL statement (not comment, not empty)
        if line.strip() and line.startswith("//") and not line.strip().startswith("//*"):
            # Check if this is a continuation line (// followed by only spaces before content)
            if len(line) > 2 and line[2:].startswith(" " * 13):  # Traditional JCL continuation
                # This is a continuation line - it should be merged with previous
                if merged_lines:
                    # Merge with previous line
                    prev_line, prev_line_num = merged_lines[-1]
                    continuation_content = line[2:].strip()  # Remove // and leading spaces
                    merged_line = prev_line + "," + continuation_content
                    merged_lines[-1] = (merged_line, prev_line_num)
                else:
                    # No previous line to merge with - treat as standalone
                    merged_lines.append((line, original_line_num))
            else:
                # Regular line - check if next lines are continuations
                merged_line = line
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    # Check if next line is a continuation
                    if (next_line.strip() and 
                        next_line.startswith("//") and 
                        len(next_line) > 2 and 
                        next_line[2:].startswith(" ") and
                        not next_line.strip().startswith("//*")):
                        # Check if this is actually a continuation (no statement name/type after spaces)
                        continuation_content = next_line[2:].strip()
                        # If it contains statement keywords like DD, EXEC, JOB, it's not a continuation
                        if not any(continuation_content.upper().startswith(kw + " ") or 
                                 continuation_content.upper() == kw for kw in 
                                 ["DD", "EXEC", "JOB", "PROC", "JCLLIB", "INCLUDE", "SET", "IF", "THEN", "ELSE", "ENDIF"]):
                            # This is a true continuation of current statement
                            merged_line += "," + continuation_content
                            j += 1
                        else:
                            # This is a new statement, not a continuation
                            break
                    else:
                        break
                
                merged_lines.append((merged_line, original_line_num))
                i = j - 1  # Skip the continuation lines we processed
        else:
            # Non-JCL statement (comment, empty line, etc.)
            merged_lines.append((line, original_line_num))
        
        i += 1
    
    # Now parse the merged lines
    job = None
    current_step = None
    current_dd = None
    inline_data_lines = []
    in_inline_data = False
    
    for line, line_num in merged_lines:
        try:
            # Handle inline data continuation
            if in_inline_data:
                if line.strip() == "/*":
                    # End of inline data
                    if current_dd:
                        current_dd.inline_data = '\n'.join(inline_data_lines)
                    inline_data_lines = []
                    in_inline_data = False
                    continue
                else:
                    # Collect inline data
                    inline_data_lines.append(line)
                    continue
            
            # Skip comments and empty lines
            if not line.strip() or line.strip().startswith("//*"):
                continue
            
            # Parse the statement
            stmt = parse_statement(line, line_num)
            if not stmt:
                continue
            
            # Process different statement types
            if stmt.type == "JOB":
                if job is not None:
                    raise JCLSyntaxError(f"Multiple JOB statements found", line_num)
                job = _create_job_from_statement(stmt)
            
            elif stmt.type == "EXEC":
                if job is None:
                    raise JCLSyntaxError("EXEC statement before JOB statement", line_num)
                
                # Basic syntax check for EXEC - must have program or procedure
                has_pgm = "PGM" in stmt.parameters
                has_positional = any(k.startswith("_pos_") for k in stmt.parameters.keys())
                if not has_pgm and not has_positional:
                    raise JCLSyntaxError("EXEC statement missing program or procedure", line_num)
                
                current_step = _create_step_from_statement(stmt)
                job.add_step(current_step)
            
            elif stmt.type == "DD":
                if current_step is None:
                    raise JCLSyntaxError("DD statement before EXEC statement", line_num)
                current_dd = _create_dd_from_statement(stmt)
                current_step.add_dd(current_dd)
                
                # Check for inline data marker
                if current_dd.parameters.get("*"):
                    in_inline_data = True
                    inline_data_lines = []
        
        except Exception as e:
            if isinstance(e, (JCLSyntaxError, JCLValidationError)):
                raise
            else:
                raise JCLSyntaxError(f"Parse error: {str(e)}", line_num)
    
    if job is None:
        raise JCLSyntaxError("No JOB statement found", 0)
    
    # Validate the parsed job if not in strict mode
    if not strict_mode:
        validation_errors = job.validate()
        if validation_errors:
            error_msg = "; ".join([err.message for err in validation_errors])
            raise JCLValidationError(f"Job validation failed: {error_msg}")
    
    return job


def validate_jcl(source: Union[str, Path, IO], level: str = "basic") -> List[ParseError]:
    """
    Validate JCL syntax and structure without full parsing.
    
    Args:
        source: JCL script to validate  
        level: Validation level (syntax_only, structure, semantic)
        
    Returns:
        List of ParseError objects (empty if valid)
    """
    errors = []
    
    # First try normal parsing to catch basic structure issues
    try:
        job = parse_jcl(source, strict_mode=True)
        
        # Additional validation based on level
        if level in ("structure", "semantic"):
            validation_errors = job.validate()
            for err in validation_errors:
                errors.append(ParseError(
                    error_type=err.error_type,
                    message=err.message,
                    line_number=0,
                    severity=ErrorSeverity.ERROR
                ))
        
        # Plugin-based validation
        if level == "semantic":
            registry = get_plugin_registry()
            for validator in registry.get_validators():
                validation_errors = validator.validate_job(job)
                for err in validation_errors:
                    errors.append(ParseError(
                        error_type=err.error_type,
                        message=err.message,
                        line_number=0,
                        severity=ErrorSeverity.ERROR
                    ))
        
        return errors
    
    except (JCLSyntaxError, JCLValidationError):
        # If parsing failed, do line-by-line validation to collect multiple errors
        pass
    
    # Line-by-line validation to catch multiple syntax errors
    # Parse content from source
    if isinstance(source, Path):
        if not source.exists():
            errors.append(ParseError(
                error_type=ErrorType.SYNTAX_ERROR,
                message=f"JCL file not found: {source}",
                line_number=0,
                severity=ErrorSeverity.ERROR
            ))
            return errors
        with open(source, 'r', encoding='utf-8') as file:
            content = file.read()
    elif isinstance(source, str):
        if (source.endswith('.jcl') or 
            (('/' in source or '\\' in source) and not source.strip().startswith('//'))):
            path = Path(source)
            if not path.exists():
                errors.append(ParseError(
                    error_type=ErrorType.SYNTAX_ERROR,
                    message=f"JCL file not found: {path}",
                    line_number=0,
                    severity=ErrorSeverity.ERROR
                ))
                return errors
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
        else:
            content = source
    else:
        content = source.read()
        if hasattr(source, 'seek'):
            source.seek(0)
    
    # Validate line by line, collecting all errors
    lines = content.splitlines()
    has_job = False
    current_step = None
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith("//*"):
            continue
        
        # Validate each statement individually
        try:
            stmt = parse_statement(line, line_num)
            if stmt:
                # Basic structure validation
                if stmt.type == "JOB":
                    if has_job:
                        errors.append(ParseError(
                            error_type=ErrorType.SYNTAX_ERROR,
                            message="Multiple JOB statements found",
                            line_number=line_num,
                            severity=ErrorSeverity.ERROR
                        ))
                    has_job = True
                
                elif stmt.type == "EXEC":
                    if not has_job:
                        errors.append(ParseError(
                            error_type=ErrorType.SYNTAX_ERROR,
                            message="EXEC statement before JOB statement",
                            line_number=line_num,
                            severity=ErrorSeverity.ERROR
                        ))
                    
                    # Check for missing program or procedure
                    has_pgm = "PGM" in stmt.parameters
                    has_positional = any(k.startswith("_pos_") for k in stmt.parameters.keys())
                    if not has_pgm and not has_positional:
                        errors.append(ParseError(
                            error_type=ErrorType.SYNTAX_ERROR,
                            message="EXEC statement missing program or procedure",
                            line_number=line_num,
                            severity=ErrorSeverity.ERROR
                        ))
                    current_step = stmt
                
                elif stmt.type == "DD":
                    if current_step is None:
                        errors.append(ParseError(
                            error_type=ErrorType.SYNTAX_ERROR,
                            message="DD statement before EXEC statement",
                            line_number=line_num,
                            severity=ErrorSeverity.ERROR
                        ))
        
        except JCLSyntaxError as e:
            errors.append(ParseError(
                error_type=ErrorType.SYNTAX_ERROR,
                message=e.message,
                line_number=e.line_number or line_num,
                context=e.context,
                severity=ErrorSeverity.ERROR
            ))
        except JCLValidationError as e:
            errors.append(ParseError(
                error_type=ErrorType.VALIDATION_ERROR,
                message=e.message,
                line_number=e.line_number or line_num,
                context=e.context,
                severity=ErrorSeverity.ERROR
            ))
    
    return errors


def parse_statement(line: str, line_number: int = 0) -> Optional[Statement]:
    """
    Parse individual JCL statement for syntax analysis.
    
    Args:
        line: Single line of JCL text
        line_number: Line number for error context
        
    Returns:
        Parsed statement object or None if comment/empty
        
    Raises:
        JCLSyntaxError: If line cannot be parsed
    """
    # Check for plugin that can handle this line
    registry = get_plugin_registry()
    plugin = registry.get_parser_for_line(line)
    if plugin:
        return plugin.parse_statement(line, line_number)
    
    # Standard JCL parsing
    line = line.strip()
    
    # Skip comments and empty lines
    if not line or line.startswith("//*"):
        return None
    
    # JCL statements must start with //
    if not line.startswith("//"):
        raise JCLSyntaxError(f"Invalid JCL statement (must start with //): {line}", line_number)
    
    # Remove // prefix
    content = line[2:]
    
    # Handle continuation lines - these start with spaces after //
    if content.startswith(" ") and content.strip():
        # This is a continuation line - return None as it should be processed with main statement
        return None
        
    content = content.strip()
    
    # Handle empty lines after //
    if not content:
        return None
    
    # Parse statement name and type
    if " " not in content:
        raise JCLSyntaxError(f"Invalid statement format: {line}", line_number)
    
    name_part, rest = content.split(" ", 1)
    rest = rest.strip()
    
    # Determine statement type
    if " " not in rest:
        statement_type = rest.upper()
        parameters_part = ""
    else:
        statement_type, parameters_part = rest.split(" ", 1)
        statement_type = statement_type.upper()
    
    # Validate statement type
    valid_types = ["JOB", "EXEC", "DD", "PROC", "JCLLIB", "INCLUDE", "SET", "IF", "THEN", "ELSE", "ENDIF"]
    if statement_type not in valid_types:
        raise JCLSyntaxError(f"Unknown statement type: {statement_type}", line_number)
    
    # Parse parameters
    parameters = _parse_parameters(parameters_part, line_number) if parameters_part else {}
    
    return Statement(
        type=statement_type,
        name=name_part,
        parameters=parameters,
        line_number=line_number
    )


def _parse_parameters(param_string: str, line_number: int = 0) -> Dict[str, Any]:
    """Parse JCL parameters from parameter string"""
    parameters = {}
    
    if not param_string.strip():
        return parameters
    
    # Handle special cases like DD * 
    if param_string.strip() == "*":
        parameters["*"] = True
        return parameters
    
    # Simple parameter parsing (can be enhanced)
    # Handle comma-separated parameters
    parts = []
    current = ""
    in_quotes = False
    paren_depth = 0
    
    for char in param_string:
        if char == "'" and (not current or current[-1] != "\\"):
            in_quotes = not in_quotes
        elif char == "(" and not in_quotes:
            paren_depth += 1
        elif char == ")" and not in_quotes:
            paren_depth -= 1
        elif char == "," and not in_quotes and paren_depth == 0:
            if current.strip():
                parts.append(current.strip())
            current = ""
            continue
        current += char
    
    if current.strip():
        parts.append(current.strip())
    
    # Check for unclosed quotes
    if in_quotes:
        raise JCLSyntaxError(f"Unclosed quote in parameter: {param_string}", line_number)
    
    # Check for unmatched parentheses
    if paren_depth != 0:
        raise JCLSyntaxError(f"Unmatched parentheses in parameter: {param_string}", line_number)
    
    # Parse individual parameters
    for i, part in enumerate(parts):
        if "=" in part:
            key, value = part.split("=", 1)
            parameters[key.strip()] = value.strip()
        else:
            # Positional parameter
            parameters[f"_pos_{i}"] = part.strip()
    
    return parameters


def _create_job_from_statement(stmt: Statement) -> Job:
    """Create Job object from JOB statement"""
    accounting_info = None
    
    # Extract accounting information (first positional parameter)
    if "_pos_0" in stmt.parameters:
        accounting_info = stmt.parameters["_pos_0"].strip("()")
    
    # Extract other parameters
    job_params = {k: v for k, v in stmt.parameters.items() if not k.startswith("_pos_")}
    
    return Job(
        name=stmt.name,
        parameters=job_params,
        accounting_info=accounting_info,
        line_number=stmt.line_number
    )


def _create_step_from_statement(stmt: Statement) -> Step:
    """Create Step object from EXEC statement"""
    program = None
    procedure = None
    
    # Check if it's a program or procedure call
    if "PGM" in stmt.parameters:
        program = stmt.parameters.pop("PGM")
    elif "_pos_0" in stmt.parameters:
        # Might be a procedure call
        procedure = stmt.parameters.pop("_pos_0")
    
    return Step(
        name=stmt.name,
        program=program,
        procedure=procedure,
        parameters=stmt.parameters,
        line_number=stmt.line_number
    )


def _create_dd_from_statement(stmt: Statement) -> DDStatement:
    """Create DDStatement object from DD statement"""
    dataset_name = stmt.parameters.get("DSN")
    disposition = stmt.parameters.get("DISP")
    
    return DDStatement(
        name=stmt.name,
        dataset_name=dataset_name,
        disposition=disposition,
        parameters=stmt.parameters,
        line_number=stmt.line_number
    )