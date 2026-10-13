"""
Core JCL parsing logic.

This module contains the main parsing entry points for converting JCL scripts
into structured Python objects with full support for syntax validation
and plugin extensibility.

The implementation is split across several modules:

* :mod:`jclparser._source_scanner` — the source pre-scan that marks in-stream
  data and CNTL records and merges continuation lines (``_merge_source_lines``).
* :mod:`jclparser._statement_parser` — single-statement line parsing
  (``parse_statement``, parameter tokenization, INCLUDE/JCLLIB pre-scans).
* :mod:`jclparser._job_builder` — ``Statement`` → model assembly
  (:class:`~jclparser._job_builder.JobBuilder` per-statement handlers), with
  the factories in :mod:`jclparser._model_factories` and the post-parse passes
  (external PROCs, OUTPUT refs, SET substitution) in
  :mod:`jclparser._post_parse`.
* this module — the public API (``parse_jcl``, ``validate_jcl``,
  ``parse_statement``), the parse loop and the phases around it.

For backward compatibility every helper that historically lived here is still
importable from ``jclparser.parser``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Literal, overload

# Backward-compatible re-exports: these helpers historically lived in this
# module and are imported from ``jclparser.parser`` by tests and downstream
# code. Keep them importable from here.
from ._job_builder import (  # noqa: F401
    _SET_SYMBOL_PATTERN,
    JobBuilder,
    _create_dd_from_statement,
    _create_job_from_statement,
    _create_step_from_statement,
    _exec_has_program_spec,
    _extract_output_ref_names,
    _has_unresolved_symbol_ref,
    _resolve_output_refs,
    _resolve_set_value,
    enforce_strict_dd_structure,
    load_external_procedures,
    resolve_set_symbols,
)
from ._source_scanner import (  # noqa: F401
    ScannedSource,
    _expects_continuation,
    _instream_delimiter,
    _merge_source_lines,
    merge_continuations,
)
from ._statement_parser import (  # noqa: F401
    _OPERATOR_PREFIXES,
    _RE_HAS_INCLUDE,
    _STATEMENT_TYPES,
    _check_param_balance,
    _extract_jcllib_order,
    _find_keyword_eq,
    _has_include_statement,
    _operand_field,
    _parse_list_parameter,
    _parse_parameters,
    parse_statement,
    split_comment_field,
    statement_operation,
)
from .continuation_handler import ContinuationLineHandler  # noqa: F401
from .errors import (
    ErrorSeverity,
    ErrorType,
    JCLStructureError,
    JCLSyntaxError,
    JCLValidationError,
    ParseError,
)
from .model import (  # noqa: F401
    ConditionalBlock,
    DDStatement,
    Job,
    OutputStatement,
    Procedure,
    Statement,
    Step,
    iter_execution_steps,
)
from .plugins import (
    ParserConfig,
    ValidationLevel,
    get_plugin_registry,
    normalize_validation_level,
)
from .profiling import ProfilerContext, ProfilingResult
from .utils import (
    POSITIONAL_PARAM_PREFIX,  # noqa: F401
    instream_delimiter,  # noqa: F401
    is_continued_card_image,  # noqa: F401
    is_positional_key,  # noqa: F401
    normalize_jcl_line,  # noqa: F401
    read_source,
    split_source_lines,  # noqa: F401
)

if TYPE_CHECKING:
    from .include_loader import IncludeMemberLoader

logger = logging.getLogger(__name__)


def _parse_jcl_core(
    source: str | Path | IO,
    strict_mode: bool = False,
    config: ParserConfig | None = None,
    proc_base_path: str | Path | None = None,
    enable_external_procs: bool = True,
    include_loader: IncludeMemberLoader | None = None,
    *,
    validate_job: bool = True,
) -> Job:
    """Core parsing implementation. See parse_jcl() for full documentation.

    *validate_job* = False skips the strict-mode ``job.validate()`` pass, for
    :func:`validate_jcl`, which reports those findings itself rather than
    losing them to a :class:`JCLValidationError` (#57).
    """
    # The keyword and the config are two ways to ask for strict parsing;
    # either one turns it on.
    strict_mode = strict_mode or (config is not None and config.strict_mode)
    # Handle different input source types (FileNotFoundError propagates)
    content = read_source(source)
    content, expanded_includes = _expand_includes(
        content, include_loader, proc_base_path
    )

    scanned = _merge_source_lines(content)
    job = _build_job(scanned, config)

    # Anything the line-classification pass discarded or repaired (a comment
    # field that looked like operands, an unterminated CNTL block) is reported
    # rather than dropped without a trace.
    job.warnings.extend(scanned.warnings)

    # Create and attach procedure loader for external PROC loading
    load_external_procedures(
        job,
        strict_mode=strict_mode,
        proc_base_path=proc_base_path,
        enable_external_procs=enable_external_procs,
    )

    # In strict mode, a DD statement with no preceding EXEC is a structural error
    if strict_mode and not job.steps:
        enforce_strict_dd_structure(content)

    _resolve_references(job, expanded_includes)

    if strict_mode and validate_job:
        _raise_on_fatal_findings(job)

    # Optional: auto-run SQL detection when requested via ParserConfig
    if config is not None and getattr(config, "detect_sql", False):
        _detect_sql(job)

    if logger.isEnabledFor(logging.INFO):
        _log_parse_summary(job)

    return job


def _expand_includes(
    content: str,
    include_loader: IncludeMemberLoader | None,
    proc_base_path: str | Path | None,
) -> tuple[str, list[str]]:
    """Expand INCLUDE MEMBER= statements; return the content and the members.

    This runs before the main parse loop so that inlined content participates
    in continuation-line merging and everything else that follows.
    """
    expanded: list[str] = []
    if not _has_include_statement(content):
        return content, expanded

    from .include_loader import JCLLIBMemberLoader, resolve_includes

    if include_loader is None:
        include_loader = JCLLIBMemberLoader(base_path=proc_base_path)
    # Pre-scan the raw content for JCLLIB ORDER so the loader can search
    # the correct libraries.  This is a best-effort single-line scan;
    # ORDER values spread across continuation lines are not picked up here
    # (those are rare in practice).
    jcllib_libs = _extract_jcllib_order(content) or None
    content = resolve_includes(
        content,
        loader=include_loader,
        libraries=jcllib_libs,
        _collected=expanded,
    )
    logger.debug(
        "expanded %d INCLUDE member(s) before parse: %s",
        len(expanded),
        expanded,
    )
    return content, expanded


def _build_job(scanned: ScannedSource, config: ParserConfig | None) -> Job:
    """Run the parse loop over the scanned source lines.

    The builder holds all loop state and has one handler per statement type
    (see jclparser/_job_builder.py).
    """
    builder = JobBuilder(dialect=config.dialect if config is not None else "standard")
    for line, line_num in scanned.merged_lines:
        # Handle inline data continuation
        if builder.consume_inline_data(line):
            continue

        # Skip comments and empty lines (but recognise JES3 //*ROUTE XEQ
        # control statements before dropping the comment).
        if not line.strip() or line.strip().startswith("//*"):
            builder.handle_comment_line(line, line_num)
            continue

        # Skip lines marked as inline data (line_num is 1-indexed, markers use 0-indexed)
        if (line_num - 1) in scanned.inline_data_indices:
            if not line.startswith(("//", "/*")):
                # In-stream data with no DD statement ahead of it.
                builder.start_implicit_sysin(line, line_num)
            continue

        # Program control records inside a CNTL/ENDCNTL block are kept with
        # the CNTL statement rather than parsed as JCL.
        if (line_num - 1) in scanned.control_data_indices:
            builder.handle_control_data(line)
            continue

        # Parse the statement
        stmt = parse_statement(line, line_num, config)
        if not stmt:
            continue

        # Process the statement (dispatches on stmt.type)
        builder.handle_statement(stmt, line_num)

    return builder.finish()


def _resolve_references(job: Job, expanded_includes: list[str]) -> None:
    """Post-parse passes that need the whole job: INCLUDEs, OUTPUT=, SET."""
    # Record any INCLUDE members that were expanded during pre-processing.
    # Members resolved before the main parse loop never reach the INCLUDE
    # handler in the loop, so we add them here to keep job.includes complete.
    for member in expanded_includes:
        if member not in job.includes:
            job.includes.append(member)

    # Resolve OUTPUT=*.name back-references on every DD.
    _resolve_output_refs(job)

    # Resolve SET symbol references in DD dataset names and EXEC parameters.
    # SET statements may appear before or after the DD statements that
    # reference them, so this substitution pass runs *after* the main parse
    # loop once all SET symbols are fully known (see resolve_set_symbols).
    if job.set_statements:
        logger.debug(
            "resolving %d SET symbol(s) across DD statements",
            len(job.set_statements),
        )
        resolve_set_symbols(job)


def _raise_on_fatal_findings(job: Job) -> None:
    """Strict-mode validation: raise if ``job.validate()`` reports an ERROR.

    WARNING/INFO findings (e.g. unresolved OUTPUT back-references, forward
    dataset references) are advisory and must not break strict parsing.
    """
    logger.debug("running strict-mode validation for job %s", job.name)
    fatal = [err for err in job.validate() if err.severity == ErrorSeverity.ERROR]
    if fatal:
        error_msg = "; ".join([err.message for err in fatal])
        raise JCLValidationError(f"Job validation failed: {error_msg}")


def _detect_sql(job: Job) -> None:
    """Store SQL detection results per step on ``job.sql_detections``."""
    from .sql_detector import detect_sql_in_job

    for result in detect_sql_in_job(job):
        if result.step_name:
            job.sql_detections[result.step_name] = result


def _log_parse_summary(job: Job) -> None:
    step_count = sum(1 for _ in iter_execution_steps(job.steps))
    dd_count = len(job.get_dd_statements())
    if job.name:
        logger.info(
            "parsed job %s: %d steps, %d DD statements",
            job.name,
            step_count,
            dd_count,
        )
    else:
        logger.info(
            "parsed PROC-only file: %d procedures, %d DD statements",
            len(job.procedures),
            dd_count,
        )


@overload
def parse_jcl(
    source: str | Path | IO,
    strict_mode: bool = ...,
    config: ParserConfig | None = ...,
    proc_base_path: str | Path | None = ...,
    enable_external_procs: bool = ...,
    include_loader: IncludeMemberLoader | None = ...,
    enable_profiling: Literal[False] = ...,
    top_n: int = ...,
    prof_output: str | None = ...,
) -> Job: ...


@overload
def parse_jcl(
    source: str | Path | IO,
    strict_mode: bool = ...,
    config: ParserConfig | None = ...,
    proc_base_path: str | Path | None = ...,
    enable_external_procs: bool = ...,
    include_loader: IncludeMemberLoader | None = ...,
    enable_profiling: Literal[True] = ...,
    top_n: int = ...,
    prof_output: str | None = ...,
) -> tuple[Job, ProfilingResult]: ...


def parse_jcl(
    source: str | Path | IO,
    strict_mode: bool = False,
    config: ParserConfig | None = None,
    proc_base_path: str | Path | None = None,
    enable_external_procs: bool = True,
    include_loader: IncludeMemberLoader | None = None,
    enable_profiling: bool = False,
    top_n: int = 50,
    prof_output: str | None = None,
) -> Job | tuple[Job, ProfilingResult]:
    """
    Parse JCL script from various input sources into structured Job object.

    Args:
        source: JCL text as a ``str``, a :class:`pathlib.Path` naming a file,
            or a file-like object. A ``str`` is always content, never a path.
        strict_mode: Enable strict parsing mode.  ``config.strict_mode`` also
            enables it; either one is enough.
        config: Optional parser configuration: its ``dialect``, the statement
            plugins it enables (plugins are opt-in; with no config none run),
            ``strict_mode`` and ``detect_sql`` all apply.
        proc_base_path: Base directory for external PROC libraries
                       (defaults to the JCL_PROCLIB_PATH env var; with neither,
                       no external PROC or INCLUDE member is read)
        enable_external_procs: Enable loading PROCs from file system via JCLLIB ORDER
        include_loader: Optional :class:`~jclparser.include_loader.IncludeMemberLoader`
            used to resolve ``INCLUDE MEMBER=name`` statements before parsing.
            When ``None`` (the default) a :class:`~jclparser.include_loader.JCLLIBMemberLoader`
            pointing at *proc_base_path* is created automatically, but only if
            INCLUDE statements are actually found in the source.
        enable_profiling: When True, wrap parsing with cProfile + tracemalloc and
            return a ``(Job, ProfilingResult)`` tuple instead of just a ``Job``.
        top_n: Number of top functions to include in the profiling report
            (by cumulative time). Only used when *enable_profiling* is True.
        prof_output: Optional file path to write the binary ``.prof`` file.
            Only used when *enable_profiling* is True.

    Returns:
        Job object representing parsed JCL structure (when enable_profiling=False),
        or a (Job, ProfilingResult) tuple (when enable_profiling=True).

    Raises:
        JCLSyntaxError: Invalid JCL syntax encountered
        JCLValidationError: Valid syntax but semantic errors
        FileNotFoundError: When source is path to non-existent file
    """
    if not enable_profiling:
        return _parse_jcl_core(
            source,
            strict_mode,
            config,
            proc_base_path,
            enable_external_procs,
            include_loader,
        )
    ctx = ProfilerContext(top_n=top_n, prof_output=prof_output)
    with ctx:
        job = _parse_jcl_core(
            source,
            strict_mode,
            config,
            proc_base_path,
            enable_external_procs,
            include_loader,
        )
    assert ctx.result is not None
    return job, ctx.result


def validate_jcl(
    source: str | Path | IO,
    level: ValidationLevel | str | None = None,
    config: ParserConfig | None = None,
) -> list[ParseError]:
    """
    Validate JCL syntax and structure without full parsing.

    Args:
        source: JCL script to validate
        level: Validation level, a :class:`~jclparser.plugins.ValidationLevel`
            or its string value (``"basic"``, ``"structure"``, ``"semantic"``;
            ``"syntax_only"`` is an alias of ``"basic"``).  When omitted,
            ``config.validation_level`` is used, else ``"basic"``.
        config: Optional parser configuration.  Its ``dialect`` and enabled
            plugins apply to the parse; at the semantic level only the
            validation plugins it enables run (with no config, none do).

    Returns:
        List of ParseError objects (empty if valid)

    Raises:
        ValueError: *level* names no validation level.
    """
    if level is None:
        level = config.validation_level if config is not None else "basic"
    effective_level = normalize_validation_level(level)

    errors: list[ParseError] = []
    if not isinstance(source, (str, Path)):
        # A file-like object can be read only once; the fallback below needs
        # the content again.
        source = read_source(source)

    # First try normal parsing to catch basic structure issues
    try:
        # Strict parse for the parse-time structure errors (unresolvable
        # PROC, orphaned DD), but without the job.validate() pass: strict
        # mode turns its ERROR findings into one JCLValidationError, which
        # used to land in the syntax-only fallback below and vanish (#57).
        job = _parse_jcl_core(
            source, strict_mode=True, config=config, validate_job=False
        )
        _add_job_findings(job, effective_level, errors)
        # Plugin-based validation (opt-in: only the plugins the config enables)
        if effective_level == ValidationLevel.SEMANTIC and config is not None:
            _add_plugin_findings(job, config, errors)
        return errors
    except (JCLSyntaxError, JCLValidationError, JCLStructureError) as exc:
        # The strict parse stops at the first error; the line-by-line pass
        # below collects the others, and the strict error itself is reported
        # too -- it is often the only one naming the real cause (#75).
        strict_error = exc

    errors.extend(_validate_line_by_line(source, config, strict_error))
    return errors


_STRICT_ERROR_TYPES: dict[type[Exception], ErrorType] = {
    JCLSyntaxError: ErrorType.SYNTAX_ERROR,
    JCLValidationError: ErrorType.VALIDATION_ERROR,
    JCLStructureError: ErrorType.STRUCTURE_ERROR,
}


def _strict_parse_error(
    exc: JCLSyntaxError | JCLValidationError | JCLStructureError,
) -> ParseError:
    """The :class:`ParseError` reporting the exception the strict parse raised."""
    error_type = next(
        (t for cls, t in _STRICT_ERROR_TYPES.items() if isinstance(exc, cls)),
        ErrorType.SYNTAX_ERROR,
    )
    return ParseError(
        error_type=error_type,
        message=exc.message,
        line_number=exc.line_number or 0,
        context=exc.context,
        severity=ErrorSeverity.ERROR,
    )


def _add_job_findings(
    job: Job, level: ValidationLevel, errors: list[ParseError]
) -> None:
    """Append the ``job.validate()`` findings to report at *level*.

    The basic level reports the ERROR ones -- exactly what makes a strict
    parse fail; structure and semantic report every finding, warnings
    included.
    """
    for err in job.validate():
        if level == ValidationLevel.BASIC and err.severity != ErrorSeverity.ERROR:
            continue
        errors.append(
            ParseError(
                error_type=err.error_type,
                message=err.message,
                line_number=err.line_number or 0,
                severity=err.severity,
            )
        )


def _add_plugin_findings(
    job: Job, config: ParserConfig, errors: list[ParseError]
) -> None:
    """Append the findings of every validation plugin *config* enables."""
    registry = get_plugin_registry()
    flat_steps = list(iter_execution_steps(job.steps))
    validators = [v for v in registry.get_validators() if config.is_plugin_enabled(v)]
    for validator in validators:
        # A ValidationPlugin has three hooks; run each of them, so a rule
        # written against validate_step / validate_dd is not silently skipped.
        validation_errors = list(validator.validate_job(job))
        for step in flat_steps:
            validation_errors.extend(validator.validate_step(step))
            for dd in step.dd_statements:
                validation_errors.extend(validator.validate_dd(dd))
        for err in validation_errors:
            errors.append(
                ParseError(
                    error_type=err.error_type,
                    message=err.message,
                    line_number=err.line_number or 0,
                    # Keep a plugin's WARNING/INFO findings as such.
                    severity=getattr(err, "severity", None) or ErrorSeverity.ERROR,
                )
            )


def _validate_line_by_line(
    source: str | Path | IO[Any],
    config: ParserConfig | None,
    strict_error: JCLSyntaxError | JCLValidationError | JCLStructureError | None = None,
) -> list[ParseError]:
    """Fallback validation when the strict parse failed.

    Each merged statement is parsed on its own, so one bad statement does not
    hide the errors in the others, and a few structural rules are checked
    along the way. In-stream data and CNTL control records are not JCL and
    are skipped, exactly as the parse loop skips them. *strict_error*, the
    exception the strict parse raised, is reported as well unless this pass
    already reports it, or it is the "No JOB statement found" a JOB-less
    member with nothing to run (no statements, or a PROC member) is exempt
    from.
    """
    try:
        content = read_source(source)
    except FileNotFoundError as exc:
        return [
            ParseError(
                error_type=ErrorType.SYNTAX_ERROR,
                message=str(exc),
                line_number=0,
                severity=ErrorSeverity.ERROR,
            )
        ]

    # Merge continuation lines so multi-line statements are validated as a
    # unit, and learn which records are in-stream data rather than JCL.
    scanned = _merge_source_lines(content)
    data_indices = scanned.inline_data_indices | scanned.control_data_indices

    errors: list[ParseError] = []
    structure = _StructureTracker(errors)
    for line, line_num in scanned.merged_lines:
        if (line_num - 1) in data_indices:
            continue
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("//*"):
            continue

        _check_statement(line, line_num, config, structure, errors)

    structure.finish()
    if strict_error is not None and not structure.exempt_from(strict_error):
        _add_unless_reported(_strict_parse_error(strict_error), errors)
    return errors


def _check_statement(
    line: str,
    line_num: int,
    config: ParserConfig | None,
    structure: _StructureTracker,
    errors: list[ParseError],
) -> None:
    """Parse one merged statement on its own and record what is wrong with it."""
    try:
        stmt = parse_statement(line, line_num, config)
        if stmt:
            structure.check(stmt, line_num)
    except JCLSyntaxError as e:
        errors.append(_statement_error(ErrorType.SYNTAX_ERROR, e, line_num))
    except JCLValidationError as e:
        errors.append(_statement_error(ErrorType.VALIDATION_ERROR, e, line_num))


def _add_unless_reported(error: ParseError, errors: list[ParseError]) -> None:
    """Add *error* in line order unless *errors* already has the same finding."""
    if any(
        e.message == error.message and e.line_number == error.line_number
        for e in errors
    ):
        return
    position = next(
        (i for i, e in enumerate(errors) if e.line_number > error.line_number),
        len(errors),
    )
    errors.insert(position, error)


def _statement_error(
    error_type: ErrorType,
    exc: JCLSyntaxError | JCLValidationError,
    line_num: int,
) -> ParseError:
    return ParseError(
        error_type=error_type,
        message=exc.message,
        line_number=exc.line_number or line_num,
        context=exc.context,
        severity=ErrorSeverity.ERROR,
    )


_NO_JOB_MESSAGE = "No JOB statement found"


class _StructureTracker:
    """Statement-order checks for :func:`_validate_line_by_line`."""

    def __init__(self, errors: list[ParseError]) -> None:
        self.errors = errors
        self.has_job = False
        self.in_proc = False
        self.has_exec = False
        self.has_dd = False
        self.has_statement = False
        self.has_proc = False

    def exempt_from(self, exc: Exception) -> bool:
        """Whether the strict parse's *exc* is not an error for this source.

        A source with no statements at all, and a PROC member with steps (a
        cataloged or in-stream procedure with no JOB), have no JOB statement
        by design; the strict parse's "No JOB statement found" is not
        reported for them.
        """
        if getattr(exc, "message", "") != _NO_JOB_MESSAGE:
            return False
        return not self.has_statement or (self.has_proc and self.has_exec)

    def _error(self, message: str, line_number: int) -> None:
        self.errors.append(
            ParseError(
                error_type=ErrorType.SYNTAX_ERROR,
                message=message,
                line_number=line_number,
                severity=ErrorSeverity.ERROR,
            )
        )

    def check(self, stmt: Statement, line_num: int) -> None:
        self.has_statement = True
        if stmt.type == "JOB":
            if self.has_job:
                self._error("Multiple JOB statements found", line_num)
            self.has_job = True
        elif stmt.type == "PROC":
            self.in_proc = self.has_proc = True
        elif stmt.type == "PEND":
            self.in_proc = False
            self.has_proc = True
        elif stmt.type == "EXEC":
            if not self.has_job and not self.in_proc:
                self._error("EXEC statement before JOB statement", line_num)
            # An unresolvable PROC= reference is reported by the strict
            # parse's own error ("Procedure 'X' not found"), not here.
            if not _exec_has_program_spec(stmt.parameters):
                self._error("EXEC statement missing program or procedure", line_num)
            self.has_exec = True
        elif stmt.type == "DD":
            # DD before EXEC is allowed (e.g. JOBLIB before the first step)
            # as long as some EXEC exists later in the job; checked for the
            # whole job in finish().
            self.has_dd = True

    def finish(self) -> None:
        # Mirrors the strict-mode structural check in _parse_jcl_core: a DD
        # statement with no EXEC anywhere in the job is a structural error,
        # not just a syntax quirk to ignore.
        if self.has_job and self.has_dd and not self.has_exec:
            self.errors.append(
                ParseError(
                    error_type=ErrorType.STRUCTURE_ERROR,
                    message="DD statement found before any EXEC step. "
                    "Each DD must belong to a step.",
                    line_number=0,
                    severity=ErrorSeverity.ERROR,
                )
            )
