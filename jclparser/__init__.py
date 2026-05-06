"""
JCL Parser for Python 3.10+

A Python package for parsing IBM JCL (Job Control Language) scripts.
Provides a simple API for extracting, analyzing, and manipulating JCL statements.
"""

# Package metadata
__version__ = "1.0.0"
__author__ = "JCL Parser Team"
__description__ = "Parse IBM JCL scripts into Python objects"

# Import main API functions
from .parser import parse_jcl, validate_jcl, parse_statement
from .model import Job, Step, DDStatement, Parameter, Statement, OutputStatement
from .errors import (
    JCLSyntaxError,
    JCLValidationError,
    JCLStructureError,
    ParseError,
    ErrorType,
    ErrorSeverity,
    ValidationError,
    UndefinedSymbolError,
    ExplosionDepthError,
    CircularProcedureError,
    ProcedureNotFoundError,
)
from .plugins import (
    StatementPlugin,
    ValidationPlugin,
    PluginRegistry,
    ParserConfig,
    ValidationLevel,
    get_plugin_registry,
)
from .validators import (
    validate_jcl_identifier,
    validate_dataset_name,
    validate_job_structure,
    validate_step_structure,
    validate_dd_statement,
)
from .explosion import (
    explode_job,
    SymbolScope,
)
from .proc_loader import (
    ProcedureLoader,
    CompositeProcedureLoader,
    create_default_loader,
)
from .system_symbols import (
    SystemSymbolProvider,
)
from .jcl_file_type import (
    FileType,
    detect_file_type,
    detect_file_type_from_content,
    is_jcl_file,
    is_proc_file,
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
from .include_loader import (
    IncludeMemberLoader,
    DictMemberLoader,
    JCLLIBMemberLoader,
    resolve_includes,
)
from .dataset_lifecycle import (
    DatasetEvent,
    analyze_dataset_lifecycle,
    validate_dataset_lifecycle,
)
from .jes_statements import (
    JESControlStatement,
    JobParmStatement,
    RouteStatement,
    XmitStatement,
    SignonStatement,
    MessageStatement,
    NetacctStatement,
    NotifyStatement,
    PriorityStatement,
    Jes3RouteXeqStatement,
    parse_jes_control,
)
from .metrics import JobMetrics, compute_metrics
from .rc_analysis import (
    FeasibilityReport,
    compute_feasible_paths,
    DEFAULT_RC_DOMAIN,
)
from .program_profiles import (
    ProgramProfile,
    ProgramAnalysis,
    register_profile,
    analyze_step,
    analyze_job,
)
from .lint import (
    LintRule,
    LintConfig,
    lint_job,
    to_sarif as lint_to_sarif,
    register_rule as register_lint_rule,
)
from .profiling import (
    FunctionProfile,
    ProfilingResult,
)

# Initialize global plugin registry
_registry = get_plugin_registry()

# Public API - what gets imported with "from jclparser import *"
__all__ = [
    # ── Tier 1: Stable public API ─────────────────────────────────────────────
    "parse_jcl",
    "validate_jcl",
    "parse_statement",
    "parse",
    "Job",
    "Step",
    "DDStatement",
    "Parameter",
    "Statement",
    "OutputStatement",
    "JCLSyntaxError",
    "JCLValidationError",
    "JCLStructureError",
    "ParseError",
    "ValidationError",
    "ErrorType",
    "ErrorSeverity",
    "ValidationLevel",
    "UndefinedSymbolError",
    "ExplosionDepthError",
    "CircularProcedureError",
    "ProcedureNotFoundError",
    "__version__",
    # ── Tier 2: Advanced / power-user API ────────────────────────────────────
    "parse_condition",
    "ConditionNode",
    "ReturnCodeCondition",
    "AbendCondition",
    "RunCondition",
    "NotCondition",
    "AndCondition",
    "OrCondition",
    "explode_job",
    "ProcedureLoader",
    "CompositeProcedureLoader",
    "create_default_loader",
    "SystemSymbolProvider",
    "ParserConfig",
    "SymbolScope",
    "validate_jcl_identifier",
    "validate_dataset_name",
    "validate_job_structure",
    "validate_step_structure",
    "validate_dd_statement",
    "FileType",
    "detect_file_type",
    "detect_file_type_from_content",
    "is_jcl_file",
    "is_proc_file",
    "SQLDetectionResult",
    "detect_sql_in_step",
    "detect_sql_in_job",
    "detect_sql_in_dd",
    "detect_sql_in_text",
    "is_db2_program",
    "DB2_PROGRAMS",
    "StatementPlugin",
    "ValidationPlugin",
    "PluginRegistry",
    "get_plugin_registry",
    # ── Tier 2: Include resolution ────────────────────────────────────────────
    "IncludeMemberLoader",
    "DictMemberLoader",
    "JCLLIBMemberLoader",
    "resolve_includes",
    # ── Tier 2: Dataset lifecycle analysis ───────────────────────────────────
    "DatasetEvent",
    "analyze_dataset_lifecycle",
    "validate_dataset_lifecycle",
    # ── Tier 2: Typed JES2/JES3 control statements ──────────────────────────
    "JESControlStatement",
    "JobParmStatement",
    "RouteStatement",
    "XmitStatement",
    "SignonStatement",
    "MessageStatement",
    "NetacctStatement",
    "NotifyStatement",
    "PriorityStatement",
    "Jes3RouteXeqStatement",
    "parse_jes_control",
    # ── Tier 2: Metrics, RC feasibility, program profiles, lint ─────────────
    "JobMetrics",
    "compute_metrics",
    "FeasibilityReport",
    "compute_feasible_paths",
    "DEFAULT_RC_DOMAIN",
    "ProgramProfile",
    "ProgramAnalysis",
    "register_profile",
    "analyze_step",
    "analyze_job",
    "LintRule",
    "LintConfig",
    "lint_job",
    "lint_to_sarif",
    "register_lint_rule",
    # ── Profiling ─────────────────────────────────────────────────────────────
    "ProfilingResult",
    "FunctionProfile",
]


# Convenience function for quick parsing
def parse(source, **kwargs):
    """
    Convenience function for parsing JCL.

    Alias for parse_jcl() with simpler name.
    """
    return parse_jcl(source, **kwargs)
