"""
JCL Parser for Python 3.13

A Python package for parsing IBM JCL (Job Control Language) scripts.
Provides a simple API for extracting, analyzing, and manipulating JCL statements.
"""

# Package metadata
__version__ = "0.1.0"
__author__ = "JCL Parser Team"
__description__ = "Parse IBM JCL scripts into Python objects"

# Import main API functions
from .parser import parse_jcl, validate_jcl, parse_statement
from .model import Job, Step, DDStatement, Parameter, Statement
from .errors import (
    JCLSyntaxError, JCLValidationError, JCLStructureError,
    ParseError, ErrorType, ErrorSeverity, ValidationError,
    UndefinedSymbolError, ExplosionDepthError, CircularProcedureError,
    ProcedureNotFoundError
)
from .plugins import (
    StatementPlugin, ValidationPlugin, PluginRegistry, 
    ParserConfig, ValidationLevel, get_plugin_registry
)
from .validators import (
    validate_jcl_identifier, validate_dataset_name,
    validate_job_structure, validate_step_structure,
    validate_dd_statement
)
from .explosion import (
    explode_job, substitute_symbols, SymbolScope, 
    ExplosionRecord, ProcExpansionInfo
)
from .proc_loader import (
    ProcedureLoader, InlineProcedureLoader, JCLLIBProcedureLoader,
    CompositeProcedureLoader, create_default_loader
)
from .system_symbols import (
    SystemSymbolProvider, MockSystemSymbolProvider,
    RuntimeSystemSymbolProvider, EnvironmentSystemSymbolProvider,
    get_default_provider, set_default_provider
)
from .jcl_file_type import (
    FileType, detect_file_type, is_jcl_file, is_proc_file
)

# Initialize global plugin registry
_registry = get_plugin_registry()

# Public API - what gets imported with "from jclparser import *"
__all__ = [
    # ── Tier 1: Stable public API ─────────────────────────────────────────────
    # These are the primary entry points for all users.
    'parse_jcl',
    'validate_jcl',
    'parse_statement',
    'parse',
    'Job',
    'Step',
    'DDStatement',
    'Parameter',
    'Statement',
    'JCLSyntaxError',
    'JCLValidationError',
    'JCLStructureError',
    'ParseError',
    'ValidationError',
    'ErrorType',
    'ErrorSeverity',
    'ValidationLevel',
    '__version__',

    # ── Tier 2: Advanced / power-user API ────────────────────────────────────
    # Stable, but intended for advanced use cases.
    'explode_job',
    'ProcedureLoader',
    'CompositeProcedureLoader',
    'create_default_loader',
    'SystemSymbolProvider',
    'ParserConfig',
    'SymbolScope',
    'validate_jcl_identifier',
    'validate_dataset_name',
    'validate_job_structure',
    'validate_step_structure',
    'validate_dd_statement',
    'FileType',
    'detect_file_type',
    'is_jcl_file',
    'is_proc_file',

    # ── Tier 3: Internal / backwards-compatibility exports ───────────────────
    # Exported for existing consumers; may be removed in a future major version.
    'MockSystemSymbolProvider',
    'EnvironmentSystemSymbolProvider',
    'RuntimeSystemSymbolProvider',
    'get_default_provider',
    'set_default_provider',
    'ExplosionRecord',
    'ProcExpansionInfo',
    'InlineProcedureLoader',
    'JCLLIBProcedureLoader',
    'UndefinedSymbolError',
    'ExplosionDepthError',
    'CircularProcedureError',
    'ProcedureNotFoundError',
    'substitute_symbols',
    'StatementPlugin',
    'ValidationPlugin',
    'PluginRegistry',
    'get_plugin_registry',
]

# Convenience function for quick parsing
def parse(source, **kwargs):
    """
    Convenience function for parsing JCL.
    
    Alias for parse_jcl() with simpler name.
    """
    return parse_jcl(source, **kwargs)