"""
JCL/PROC file type detection module.

Provides utilities to detect whether a file contains JCL (with JOB card)
or PROC (procedure definition without JOB card) by analyzing file content.

This module follows the KISS (Keep It Simple, Stupid) principle:
- Simple detection logic: scan for first non-comment statement
- Clear decision rule: JOB statement → JCL, otherwise → PROC
- Minimal API surface: detect_file_type() + helper functions
"""

import logging
from enum import Enum
from pathlib import Path
from typing import IO

from .utils import read_source

logger = logging.getLogger(__name__)

# Module-level constants (avoids per-call set/list construction)
_PREAMBLE_STATEMENTS = frozenset(
    {"SET", "JCLLIB", "IF", "THEN", "ELSE", "ENDIF", "INCLUDE"}
)
# Statement types that may appear without a leading //NAME label. Prefix-match
# order is irrelevant here since no entry is a prefix of another.
_NAMELESS_STATEMENTS = _PREAMBLE_STATEMENTS | {"PEND"}
_KNOWN_TYPES = frozenset(
    {
        "JOB",
        "EXEC",
        "DD",
        "PROC",
        "PEND",
        "JCLLIB",
        "INCLUDE",
        "SET",
        "IF",
        "THEN",
        "ELSE",
        "ENDIF",
    }
)


class FileType(Enum):
    """Enumeration of JCL file types."""

    JCL = "JCL"  # File contains a JOB card
    PROC = "PROC"  # File is a procedure definition (no JOB card)
    UNKNOWN = "UNKNOWN"  # File type cannot be determined


def detect_file_type(source: str | Path | IO) -> FileType:
    """
    Detect whether a file contains JCL or PROC by checking for JOB card.

    Detection Logic:
    1. Read file content (handle all source types)
    2. Iterate through lines
    3. Skip comments (//*) and blank lines
    4. Find first valid JCL statement
    5. If statement type is "JOB" → return FileType.JCL
    6. If statement type is "PROC" or other → return FileType.PROC
    7. If no valid statements found → return FileType.UNKNOWN

    Args:
        source: JCL content as string, file path (Path/str), or file-like object

    Returns:
        FileType enum value (JCL, PROC, or UNKNOWN)

    Raises:
        FileNotFoundError: If source is a path to non-existent file
        TypeError: If source is not a valid type
        ValueError: If source is None

    Examples:
        >>> detect_file_type("//MYJOB JOB CLASS=A")
        FileType.JCL

        >>> detect_file_type("//MYPROC PROC\\n//PEND")
        FileType.PROC

        >>> detect_file_type(Path("job.jcl"))
        FileType.JCL
    """
    # Validate input
    if source is None:
        raise ValueError("Source cannot be None")

    # Get content as string, then delegate to the content-based detector.
    return detect_file_type_from_content(read_source(source))


def detect_file_type_from_content(content: str) -> FileType:
    """
    Detect whether content is JCL or PROC without reading from a file path.

    This mirrors ``detect_file_type()`` but accepts already-read content,
    avoiding a second disk read when the caller already has the content in memory.

    Args:
        content: JCL file content as a string

    Returns:
        FileType enum value (JCL, PROC, or UNKNOWN)
    """
    first_statement_type = _find_first_statement_type(content)
    if first_statement_type is None:
        return FileType.UNKNOWN
    elif first_statement_type == "JOB":
        return FileType.JCL
    else:
        return FileType.PROC


def is_jcl_file(source: str | Path | IO) -> bool:
    """
    Check if a file is a JCL file (contains JOB card).

    Args:
        source: JCL content as string, file path, or file-like object

    Returns:
        True if file is JCL, False otherwise

    Examples:
        >>> is_jcl_file("//MYJOB JOB CLASS=A")
        True

        >>> is_jcl_file("//MYPROC PROC")
        False
    """
    try:
        return detect_file_type(source) == FileType.JCL
    except (TypeError, ValueError, OSError) as exc:
        logger.debug("is_jcl_file: could not detect file type: %s", exc)
        return False


def is_proc_file(source: str | Path | IO) -> bool:
    """
    Check if a file is a PROC file (no JOB card).

    Args:
        source: JCL content as string, file path, or file-like object

    Returns:
        True if file is PROC, False otherwise

    Examples:
        >>> is_proc_file("//MYPROC PROC")
        True

        >>> is_proc_file("//MYJOB JOB CLASS=A")
        False
    """
    try:
        return detect_file_type(source) == FileType.PROC
    except (TypeError, ValueError, OSError) as exc:
        logger.debug("is_proc_file: could not detect file type: %s", exc)
        return False


# ============================================================================
# Internal Helper Functions
# ============================================================================


def _find_first_statement_type(content: str) -> str | None:
    """
    Find the type of the first valid JCL statement in content.

    Skips comment lines (//*) and blank lines.
    Also skips SET, JCLLIB, IF, INCLUDE statements to find the actual job/proc definition.

    Args:
        content: JCL file content

    Returns:
        Statement type (e.g., "JOB", "PROC", "EXEC", "DD") or None if no valid statement
    """
    lines = content.split("\n")

    for line in lines:
        # Remove carriage return if present
        line = line.rstrip("\r")

        # Skip blank lines
        if not line.strip():
            continue

        # Skip comment lines (start with //*)
        if line.lstrip().startswith("//*"):
            continue

        # Check if it's a JCL statement (starts with //)
        if not line.lstrip().startswith("//"):
            continue

        # Extract statement type
        statement_type = _extract_statement_type(line)

        if statement_type:
            # If it's a preamble statement, skip it and continue looking
            if statement_type in _PREAMBLE_STATEMENTS:
                continue

            # Found a meaningful statement
            return statement_type

    return None


def _extract_statement_type(line: str) -> str | None:
    """
    Extract the statement type from a JCL line.

    JCL statement format:
    //[name] [type] [parameters]
    or
    // [type] [parameters]  (for statements without name)

    Args:
        line: Single JCL line

    Returns:
        Statement type (uppercase) or None if cannot be determined
    """
    # Remove leading/trailing whitespace
    line = line.strip()

    # Must start with //
    if not line.startswith("//"):
        return None

    # Remove the //
    line = line[2:].lstrip()

    # Empty line after //
    if not line:
        return None

    # Check for nameless statement types (those that may omit a //NAME label)
    line_upper = line.upper()
    for stmt_type in _NAMELESS_STATEMENTS:
        if line_upper.startswith(stmt_type):
            return stmt_type

    # For statements with names: //NAME TYPE PARAMS
    # Split on whitespace
    parts = line.split(None, 2)  # Split into max 3 parts

    if len(parts) < 2:
        # Only one part - could be just a name (null statement) or invalid
        # Check if it's a statement type keyword
        if parts[0].upper() in ["JOB", "EXEC", "DD", "PROC"]:
            return parts[0].upper()
        return None

    # parts[0] is the name, parts[1] is the type
    statement_type = parts[1].upper()

    # Validate it's a known statement type
    if statement_type in _KNOWN_TYPES:
        return statement_type

    # Check if parts[1] contains a statement type (e.g., "JOB(ACCT)")
    for known_type in _KNOWN_TYPES:
        if statement_type.startswith(known_type):
            return known_type

    return None
