"""
INCLUDE member loader for JCL parsing.

Provides an abstract interface and a filesystem-based implementation for
loading JCL library members referenced by ``// INCLUDE MEMBER=name``
statements.

The resolution order mirrors how JCLLIB is searched for PROCs:
  1. Members found in explicitly listed JCLLIB libraries take precedence.
  2. If not found there, the default base path is searched using the same
     ``<base_path>/<LIBNAME>/<MEMBER>.jcl`` convention used by
     :class:`~jclparser.proc_loader.JCLLIBProcedureLoader`.

Usage::

    from jclparser.include_loader import JCLLIBMemberLoader

    loader = JCLLIBMemberLoader(base_path="/opt/jcllib")
    content = loader.load_member("COMMON", ["SYS1.JCLLIB"])
    # Returns the raw JCL text of the member, or None if not found.
"""

from __future__ import annotations

import errno
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from .errors import JCLStructureError
from .utils import (
    MAX_LIBRARY_MEMBER_BYTES,
    _read_file_with_fallback,
    is_within_directory,
    split_source_lines,
)

logger = logging.getLogger(__name__)


class IncludeMemberLoader(ABC):
    """
    Abstract base class for loading JCL INCLUDE members.

    Implement this interface to supply member content from any backing
    store (filesystem, database, in-memory dict for tests, etc.).
    """

    @abstractmethod
    def load_member(
        self,
        member_name: str,
        libraries: list[str] | None = None,
    ) -> str | None:
        """
        Return the raw JCL text of *member_name*, or ``None`` if not found.

        Args:
            member_name: Name of the INCLUDE member (e.g. ``"COMMON"``).
            libraries: Ordered list of library names / paths to search.
                       Entries are tried in order; the first match wins.

        Returns:
            Member content as a string, or ``None`` if the member cannot
            be located in any of the specified libraries.
        """


class DictMemberLoader(IncludeMemberLoader):
    """
    In-memory member loader backed by a plain dictionary.

    Primarily intended for unit tests where real files are not available.

    Example::

        loader = DictMemberLoader({
            "COMMON": "//COMMSTEP EXEC PGM=IEFBR14\\n",
            "SYSIN":  "//SYSIN DD *\\nSELECT * FROM T\\n",
        })
    """

    def __init__(self, members: dict[str, str]) -> None:
        self._members: dict[str, str] = {k.upper(): v for k, v in members.items()}

    def load_member(
        self,
        member_name: str,
        libraries: list[str] | None = None,
    ) -> str | None:
        return self._members.get(member_name.upper())


class JCLLIBMemberLoader(IncludeMemberLoader):
    """
    Filesystem-based INCLUDE member loader.

    Searches for members in directories that follow the same naming
    convention used by :class:`~jclparser.proc_loader.JCLLIBProcedureLoader`:

    ::

        <base_path>/<LIBRARY_NAME>/<MEMBER_NAME>.jcl

    where ``<LIBRARY_NAME>`` is the JCLLIB dataset name with dots replaced by
    path separators (e.g. ``SYS1.JCLLIB`` → ``SYS1/JCLLIB`` or ``SYS1.JCLLIB``
    as a subdirectory), and ``<MEMBER_NAME>`` is case-insensitive.

    The base path defaults to the ``JCL_PROCLIB_PATH`` environment variable.
    With neither, no member is ever read: the process's working directory is
    not searched implicitly, since the member and library names come from the
    JCL being parsed.

    Args:
        base_path: Root directory to search for library subdirectories.
    """

    def __init__(self, base_path: Path | str | None = None) -> None:
        if base_path is None:
            env_path = os.environ.get("JCL_PROCLIB_PATH")
            base_path = Path(env_path) if env_path else None
        self._base: Path | None = Path(base_path) if base_path is not None else None

    def load_member(
        self,
        member_name: str,
        libraries: list[str] | None = None,
    ) -> str | None:
        """Search libraries in order and return the first matching member."""
        if self._base is None:
            return None
        candidates = self._candidate_paths(member_name, libraries)
        for path in candidates:
            # Guard against path traversal outside the configured base directory.
            if not is_within_directory(path, self._base):
                continue
            try:
                resolved = path.resolve()
                if resolved.is_file():
                    return _read_file_with_fallback(
                        resolved, max_bytes=MAX_LIBRARY_MEMBER_BYTES
                    )
            except OSError as exc:
                if exc.errno == errno.EFBIG:
                    logger.warning("INCLUDE member %r not read: %s", member_name, exc)
                continue
        return None

    def _candidate_paths(
        self,
        member_name: str,
        libraries: list[str] | None,
    ) -> list[Path]:
        """Build an ordered list of filesystem paths to try."""
        paths: list[Path] = []
        if self._base is None:
            return paths
        name_upper = member_name.upper()
        extensions = [".jcl", ".JCL", ""]

        if libraries:
            for lib in libraries:
                lib_dir = self._base / lib.replace(".", "/")
                alt_dir = self._base / lib  # some layouts keep dots in dir name
                for directory in (lib_dir, alt_dir):
                    for ext in extensions:
                        paths.append(directory / f"{name_upper}{ext}")

        # Fallback: flat search directly under base_path
        for ext in extensions:
            paths.append(self._base / f"{name_upper}{ext}")

        return paths


class LineOrigin(NamedTuple):
    """Where one line of INCLUDE-expanded JCL came from.

    Attributes:
        member: The INCLUDE member the line was read from -- the innermost
            one for a nested INCLUDE -- or ``None`` for a line of the main
            source.
        line: 1-based line number in the main source: the line itself for a
            main-source line, else the line of the (outermost) ``// INCLUDE``
            statement in the main source that brought it in.
        member_line: 1-based line number within *member* (``None`` for a
            main-source line).
    """

    member: str | None
    line: int
    member_line: int | None = None


#: One line of expanded text (line end included) and where it came from.
_Entry = tuple[str, LineOrigin]


def resolve_includes(
    content: str,
    loader: IncludeMemberLoader,
    libraries: list[str] | None = None,
    max_depth: int = 8,
    _depth: int = 0,
    _collected: list[str] | None = None,
    max_lines: int = 1_000_000,
    _active: frozenset[str] = frozenset(),
    _budget: list[int] | None = None,
    _symbols: dict[str, str] | None = None,
) -> str:
    """
    Expand ``// INCLUDE MEMBER=name`` statements by inlining member content.

    Processes the JCL text line by line.  Each INCLUDE statement is replaced
    by the content of the referenced member (loaded via *loader*).  If the
    member itself contains INCLUDE statements they are expanded recursively,
    up to *max_depth* levels deep.

    Unresolvable members (loader returns ``None``) are left as-is so that
    the caller can decide how to handle them (e.g. log a warning).

    :func:`resolve_includes_with_origins` does the same and also returns
    where each line of the result came from.

    Args:
        content: Raw JCL text to process.
        loader: Member loader used to fetch included content.
        libraries: JCLLIB library names passed to the loader.
        max_depth: Maximum recursion depth for nested INCLUDEs.
            Expansion stops when ``_depth >= max_depth``.
        _depth: Current recursion depth (internal — do not pass).
        _collected: If provided, member names that were successfully
            expanded are appended to this list (internal — callers may
            pass an empty list to collect all resolved member names).
        max_lines: Maximum number of member lines inlined in total. Fan-out
            (a member including another several times, at every level)
            grows exponentially with depth, so depth alone is no bound.
        _active: Members being expanded above this level (internal). An
            INCLUDE of one of them is recursive and is left intact.
        _budget: Remaining line budget shared across levels (internal).
        _symbols: SET symbols seen so far, shared across levels (internal).
            ``// INCLUDE MEMBER=&M`` after ``// SET M=MEMA`` includes MEMA.

    Returns:
        JCL text with all resolvable INCLUDE statements expanded.

    Raises:
        JCLStructureError: If expansion would inline more than *max_lines*.
    """
    expander = _IncludeExpander(
        loader,
        libraries,
        max_depth,
        max_lines,
        _collected,
        [max_lines] if _budget is None else _budget,
        {} if _symbols is None else _symbols,
    )
    return "".join(text for text, _ in expander.expand(content, _depth, _active))


def resolve_includes_with_origins(
    content: str,
    loader: IncludeMemberLoader,
    libraries: list[str] | None = None,
    max_depth: int = 8,
    max_lines: int = 1_000_000,
    collected: list[str] | None = None,
) -> tuple[str, list[LineOrigin]]:
    """Expand INCLUDEs like :func:`resolve_includes`; also map lines to origins.

    Returns:
        ``(text, origins)``: the expanded text, and one :class:`LineOrigin`
        per line of it (``origins[n - 1]`` is where line *n* came from), so
        a line number in the expanded text can be reported against the main
        source -- and the member -- it was read from.  *collected*, when
        given, receives the name of every member expanded.

    Raises:
        JCLStructureError: If expansion would inline more than *max_lines*.
    """
    expander = _IncludeExpander(
        loader, libraries, max_depth, max_lines, collected, [max_lines], {}
    )
    entries = expander.expand(content, 0, frozenset())
    return "".join(text for text, _ in entries), [origin for _, origin in entries]


class _IncludeExpander:
    """The state shared by every level of one INCLUDE expansion."""

    def __init__(
        self,
        loader: IncludeMemberLoader,
        libraries: list[str] | None,
        max_depth: int,
        max_lines: int,
        collected: list[str] | None,
        budget: list[int],
        symbols: dict[str, str],
    ) -> None:
        self.loader = loader
        self.libraries = libraries
        self.max_depth = max_depth
        self.max_lines = max_lines
        self.collected = collected
        self.budget = budget
        self.symbols = symbols

    def expand(self, content: str, depth: int, active: frozenset[str]) -> list[_Entry]:
        """Expand the INCLUDEs of *content*; one entry per resulting line.

        Line origins are relative to *content*: its own lines map to
        themselves, a member's lines to the INCLUDE line that brought them.
        """
        lines = split_source_lines(content, keepends=True)
        if depth >= self.max_depth:
            return [(line, LineOrigin(None, i + 1)) for i, line in enumerate(lines)]

        # Records of in-stream data (``DD *`` / ``DD DATA,DLM=``) and CNTL
        # blocks are not JCL: a ``// INCLUDE`` among them is data and must
        # stay as-is. They are located with the same scan the parser uses.
        from ._source_scanner import _merge_source_lines

        scanned = _merge_source_lines(content)
        data_indices = (
            scanned.inline_data_indices
            | scanned.control_data_indices
            | scanned.jes3_data_indices
        )

        result: list[_Entry] = []
        for index, line in enumerate(lines):
            expanded = None
            if index not in data_indices:
                expanded = self._expand_statement(lines, index, depth, active)
            if expanded is None:
                expanded = [(line, LineOrigin(None, index + 1))]
            result.extend(expanded)
        return result

    def _expand_statement(
        self, lines: list[str], index: int, depth: int, active: frozenset[str]
    ) -> list[_Entry] | None:
        """The expansion of ``lines[index]`` if it is a resolvable INCLUDE."""
        line_number = index + 1
        # Preserve leading whitespace: only strip the line terminator so that
        # in-stream data lines (which may contain '//' after leading spaces)
        # are never mistaken for JCL statements.
        statement_line = lines[index].rstrip("\r\n")
        _record_set_symbols(statement_line, self.symbols, lines, index + 1)
        member = _extract_include_member(statement_line)
        if member is None:
            return None
        if "&" in member:
            member = _substitute_member_symbols(member, self.symbols)
        if member in active:
            logger.warning(
                "INCLUDE member %r is recursive; leaving statement intact", member
            )
            return None
        expanded = self._expand_member(member, depth, active)
        if expanded is None:
            # Member not found — leave the INCLUDE line intact
            logger.debug(
                "INCLUDE member %r not found; leaving statement intact", member
            )
            return None
        return [
            (text, _member_origin(origin, member, line_number))
            for text, origin in expanded
        ]

    def _expand_member(
        self, member: str, depth: int, active: frozenset[str]
    ) -> list[_Entry] | None:
        """Load *member* and return its recursively expanded lines.

        Returns ``None`` if the loader cannot find the member. Charges the
        member's lines against the shared budget (see :func:`resolve_includes`).
        The last line always ends with a newline.

        Raises:
            JCLStructureError: If the expansion exceeds *max_lines*.
        """
        member_content = self.loader.load_member(member, self.libraries)
        if member_content is None:
            return None
        self.budget[0] -= member_content.count("\n") + 1
        if self.budget[0] < 0:
            raise JCLStructureError(
                f"INCLUDE expansion exceeds {self.max_lines:,} lines "
                f"(at member {member})"
            )
        if self.collected is not None:
            self.collected.append(member)
        logger.debug("resolved INCLUDE member %r (depth %d)", member, depth)
        entries = self.expand(member_content, depth + 1, active | {member})
        # Ensure the inlined content ends with a newline
        if not entries:
            return [("\n", LineOrigin(None, 1))]
        text, origin = entries[-1]
        if not text.endswith("\n"):
            entries[-1] = (text + "\n", origin)
        return entries


def _member_origin(origin: LineOrigin, member: str, include_line: int) -> LineOrigin:
    """Re-base *origin*, relative to *member*, on the INCLUDE line that read it."""
    if origin.member is None:
        return LineOrigin(member, include_line, origin.line)
    return LineOrigin(origin.member, include_line, origin.member_line)


def _record_set_symbols(
    line: str,
    symbols: dict[str, str],
    lines: Sequence[str] = (),
    follow: int = 0,
) -> None:
    """Record the assignments of a ``// SET`` statement *line* into *symbols*.

    Values are resolved against the symbols already recorded, mirroring the
    parser's left-to-right SET evaluation. Lines that are not a SET statement
    are ignored. A SET whose operand field ends in a comma is continued on the
    following ``//`` records: *lines* from index *follow* on (the record after
    *line*) are read for its remaining assignments (#180).
    """
    if not line.startswith("//") or line.startswith("//*"):
        return
    tokens = line[2:].split(None, 2)
    if not tokens:
        return
    # The operation is the first token (no label) or the second (labelled).
    if tokens[0].upper() != "SET" and (
        line[2:3].isspace() or len(tokens) < 2 or tokens[1].upper() != "SET"
    ):
        return

    from ._model_factories import _resolve_set_value
    from ._statement_parser import parse_statement, split_comment_field
    from .utils import is_positional_key, jcl_value_text

    statement, _ = split_comment_field(line)
    statement = _continue_operands(statement, lines, follow)
    stmt = parse_statement(statement)
    if stmt is None or stmt.type != "SET":
        return
    for key, value in stmt.parameters.items():
        if value is True or is_positional_key(key):
            continue
        symbols[key.upper()] = _resolve_set_value(jcl_value_text(value), symbols)


def _continue_operands(statement: str, lines: Sequence[str], follow: int) -> str:
    """Append the operands of the continuation records of *statement*.

    A statement whose operand field ends in a comma continues on the next
    ``//`` record that has a blank in column 3; its operand field (up to the
    first blank) is appended. ``//*`` comment records in between are skipped.
    """
    from ._statement_parser import split_comment_field

    statement = statement.rstrip()
    while statement.endswith(",") and follow < len(lines):
        cont = lines[follow].rstrip("\r\n")
        follow += 1
        if cont.startswith("//*"):
            continue
        if not cont.startswith("// ") or not cont[2:].strip():
            break
        operands, _ = split_comment_field("//  " + cont[2:].lstrip())
        statement += operands[2:].strip()
    return statement


def _substitute_member_symbols(member: str, symbols: dict[str, str]) -> str:
    """Resolve ``&SYMBOL`` references in an INCLUDE member name.

    Symbols with no recorded SET value are left as written.
    """
    from .explosion import SymbolScope, substitute_symbols

    return substitute_symbols(
        member, SymbolScope(set_symbols=symbols), allow_undefined=True
    ).upper()


def _extract_include_member(line: str) -> str | None:
    """
    Return the member name from a JCL INCLUDE statement, or ``None``.

    Recognises all syntactic forms accepted by the JCL parser
    (case-insensitive)::

        //          INCLUDE MEMBER=MYMEMBER    — no label, leading spaces
        //INCLUDE   MEMBER=MYMEMBER            — no label, no space after //
        //LABEL     INCLUDE MEMBER=MYMEMBER    — explicit label
        //LABEL     INCLUDE MEMBER=(MYMEMBER)  — parenthesised member name

    Detection is token-based: the INCLUDE keyword is identified as the
    operation field rather than by substring search, so lines where
    "INCLUDE" appears only in a dataset name or comment are not matched.

    Args:
        line: A single JCL source line (stripped or unstripped).

    Returns:
        Upper-cased member name, or ``None`` if not an INCLUDE statement.
    """
    if not line.startswith("//") or line.startswith("//*"):
        return None

    # Content after the mandatory "//" prefix
    statement = line[2:]
    stripped = statement.lstrip()
    if not stripped:
        return None

    # Split into at most two tokens: [first_token, remainder]
    parts = stripped.split(None, 1)
    first_upper = parts[0].upper()

    if first_upper == "INCLUDE":
        # No label: // INCLUDE ...  OR  //INCLUDE ...
        params_part = parts[1] if len(parts) > 1 else ""
    else:
        # Potentially: //LABEL INCLUDE ...
        if len(parts) < 2:
            return None
        rest_parts = parts[1].split(None, 1)
        if not rest_parts or rest_parts[0].upper() != "INCLUDE":
            return None
        params_part = rest_parts[1] if len(rest_parts) > 1 else ""

    # Parse MEMBER= from params_part
    upper_params = params_part.upper()
    member_idx = upper_params.find("MEMBER=")
    if member_idx == -1:
        return None

    name_part = params_part[member_idx + 7 :].strip()
    # Strip optional surrounding parentheses
    name_part = name_part.removeprefix("(")
    # Read identifier characters up to whitespace, comma, or closing paren
    name: list[str] = []
    for ch in name_part:
        if ch in " \t,)":
            break
        name.append(ch)
    return "".join(name).upper() if name else None
