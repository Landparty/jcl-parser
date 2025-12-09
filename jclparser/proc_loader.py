"""
Procedure loader system for JCL explosion.

Provides abstract interface and implementations for loading procedure definitions
from various sources (inline, external files, JCLLIB libraries).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Dict
from functools import lru_cache
import os

from .model import Procedure
from .errors import ProcedureNotFoundError


class ProcedureLoader(ABC):
    """
    Abstract base class for procedure loading.
    
    Implementations provide mechanisms to locate and load procedure
    definitions from various sources during explosion.
    """
    
    @abstractmethod
    def load_procedure(self, name: str, libraries: Optional[List[str]] = None) -> Optional[Procedure]:
        """
        Load a procedure definition by name.
        
        Args:
            name: Procedure name to load
            libraries: Optional list of library paths/names to search
            
        Returns:
            Procedure object if found, None otherwise
        """
        pass
    
    def has_procedure(self, name: str, libraries: Optional[List[str]] = None) -> bool:
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
    
    def __init__(self, procedures: List[Procedure]):
        """
        Initialize inline loader.
        
        Args:
            procedures: List of inline procedure definitions from job
        """
        self._procedures: Dict[str, Procedure] = {
            proc.name.upper(): proc for proc in procedures
        }
    
    def load_procedure(self, name: str, libraries: Optional[List[str]] = None) -> Optional[Procedure]:
        """Load procedure from inline definitions"""
        return self._procedures.get(name.upper())


class JCLLIBProcedureLoader(ProcedureLoader):
    """
    Loader for procedures from external JCLLIB libraries.
    
    Reads procedure definitions from files in specified library directories.
    Supports environment variable JCL_PROCLIB_PATH for base path configuration.
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize JCLLIB loader.
        
        Args:
            base_path: Base directory for procedure libraries
                      (defaults to JCL_PROCLIB_PATH env var or current directory)
        """
        if base_path is None:
            env_path = os.environ.get('JCL_PROCLIB_PATH')
            base_path = Path(env_path) if env_path else Path.cwd()
        
        self.base_path = Path(base_path)
    
    def load_procedure(self, name: str, libraries: Optional[List[str]] = None) -> Optional[Procedure]:
        """
        Load procedure from JCLLIB libraries.
        
        Searches in order through specified libraries for a file matching
        the procedure name (with or without .jcl extension).
        Uses internal caching via _cache dict.
        """
        # Create cache key
        cache_key = (name.upper(), tuple(libraries) if libraries else ())
        if not hasattr(self, '_cache'):
            self._cache = {}
        
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
    
    def _load_from_library(self, name: str, library: str) -> Optional[Procedure]:
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
        
        # Try different file name variations
        candidates = [
            library_path / f"{name}.jcl",
            library_path / f"{name}.JCL",
            library_path / name.lower(),
            library_path / name.upper(),
        ]
        
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return self._parse_procedure_file(candidate, name)
        
        return None
    
    def _parse_procedure_file(self, file_path: Path, proc_name: str) -> Optional[Procedure]:
        """
        Parse a procedure from a file.
        
        Args:
            file_path: Path to procedure file
            proc_name: Expected procedure name
            
        Returns:
            Procedure object
        """
        from .parser import parse_jcl
        
        try:
            # Parse the file as JCL
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse to extract procedure definition
            job = parse_jcl(content, strict=False)
            
            # Look for the procedure in the parsed job
            for proc in job.procedures:
                if proc.name.upper() == proc_name.upper():
                    return proc
            
            # If no explicit PROC/PEND, treat entire file as procedure
            # This is a simplified approach - real z/OS might differ
            if job.steps:
                return Procedure(
                    name=proc_name,
                    parameters={},
                    steps=job.steps,
                    line_number=0
                )
            
        except Exception:
            # Parsing failed - return None
            pass
        
        return None


class CompositeProcedureLoader(ProcedureLoader):
    """
    Composite loader implementing fallback chain.
    
    Tries multiple loaders in sequence, returning the first successful result.
    Provides LRU caching for performance optimization.
    """
    
    def __init__(self, loaders: List[ProcedureLoader]):
        """
        Initialize composite loader.
        
        Args:
            loaders: List of loaders to try in order
        """
        self.loaders = loaders
    
    @lru_cache(maxsize=256)
    def load_procedure(self, name: str, libraries: Optional[tuple] = None) -> Optional[Procedure]:
        """
        Load procedure using fallback chain.
        
        Note: libraries converted to tuple for cache hashability.
        """
        # Convert tuple back to list for internal use
        lib_list = list(libraries) if libraries else None
        
        # Try each loader in sequence
        for loader in self.loaders:
            proc = loader.load_procedure(name, lib_list)
            if proc is not None:
                return proc
        
        return None
    
    def has_procedure(self, name: str, libraries: Optional[List[str]] = None) -> bool:
        """Check if any loader can provide the procedure"""
        # Convert list to tuple for caching
        lib_tuple = tuple(libraries) if libraries else None
        return self.load_procedure(name, lib_tuple) is not None


def create_default_loader(
    inline_procedures: List[Procedure],
    base_path: Optional[Path] = None,
    include_jcllib: bool = True
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
    loaders: List[ProcedureLoader] = [
        InlineProcedureLoader(inline_procedures)
    ]
    
    if include_jcllib:
        loaders.append(JCLLIBProcedureLoader(base_path))
    
    return CompositeProcedureLoader(loaders)
