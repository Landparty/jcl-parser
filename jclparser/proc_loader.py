"""
Procedure loader system for JCL explosion.

Provides abstract interface and implementations for loading procedure definitions
from various sources (inline, external files, JCLLIB libraries).
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from .errors import JCLSyntaxError, JCLValidationError
from .model import Procedure
from .utils import (
    MAX_LIBRARY_MEMBER_BYTES,
    _read_file_with_fallback,
    is_within_directory,
)

logger = logging.getLogger(__name__)


def _build_procedure_from_content(content: str, proc_name: str) -> Procedure | None:
    """Parse JCL PROC *content* into a :class:`Procedure`.

    Returns ``None`` when the content is a full JOB file (not a PROC) or holds
    nothing usable. Underlying parse errors propagate so callers can add
    context-specific logging.
    """
    from .jcl_file_type import FileType, detect_file_type_from_content
    from .parser import parse_jcl

    source_text = content
    file_type = detect_file_type_from_content(content)
    # A PROC file must not carry a JOB card; a full JCL job is not a procedure.
    if file_type == FileType.JCL:
        return None
    # Standalone PROC files (no JOB statement) are wrapped so the parser accepts them.
    if file_type == FileType.PROC:
        content = f"//DUMMYJOB JOB\n{content}"

    job = parse_jcl(content, strict_mode=False)
    target = proc_name.upper()
    for proc in job.procedures:
        if proc.name.upper() == target:
            proc.is_external = True
            proc.source_text = source_text
            return proc

    # z/OS calls a cataloged procedure by its member name; the PROC label is
    # optional and ignored when it differs (#184). A member holding exactly
    # one PROC, named otherwise or not at all, is that procedure.
    if len(job.procedures) == 1 and not job.steps:
        proc = job.procedures[0]
        proc.name = proc_name
        proc.is_external = True
        proc.source_text = source_text
        return proc

    # No explicit PROC/PEND: treat the whole file's steps as the procedure body.
    # Its SETs landed in the wrapper job's table; they belong to the procedure.
    # (With PROC/PEND, the parser already records them on the Procedure.)
    if job.steps:
        return Procedure(
            name=proc_name,
            parameters={},
            steps=job.steps,
            line_number=0,
            is_external=True,
            set_statements=dict(job.set_statements),
            source_text=source_text,
        )
    return None


class ProcedureLoader(ABC):
    """
    Abstract base class for procedure loading.

    Implementations provide mechanisms to locate and load procedure
    definitions from various sources during explosion.
    """

    @abstractmethod
    def load_procedure(
        self, name: str, libraries: Sequence[str] | None = None
    ) -> Procedure | None:
        """
        Load a procedure definition by name.

        Args:
            name: Procedure name to load
            libraries: Optional list of library paths/names to search

        Returns:
            Procedure object if found, None otherwise
        """

    def has_procedure(self, name: str, libraries: Sequence[str] | None = None) -> bool:
        """
        Check if a procedure can be loaded.

        Args:
            name: Procedure name
            libraries: Optional list of library paths/names

        Returns:
            True if procedure is available
        """
        return self.load_procedure(name, libraries) is not None


class InlineProcedureLoader(ProcedureLoader):
    """
    Loader for procedures defined inline within the JCL job.

    Extracts procedures from the job's procedures list.
    """

    def __init__(self, procedures: list[Procedure]):
        """
        Initialize inline loader.

        Args:
            procedures: List of inline procedure definitions from job
        """
        self._procedures: dict[str, Procedure] = {
            proc.name.upper(): proc for proc in procedures
        }

    def load_procedure(
        self, name: str, libraries: Sequence[str] | None = None
    ) -> Procedure | None:
        """Load procedure from inline definitions"""
        return self._procedures.get(name.upper())


#: The system procedure libraries JES searches after the ``JCLLIB ORDER``
#: libraries -- and on their own when a job has no JCLLIB.  Under the
#: loader's base path they are ``<base_path>/SYS1.PROCLIB/<NAME>.jcl``.
DEFAULT_SYSTEM_PROCLIBS: tuple[str, ...] = ("SYS1.PROCLIB",)

#: File extensions a PROC member may have under a library directory, in
#: search order (any case); a member with no extension is tried last.
_PROC_MEMBER_EXTENSIONS: tuple[str, ...] = (".jcl", ".prc", ".proc")


class JCLLIBProcedureLoader(ProcedureLoader):
    """
    Loader for procedures from external JCLLIB libraries.

    Reads procedure definitions from files in specified library directories,
    then in :data:`DEFAULT_SYSTEM_PROCLIBS`, as JES searches the JCLLIB
    libraries before the system PROCLIB.
    Supports environment variable JCL_PROCLIB_PATH for base path configuration.
    With neither a base path nor that variable it reads no files at all: the
    process's working directory is never searched implicitly, since JCLLIB
    ORDER comes from the JCL being parsed.
    """

    def __init__(self, base_path: Path | None = None):
        """
        Initialize JCLLIB loader.

        Args:
            base_path: Base directory for procedure libraries (defaults to the
                JCL_PROCLIB_PATH env var; with neither, no library is searched)
        """
        if base_path is None:
            env_path = os.environ.get("JCL_PROCLIB_PATH")
            base_path = Path(env_path) if env_path else None

        self.base_path: Path | None = Path(base_path) if base_path is not None else None
        self._cache: dict = {}

    def load_procedure(
        self, name: str, libraries: Sequence[str] | None = None
    ) -> Procedure | None:
        """
        Load procedure from JCLLIB libraries.

        Searches in order through specified libraries, then
        :data:`DEFAULT_SYSTEM_PROCLIBS`, for a file matching the procedure
        name (with or without .jcl extension).
        Uses internal caching via _cache dict.
        """
        # Create cache key
        cache_key = (name.upper(), tuple(libraries) if libraries else ())

        if cache_key in self._cache:
            return self._cache[cache_key]
        listed = list(libraries or [])
        listed_upper = {lib.upper() for lib in listed}
        search = listed + [
            lib for lib in DEFAULT_SYSTEM_PROCLIBS if lib.upper() not in listed_upper
        ]

        # Try each library in order
        for library in search:
            proc = self._load_from_library(name, library)
            if proc is not None:
                self._cache[cache_key] = proc
                return proc

        self._cache[cache_key] = None
        return None

    def list_all_procedures(self) -> dict[str, list[str]]:
        """Discover all available PROCs under the base path.

        Scans each immediate subdirectory of base_path as a library and
        returns a mapping of library_name -> sorted list of PROC names.
        """
        result: dict[str, list[str]] = {}
        if (
            self.base_path is None
            or not self.base_path.exists()
            or not self.base_path.is_dir()
        ):
            return result
        for lib_dir in sorted(self.base_path.iterdir()):
            if not lib_dir.is_dir():
                continue
            procs: list[str] = []
            for f in sorted(lib_dir.iterdir()):
                if not f.is_file():
                    continue
                if not is_within_directory(f, lib_dir):
                    continue
                if f.suffix.lower() in _PROC_MEMBER_EXTENSIONS or not f.suffix:
                    procs.append(f.stem.upper())
            if procs:
                result[lib_dir.name] = sorted(procs)
        return result

    def _load_from_library(self, name: str, library: str) -> Procedure | None:
        """
        Load procedure from a specific library.

        Args:
            name: Procedure name
            library: Library name/path

        Returns:
            Procedure if found, None otherwise
        """
        if self.base_path is None:
            return None
        # Construct library path
        library_path = self.base_path / library

        # JCLLIB ORDER comes from the JCL being parsed: an absolute or ``..``
        # library must not escape the configured base directory. Checked
        # lexically, so a library the operator symlinked into base_path works.
        if not Path(os.path.abspath(library_path)).is_relative_to(
            os.path.abspath(self.base_path)
        ):
            return None

        if not library_path.exists() or not library_path.is_dir():
            return None

        # Try different file name variations (case-insensitive on case-sensitive
        # fs). ``.prc`` / ``.proc`` are common PROC member extensions in
        # source trees (AWS CardDemo keeps every PROC as ``NAME.prc``).
        name_upper = name.upper()
        name_lower = name.lower()
        candidates = [
            library_path / f"{stem}{suffix}"
            for ext in _PROC_MEMBER_EXTENSIONS
            for stem in (name_upper, name, name_lower)
            for suffix in (ext, ext.upper())
        ]
        candidates += [library_path / name_lower, library_path / name_upper]

        for candidate in candidates:
            # Guard against path traversal (e.g. name="../../secret")
            if not is_within_directory(candidate, library_path):
                continue
            if candidate.exists() and candidate.is_file():
                return self._parse_procedure_file(candidate, name)

        return None

    def _parse_procedure_file(
        self, file_path: Path, proc_name: str
    ) -> Procedure | None:
        """
        Parse a procedure from a file.

        Args:
            file_path: Path to procedure file
            proc_name: Expected procedure name

        Returns:
            Procedure object
        """
        try:
            # Read the file content once using the shared encoding-fallback reader
            content = _read_file_with_fallback(
                file_path, max_bytes=MAX_LIBRARY_MEMBER_BYTES
            )
            return _build_procedure_from_content(content, proc_name)
        except (JCLSyntaxError, JCLValidationError, OSError, ValueError) as exc:
            # Parsing/reading failed - log the cause and return None so the
            # composite loader can fall through to the next candidate/loader.
            logger.warning(
                "Failed to load procedure %r from %s: %s: %s",
                proc_name,
                file_path,
                type(exc).__name__,
                exc,
            )
            return None


class CompositeProcedureLoader(ProcedureLoader):
    """
    Composite loader implementing fallback chain.

    Tries multiple loaders in sequence, returning the first successful result.
    Only successful (non-None) lookups are cached so that a procedure that
    was unavailable at first call can still be found once it becomes available.
    """

    def __init__(self, loaders: list[ProcedureLoader]):
        """
        Initialize composite loader.

        Args:
            loaders: List of loaders to try in order
        """
        self.loaders = loaders
        self._cache: dict[tuple, Procedure] = {}

    def load_procedure(
        self, name: str, libraries: Sequence[str] | None = None
    ) -> Procedure | None:
        """
        Load procedure using fallback chain.

        Tries each loader in order and caches the first successful result.
        """
        lib_tuple = tuple(libraries) if libraries else ()
        cache_key = (name.upper(), lib_tuple)
        if cache_key in self._cache:
            return self._cache[cache_key]

        lib_list = list(libraries) if libraries else None

        for loader in self.loaders:
            proc = loader.load_procedure(name, lib_list)
            if proc is not None:
                self._cache[cache_key] = proc  # only cache successes
                logger.debug(
                    "resolved procedure %r via %s",
                    name,
                    type(loader).__name__,
                )
                return proc

        logger.debug(
            "procedure %r not found in any loader (libraries=%s)", name, lib_list
        )
        return None  # not found — do NOT cache so retries can succeed

    def has_procedure(self, name: str, libraries: Sequence[str] | None = None) -> bool:
        """Check if any loader can provide the procedure"""
        return self.load_procedure(name, libraries) is not None


def create_default_loader(
    inline_procedures: list[Procedure],
    base_path: Path | None = None,
    include_jcllib: bool = True,
    include_builtins: bool = True,
) -> ProcedureLoader:
    """
    Create a default composite loader with standard configuration.

    The chain resolves in precedence order: inline procedures first, then
    external JCLLIB procedures, then the bundled utility PROC templates for
    common IBM-supplied procedure names (IMSBATCH, DLIBATCH, DSNUPROC, ...)
    as a last-resort fallback.

    Args:
        inline_procedures: Inline procedures from job
        base_path: Base path for JCLLIB loading
        include_jcllib: Whether to include JCLLIB loader in chain
        include_builtins: Whether to append the bundled utility PROC templates
            as the final fallback

    Returns:
        Configured composite loader
    """
    loaders: list[ProcedureLoader] = [InlineProcedureLoader(inline_procedures)]

    if include_jcllib:
        loaders.append(JCLLIBProcedureLoader(base_path))

    if include_builtins:
        # Imported lazily to avoid a circular import (builtin_procs imports
        # from this module).
        from .builtin_procs import create_builtin_proc_loader

        loaders.append(create_builtin_proc_loader())

    return CompositeProcedureLoader(loaders)


class DictProcedureLoader(ProcedureLoader):
    """Loads procedures from an in-memory dict[str, str] (proc_name -> JCL content).

    Parses each procedure lazily on first access and caches the Procedure object
    so subsequent calls are pure dict lookups.
    """

    def __init__(self, data: dict[str, str]) -> None:
        self._content: dict[str, str] = {k.upper(): v for k, v in data.items()}
        self._parsed: dict[str, Procedure] = {}

    def load_procedure(
        self, name: str, libraries: Sequence[str] | None = None
    ) -> Procedure | None:
        if not name:
            return None
        key = name.upper()
        if key in self._parsed:
            return self._parsed[key]
        content = self._content.get(key)
        if content is None:
            return None
        proc = self._parse_proc_content(content, key)
        if proc is not None:
            self._parsed[key] = proc
        return proc

    def _parse_proc_content(self, content: str, proc_name: str) -> Procedure | None:
        """Parse JCL PROC content string into a Procedure object."""
        try:
            return _build_procedure_from_content(content, proc_name)
        except (JCLSyntaxError, JCLValidationError, ValueError) as exc:
            # Parsing failed - log the cause and return None. Narrowed from a
            # bare ``except Exception`` so genuine programming errors surface.
            logger.warning(
                "Failed to parse in-memory procedure %r: %s: %s",
                proc_name,
                type(exc).__name__,
                exc,
            )
            return None
