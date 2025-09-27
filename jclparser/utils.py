"""
Helper utilities for JCL syntax handling.

Contains utility functions for parsing parameters, handling quotes,
and other JCL-specific syntax operations.
"""

import re
from typing import List, Dict, Any, Tuple, Optional


def normalize_jcl_line(line: str) -> str:
    """
    Normalize JCL line by removing extra whitespace and handling continuations.
    
    Args:
        line: Raw JCL line
        
    Returns:
        Normalized line
    """
    # Remove trailing whitespace but preserve leading spaces for continuation detection
    line = line.rstrip()
    
    # Convert tabs to spaces
    line = line.expandtabs(4)
    
    return line


def is_continuation_line(line: str) -> bool:
    """
    Check if line is a JCL continuation line.
    
    Args:
        line: JCL line to check
        
    Returns:
        True if line is a continuation
    """
    stripped = line.lstrip()
    return stripped.startswith("//") and not stripped.startswith("//*") and len(stripped) > 2 and stripped[2] == " "


def split_jcl_parameters(param_string: str) -> List[str]:
    """
    Split JCL parameter string into individual parameters.
    
    Handles quoted strings, parentheses, and nested structures properly.
    
    Args:
        param_string: String containing JCL parameters
        
    Returns:
        List of individual parameter strings
    """
    if not param_string.strip():
        return []
    
    parameters = []
    current = ""
    in_quotes = False
    paren_depth = 0
    i = 0
    
    while i < len(param_string):
        char = param_string[i]
        
        if char == "'" and (i == 0 or param_string[i-1] != "\\"):
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
                parameters.append(current.strip())
            current = ""
        else:
            current += char
        
        i += 1
    
    if current.strip():
        parameters.append(current.strip())
    
    return parameters


def parse_jcl_parameter(param: str) -> Tuple[str, Any]:
    """
    Parse individual JCL parameter into key-value pair.
    
    Args:
        param: Parameter string (e.g., "DSN=MY.DATA", "CLASS=A")
        
    Returns:
        Tuple of (parameter_name, parameter_value)
    """
    if "=" not in param:
        # Positional parameter
        return f"_positional", param.strip()
    
    key, value = param.split("=", 1)
    key = key.strip()
    value = value.strip()
    
    # Handle quoted values
    if value.startswith("'") and value.endswith("'") and len(value) > 1:
        value = value[1:-1]
        # Handle escaped quotes
        value = value.replace("''", "'")
    
    # Handle parenthesized values (like DISP)
    if value.startswith("(") and value.endswith(")") and len(value) > 2:
        # Parse as sub-parameters
        inner = value[1:-1]
        sub_params = split_jcl_parameters(inner)
        if len(sub_params) == 1:
            value = sub_params[0]
        else:
            value = sub_params
    
    return key, value


def quote_jcl_value(value: str) -> str:
    """
    Add JCL quotes to value if needed.
    
    Args:
        value: Value to potentially quote
        
    Returns:
        Quoted value if necessary
    """
    # Quote if contains special characters or spaces
    if re.search(r'[,()=\s]', value):
        # Escape existing quotes
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    
    return value


def unquote_jcl_value(value: str) -> str:
    """
    Remove JCL quotes from value.
    
    Args:
        value: Potentially quoted value
        
    Returns:
        Unquoted value
    """
    if value.startswith("'") and value.endswith("'") and len(value) > 1:
        # Remove quotes and unescape
        unquoted = value[1:-1]
        return unquoted.replace("''", "'")
    
    return value


def validate_jcl_name(name: str, max_length: int = 8) -> bool:
    """
    Validate JCL name format.
    
    Args:
        name: Name to validate
        max_length: Maximum allowed length
        
    Returns:
        True if valid JCL name
    """
    if not name or len(name) > max_length:
        return False
    
    # Must start with letter or @, #, $
    if not re.match(r'^[A-Za-z@#$]', name):
        return False
    
    # Remaining characters can be alphanumeric or @, #, $
    return re.match(r'^[A-Za-z0-9@#$]+$', name) is not None


def format_jcl_line(statement_type: str, name: str, parameters: Dict[str, Any], 
                   max_line_length: int = 71) -> List[str]:
    """
    Format JCL statement with proper line length and continuation.
    
    Args:
        statement_type: JCL statement type (JOB, EXEC, DD)
        name: Statement name
        parameters: Statement parameters
        max_line_length: Maximum line length before continuation
        
    Returns:
        List of formatted JCL lines
    """
    lines = []
    
    # Start with basic statement
    base = f"//{name} {statement_type}"
    
    if not parameters:
        return [base]
    
    # Format parameters
    param_parts = []
    for key, value in parameters.items():
        if key.startswith("_positional"):
            param_parts.append(str(value))
        else:
            if isinstance(value, (list, tuple)):
                # Handle list values (like DISP)
                value_str = "(" + ",".join(str(v) for v in value) + ")"
            else:
                value_str = str(value)
            
            # Quote if necessary
            if isinstance(value_str, str):
                value_str = quote_jcl_value(value_str)
            
            param_parts.append(f"{key}={value_str}")
    
    param_string = ",".join(param_parts)
    full_line = f"{base} {param_string}"
    
    # Handle line length
    if len(full_line) <= max_line_length:
        return [full_line]
    
    # Need continuation
    lines.append(base)
    
    # Add parameters with continuation
    current_line = "//"
    remaining_params = param_parts.copy()
    
    while remaining_params:
        param = remaining_params.pop(0)
        
        # Check if we can fit this parameter
        test_line = current_line + (" " if len(current_line) > 2 else "") + param
        if remaining_params:
            test_line += ","
        
        if len(test_line) <= max_line_length:
            current_line = test_line
            if not remaining_params:
                lines.append(current_line)
        else:
            # Start new continuation line
            if len(current_line) > 2:  # Has content
                lines.append(current_line + ",")
            current_line = "// " + param
            if not remaining_params:
                lines.append(current_line)
    
    return lines


def extract_inline_data(lines: List[str], start_index: int) -> Tuple[Optional[str], int]:
    """
    Extract inline data from DD * statement.
    
    Args:
        lines: List of JCL lines
        start_index: Index where DD * statement was found
        
    Returns:
        Tuple of (inline_data, end_index) or (None, start_index)
    """
    if start_index >= len(lines):
        return None, start_index
    
    data_lines = []
    current_index = start_index + 1
    
    while current_index < len(lines):
        line = lines[current_index]
        
        # Check for end marker
        if line.strip() == "/*":
            return "\n".join(data_lines), current_index
        
        # Collect data line
        data_lines.append(line)
        current_index += 1
    
    # No end marker found
    return "\n".join(data_lines), current_index - 1


def merge_continuation_lines(lines: List[str]) -> List[str]:
    """
    Merge JCL continuation lines into complete statements.
    
    Args:
        lines: List of raw JCL lines
        
    Returns:
        List of complete JCL statements
    """
    merged_lines = []
    current_statement = ""
    
    for line in lines:
        normalized = normalize_jcl_line(line)
        
        # Skip empty lines and comments
        if not normalized or normalized.strip().startswith("//*"):
            if current_statement:
                merged_lines.append(current_statement)
                current_statement = ""
            merged_lines.append(normalized)
            continue
        
        # Check if this is a continuation
        if is_continuation_line(normalized):
            # Add to current statement
            continuation_part = normalized[2:].strip()  # Remove // prefix
            if current_statement:
                current_statement += " " + continuation_part
            else:
                # Continuation without previous statement - treat as new statement
                current_statement = "//" + continuation_part
        else:
            # New statement
            if current_statement:
                merged_lines.append(current_statement)
            current_statement = normalized
    
    # Don't forget the last statement
    if current_statement:
        merged_lines.append(current_statement)
    
    return merged_lines


def calculate_jcl_checksum(jcl_content: str) -> str:
    """
    Calculate checksum for JCL content (useful for caching).
    
    Args:
        jcl_content: JCL script content
        
    Returns:
        Hexadecimal checksum string
    """
    import hashlib
    
    # Normalize content for consistent checksums
    normalized = "\n".join(line.strip() for line in jcl_content.splitlines() if line.strip())
    
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()