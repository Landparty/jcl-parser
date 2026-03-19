"""
Helper utilities for JCL syntax handling.

Contains utility functions for parsing parameters, handling quotes,
and other JCL-specific syntax operations.

Function classification
-----------------------
Runtime-critical (used by the main parse path):
    read_source, normalize_jcl_line, is_continuation_line,
    quote_jcl_value, unquote_jcl_value

Public utility API (used externally, not on the hot path):
    split_jcl_parameters, parse_jcl_parameter,
    validate_jcl_name, format_jcl_line,
    extract_inline_data, merge_continuation_lines,
    calculate_jcl_checksum
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union

#: Prefix used to store positional (keyword-less) JCL parameters in dicts.
POSITIONAL_PARAM_PREFIX: str = "_pos_"

# Precompiled regex patterns for performance
_RE_SPECIAL_CHARS = re.compile(r"[,()=\s']")
_RE_JCL_NAME_START = re.compile(r'^[A-Za-z@#$]')
_RE_JCL_NAME_FULL = re.compile(r'^[A-Za-z0-9@#$]+$')


def is_positional_key(key: str) -> bool:
    """Return ``True`` if *key* represents a positional (keyword-less) JCL parameter."""
    return key.startswith(POSITIONAL_PARAM_PREFIX)


def normalize_jcl_line(line: str) -> str:
    """
    Normalize JCL line by removing extra whitespace and handling continuations.

    Strips mainframe sequence numbers from columns 73-80.  In the standard
    80-column JCL record format columns 73-80 are identifier/sequence fields
    that must not be interpreted as JCL content.  Truncating to column 72 is
    always safe: lines shorter than 73 characters are unaffected.

    Args:
        line: Raw JCL line

    Returns:
        Normalized line
    """
    # Strip mainframe sequence numbers (cols 73-80, 0-indexed 72-79)
    if len(line) > 72:
        line = line[:72]

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


def read_source(source: Union[str, Path, Any]) -> str:
    """
    Resolve a JCL source (string content, file path, or file-like object) into a
    string of JCL content.

    Runtime-critical — used by the main parse path.

    Args:
        source: JCL content as string, a :class:`pathlib.Path`, or any file-like
                object with a ``read()`` method.

    Returns:
        String of JCL content.

    Raises:
        FileNotFoundError: If *source* is a path to a file that does not exist.
    """
    if isinstance(source, Path):
        if not source.exists():
            raise FileNotFoundError(f"JCL file not found: {source}")
        with open(source, 'r', encoding='utf-8') as fh:
            return fh.read()
    if isinstance(source, str):
        # Treat as a file path when it looks like one
        if source.endswith('.jcl') or (
            ('/' in source or '\\' in source) and not source.strip().startswith('//')
        ):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"JCL file not found: {path}")
            with open(path, 'r', encoding='utf-8') as fh:
                return fh.read()
        return source
    # File-like object
    content = source.read()
    if hasattr(source, 'seek'):
        source.seek(0)
    return content


def split_jcl_parameters(param_string: str) -> List[str]:
    """
    Split JCL parameter string into individual parameters.

    Handles quoted strings, parentheses, and nested structures properly.

    .. note::
        This is a compatibility wrapper that delegates to
        :meth:`jclparser.parameter_ast.ParameterParser._split_parameters`,
        which is the canonical implementation.

    Args:
        param_string: String containing JCL parameters

    Returns:
        List of individual parameter strings
    """
    if not param_string.strip():
        return []
    from .parameter_ast import ParameterParser
    return ParameterParser()._split_parameters(param_string)


def parse_jcl_parameter(param: str) -> Tuple[str, Any]:
    """
    Parse individual JCL parameter into key-value pair.

    .. deprecated::
        Superseded by :class:`jclparser.parameter_ast.ParameterParser`, which
        provides a richer AST and handles all JCL parameter types correctly.
        Use ``ParameterParser`` for new code.

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
    # Quote if contains special characters or spaces (including apostrophes)
    if _RE_SPECIAL_CHARS.search(value):
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

    .. note::
        Identical to ``validators.validate_jcl_identifier()``.
        Consider using that function directly.

    Args:
        name: Name to validate
        max_length: Maximum allowed length

    Returns:
        True if valid JCL name
    """
    if not name or len(name) > max_length:
        return False
    
    # Must start with letter or @, #, $
    if not _RE_JCL_NAME_START.match(name):
        return False

    # Remaining characters can be alphanumeric or @, #, $
    return _RE_JCL_NAME_FULL.match(name) is not None


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
                # Handle list values (like DISP) - don't quote parenthesized values
                value_str = "(" + ",".join(str(v) for v in value) + ")"
                param_parts.append(f"{key}={value_str}")
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

    .. deprecated::
        Inline data extraction is now handled internally by the main parser
        in :func:`jclparser.parser.parse_jcl`.  This standalone helper may
        produce inconsistent results for complex JCL with custom delimiters.

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

    .. deprecated::
        Superseded by :class:`jclparser.continuation_handler.ContinuationLineHandler`,
        which correctly handles all edge-cases defined in z/OS JCL syntax rules.
        Use that class for new code.

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