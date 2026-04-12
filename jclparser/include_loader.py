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

import os
from abc import ABC, abstractmethod
from pathlib import Path


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
            try:
                return path.read_text(encoding="utf-8", errors="replace")
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
        _depth: Current recursion depth (internal — do not pass).

    Returns:
        JCL text with all resolvable INCLUDE statements expanded.
    """
    if _depth > max_depth:
        return content

    result: list[str] = []
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        member = _extract_include_member(stripped)
        if member is not None:
            member_content = loader.load_member(member, libraries)
            if member_content is not None:
                expanded = resolve_includes(
                    member_content,
                    loader=loader,
                    libraries=libraries,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )
                # Ensure the inlined content ends with a newline
                if not expanded.endswith("\n"):
                    expanded += "\n"
                result.append(expanded)
                continue
            # Member not found — leave the INCLUDE line intact
        result.append(line)

    return "".join(result)


def _extract_include_member(line: str) -> str | None:
    """
    Return the member name from a JCL INCLUDE statement, or ``None``.

    Recognises these forms (case-insensitive)::

        //          INCLUDE MEMBER=MYMEMBER
        //LABEL     INCLUDE MEMBER=MYMEMBER
        //LABEL     INCLUDE MEMBER=(MYMEMBER)

    Args:
        line: A single (already stripped) JCL source line.

    Returns:
        Upper-cased member name, or ``None`` if not an INCLUDE statement.
    """
    if not line.startswith("//"):
        return None
    upper = line.upper()
    if " INCLUDE " not in upper and "\tINCLUDE " not in upper:
        return None

    # Find MEMBER= keyword
    member_idx = upper.find("MEMBER=")
    if member_idx == -1:
        return None

    rest = line[member_idx + 7:].strip()
    # Strip optional surrounding parentheses
    if rest.startswith("("):
        rest = rest[1:]
    # Read up to next whitespace, comma, or closing paren
    name = []
    for ch in rest:
        if ch in " \t,)":
            break
        name.append(ch)
    return "".join(name).upper() if name else None
