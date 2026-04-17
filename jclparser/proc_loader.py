"""
Procedure loader system for JCL explosion.

Provides abstract interface and implementations for loading procedure definitions
from various sources (inline, external files, JCLLIB libraries).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
import os

from .model import Procedure
from .errors import JCLSyntaxError, JCLValidationError
from .utils import _read_file_with_fallback


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
        pass

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


class JCLLIBProcedureLoader(ProcedureLoader):
    """
    Loader for procedures from external JCLLIB libraries.

    Reads procedure definitions from files in specified library directories.
    Supports environment variable JCL_PROCLIB_PATH for base path configuration.
    """

    def __init__(self, base_path: Path | None = None):
        """
        Initialize JCLLIB loader.

        Args:
            base_path: Base directory for procedure libraries
                      (defaults to JCL_PROCLIB_PATH env var or current directory)
        """
        if base_path is None:
            env_path = os.environ.get("JCL_PROCLIB_PATH")
            base_path = Path(env_path) if env_path else Path.cwd()

        self.base_path = Path(base_path)
        self._cache: dict = {}

    def load_procedure(
        self, name: str, libraries: Sequence[str] | None = None
    ) -> Procedure | None:
        """
        Load procedure from JCLLIB libraries.

        Searches in order through specified libraries for a file matching
        the procedure name (with or without .jcl extension).
        Uses internal caching via _cache dict.
        """
        # Create cache key
        cache_key = (name.upper(), tuple(libraries) if libraries else ())

        if cache_key in self._cache:
            return self._cache[cache_key]
        if libraries is None:
            libraries = []

        # Try each library in order
        for library in libraries:
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
        if not self.base_path.exists() or not self.base_path.is_dir():
            return result
        for lib_dir in sorted(self.base_path.iterdir()):
            if not lib_dir.is_dir():
                continue
            procs: list[str] = []
            for f in sorted(lib_dir.iterdir()):
                if not f.is_file():
                    continue
                try:
                    if not f.resolve().is_relative_to(lib_dir.resolve()):
                        continue
                except (OSError, ValueError):
                    continue
                if f.suffix.lower() in (".jcl",) or not f.suffix:
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
        # Construct library path
        library_path = self.base_path / library

        if not library_path.exists() or not library_path.is_dir():
            return None

        # Try different file name variations (case-insensitive on case-sensitive fs)
        name_upper = name.upper()
        name_lower = name.lower()
        candidates = [
            library_path / f"{name_upper}.jcl",
            library_path / f"{name_upper}.JCL",
            library_path / f"{name}.jcl",
            library_path / f"{name}.JCL",
            library_path / f"{name_lower}.jcl",
            library_path / f"{name_lower}.JCL",
            library_path / name_lower,
            library_path / name_upper,
        ]

        for candidate in candidates:
            # Guard against path traversal (e.g. name="../../secret")
            try:
                resolved = candidate.resolve()
                if not resolved.is_relative_to(library_path.resolve()):
                    continue
            except (OSError, ValueError):
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
        from .parser import parse_jcl
        from .jcl_file_type import detect_file_type_from_content, FileType

        try:
            # Read the file content once using the shared encoding-fallback reader
            content = _read_file_with_fallback(file_path)

            # Detect the file type from already-read content (avoids second read)
            file_type = detect_file_type_from_content(content)

            # Reject if it's a JCL job file (has JOB card)
            # A PROC file should NOT have a JOB card
            if file_type == FileType.JCL:
                # This is a JCL job file, not a PROC - skip it
                # In a real system, you might want to log a warning
                return None

            # For standalone PROC files (no JOB statement), we need to wrap them
            # in a dummy JOB statement so the parser can handle them
            if file_type == FileType.PROC:
                # Prepend a dummy JOB statement
                content = f"//DUMMYJOB JOB\n{content}"

            # Parse to extract procedure definition
            job = parse_jcl(content, strict_mode=False)

            # Look for the procedure in the parsed job
            for proc in job.procedures:
                if proc.name.upper() == proc_name.upper():
                    proc.is_external = True
                    return proc

            # If no explicit PROC/PEND, treat entire file as procedure
            # This is a simplified approach - real z/OS might differ
            if job.steps:
                return Procedure(
                    name=proc_name,
                    parameters={},
                    steps=job.steps,
                    line_number=0,
                    is_external=True,
                )

        except (JCLSyntaxError, JCLValidationError, OSError, ValueError):
            # Parsing failed - return None
            pass

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
                return proc

        return None  # not found — do NOT cache so retries can succeed

    def has_procedure(self, name: str, libraries: Sequence[str] | None = None) -> bool:
        """Check if any loader can provide the procedure"""
        return self.load_procedure(name, libraries) is not None


def create_default_loader(
    inline_procedures: list[Procedure],
    base_path: Path | None = None,
    include_jcllib: bool = True,
) -> ProcedureLoader:
    """
    Create a default composite loader with standard configuration.

    Args:
        inline_procedures: Inline procedures from job
        base_path: Base path for JCLLIB loading
        include_jcllib: Whether to include JCLLIB loader in chain

    Returns:
        Configured composite loader
    """
    loaders: list[ProcedureLoader] = [InlineProcedureLoader(inline_procedures)]

    if include_jcllib:
        loaders.append(JCLLIBProcedureLoader(base_path))

    return CompositeProcedureLoader(loaders)
