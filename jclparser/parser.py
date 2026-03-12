"""
Core JCL parsing logic.

This module contains the main parsing functions for converting JCL scripts
into structured Python objects with full support for syntax validation
and plugin extensibility.
"""

import re
from pathlib import Path
from typing import Union, List, Optional, Dict, Any, IO
from .model import Job, Step, DDStatement, Statement, Parameter, ConditionalBlock, Procedure
from .errors import (
    JCLSyntaxError, JCLValidationError, ParseError, 
    ErrorType, ErrorSeverity
)
from .plugins import get_plugin_registry, ParserConfig
from .utils import normalize_jcl_line, read_source, POSITIONAL_PARAM_PREFIX, is_positional_key
from .continuation_handler import ContinuationLineHandler

#: All recognised JCL statement type keywords (single canonical definition).
_STATEMENT_TYPES: frozenset = frozenset({
    "JOB", "EXEC", "DD", "PROC", "PEND", "JCLLIB", "INCLUDE",
    "SET", "IF", "THEN", "ELSE", "ENDIF", "XMIT", "OUTPUT",
    "SCHEDULE", "NULL", "COMMAND", "CNTL", "ENDCNTL",
})


def parse_jcl(
    source: Union[str, Path, IO], 
    strict_mode: bool = False, 
    config: Optional[ParserConfig] = None,
    proc_base_path: Optional[Union[str, Path]] = None,
    enable_external_procs: bool = True
) -> Job:
    """
    Parse JCL script from various input sources into structured Job object.
    
    Args:
        source: JCL script content as string, file path, or file-like object
        strict_mode: Enable strict parsing mode
        config: Optional parser configuration
        proc_base_path: Base directory for external PROC libraries
                       (defaults to JCL_PROCLIB_PATH env var or current directory)
        enable_external_procs: Enable loading PROCs from file system via JCLLIB ORDER
        
    Returns:
        Job object representing parsed JCL structure
        
    Raises:
        JCLSyntaxError: Invalid JCL syntax encountered
        JCLValidationError: Valid syntax but semantic errors
        FileNotFoundError: When source is path to non-existent file
    """
    # Handle different input source types
    try:
        content = read_source(source)
    except FileNotFoundError:
        raise

    # Parse the content
    raw_lines = content.splitlines()
    lines = [normalize_jcl_line(line) for line in raw_lines]
    
    # First pass: handle inline data sections (must be before continuation line merging)
    # Mark lines that are inside inline data blocks
    inline_data_markers = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if this line starts DD * or DD DATA
        if line.strip() and line.startswith("//") and not line.strip().startswith("//*"):
            upper_line = line.upper()
            # Match DD followed by * or DATA (with possible spaces)
            if " DD " in upper_line or " DD*" in upper_line or "\tDD\t" in upper_line:
                if (" DD *" in upper_line or " DD*" in upper_line or 
                    " DD DATA" in upper_line or "\tDD\t*" in upper_line or
                    ",DLM=" in upper_line):  # DD DATA,DLM=...
                    # Extract delimiter if specified
                    delimiter = "/*"  # default
                    if "DLM=" in upper_line:
                        dlm_start = upper_line.index("DLM=") + 4
                        dlm_end = dlm_start
                        while dlm_end < len(upper_line) and upper_line[dlm_end] not in ",) \t\r\n":
                            dlm_end += 1
                        delimiter = line[dlm_start:dlm_end]
                    
                    # Mark all following lines until delimiter as inline data
                    i += 1
                    while i < len(lines):
                        if lines[i].strip() == delimiter or lines[i].strip().startswith(delimiter):
                            inline_data_markers[i] = True  # Mark delimiter line too
                            break
                        inline_data_markers[i] = True
                        i += 1
        i += 1
    
    
    # Second pass: merge continuation lines using enhanced handler
    # Filter out inline data lines before merging (they should not be merged)
    non_inline_lines = []
    inline_line_map = {}  # Map from non-inline index to original index
    
    for i, line in enumerate(lines):
        if i not in inline_data_markers:
            inline_line_map[len(non_inline_lines)] = i
            non_inline_lines.append(line)
    
    # Use enhanced continuation handler
    handler = ContinuationLineHandler()
    merged_non_inline = handler.merge_continuation_lines(non_inline_lines)
    
    # Now interleave the merged lines with inline data lines
    merged_lines = []
    merged_idx = 0
    
    for i, line in enumerate(lines):
        if i in inline_data_markers:
            # This is an inline data line - add it directly
            merged_lines.append((line, i + 1))
        else:
            # This is a regular line - check if we have a merged version
            # Find the corresponding merged line
            if merged_idx < len(merged_non_inline):
                merged_line, orig_line_num = merged_non_inline[merged_idx]
                # Check if this merged line starts at this position
                if inline_line_map.get(orig_line_num - 1) == i:
                    merged_lines.append((merged_line, i + 1))
                    merged_idx += 1
    
    # Now parse the merged lines
    job = None
    conditional_stack = []  # List of tuples: (ConditionalBlock, active_branch)
    current_step = None
    current_dd = None
    inline_data_lines = []
    in_inline_data = False
    current_procedure = None  # Track when we're inside a PROC/PEND block
    current_delimiter = "/*"
    orphaned_dds = []  # Track DDs that appear before first EXEC

    
    for line, line_num in merged_lines:
        try:
            # Handle inline data continuation
            if in_inline_data:
                if line.strip() == current_delimiter or line.strip().startswith(current_delimiter):
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
            
            # Skip lines marked as inline data (line_num is 1-indexed, markers use 0-indexed)
            if (line_num - 1) in inline_data_markers:
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
                
                # Basic syntax check for EXEC - must have program, procedure, or positional parameter
                has_pgm = "PGM" in stmt.parameters
                has_proc = "PROC" in stmt.parameters
                has_positional = any(is_positional_key(k) for k in stmt.parameters.keys())
                if not has_pgm and not has_proc and not has_positional:
                    raise JCLSyntaxError("EXEC statement missing program or procedure", line_num)
                
                current_step = _create_step_from_statement(stmt)
                
                # Attach any orphaned DDs to this first step
                if orphaned_dds:
                    for dd in orphaned_dds:
                        current_step.add_dd(dd)
                    orphaned_dds = []
                
                # Add step to procedure if we're inside PROC/PEND, otherwise to job
                if conditional_stack:
                    active_cond, active_branch = conditional_stack[-1]
                    if active_branch == 'THEN':
                        active_cond.add_then_step(current_step)
                    else:
                        active_cond.add_else_step(current_step)
                elif current_procedure is not None:
                    current_procedure.steps.append(current_step)
                else:
                    job.add_step(current_step)
            elif stmt.type == "DD":
                # Create the DD statement
                current_dd = _create_dd_from_statement(stmt)
                
                if current_step is None:
                    # Store as orphaned DD to be attached to next step
                    orphaned_dds.append(current_dd)
                elif stmt.name and '.' in stmt.name:
                    # This is a DD override for a procedure step
                    parts = stmt.name.split('.', 1)  # Split on first dot only
                    if len(parts) == 2:
                        # Store as override on the current step
                        current_dd = _create_dd_from_statement(stmt)
                        # Keep the qualified name for matching during explosion
                        current_step.dd_overrides[stmt.name] = current_dd
                    else:
                        # Regular DD statement
                        current_step.add_dd(current_dd)
                else:
                    # Regular DD statement
                    current_step.add_dd(current_dd)
                
                # Check for inline data marker (only for non-override DDs)
                has_star_pos = any(v == "*" for k, v in current_dd.parameters.items() if is_positional_key(k))
                if current_dd and (current_dd.parameters.get("*") or "DATA" in current_dd.parameters or has_star_pos):
                    in_inline_data = True
                    inline_data_lines = []
                    current_delimiter = current_dd.parameters.get("DLM", "/*")
                    # Handle quoted delimiter
                    if current_delimiter.startswith("'") and current_delimiter.endswith("'"):
                        current_delimiter = current_delimiter[1:-1]
            
            elif stmt.type == "PROC":
                # Inline procedure definition - start tracking procedure
                current_procedure = Procedure(
                    name=stmt.name or "UNNAMED",
                    parameters=stmt.parameters,
                    line_number=stmt.line_number
                )
                if job:
                    job.add_procedure(current_procedure)
                # Reset current_step since we're now inside procedure
                current_step = None
            
            elif stmt.type == "PEND":
                # End of procedure definition - stop tracking
                current_procedure = None
                current_step = None
            
            elif stmt.type == "SET":
                # SET symbol=value statement
                if job:
                    # For SET statements, parameters are in the format SYMBOL=VALUE
                    for key, value in stmt.parameters.items():
                        if not is_positional_key(key):
                            job.add_set(key, value)
                        elif is_positional_key(key):
                            # Positional parameter might be SYMBOL=VALUE without keyword
                            param_val = value
                            if "=" in param_val:
                                sym, val = param_val.split("=", 1)
                                job.add_set(sym.strip(), val.strip())
            
            elif stmt.type == "JCLLIB":
                # JCLLIB ORDER=(lib1,lib2,...)
                if job and "ORDER" in stmt.parameters:
                    order_value = stmt.parameters["ORDER"]
                    # ORDER parameter might already be parsed as a list
                    if isinstance(order_value, list):
                        job.jcllib_order.extend(order_value)
                    elif isinstance(order_value, str):
                        libs = order_value.strip("()").split(",")
                        job.jcllib_order.extend([lib.strip() for lib in libs])
            
            elif stmt.type == "INCLUDE":
                # INCLUDE MEMBER=name
                if job:
                    member = stmt.parameters.get("MEMBER") or stmt.parameters.get(f"{POSITIONAL_PARAM_PREFIX}0")
                    if member:
                        job.includes.append(member)
            
            elif stmt.type in ["IF", "THEN", "ELSE", "ENDIF"]:
                # Conditional logic - track conditionals properly
                if stmt.type == "IF" and job:
                    condition_parts = []
                    if stmt.name and stmt.name != "IF":
                        condition_parts.append(stmt.name)
                    for key, value in stmt.parameters.items():
                        if not key.startswith("_"):
                            condition_parts.append(f"{key}={value}")
                        else:
                            condition_parts.append(str(value))
                    condition = " ".join(condition_parts)
                    if condition.upper().endswith(' THEN'):
                        condition = condition[:-5]
                    conditional = ConditionalBlock(
                        condition=condition,
                        line_number=stmt.line_number
                    )
                    job.add_conditional(conditional)
                    if conditional_stack:
                        active_cond, active_branch = conditional_stack[-1]
                        if active_branch == 'THEN':
                            active_cond.add_then_step(conditional)
                        else:
                            active_cond.add_else_step(conditional)
                    elif current_procedure is not None:
                        current_procedure.steps.append(conditional)
                    else:
                        job.steps.append(conditional)
                    conditional_stack.append((conditional, 'THEN'))
                elif stmt.type == "THEN" and conditional_stack:
                    active_cond, _ = conditional_stack.pop()
                    conditional_stack.append((active_cond, 'THEN'))
                elif stmt.type == "ELSE" and conditional_stack:
                    active_cond, _ = conditional_stack.pop()
                    conditional_stack.append((active_cond, 'ELSE'))
                elif stmt.type == "ENDIF" and conditional_stack:
                    conditional_stack.pop()
            elif stmt.type == "JES":
                if job:
                    content = f"/*{stmt.name} {stmt.parameters.get('_raw', '')}".strip()
                    job.jes_statements.append(content)
            
            elif stmt.type == "NULL":
                # NULL statement (//) - just ignore, used as delimiter
                pass
            
            elif stmt.type == "COMMAND":
                # COMMAND statement - operator commands, just ignore
                pass
            
            elif stmt.type in ["CNTL", "ENDCNTL"]:
                # CNTL/ENDCNTL statements - utility control, just ignore
                pass
            
            elif stmt.type == "UNKNOWN":
                # Unknown statement type - log but continue processing
                # Could add to job.warnings list if we create one
                pass
            
            elif stmt.type == "XMIT":
                # XMIT statement - similar to DD but for data transmission
                if current_step:
                    current_dd = DDStatement(
                        name=stmt.name or "XMIT",
                        parameters=stmt.parameters,
                        line_number=stmt.line_number
                    )
                    current_step.add_dd(current_dd)
                    in_inline_data = True
                    inline_data_lines = []
                else:
                    # Treat job-level XMIT as ignored/comment
                    pass
        
        except Exception as e:
            if isinstance(e, (JCLSyntaxError, JCLValidationError)):
                raise
            else:
                raise JCLSyntaxError(f"Parse error: {str(e)}", line_num)
    
    if job is None:
        raise JCLSyntaxError("No JOB statement found", 0)
    
    # Create and attach procedure loader for external PROC loading
    if enable_external_procs and job.jcllib_order:
        from .proc_loader import create_default_loader
        proc_loader = create_default_loader(
            inline_procedures=job.procedures,
            base_path=proc_base_path,
            include_jcllib=True
        )
        # Store loader on job for later use (e.g., in explosion)
        job._proc_loader = proc_loader
        
        # Try to load any external PROCs that were referenced but not found inline
        # This happens when EXEC PROC is used but PROC is not defined inline
        for step in job.steps:
            if step.procedure and not job.get_procedure(step.procedure):
                # Try to load external PROC
                # Convert list to tuple for caching (CompositeProcedureLoader requires hashable)
                libraries_tuple = tuple(job.jcllib_order) if job.jcllib_order else None
                proc = proc_loader.load_procedure(step.procedure, libraries_tuple)
                if proc:
                    job.add_procedure(proc)
                elif strict_mode:
                    raise JCLSyntaxError(
                        f"Procedure '{step.procedure}' not found. "
                        f"Searched in: inline={len(job.procedures)} procedures, "
                        f"libraries={job.jcllib_order}",
                        step.line_number
                    )
    else:
        # External loading disabled or no JCLLIB - check for missing PROCs in strict mode
        if strict_mode:
            for step in job.steps:
                if step.procedure and not job.get_procedure(step.procedure):
                    reason = "external PROC loading is disabled" if not enable_external_procs else "no JCLLIB ORDER specified"
                    raise JCLSyntaxError(
                        f"Procedure '{step.procedure}' not found ({reason}). "
                        f"Searched in: inline={len(job.procedures)} procedures",
                        step.line_number
                    )
    
    # Validate the parsed job if in strict mode
    if strict_mode:
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
    try:
        content = read_source(source)
    except FileNotFoundError as exc:
        errors.append(ParseError(
            error_type=ErrorType.SYNTAX_ERROR,
            message=str(exc),
            line_number=0,
            severity=ErrorSeverity.ERROR
        ))
        return errors

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
                    has_positional = any(is_positional_key(k) for k in stmt.parameters.keys())
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
                        # DD before EXEC is allowed
                        pass
        
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
    if line.startswith("/*"):
        if len(line) <= 2 or not line[2].strip():
             # Just '/*' or '/* ' is an EOF delimiter, ignore if treating as stmt
             return None
        
        # Parse JES statement
        # Format: /*COMMAND options
        parts = line[2:].split(None, 1)
        command = parts[0]
        params = parts[1] if len(parts) > 1 else ""
        
        return Statement(
            type="JES",
            name=command,
            parameters={"_raw": params},
            line_number=line_number
        )

    if not line.startswith("//"):
        raise JCLSyntaxError(f"Invalid JCL statement (must start with //): {line}", line_number)
    
    # Remove // prefix
    content = line[2:]
    
    # Handle continuation lines - these start with spaces after // BUT check if it's actually a statement without name
    if content.startswith(" ") and content.strip():
        # Check if this might be a statement without a name field (like // SET, // IF, // EXEC, // DD, etc.)
        content_stripped = content.strip()
        first_token = content_stripped.split()[0].upper() if content_stripped.split() else ""
        # All valid JCL statement types that can appear without a name field
        if first_token not in _STATEMENT_TYPES:
            # This is a true continuation line - return None
            return None
        
    content = content.strip()
    
    # Handle empty lines after // (NULL statement)
    if not content:
        # This is a NULL statement (//)
        return Statement(
            type="NULL",
            name="",
            parameters={},
            line_number=line_number
        )
    
    # Parse statement name and type
    # Handle cases like "//         IF ..." where there's no name
    content_stripped = content.lstrip()
    
    if not content_stripped:
        return None
    
    # Check if first token is a statement type (no name field)
    first_token = content_stripped.split()[0] if content_stripped.split() else ""

    if first_token.upper() in _STATEMENT_TYPES:
        # No name field - statement starts directly with type
        name_part = ""
        rest = content_stripped
    elif " " not in content_stripped:
        # Only one token - could be name without operation
        name_part = content_stripped
        rest = ""
    else:
        # Has name field
        name_part, rest = content_stripped.split(" ", 1)
        rest = rest.strip()
    
    # Determine statement type
    if " " not in rest:
        statement_type = rest.upper()
        parameters_part = ""
    else:
        # Special handling for SET statements - syntax is: //  SET VAR=VALUE
        if rest.upper().startswith("SET "):
            statement_type = "SET"
            parameters_part = rest[4:].strip()  # Everything after "SET "
        else:
            statement_type, parameters_part = rest.split(" ", 1)
            statement_type = statement_type.upper()
    
    # Validate statement type
    if statement_type not in _STATEMENT_TYPES:
        # Don't crash on unknown statement types - create UNKNOWN type for graceful degradation
        return Statement(
            type="UNKNOWN",
            name=name_part,
            parameters={"_raw": parameters_part, "_statement_type": statement_type},
            line_number=line_number
        )
    
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
    
    # Handle special cases like DD * or DD DATA (only if standalone)
    param_upper = param_string.strip().upper()
    if param_upper == "*":
        parameters["*"] = True
        return parameters
    elif param_upper == "DATA" or param_upper.startswith("DATA,"):
        parameters["DATA"] = True
        # Continue parsing if there are additional parameters after DATA,
        if "," in param_string:
            # Parse remaining parameters
            remaining = param_string[param_string.index(",") + 1:]
            # Continue to normal parameter parsing
            param_string = remaining
        else:
            return parameters
    
    # Enhanced parameter parsing with better list and parentheses handling
    parts = []
    current = ""
    in_quotes = False
    paren_depth = 0
    
    i = 0
    while i < len(param_string):
        char = param_string[i]
        if char == "'":
            # Handle escaped quotes: '' inside a quoted string represents a single quote
            if in_quotes and i + 1 < len(param_string) and param_string[i + 1] == "'":
                # Escaped quote - add only one quote to current and skip the next quote
                current += "'"
                i += 2  # Skip both quotes
                continue
            # Regular quote - toggle state
            in_quotes = not in_quotes
            current += char
        elif char == "(" and not in_quotes:
            paren_depth += 1
            current += char
        elif char == ")" and not in_quotes:
            paren_depth -= 1
            current += char
        elif char == "," and not in_quotes and paren_depth == 0:
            if current.strip():
                parts.append(current.strip())
            current = ""
        else:
            current += char
        i += 1
    
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
        if "=" in part and not part.startswith("("):
            # Keyword parameter
            eq_pos = part.index("=")
            key = part[:eq_pos].strip().upper()  # Uppercase key
            value = part[eq_pos+1:].strip()
            
            # Handle parameter lists like DSN=(A,B,C)
            if value.startswith("(") and value.endswith(")"):
                # Parse list value
                list_content = value[1:-1]
                list_items = _parse_list_parameter(list_content)
                parameters[key] = list_items
            else:
                # Remove quotes from quoted values
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1].replace("''", "'")
                parameters[key] = value
        else:
            # Positional parameter
            value = part
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            parameters[f"{POSITIONAL_PARAM_PREFIX}{i}"] = value
    
    return parameters


def _parse_list_parameter(list_content: str) -> List[str]:
    """Parse parameter list like A,B,C or 'A','B','C'"""
    items = []
    current = ""
    in_quotes = False
    paren_depth = 0
    
    i = 0
    while i < len(list_content):
        char = list_content[i]
        if char == "'":
            # Handle escaped quotes
            if in_quotes and i + 1 < len(list_content) and list_content[i + 1] == "'":
                current += "'"
                i += 2
                continue
            in_quotes = not in_quotes
            current += char
        elif char == "(" and not in_quotes:
            paren_depth += 1
            current += char
        elif char == ")" and not in_quotes:
            paren_depth -= 1
            current += char
        elif char == "," and not in_quotes and paren_depth == 0:
            if current.strip():
                item = current.strip()
                if item.startswith("'") and item.endswith("'"):
                    item = item[1:-1].replace("''", "'")
                items.append(item)
            current = ""
        else:
            current += char
        i += 1
    
    if current.strip():
        item = current.strip()
        if item.startswith("'") and item.endswith("'"):
            item = item[1:-1].replace("''", "'")
        items.append(item)
    
    return items


def _create_job_from_statement(stmt: Statement) -> Job:
    """Create Job object from JOB statement"""
    accounting_info = None
    
    # Extract accounting information (first positional parameter)
    if f"{POSITIONAL_PARAM_PREFIX}0" in stmt.parameters:
        accounting_info = stmt.parameters[f"{POSITIONAL_PARAM_PREFIX}0"].strip("()")
    
    # Extract other parameters
    job_params = {k: v for k, v in stmt.parameters.items() if not is_positional_key(k)}
    
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
    elif "PROC" in stmt.parameters:
        procedure = stmt.parameters.pop("PROC")
    elif f"{POSITIONAL_PARAM_PREFIX}0" in stmt.parameters:
        # Might be a procedure call without keyword
        proc_or_pgm = stmt.parameters.pop(f"{POSITIONAL_PARAM_PREFIX}0")
        # If it looks like a procedure name (no path separators), treat as procedure
        if "." not in proc_or_pgm and "/" not in proc_or_pgm:
            procedure = proc_or_pgm
        else:
            program = proc_or_pgm
    
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