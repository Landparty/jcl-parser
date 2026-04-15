"""
Helper utilities for JCL syntax handling.

Contains utility functions for JCL-specific syntax operations.

Function classification
-----------------------
Runtime-critical (used by the main parse path):
    read_source, normalize_jcl_line, is_continuation_line
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: Prefix used to store positional (keyword-less) JCL parameters in dicts.
POSITIONAL_PARAM_PREFIX: str = "_pos_"


def is_positional_key(key: str) -> bool:
    """Return ``True`` if *key* represents a positional (keyword-less) JCL parameter."""
    return key.startswith(POSITIONAL_PARAM_PREFIX)


def normalize_jcl_line(line: str) -> str:
    """
    Normalize JCL line by removing extra whitespace and handling continuations.

    Strips mainframe sequence numbers from columns 73-80.  In the standard
    80-column JCL record format columns 73-80 are identifier/sequence fields
    that must not be interpreted as JCL content.

    Truncation is only applied when the raw line is at least 80 characters,
    indicating a true mainframe fixed-width record.  Lines shorter than 80
    characters are assumed to come from a modern text editor where all
    characters are actual JCL content and must not be truncated.

    Args:
        line: Raw JCL line

    Returns:
        Normalized line
    """
    # Strip mainframe sequence numbers (cols 73-80, 0-indexed 72-79).
    # Only do this for full 80-column mainframe records; shorter lines are
    # modern text-editor JCL where every character is content.
    if len(line) >= 80:
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
    return (
        stripped.startswith("//")
        and not stripped.startswith("//*")
        and len(stripped) > 2
        and stripped[2] == " "
    )


def _read_file_with_fallback(path: Path) -> str:
    """
    Read a file trying utf-8, latin-1, cp1252, then binary fallback.

    Args:
        path: Existing file path (caller must verify existence).

    Returns:
        File content as a string.
    """
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=encoding) as fh:
                return fh.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Last resort: binary decode with replacement
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", errors="ignore")


def _require_file(path: Path) -> str:
    """Raise ``FileNotFoundError`` if *path* does not exist, otherwise return its content."""
    if not path.exists():
        raise FileNotFoundError(f"JCL file not found: {path}")
    return _read_file_with_fallback(path)


def read_source(source: str | Path | Any) -> str:
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
        return _require_file(source)
    if isinstance(source, str):
        # Treat as a file path when it looks like one by extension or separator.
        if source.endswith(".jcl") or (
            ("/" in source or "\\" in source) and not source.strip().startswith("//")
        ):
            return _require_file(Path(source))
        # For plain strings without path markers (no extension, no separators),
        # check whether the string names an existing file.  JCL content always
        # starts with "//" or contains newlines, so this fallback is safe.
        if "\n" not in source and "\r" not in source and not source.strip().startswith("//"):
            try:
                path = Path(source)
                if path.is_file():
                    return _read_file_with_fallback(path)
            except (OSError, ValueError):
                pass
        return source
    # File-like object
    if not hasattr(source, "read"):
        raise TypeError(
            f"Invalid source type: {type(source)}. Expected str, Path, or file-like object."
        )
    content = source.read()
    if hasattr(source, "seek"):
        try:
            source.seek(0)
        except (OSError, IOError):
            pass  # Non-seekable streams are fine; seek is best-effort only
    return content
