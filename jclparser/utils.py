"""
Helper utilities for JCL syntax handling.

Contains utility functions for JCL-specific syntax operations used by the
main parse path: ``read_source``, ``normalize_jcl_line``, ``is_positional_key``.
"""

from __future__ import annotations

import builtins
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

    Strips mainframe sequence numbers from columns 73-80 and the column-72
    continuation indicator.  In the standard 80-column JCL record format
    columns 1-71 hold the statement, column 72 holds a non-blank character
    when the statement continues on the next record, and columns 73-80 are
    identifier/sequence fields.  None of those must be interpreted as JCL
    content.

    Truncation is only applied when the raw line is at least 80 characters,
    indicating a true mainframe fixed-width record.  Lines shorter than 80
    characters are assumed to come from a modern text editor where all
    characters are actual JCL content and must not be truncated — with one
    exception: a record of exactly 72 characters whose column 71 is blank and
    whose column 72 is not is a fixed-format record that had its trailing
    sequence field trimmed, so its column-72 character is a continuation
    indicator rather than content.

    Args:
        line: Raw JCL line

    Returns:
        Normalized line
    """
    # Strip mainframe sequence numbers (cols 73-80, 0-indexed 72-79) and the
    # column-72 continuation indicator (0-indexed 71).  Only do this for full
    # 80-column mainframe records; shorter lines are modern text-editor JCL
    # where every character is content.
    if len(line) >= 80:
        line = line[:71]
    elif len(line) == 72 and line[70] == " " and not line[71].isspace():
        # Sequence field trimmed away, continuation indicator left behind.
        line = line[:71]

    # Remove trailing whitespace but preserve leading spaces for continuation detection
    line = line.rstrip()

    # Convert tabs to spaces
    line = line.expandtabs(4)

    return line


def _read_file_with_fallback(path: Path) -> str:
    """
    Read a file trying utf-8, latin-1, cp1252, then binary fallback.

    Args:
        path: Existing file path (caller must verify existence).

    Returns:
        File content as a string.
    """
    # Via the `builtins` module rather than a bare `open(...)` call: this
    # module is cythonized for the closed-source PyPI release build (see
    # setup.py), and Cython caches a bare builtin name's target at first
    # use, which is invisible to a `unittest.mock.patch("builtins.open")`
    # made afterward. Routing through the module object keeps every call a
    # live attribute lookup, matching plain-Python monkeypatch semantics.
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            with builtins.open(path, "r", encoding=encoding) as fh:
                return fh.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Last resort: binary decode with replacement
    with builtins.open(path, "rb") as fh:
        return fh.read().decode("utf-8", errors="ignore")


def _require_file(path: Path) -> str:
    """Raise ``FileNotFoundError`` if *path* does not exist, otherwise return its content."""
    if not path.exists():
        raise FileNotFoundError(f"JCL file not found: {path}")
    return _read_file_with_fallback(path)


def is_within_directory(path: Path, anchor: Path) -> bool:
    """Return ``True`` if *path* resolves to a location inside *anchor*.

    Path-traversal guard used by the PROC/INCLUDE loaders so a crafted member
    name (e.g. ``../../secret``) cannot escape its library directory. Any
    resolution failure is treated as "not contained".
    """
    try:
        return path.resolve().is_relative_to(anchor.resolve())
    except (OSError, ValueError):
        return False


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
        # JCL content starts with "//" (a statement) or "/*" (a JES2/JES3
        # control card, e.g. "/*JOBPARM", which may legally precede the JOB
        # statement) -- never treat either as a file path.
        looks_like_jcl_start = source.strip().startswith(("//", "/*"))
        # Treat as a file path when it looks like one by extension or separator.
        if source.endswith(".jcl") or (
            ("/" in source or "\\" in source) and not looks_like_jcl_start
        ):
            return _require_file(Path(source))
        # For plain strings without path markers (no extension, no separators),
        # check whether the string names an existing file.  JCL content always
        # starts with "//" or "/*", or contains newlines, so this fallback is safe.
        if "\n" not in source and "\r" not in source and not looks_like_jcl_start:
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
