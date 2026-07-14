"""
Core JCL parsing logic.

This module contains the main parsing entry points for converting JCL scripts
into structured Python objects with full support for syntax validation
and plugin extensibility.

The implementation is split across three modules:

* :mod:`jclparser._statement_parser` — single-statement line parsing
  (``parse_statement``, parameter tokenization, INCLUDE/JCLLIB pre-scans).
* :mod:`jclparser._job_builder` — ``Statement`` → model assembly
  (:class:`~jclparser._job_builder.JobBuilder` per-statement handlers) and
  the post-parse passes (external PROCs, OUTPUT refs, SET substitution).
* this module — the public API (``parse_jcl``, ``validate_jcl``,
  ``parse_statement``) and the core loop orchestration.

For backward compatibility every helper that historically lived here is still
importable from ``jclparser.parser``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal, overload

from ._job_builder import (
    JobBuilder,
    _resolve_output_refs,
    enforce_strict_dd_structure,
    load_external_procedures,
    resolve_set_symbols,
)
from ._statement_parser import (
    _extract_jcllib_order,
    _has_include_statement,
    parse_statement,
)
from .continuation_handler import ContinuationLineHandler
from .errors import (
    ErrorSeverity,
    ErrorType,
    JCLStructureError,
    JCLSyntaxError,
    JCLValidationError,
    ParseError,
)
from .model import Job
from .plugins import ParserConfig, get_plugin_registry
from .profiling import ProfilerContext, ProfilingResult
from .utils import is_positional_key, normalize_jcl_line, read_source

# Backward-compatible re-exports: these helpers historically lived in this
# module and are imported from ``jclparser.parser`` by tests and downstream
# code. Keep them importable from here.
from ._job_builder import (  # noqa: F401
    _SET_SYMBOL_PATTERN,
    _create_dd_from_statement,
    _create_job_from_statement,
    _create_step_from_statement,
    _exec_has_program_spec,
    _extract_output_ref_names,
    _has_unresolved_symbol_ref,
    _resolve_set_value,
)
from ._statement_parser import (  # noqa: F401
    _OPERATOR_PREFIXES,
    _RE_HAS_INCLUDE,
    _STATEMENT_TYPES,
    _check_param_balance,
    _find_keyword_eq,
    _parse_list_parameter,
    _parse_parameters,
)
from .model import (  # noqa: F401
    ConditionalBlock,
    DDStatement,
    OutputStatement,
    Procedure,
    Statement,
    Step,
)
from .utils import POSITIONAL_PARAM_PREFIX  # noqa: F401

if TYPE_CHECKING:
    from .include_loader import IncludeMemberLoader

logger = logging.getLogger(__name__)


def _merge_source_lines(content: str) -> tuple[list[tuple[str, int]], set[int]]:
    """Normalize, mark in-stream data, and merge continuation lines.

    Returns ``(merged_lines, inline_data_indices)`` where *merged_lines* is a
    list of ``(line, 1-based line number)`` pairs ready for the parse loop and
    *inline_data_indices* is the set of 0-based original indices that belong
    to in-stream (``DD *`` / ``DD DATA``) data blocks and must never be parsed
    as JCL statements.
    """
    raw_lines = content.splitlines()
    lines = [normalize_jcl_line(line) for line in raw_lines]

    # Single pass: separate inline data lines from regular lines.
    # Simultaneously records which original indices are inline data
    # and builds the non-inline list for continuation merging.
    inline_data_indices: set[int] = set()
    non_inline_lines: list[str] = []
    non_inline_orig_indices: list[int] = []  # parallel to non_inline_lines
    in_inline_data = False
    delimiter = "/*"
    # When the current in-stream dataset was opened with ``DD *`` (and *no*
    # custom ``DLM=``), z/OS terminates the data at the next record beginning
    # with ``//`` as well as at ``/*``.  ``DD DATA`` deliberately does not do
    # this so that records containing ``//`` can be supplied as data; for
    # ``DD DATA`` (or any dataset with an explicit ``DLM=``) only the delimiter
    # ends the data.
    terminates_on_slash = False

    for i, line in enumerate(lines):
        if in_inline_data:
            if line.strip() == delimiter or line.strip().startswith(delimiter):
                # The delimiter record belongs to the in-stream data block
                # (it is not a JCL statement) — mark it and stop collecting.
                inline_data_indices.add(i)
                in_inline_data = False
                continue
            if terminates_on_slash and line.startswith("//"):
                # Unterminated ``DD *`` data: the next JCL statement ends it.
                # Fall through so this line is treated as a normal statement.
                in_inline_data = False
            else:
                inline_data_indices.add(i)
                continue
        if (
            line.strip()
            and line.startswith("//")
            and not line.strip().startswith("//*")
        ):
            upper_line = line.upper()
            if " DD " in upper_line or " DD*" in upper_line or "\tDD\t" in upper_line:
                is_star = (
                    " DD *" in upper_line
                    or " DD*" in upper_line
                    or "\tDD\t*" in upper_line
                )
                has_dlm = ",DLM=" in upper_line
                if is_star or " DD DATA" in upper_line or has_dlm:
                    delimiter = "/*"
                    if "DLM=" in upper_line:
                        dlm_start = upper_line.index("DLM=") + 4
                        dlm_end = dlm_start
                        while (
                            dlm_end < len(upper_line)
                            and upper_line[dlm_end] not in ",) \t\r\n"
                        ):
                            dlm_end += 1
                        delimiter = line[dlm_start:dlm_end]
                    in_inline_data = True
                    terminates_on_slash = is_star and not has_dlm
        non_inline_lines.append(line)
        non_inline_orig_indices.append(i)

    # Merge continuation lines on the non-inline subset only.
    handler = ContinuationLineHandler()
    merged_non_inline = handler.merge_continuation_lines(non_inline_lines)

    # Recombine: build lookup of orig_idx -> merged_line for group-start lines only.
    # Continuation lines that were folded into a group are simply absent from this map
    # and will be skipped in the loop below — which is correct.
    merged_start: dict[int, str] = {}
    for merged_line, ni_line_num in merged_non_inline:
        orig_idx = non_inline_orig_indices[ni_line_num - 1]
        merged_start[orig_idx] = merged_line

    merged_lines: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        if i in inline_data_indices:
            merged_lines.append((line, i + 1))
        elif i in merged_start:
            merged_lines.append((merged_start[i], i + 1))

    return merged_lines, inline_data_indices


def _parse_jcl_core(
    source: str | Path | IO,
    strict_mode: bool = False,
    config: ParserConfig | None = None,
    proc_base_path: str | Path | None = None,
    enable_external_procs: bool = True,
    include_loader: "IncludeMemberLoader | None" = None,
) -> Job:
    """Core parsing implementation. See parse_jcl() for full documentation."""
    # Handle different input source types
    try:
        content = read_source(source)
    except FileNotFoundError:
        raise

    # Expand INCLUDE MEMBER= statements before the main parse loop so that
    # inlined content participates in continuation-line merging and everything
    # else that follows.
    _expanded_includes: list[str] = []
    if _has_include_statement(content):
        from .include_loader import resolve_includes, JCLLIBMemberLoader

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
            _collected=_expanded_includes,
        )
        logger.debug(
            "expanded %d INCLUDE member(s) before parse: %s",
            len(_expanded_includes),
            _expanded_includes,
        )

    # Normalize the content and merge continuation lines
    merged_lines, inline_data_indices = _merge_source_lines(content)

    # Now parse the merged lines; the builder holds all loop state and has
    # one handler per statement type (see jclparser/_job_builder.py).
    builder = JobBuilder()
    for line, line_num in merged_lines:
        # Handle inline data continuation
        if builder.consume_inline_data(line):
            continue

        # Skip comments and empty lines (but recognise JES3 //*ROUTE XEQ
        # control statements before dropping the comment).
        if not line.strip() or line.strip().startswith("//*"):
            builder.handle_comment_line(line, line_num)
            continue

        # Skip lines marked as inline data (line_num is 1-indexed, markers use 0-indexed)
        if (line_num - 1) in inline_data_indices:
            continue

        # Parse the statement
        stmt = parse_statement(line, line_num)
        if not stmt:
            continue

        # Process the statement (dispatches on stmt.type)
        builder.handle_statement(stmt, line_num)

    job = builder.finish()

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

    # Record any INCLUDE members that were expanded during pre-processing.
    # Members resolved before the main parse loop never reach the INCLUDE
    # handler in the loop, so we add them here to keep job.includes complete.
    for _member in _expanded_includes:
        if _member not in job.includes:
            job.includes.append(_member)

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

    # Validate the parsed job if in strict mode.  Only ERROR-severity findings
    # are fatal — WARNING/INFO findings (e.g. unresolved OUTPUT back-references,
    # forward dataset references) are advisory and must not break strict parsing.
    if strict_mode:
        logger.debug("running strict-mode validation for job %s", job.name)
        validation_errors = job.validate()
        fatal = [
            err for err in validation_errors if err.severity == ErrorSeverity.ERROR
        ]
        if fatal:
            error_msg = "; ".join([err.message for err in fatal])
            raise JCLValidationError(f"Job validation failed: {error_msg}")

    # Optional: auto-run SQL detection when requested via ParserConfig
    if config is not None and getattr(config, "detect_sql", False):
        from .sql_detector import detect_sql_in_job

        for result in detect_sql_in_job(job):
            if result.step_name:
                job.sql_detections[result.step_name] = result

    if logger.isEnabledFor(logging.INFO):
        from .model import iter_execution_steps

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

    return job


@overload
def parse_jcl(
    source: str | Path | IO,
    strict_mode: bool = ...,
    config: ParserConfig | None = ...,
    proc_base_path: str | Path | None = ...,
    enable_external_procs: bool = ...,
    include_loader: "IncludeMemberLoader | None" = ...,
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
    include_loader: "IncludeMemberLoader | None" = ...,
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
    include_loader: "IncludeMemberLoader | None" = None,
    enable_profiling: bool = False,
    top_n: int = 50,
    prof_output: str | None = None,
) -> "Job | tuple[Job, ProfilingResult]":
    """
    Parse JCL script from various input sources into structured Job object.

    Args:
        source: JCL script content as string, file path, or file-like object
        strict_mode: Enable strict parsing mode
        config: Optional parser configuration
        proc_base_path: Base directory for external PROC libraries
                       (defaults to JCL_PROCLIB_PATH env var or current directory)
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


def validate_jcl(source: str | Path | IO, level: str = "basic") -> list[ParseError]:
    """
    Validate JCL syntax and structure without full parsing.

    Args:
        source: JCL script to validate
        level: Validation level (syntax_only, structure, semantic)

    Returns:
        List of ParseError objects (empty if valid)
    """
    errors = []

    # First try normal parsing to catch basic structure issues
    try:
        job = parse_jcl(source, strict_mode=True)

        # Additional validation based on level
        if level in ("structure", "semantic"):
            validation_errors = job.validate()
            for err in validation_errors:
                errors.append(
                    ParseError(
                        error_type=err.error_type,
                        message=err.message,
                        line_number=0,
                        severity=ErrorSeverity.ERROR,
                    )
                )

        # Plugin-based validation
        if level == "semantic":
            registry = get_plugin_registry()
            for validator in registry.get_validators():
                validation_errors = validator.validate_job(job)
                for err in validation_errors:
                    errors.append(
                        ParseError(
                            error_type=err.error_type,
                            message=err.message,
                            line_number=0,
                            severity=ErrorSeverity.ERROR,
                        )
                    )

        return errors

    except (JCLSyntaxError, JCLValidationError, JCLStructureError):
        # If parsing failed, do line-by-line validation to collect multiple errors
        pass

    # Line-by-line validation to catch multiple syntax errors
    # Parse content from source
    try:
        content = read_source(source)
    except FileNotFoundError as exc:
        errors.append(
            ParseError(
                error_type=ErrorType.SYNTAX_ERROR,
                message=str(exc),
                line_number=0,
                severity=ErrorSeverity.ERROR,
            )
        )
        return errors

    # Merge continuation lines so multi-line statements are validated as a unit
    raw_lines = [normalize_jcl_line(line) for line in content.splitlines()]
    handler = ContinuationLineHandler()
    merged_pairs = handler.merge_continuation_lines(raw_lines)
    has_job = False
    in_proc = False
    has_exec = False
    has_dd = False
    current_step = None

    for line, line_num in merged_pairs:
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("//*"):
            continue

        # Validate each statement individually
        try:
            stmt = parse_statement(line, line_num)
            if stmt:
                # Basic structure validation
                if stmt.type == "JOB":
                    if has_job:
                        errors.append(
                            ParseError(
                                error_type=ErrorType.SYNTAX_ERROR,
                                message="Multiple JOB statements found",
                                line_number=line_num,
                                severity=ErrorSeverity.ERROR,
                            )
                        )
                    has_job = True

                elif stmt.type == "PROC":
                    in_proc = True

                elif stmt.type == "PEND":
                    in_proc = False

                elif stmt.type == "EXEC":
                    if not has_job and not in_proc:
                        errors.append(
                            ParseError(
                                error_type=ErrorType.SYNTAX_ERROR,
                                message="EXEC statement before JOB statement",
                                line_number=line_num,
                                severity=ErrorSeverity.ERROR,
                            )
                        )

                    # Check for missing program or procedure.
                    # This fallback path is only reached when parse_jcl raised
                    # (e.g., undefined PROC), so we intentionally do NOT accept
                    # bare "PROC=name" here — the reference is known to be
                    # unresolvable, and we want at least one error in the output.
                    has_pgm = "PGM" in stmt.parameters
                    has_positional = any(is_positional_key(k) for k in stmt.parameters)
                    if not has_pgm and not has_positional:
                        errors.append(
                            ParseError(
                                error_type=ErrorType.SYNTAX_ERROR,
                                message="EXEC statement missing program or procedure",
                                line_number=line_num,
                                severity=ErrorSeverity.ERROR,
                            )
                        )
                    has_exec = True
                    current_step = stmt

                elif stmt.type == "DD":
                    has_dd = True
                    if current_step is None:
                        # DD before EXEC is allowed (e.g. JOBLIB before the
                        # first step) as long as some EXEC exists later in
                        # the job; checked for the whole job after the loop.
                        pass

        except JCLSyntaxError as e:
            errors.append(
                ParseError(
                    error_type=ErrorType.SYNTAX_ERROR,
                    message=e.message,
                    line_number=e.line_number or line_num,
                    context=e.context,
                    severity=ErrorSeverity.ERROR,
                )
            )
        except JCLValidationError as e:
            errors.append(
                ParseError(
                    error_type=ErrorType.VALIDATION_ERROR,
                    message=e.message,
                    line_number=e.line_number or line_num,
                    context=e.context,
                    severity=ErrorSeverity.ERROR,
                )
            )

    # Mirrors the strict-mode structural check in _parse_jcl_core: a DD
    # statement with no EXEC anywhere in the job is a structural error, not
    # just a syntax quirk to ignore.
    if has_job and has_dd and not has_exec:
        errors.append(
            ParseError(
                error_type=ErrorType.STRUCTURE_ERROR,
                message="DD statement found before any EXEC step. "
                "Each DD must belong to a step.",
                line_number=0,
                severity=ErrorSeverity.ERROR,
            )
        )

    return errors
