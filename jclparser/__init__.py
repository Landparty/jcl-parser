"""
JCL Parser for Python 3.10+

A Python package for parsing IBM JCL (Job Control Language) scripts.
Provides a simple API for extracting, analyzing, and manipulating JCL statements.

Logging
-------
This library emits diagnostics via the standard :mod:`logging` module under the
``jclparser`` logger. Following library convention, a :class:`logging.NullHandler`
is attached so applications that do not configure logging see no output. To see
diagnostics (e.g. why an external PROC failed to load), configure logging in the
application, for example::

    import logging
    logging.getLogger("jclparser").setLevel(logging.DEBUG)
    logging.basicConfig()
"""

import logging as _logging

# Package metadata
__version__ = "2.2.3"  # x-release-please-version
__author__ = "JCL Parser Team"
__description__ = "Parse IBM JCL scripts into Python objects"

# Import main API functions
from .builtin_procs import (
    BUILTIN_UTILITY_PROCS,
    create_builtin_proc_loader,
)
from .condition_parser import (
    AbendCondition,
    AndCondition,
    ConditionNode,
    NotCondition,
    OrCondition,
    ReturnCodeCondition,
    RunCondition,
    parse_condition,
)
from .dataset_lifecycle import (
    DatasetEvent,
    analyze_dataset_lifecycle,
    validate_dataset_lifecycle,
)
from .errors import (
    CircularProcedureError,
    ErrorSeverity,
    ErrorType,
    ExplosionDepthError,
    JCLParseError,
    JCLStructureError,
    JCLSyntaxError,
    JCLValidationError,
    ParseError,
    ProcedureNotFoundError,
    UndefinedSymbolError,
    ValidationError,
)
from .explosion import (
    SymbolScope,
    explode_job,
)
from .include_loader import (
    DictMemberLoader,
    IncludeMemberLoader,
    JCLLIBMemberLoader,
    LineOrigin,
    resolve_includes,
    resolve_includes_with_origins,
)
from .jcl_file_type import (
    FileType,
    detect_file_type,
    detect_file_type_from_content,
    is_jcl_file,
    is_proc_file,
)
from .jes_statements import (
    Jes3RouteXeqStatement,
    JESControlStatement,
    JobParmStatement,
    MessageStatement,
    NetacctStatement,
    NotifyStatement,
    PriorityStatement,
    RouteStatement,
    SignonStatement,
    XmitStatement,
    parse_jes_control,
)
from .lineage import (
    DatasetLineage,
    DatasetUse,
    JobDependency,
    JobStream,
    LineageReport,
    build_lineage,
    load_job_stream,
)
from .lint import (
    LintConfig,
    LintRule,
    lint_job,
)
from .lint import (
    register_rule as register_lint_rule,
)
from .lint import (
    to_sarif as lint_to_sarif,
)
from .metrics import JobMetrics, compute_metrics
from .model import (
    ConditionalBlock,
    DDStatement,
    Job,
    OutputStatement,
    Parameter,
    Statement,
    Step,
    iter_execution_steps,
)
from .parser import parse_jcl, parse_statement, validate_jcl
from .plugins import (
    ParserConfig,
    PluginRegistry,
    StatementPlugin,
    ValidationLevel,
    ValidationPlugin,
    get_plugin_registry,
)
from .proc_loader import (
    CompositeProcedureLoader,
    DictProcedureLoader,
    ProcedureLoader,
    create_default_loader,
)
from .profiling import (
    FunctionProfile,
    ProfilingResult,
)
from .program_profiles import (
    ProgramAnalysis,
    ProgramProfile,
    analyze_job,
    analyze_step,
    register_profile,
)
from .rc_analysis import (
    DEFAULT_RC_DOMAIN,
    FeasibilityReport,
    compute_feasible_paths,
)
from .serialization import (
    JOB_JSON_SCHEMA,
    SCHEMA_VERSION,
    job_to_dict,
    job_to_json,
)
from .sql_detector import (
    DB2_PROGRAMS,
    SQLDetectionResult,
    detect_sql_in_dd,
    detect_sql_in_job,
    detect_sql_in_step,
    detect_sql_in_text,
    is_db2_program,
)
from .system_symbols import (
    SystemSymbolProvider,
)
from .validators import (
    validate_dataset_name,
    validate_dd_statement,
    validate_jcl_identifier,
    validate_job_structure,
    validate_step_structure,
)

# Attach a NullHandler to the package logger so library logging is silent by
# default unless the consuming application configures handlers.
_logging.getLogger(__name__).addHandler(_logging.NullHandler())

# Public API - what gets imported with "from jclparser import *"
__all__ = [  # noqa: RUF022 — grouped by API tier, not alphabetically
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
    "ConditionalBlock",
    "iter_execution_steps",
    "JCLParseError",
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
    "DictProcedureLoader",
    "create_default_loader",
    "BUILTIN_UTILITY_PROCS",
    "create_builtin_proc_loader",
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
    "LineOrigin",
    "resolve_includes",
    "resolve_includes_with_origins",
    # ── Tier 2: JSON export ───────────────────────────────────────────────────
    "job_to_dict",
    "job_to_json",
    "JOB_JSON_SCHEMA",
    "SCHEMA_VERSION",
    # ── Tier 2: Cross-job dataset lineage ─────────────────────────────────────
    "load_job_stream",
    "build_lineage",
    "JobStream",
    "LineageReport",
    "DatasetLineage",
    "DatasetUse",
    "JobDependency",
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
