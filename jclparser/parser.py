"""
Core JCL parsing logic.

This module contains the main parsing functions for converting JCL scripts
into structured Python objects with full support for syntax validation
and plugin extensibility.
"""

from pathlib import Path
from typing import Union, List, Optional, Dict, Any, IO
from .model import Job, Step, DDStatement, Statement, ConditionalBlock, Procedure
from .errors import (
    JCLSyntaxError, JCLValidationError, JCLStructureError,
    ParseError, ErrorType, ErrorSeverity
)
from .plugins import get_plugin_registry, ParserConfig
from .utils import normalize_jcl_line, read_source, POSITIONAL_PARAM_PREFIX, is_positional_key
from .continuation_handler import ContinuationLineHandler
from .condition_parser import parse_condition

#: All recognised JCL statement type keywords (single canonical definition).
_STATEMENT_TYPES: frozenset = frozenset({
    "JOB", "EXEC", "DD", "PROC", "PEND", "JCLLIB", "INCLUDE",
    "SET", "IF", "THEN", "ELSE", "ENDIF", "XMIT", "OUTPUT",
    "SCHEDULE", "NULL", "COMMAND", "CNTL", "ENDCNTL",
})

#: Lazily-initialised ParameterParser instance shared across calls (same pattern as utils.py).
_PARAMETER_PARSER = None


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
    
    # Single pass: separate inline data lines from regular lines.
    # Simultaneously records which original indices are inline data
    # and builds the non-inline list for continuation merging.
    inline_data_indices: set[int] = set()
    non_inline_lines: list[str] = []
    non_inline_orig_indices: list[int] = []  # parallel to non_inline_lines
    in_inline_data = False
    delimiter = "/*"

    for i, line in enumerate(lines):
        if in_inline_data:
            inline_data_indices.add(i)
            if line.strip() == delimiter or line.strip().startswith(delimiter):
                in_inline_data = False
        else:
            if line.strip() and line.startswith("//") and not line.strip().startswith("//*"):
                upper_line = line.upper()
                if " DD " in upper_line or " DD*" in upper_line or "\tDD\t" in upper_line:
                    if (" DD *" in upper_line or " DD*" in upper_line or
                            " DD DATA" in upper_line or "\tDD\t*" in upper_line or
                            ",DLM=" in upper_line):
                        delimiter = "/*"
                        if "DLM=" in upper_line:
                            dlm_start = upper_line.index("DLM=") + 4
                            dlm_end = dlm_start
                            while dlm_end < len(upper_line) and upper_line[dlm_end] not in ",) \t\r\n":
                                dlm_end += 1
                            delimiter = line[dlm_start:dlm_end]
                        in_inline_data = True
            non_inline_lines.append(line)
            non_inline_orig_indices.append(i)

    # Merge continuation lines on the non-inline subset only.
    handler = ContinuationLineHandler()
    merged_non_inline = handler.merge_continuation_lines(non_inline_lines)

    # Recombine: build lookup of orig_idx -> merged_line for group-start lines only.
    # Continuation lines that were folded into a group are simply absent from this map
    # and will be skipped in the loop below — which is correct.
    merged_start: dict[int, str] = {}
    for merged_line, ni_line_num in merged_non_inline:
        orig_idx = non_inline_orig_indices[ni_line_num - 1]
        merged_start[orig_idx] = merged_line

    merged_lines: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        if i in inline_data_indices:
            merged_lines.append((line, i + 1))
        elif i in merged_start:
            merged_lines.append((merged_start[i], i + 1))
    
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
            if (line_num - 1) in inline_data_indices:
                continue
            
            # Parse the statement
            stmt = parse_statement(line, line_num)
            if not stmt:
                continue
            
            # Process different statement types
            if stmt.type == "JOB":
                if job is not None:
                    raise JCLSyntaxError("Multiple JOB statements found", line_num)
                job = _create_job_from_statement(stmt)
            
            elif stmt.type == "EXEC":
                if job is None and current_procedure is None:
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
                        condition_ast=parse_condition(condition),
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
                    jes_content = f"/*{stmt.name} {stmt.parameters.get('_raw', '')}".strip()
                    job.jes_statements.append(jes_content)
            
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
        
        except (JCLSyntaxError, JCLValidationError):
            raise
    
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
            if isinstance(step, Step) and step.procedure and not job.get_procedure(step.procedure):
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
                if isinstance(step, Step) and step.procedure and not job.get_procedure(step.procedure):
                    reason = "external PROC loading is disabled" if not enable_external_procs else "no JCLLIB ORDER specified"
                    raise JCLSyntaxError(
                        f"Procedure '{step.procedure}' not found ({reason}). "
                        f"Searched in: inline={len(job.procedures)} procedures",
                        step.line_number
                    )
    
    # In strict mode, a DD statement with no preceding EXEC is a structural error
    if strict_mode and not job.steps:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") and not stripped.startswith("//*"):
                parts = stripped.split()
                if len(parts) >= 2 and parts[1].upper() == "DD":
                    raise JCLStructureError(
                        "DD statement found before any EXEC step. "
                        "Each DD must belong to a step."
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

    # Merge continuation lines so multi-line statements are validated as a unit
    raw_lines = [normalize_jcl_line(line) for line in content.splitlines()]
    handler = ContinuationLineHandler()
    merged_pairs = handler.merge_continuation_lines(raw_lines)
    has_job = False
    in_proc = False
    current_step = None

    for line, line_num in merged_pairs:
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

                elif stmt.type == "PROC":
                    in_proc = True

                elif stmt.type == "PEND":
                    in_proc = False

                elif stmt.type == "EXEC":
                    if not has_job and not in_proc:
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
        _cs_parts = content_stripped.split()
        first_token = _cs_parts[0].upper() if _cs_parts else ""
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
    _cs_parts2 = content_stripped.split()
    first_token = _cs_parts2[0] if _cs_parts2 else ""

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
        rest_upper = rest.upper()
        if rest_upper.startswith("SET "):
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


def _find_keyword_eq(part: str, operator_prefixes: frozenset) -> Optional[int]:
    """Find the position of '=' that acts as a keyword parameter delimiter.

    Returns None if no keyword '=' is found (i.e., all '=' signs are part of
    relational operators like ¬=, ^=, ~=, !=, <=, >=).
    """
    pos = 0
    while pos < len(part):
        eq_pos = part.find("=", pos)
        if eq_pos == -1:
            return None
        # An '=' is a keyword delimiter if it's at position 0 or the preceding
        # character is NOT an operator prefix (¬, ^, ~, !, <, >)
        if eq_pos == 0 or part[eq_pos - 1] not in operator_prefixes:
            return eq_pos
        pos = eq_pos + 1
    return None


def _check_param_balance(param_string: str, line_number: int) -> None:
    """Validate that *param_string* has balanced quotes and parentheses.

    Raises JCLSyntaxError with a descriptive message on the first imbalance
    detected.
    """
    in_quotes = False
    paren_depth = 0
    i = 0
    while i < len(param_string):
        c = param_string[i]
        if c == "'":
            if in_quotes and i + 1 < len(param_string) and param_string[i + 1] == "'":
                i += 2
                continue
            in_quotes = not in_quotes
        elif c == "(" and not in_quotes:
            paren_depth += 1
        elif c == ")" and not in_quotes:
            paren_depth -= 1
        i += 1
    if in_quotes:
        raise JCLSyntaxError(
            f"Unclosed quote in parameter: {param_string}", line_number
        )
    if paren_depth != 0:
        hint = (
            " (statement may have been truncated at column 71 —"
            " use JCL continuation lines to break long statements"
            " across multiple records)"
        )
        raise JCLSyntaxError(
            f"Unmatched parentheses in parameter: {param_string}{hint}",
            line_number,
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
    
    # Validate balance then split using the canonical ParameterParser implementation
    _check_param_balance(param_string, line_number)
    global _PARAMETER_PARSER
    if _PARAMETER_PARSER is None:
        from .parameter_ast import ParameterParser
        _PARAMETER_PARSER = ParameterParser()
    parts = _PARAMETER_PARSER._split_parameters(param_string)
    
    # Parse individual parameters
    # Characters that form relational operators when followed by '='
    # (e.g., ¬=, ^=, ~=, !=, <=, >= in JCL IF conditions)
    _OPERATOR_PREFIXES = frozenset("¬^~!<>")

    for i, part in enumerate(parts):
        # Find the first '=' that acts as a keyword parameter delimiter
        # (not part of a relational operator like ¬=, ^=, ~=, !=, <=, >=)
        keyword_eq_pos = _find_keyword_eq(part, _OPERATOR_PREFIXES)
        if keyword_eq_pos is not None and not part.startswith("("):
            # Keyword parameter
            eq_pos = keyword_eq_pos
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
    """Parse parameter list like A,B,C or 'A','B','C'.

    Empty positional subfields are preserved so that omitted DISP subfields
    such as ``DISP=(,CATLG,DELETE)`` retain their positional meaning.
    Trailing empty elements are stripped (from trailing commas).
    """
    items = []
    in_quotes = False
    paren_depth = 0
    start = 0

    i = 0
    while i < len(list_content):
        char = list_content[i]
        if char == "'":
            # Handle escaped quotes
            if in_quotes and i + 1 < len(list_content) and list_content[i + 1] == "'":
                i += 2
                continue
            in_quotes = not in_quotes
        elif char == "(" and not in_quotes:
            paren_depth += 1
        elif char == ")" and not in_quotes:
            paren_depth -= 1
        elif char == "," and not in_quotes and paren_depth == 0:
            item = list_content[start:i].strip()
            if item.startswith("'") and item.endswith("'"):
                item = item[1:-1].replace("''", "'")
            items.append(item)  # preserve empty strings for omitted positional subfields
            start = i + 1
        i += 1

    # Append final element
    item = list_content[start:].strip()
    if item.startswith("'") and item.endswith("'"):
        item = item[1:-1].replace("''", "'")
    items.append(item)

    # Strip trailing empty elements (from trailing commas) but keep internal ones
    while items and items[-1] == "":
        items.pop()

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