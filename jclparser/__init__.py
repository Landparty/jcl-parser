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
    FileType, detect_file_type, detect_file_type_from_content, is_jcl_file, is_proc_file
)
from .sql_detector import (
    SQLDetectionResult,
    detect_sql_in_step,
    detect_sql_in_job,
    detect_sql_in_dd,
    detect_sql_in_text,
    is_db2_program,
    DB2_PROGRAMS,
)
from .condition_parser import (
    parse_condition,
    ConditionNode,
    ReturnCodeCondition,
    AbendCondition,
    RunCondition,
    NotCondition,
    AndCondition,
    OrCondition,
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
    'parse_condition',
    'ConditionNode',
    'ReturnCodeCondition',
    'AbendCondition',
    'RunCondition',
    'NotCondition',
    'AndCondition',
    'OrCondition',
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
    'detect_file_type_from_content',
    'is_jcl_file',
    'is_proc_file',
    'SQLDetectionResult',
    'detect_sql_in_step',
    'detect_sql_in_job',
    'detect_sql_in_dd',
    'detect_sql_in_text',
    'is_db2_program',
    'DB2_PROGRAMS',

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


# Lazy import map for heavy / optional symbols not imported at the top level
_LAZY: dict = {
    # explosion module
    'explode_job':      ('explosion', 'explode_job'),
    'SymbolScope':      ('explosion', 'SymbolScope'),
    'ExplosionRecord':  ('explosion', 'ExplosionRecord'),
    'ProcExpansionInfo': ('explosion', 'ProcExpansionInfo'),
    'substitute_symbols': ('explosion', 'substitute_symbols'),
    # proc_loader module
    'ProcedureLoader':          ('proc_loader', 'ProcedureLoader'),
    'InlineProcedureLoader':    ('proc_loader', 'InlineProcedureLoader'),
    'JCLLIBProcedureLoader':    ('proc_loader', 'JCLLIBProcedureLoader'),
    'CompositeProcedureLoader': ('proc_loader', 'CompositeProcedureLoader'),
    'create_default_loader':    ('proc_loader', 'create_default_loader'),
    # system_symbols module
    'SystemSymbolProvider':          ('system_symbols', 'SystemSymbolProvider'),
    'MockSystemSymbolProvider':      ('system_symbols', 'MockSystemSymbolProvider'),
    'RuntimeSystemSymbolProvider':   ('system_symbols', 'RuntimeSystemSymbolProvider'),
    'EnvironmentSystemSymbolProvider': ('system_symbols', 'EnvironmentSystemSymbolProvider'),
    'get_default_provider':          ('system_symbols', 'get_default_provider'),
    'set_default_provider':          ('system_symbols', 'set_default_provider'),
}


def __getattr__(name: str):
    """Lazily import heavy module attributes on first access."""
    if name in _LAZY:
        import importlib
        mod_name, attr = _LAZY[name]
        mod = importlib.import_module(f'.{mod_name}', __package__)
        return getattr(mod, attr)
    raise AttributeError(f"module 'jclparser' has no attribute {name!r}")