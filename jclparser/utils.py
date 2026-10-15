"""
Helper utilities for JCL syntax handling.

Contains utility functions for JCL-specific syntax operations used by the
main parse path: ``read_source``, ``normalize_jcl_line``, ``is_positional_key``.
"""

from __future__ import annotations

import builtins
import errno
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: Prefix used to store positional (keyword-less) JCL parameters in dicts.
POSITIONAL_PARAM_PREFIX: str = "_pos_"

_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def split_source_lines(text: str, keepends: bool = False) -> list[str]:
    """Split source *text* into records on ``\\n``, ``\\r\\n`` and ``\\r`` only.

    The one record splitter for JCL source and in-stream data. ``str.splitlines``
    also breaks on form feed, vertical tab, ``\\x1c``-``\\x1e``, NEL (``\\x85``)
    and U+2028/U+2029, which split a data record in two and shifted every later
    line number (issue #62). Like ``splitlines``, a single trailing line end
    does not yield a final empty record; with *keepends* each record keeps
    its line end.
    """
    if keepends:
        records: list[str] = []
        start = 0
        for match in _LINE_BREAK.finditer(text):
            records.append(text[start : match.end()])
            start = match.end()
        if start < len(text):
            records.append(text[start:])
        return records
    records = _LINE_BREAK.split(text)
    if records[-1] == "":
        records.pop()
    return records


def is_positional_key(key: str) -> bool:
    """Return ``True`` if *key* represents a positional (keyword-less) JCL parameter."""
    return key.startswith(POSITIONAL_PARAM_PREFIX)


def instream_delimiter(parameters: dict[str, Any]) -> tuple[Any, bool] | None:
    """Return ``(delimiter, ends_at_slash)`` if a DD's parameters open in-stream data.

    The one rule both the source pre-scan and the JobBuilder use, so they can
    never disagree about where data starts. In-stream data starts at ``DD *``
    or ``DD DATA`` only; ``DLM=`` changes the delimiter of such a DD and is
    ignored anywhere else. *parameters* are the DD's parsed parameters, so a
    ``DLM=`` inside a quoted value (``PATH='/u/DLM=1'``) is never mistaken for
    the keyword. ``DD *`` without ``DLM=`` also ends at the next ``//``
    record; ``DD DATA`` does not, so ``//`` can be data. The delimiter is
    returned as parsed (a list for a malformed ``DLM=(A,B)``), for the caller
    to validate.
    """
    is_star = bool(parameters.get("*")) or any(
        v == "*" for k, v in parameters.items() if is_positional_key(k)
    )
    if not (is_star or "DATA" in parameters):
        return None
    has_dlm = "DLM" in parameters
    delimiter = parameters.get("DLM", "/*")
    if (
        isinstance(delimiter, str)
        and len(delimiter) >= 2
        and delimiter.startswith("'")
        and delimiter.endswith("'")
    ):
        delimiter = delimiter[1:-1]
    return delimiter, is_star and not has_dlm


def jcl_value_text(value: Any) -> str:
    """Render a tokenized operand value back as JCL text.

    The statement tokenizer stores a parenthesised operand as a list --
    ``DISP=(NEW,CATLG)`` becomes ``["NEW", "CATLG"]`` -- and a bare flag as
    ``True``. Wherever such a value is used as text (a symbol's value, a SET
    value) it must read ``(NEW,CATLG)``, never the Python repr.
    """
    if isinstance(value, (list, tuple)):
        return "(" + ",".join(jcl_value_text(v) for v in value) + ")"
    if value is True or value is None:
        return ""
    return str(value)


def _continues_on_next_record(line: str) -> bool:
    """True if a 72-character ``//`` statement record leaves its operand open
    at column 71: a trailing comma, or an unclosed quoted string."""
    if not line.startswith("//") or line.startswith("//*"):
        return False
    return line[70] == "," or line[:71].count("'") % 2 == 1


def _is_continuation_record(line: str) -> bool:
    """True if *line* is a ``//`` record with a blank name field and operands."""
    return line.startswith("// ") and bool(line[3:].strip())


def _has_column_72_indicator(line: str, next_line: str | None) -> bool:
    """True if column 72 of a 72-character record is a continuation indicator.

    Such a record is a fixed-format card whose sequence field was trimmed.
    A blank column 71 says so on its own. With column 71 non-blank, the
    record could equally be an editor line whose last character is content,
    so column 72 counts as the indicator only when the operand is left open
    at column 71 (trailing comma or unclosed quote) *and* the next record,
    *next_line*, is a continuation (issue #80).
    """
    if len(line) != 72 or line[71].isspace():
        return False
    if line[70] == " ":
        return True
    return (
        next_line is not None
        and _continues_on_next_record(line)
        and _is_continuation_record(next_line)
    )


def is_continued_card_image(line: str, next_line: str | None = None) -> bool:
    """Return ``True`` if raw record *line* is a card image continued in column 72.

    Exactly the records :func:`normalize_jcl_line` takes a non-blank column-72
    continuation indicator off (*next_line* is the raw record after *line*,
    as there). For such a record the statement text fills columns 1-71, so
    blanks up to column 71 are known to be coded -- which matters when a
    quoted string is continued: it runs through column 71 and its trailing
    blanks are part of the value (issue #65).
    """
    if len(line) >= 80:
        return not line[71].isspace()
    return _has_column_72_indicator(line, next_line)


def control_card_text(text: str) -> str:
    """In-stream control statements as a utility reads them: columns 1-71.

    In-stream data keeps whole records (issue #115), so on an 80-column card
    image columns 72-80 -- a continuation indicator and a sequence field to
    the utilities that read control statements -- are still in the text.
    This drops them from every record longer than 71 characters, as
    :func:`normalize_jcl_line` does for JCL, so a numbered deck does not
    leak its sequence numbers into the statements.
    """
    return "\n".join(
        record[:71].rstrip() if len(record) > 71 else record
        for record in split_source_lines(text)
    )


def normalize_jcl_line(line: str, next_line: str | None = None) -> str:
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
    exception: a record of exactly 72 characters whose column 72 is a
    continuation indicator is a fixed-format record that had its trailing
    sequence field trimmed. That is the case when column 71 is blank, or when
    column 71 leaves the operand open (a trailing comma or an unclosed quoted
    string) and *next_line*, the raw record after *line*, is a continuation
    record (``//`` and a blank name field). Without *next_line* only the
    blank-column-71 case applies. Use :func:`normalize_jcl_lines` for a whole
    source.

    Args:
        line: Raw JCL line
        next_line: The raw record after *line*, if any

    Returns:
        Normalized line
    """
    # Strip mainframe sequence numbers (cols 73-80, 0-indexed 72-79) and the
    # column-72 continuation indicator (0-indexed 71).  Only do this for full
    # 80-column mainframe records; shorter lines are modern text-editor JCL
    # where every character is content.
    if len(line) >= 80 or _has_column_72_indicator(line, next_line):
        line = line[:71]

    # Remove trailing whitespace but preserve leading spaces for continuation detection
    line = line.rstrip()

    # Convert tabs to spaces
    line = line.expandtabs(4)

    return line


def normalize_jcl_lines(raw_lines: Sequence[str]) -> list[str]:
    """:func:`normalize_jcl_line` every record of *raw_lines*, with lookahead."""
    return [
        normalize_jcl_line(line, raw_lines[i + 1] if i + 1 < len(raw_lines) else None)
        for i, line in enumerate(raw_lines)
    ]


#: Longest value a symbol substitution may produce: a resolved SET value, a
#: pre-resolved SET table entry, or the characters one ``substitute_symbols()``
#: call splices in. A safety limit against chained symbols that double at each
#: step (``SET A2='&A1&A1'`` ...), deliberately far above the z/OS 255-character
#: symbol limit so every currently accepted job still parses. Past it the text
#: is left unresolved with a warning, or the strict paths raise.
MAX_SYMBOL_VALUE_LENGTH: int = 65536


#: Largest PROC / INCLUDE library member the loaders will read. Members are
#: named by the JCL being parsed, so an oversized file is refused (read as
#: missing, with a warning) rather than pulled into memory whole.
MAX_LIBRARY_MEMBER_BYTES: int = 4 * 1024 * 1024


def _read_file_with_fallback(path: Path, max_bytes: int | None = None) -> str:
    """
    Read a file trying utf-8, cp1252, then latin-1 (then a binary fallback).

    cp1252 comes before latin-1: latin-1 decodes every byte, so anything
    after it was unreachable, and a Windows-1252 ``\\x85`` (ellipsis) decoded
    as NEL. cp1252 leaves five bytes undefined; a file holding one of them
    falls through to latin-1.

    Args:
        path: Existing file path (caller must verify existence).
        max_bytes: When set, refuse a file larger than this many bytes with
            :class:`OSError` (``EFBIG``) before reading any of it.

    Returns:
        File content as a string.
    """
    if max_bytes is not None:
        size = path.stat().st_size
        if size > max_bytes:
            raise OSError(
                errno.EFBIG,
                f"{path.name} is {size} bytes, over the {max_bytes}-byte limit",
            )
    # Via the `builtins` module rather than a bare `open(...)` call, so a
    # `unittest.mock.patch("builtins.open")` is honoured even if this module
    # is ever compiled (Cython caches a bare builtin name at first use).
    # utf-8-sig reads plain UTF-8 too, and drops a byte-order mark.
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with builtins.open(path, "r", encoding=encoding) as fh:
                return fh.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Defensive only: latin-1 maps every byte, so it does not fail.
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


#: UTF-8 byte-order mark some editors put at the start of a text file.
_BOM = "\ufeff"


def read_source(source: str | Path | Any) -> str:
    """
    Resolve a JCL source (string content, file path, or file-like object) into a
    string of JCL content.

    A ``str`` is always treated as JCL content. To read a file, pass a
    :class:`pathlib.Path` (or an open file object).

    Runtime-critical — used by the main parse path.

    Args:
        source: JCL content as a string, a :class:`pathlib.Path` naming a file,
                or any file-like object with a ``read()`` method.

    Returns:
        String of JCL content.

    Raises:
        FileNotFoundError: If *source* is a :class:`pathlib.Path` to a file that
            does not exist.
    """
    content = _read_source_raw(source)
    # A byte-order mark is not JCL; left in place it hides the first "//".
    if isinstance(content, str):
        content = content.removeprefix(_BOM)
    return content


def _read_source_raw(source: str | Path | Any) -> str:
    """:func:`read_source` without the byte-order-mark cleanup."""
    if isinstance(source, Path):
        return _require_file(source)
    if isinstance(source, str):
        # A string is always JCL content, never a file name: pass a
        # pathlib.Path to read a file. Guessing ("one line ending in .jcl",
        # "contains a slash", "names an existing file") let a one-line upload
        # such as "/etc/passwd" read an arbitrary server file and echo its
        # first line back in the parse error.
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
        except OSError:
            pass  # Non-seekable streams are fine; seek is best-effort only
    return content
