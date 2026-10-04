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
from .continuation_handler import ContinuationLineHandler
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
    instream_delimiter,
    is_positional_key,
    normalize_jcl_line,
    read_source,
)

if TYPE_CHECKING:
    from .include_loader import IncludeMemberLoader

logger = logging.getLogger(__name__)


def _merge_source_lines(
    content: str,
) -> tuple[list[tuple[str, int]], set[int], set[int], list[str]]:
    """Normalize, mark in-stream data, and merge continuation lines.

    Returns ``(merged_lines, inline_data_indices, control_data_indices,
    source_warnings)`` where *merged_lines* is a list of ``(line, 1-based line
    number)`` pairs ready for the parse loop, *inline_data_indices* is the set
    of 0-based original indices that belong to in-stream (``DD *`` / ``DD
    DATA``) data blocks, *control_data_indices* is the set of 0-based indices
    holding the program control records of a ``CNTL``/``ENDCNTL`` block — both
    of which must never be parsed as JCL statements — and *comment_warnings*
    reports comment fields that were stripped off statements but still looked
    like operands (truncated or garbled records).
    """
    raw_lines = content.splitlines()
    lines = [normalize_jcl_line(line) for line in raw_lines]

    # Single pass: separate inline data lines from regular lines.
    # Simultaneously records which original indices are inline data
    # and builds the non-inline list for continuation merging.
    inline_data_indices: set[int] = set()
    control_data_indices: set[int] = set()
    non_inline_lines: list[str] = []
    non_inline_orig_indices: list[int] = []  # parallel to non_inline_lines
    in_inline_data = False
    in_cntl_block = False
    cntl_start_line = 0
    source_warnings: list[str] = []
    delimiter = "/*"
    # When the current in-stream dataset was opened with ``DD *`` (and *no*
    # custom ``DLM=``), z/OS terminates the data at the next record beginning
    # with ``//`` as well as at ``/*``.  ``DD DATA`` deliberately does not do
    # this so that records containing ``//`` can be supplied as data; for
    # ``DD DATA`` (or any dataset with an explicit ``DLM=``) only the delimiter
    # ends the data.
    terminates_on_slash = False
    # Once a step exists, a record that is not JCL (no ``//`` or ``/*``)
    # starts in-stream data with no DD statement, which JES reads as an
    # implicit ``//SYSIN DD *`` (see JobBuilder.start_implicit_sysin).
    seen_exec = False
    # Operands of a DD statement whose continuation records are still coming.
    pending_dd: str | None = None

    for i, line in enumerate(lines):
        if in_inline_data:
            # The delimiter only counts in columns 1-2: an indented ``/*`` is
            # data (a C, REXX or SQL comment in SYSIN).
            if line.startswith(delimiter):
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
        if in_cntl_block:
            # Records between CNTL and ENDCNTL are program control statements
            # handed to the program, not JCL: they must not be merged as
            # continuations nor parsed.  ENDCNTL closes the block; so does any
            # record that is unmistakably a JCL statement, so an unterminated
            # CNTL cannot swallow the rest of the job (that gets a warning).
            cntl_operation = statement_operation(line)
            if cntl_operation == "ENDCNTL":
                in_cntl_block = False
            elif cntl_operation in _STATEMENT_TYPES:
                in_cntl_block = False
                source_warnings.append(
                    f"Line {cntl_start_line}: CNTL block has no matching ENDCNTL; "
                    f"ended at the {cntl_operation} statement on line {i + 1}"
                )
            else:
                control_data_indices.add(i)
                continue
        if (
            not line.startswith(("//", "/*"))
            and seen_exec
            and line.strip()
            and not _expects_continuation(lines, i)
        ):
            inline_data_indices.add(i)
            in_inline_data = True
            delimiter = "/*"
            terminates_on_slash = True
            continue
        if (
            line.strip()
            and line.startswith("//")
            and not line.strip().startswith("//*")
        ):
            upper_line = line.upper()
            if (
                not seen_exec
                and "EXEC" in upper_line
                and statement_operation(line) == "EXEC"
            ):
                seen_exec = True
            if "CNTL" in upper_line and statement_operation(line) == "CNTL":
                in_cntl_block = True
                cntl_start_line = i + 1
            # In-stream data starts at ``DD *`` / ``DD DATA`` / any DD with an
            # explicit DLM=.  The operand field is located by tokenizing the
            # record — the same way the JobBuilder reads it — so that spacing
            # ("//SYSIN    DD    *") can never make the two disagree and leave
            # data records to be parsed as JCL.
            # A DD statement continued onto further records (``DD DATA,`` /
            # ``//   DLM=$$``) is only judged once its last record is read:
            # those records are JCL, and DLM= may sit on any of them.
            dd_operands: str | None = None
            if pending_dd is not None:
                if statement_operation(line) in _STATEMENT_TYPES:
                    pending_dd = None  # continuation never came
                else:
                    cont = split_comment_field(line, "DD")[0][2:].strip()
                    pending_dd += cont
                    if not cont.endswith(","):
                        dd_operands, pending_dd = pending_dd, None
            elif "DD" in upper_line:
                dd_field = _operand_field(line)
                if dd_field is not None and dd_field[1] == "DD":
                    statement = split_comment_field(line, "DD")[0]
                    operands = statement[dd_field[0] :].strip()
                    if operands.endswith(","):
                        pending_dd = operands
                    else:
                        dd_operands = operands
            if dd_operands is not None:
                instream = _instream_delimiter(dd_operands)
                if instream is not None:
                    delimiter, terminates_on_slash = instream
                    in_inline_data = True
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

    # A comment (or blank) record met inside a continued statement is its own
    # entry, but it must come *before* that merged statement: a DD that opens
    # in-stream data (``DD *,`` / ``//* c`` / ``//  DLM=$$``) would otherwise
    # read the comment as its first data record, or end its data at it
    # (issue #58).  ``stmt_pos`` is the entry of the last statement still
    # open to continuation records.
    merged_lines: list[tuple[str, int]] = []
    stmt_pos: int | None = None
    for i, line in enumerate(lines):
        if i in inline_data_indices or i in control_data_indices:
            merged_lines.append((line, i + 1))
            stmt_pos = None
        elif i in merged_start:
            merged_lines.append((merged_start[i], i + 1))
            if line.strip() and not line.startswith("//*"):
                stmt_pos = len(merged_lines) - 1
        elif stmt_pos is not None and stmt_pos < len(merged_lines) - 1:
            # A continuation record folded into the statement at stmt_pos,
            # with comment records in between: move the statement after them.
            merged_lines.append(merged_lines.pop(stmt_pos))
            stmt_pos = len(merged_lines) - 1

    # Map the handler's suspect comment fields back to original line numbers.
    source_warnings.extend(
        f"Line {non_inline_orig_indices[ni_line_num - 1] + 1}: text after the "
        f"operand field ignored as a comment, but it looks like operands: "
        f"{comment!r}"
        for ni_line_num, comment in handler.suspect_comments
    )

    return merged_lines, inline_data_indices, control_data_indices, source_warnings


def _instream_delimiter(operands: str) -> tuple[str, bool] | None:
    """Return ``(delimiter, ends_at_slash)`` if a DD's operands open in-stream data.

    *operands* is the DD's whole operand field (continuations joined, comment
    field removed). They are tokenized exactly as the JobBuilder tokenizes
    them and judged by the same :func:`~jclparser.utils.instream_delimiter`
    rule, so the pre-scan can never mark records as data that the builder
    then has no DD to attach to (the old substring test did, for any DD
    mentioning ``DLM=``, silently dropping the rest of the job).
    """
    try:
        parameters = _parse_parameters(operands)
    except JCLSyntaxError:
        # Unbalanced operands: the statement parser reports them; no data.
        return None
    instream = instream_delimiter(parameters)
    if instream is None:
        return None
    delimiter, ends_at_slash = instream
    if not isinstance(delimiter, str):
        # A malformed DLM= is rejected by the JobBuilder; keep the default
        # delimiter here so the pre-scan stays in step until then.
        delimiter = "/*"
    return delimiter, ends_at_slash


def _expects_continuation(lines: list[str], index: int) -> bool:
    """Return True if the JCL record before *index* awaits a continuation.

    A statement whose operand field ends in a comma expects a ``//``
    continuation record; a non-JCL record there is a broken continuation,
    not in-stream data, and is left for parse_statement() to reject.
    Only called for the rare non-JCL record, so the backward scan is cheap.
    """
    prev = index - 1
    while prev >= 0 and (not lines[prev].strip() or lines[prev].startswith("//*")):
        prev -= 1
    if prev < 0 or not lines[prev].startswith("//"):
        return False
    # The operation of the statement that record belongs to decides where
    # its comment field starts.
    group_operation = ""
    for k in range(prev, -1, -1):
        operation = statement_operation(lines[k])
        if operation in _STATEMENT_TYPES:
            group_operation = operation
            break
    statement_part = split_comment_field(lines[prev], group_operation)[0]
    return statement_part.rstrip().endswith(",")


def _parse_jcl_core(
    source: str | Path | IO,
    strict_mode: bool = False,
    config: ParserConfig | None = None,
    proc_base_path: str | Path | None = None,
    enable_external_procs: bool = True,
    include_loader: IncludeMemberLoader | None = None,
) -> Job:
    """Core parsing implementation. See parse_jcl() for full documentation."""
    # The keyword and the config are two ways to ask for strict parsing;
    # either one turns it on.
    strict_mode = strict_mode or (config is not None and config.strict_mode)
    # Handle different input source types (FileNotFoundError propagates)
    content = read_source(source)

    # Expand INCLUDE MEMBER= statements before the main parse loop so that
    # inlined content participates in continuation-line merging and everything
    # else that follows.
    _expanded_includes: list[str] = []
    if _has_include_statement(content):
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
            _collected=_expanded_includes,
        )
        logger.debug(
            "expanded %d INCLUDE member(s) before parse: %s",
            len(_expanded_includes),
            _expanded_includes,
        )

    # Normalize the content and merge continuation lines
    (
        merged_lines,
        inline_data_indices,
        control_data_indices,
        source_warnings,
    ) = _merge_source_lines(content)

    # Now parse the merged lines; the builder holds all loop state and has
    # one handler per statement type (see jclparser/_job_builder.py).
    builder = JobBuilder(dialect=config.dialect if config is not None else "standard")
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
            if not line.startswith(("//", "/*")):
                # In-stream data with no DD statement ahead of it.
                builder.start_implicit_sysin(line, line_num)
            continue

        # Program control records inside a CNTL/ENDCNTL block are kept with
        # the CNTL statement rather than parsed as JCL.
        if (line_num - 1) in control_data_indices:
            builder.handle_control_data(line)
            continue

        # Parse the statement
        stmt = parse_statement(line, line_num, config)
        if not stmt:
            continue

        # Process the statement (dispatches on stmt.type)
        builder.handle_statement(stmt, line_num)

    job = builder.finish()

    # Anything the line-classification pass discarded or repaired (a comment
    # field that looked like operands, an unterminated CNTL block) is reported
    # rather than dropped without a trace.
    job.warnings.extend(source_warnings)

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
    errors = []

    # First try normal parsing to catch basic structure issues
    try:
        job = parse_jcl(source, strict_mode=True, config=config)

        # Additional validation based on level
        if effective_level in (ValidationLevel.STRUCTURE, ValidationLevel.SEMANTIC):
            validation_errors = job.validate()
            for err in validation_errors:
                errors.append(
                    ParseError(
                        error_type=err.error_type,
                        message=err.message,
                        line_number=err.line_number or 0,
                        severity=err.severity,
                    )
                )

        # Plugin-based validation (opt-in: only the plugins the config enables)
        if effective_level == ValidationLevel.SEMANTIC and config is not None:
            registry = get_plugin_registry()
            flat_steps = list(iter_execution_steps(job.steps))
            validators = [
                v for v in registry.get_validators() if config.is_plugin_enabled(v)
            ]
            for validator in validators:
                # A ValidationPlugin has three hooks; run each of them, so a
                # rule written against validate_step / validate_dd is not
                # silently skipped.
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
                            severity=getattr(err, "severity", None)
                            or ErrorSeverity.ERROR,
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
            stmt = parse_statement(line, line_num, config)
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
