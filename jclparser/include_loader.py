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

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

from .errors import JCLStructureError
from .utils import _read_file_with_fallback, is_within_directory

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

    The base path defaults to the ``JCL_PROCLIB_PATH`` environment variable
    (if set) or the current working directory.

    Args:
        base_path: Root directory to search for library subdirectories.
    """

    def __init__(self, base_path: Path | str | None = None) -> None:
        if base_path is None:
            env_path = os.environ.get("JCL_PROCLIB_PATH")
            base_path = Path(env_path) if env_path else Path.cwd()
        self._base = Path(base_path)

    def load_member(
        self,
        member_name: str,
        libraries: list[str] | None = None,
    ) -> str | None:
        """Search libraries in order and return the first matching member."""
        candidates = self._candidate_paths(member_name, libraries)
        for path in candidates:
            # Guard against path traversal outside the configured base directory.
            if not is_within_directory(path, self._base):
                continue
            try:
                resolved = path.resolve()
                if resolved.is_file():
                    return _read_file_with_fallback(resolved)
            except (OSError, PermissionError):
                continue
        return None

    def _candidate_paths(
        self,
        member_name: str,
        libraries: list[str] | None,
    ) -> list[Path]:
        """Build an ordered list of filesystem paths to try."""
        paths: list[Path] = []
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
) -> str:
    """
    Expand ``// INCLUDE MEMBER=name`` statements by inlining member content.

    Processes the JCL text line by line.  Each INCLUDE statement is replaced
    by the content of the referenced member (loaded via *loader*).  If the
    member itself contains INCLUDE statements they are expanded recursively,
    up to *max_depth* levels deep.

    Unresolvable members (loader returns ``None``) are left as-is so that
    the caller can decide how to handle them (e.g. log a warning).

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

    Returns:
        JCL text with all resolvable INCLUDE statements expanded.

    Raises:
        JCLStructureError: If expansion would inline more than *max_lines*.
    """
    if _depth >= max_depth:
        return content
    if _budget is None:
        _budget = [max_lines]

    # Records of in-stream data (``DD *`` / ``DD DATA,DLM=``) and CNTL blocks
    # are not JCL: a ``// INCLUDE`` among them is data and must stay as-is.
    # They are located with the same scan the parser itself uses.
    from .parser import _merge_source_lines

    _, inline_data, control_data, _ = _merge_source_lines(content)
    data_indices = inline_data | control_data

    result: list[str] = []
    for index, line in enumerate(content.splitlines(keepends=True)):
        if index in data_indices:
            result.append(line)
            continue
        # Preserve leading whitespace: only strip the line terminator so that
        # in-stream data lines (which may contain '//' after leading spaces)
        # are never mistaken for JCL statements.
        statement_line = line.rstrip("\r\n")
        member = _extract_include_member(statement_line)
        if member is not None and member in _active:
            logger.warning(
                "INCLUDE member %r is recursive; leaving statement intact", member
            )
        elif member is not None:
            member_content = loader.load_member(member, libraries)
            if member_content is not None:
                _budget[0] -= member_content.count("\n") + 1
                if _budget[0] < 0:
                    raise JCLStructureError(
                        f"INCLUDE expansion exceeds {max_lines:,} lines "
                        f"(at member {member})"
                    )
                if _collected is not None:
                    _collected.append(member)
                logger.debug("resolved INCLUDE member %r (depth %d)", member, _depth)
                expanded = resolve_includes(
                    member_content,
                    loader=loader,
                    libraries=libraries,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _collected=_collected,
                    max_lines=max_lines,
                    _active=_active | {member},
                    _budget=_budget,
                )
                # Ensure the inlined content ends with a newline
                if not expanded.endswith("\n"):
                    expanded += "\n"
                result.append(expanded)
                continue
            # Member not found — leave the INCLUDE line intact
            logger.debug(
                "INCLUDE member %r not found; leaving statement intact", member
            )
        result.append(line)

    return "".join(result)


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
