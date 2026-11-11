"""
Command-line interface for jclparser.

Usage:
    jcl-parser FILE                              Show job summary (FILE "-" is stdin)
    jcl-parser FILE steps                        List all steps
    jcl-parser FILE procs [PROCNAME]             List/detail procedures
    jcl-parser FILE procs --explode              Show procedure expansion audit
    jcl-parser FILE procs --list-available       List PROCs in --proc-path libraries
    jcl-parser FILE STEP                         Show step details
    jcl-parser FILE STEP.DDNAME                  Show a specific DD statement
    jcl-parser FILE DDNAME                       Show all DDs with that name
    jcl-parser FILE --json                       Full parse result as JSON
    jcl-parser FILE --validate                   Validate the JCL
    jcl-parser FILE detect                       Detect file type (JCL/PROC/UNKNOWN)
    jcl-parser FILE metrics                      Structural metrics for the job
    jcl-parser FILE lint [--sarif]               Run lint rules against the job
    jcl-parser --lint-list                       List all available lint rule codes
    jcl-parser --json-schema                     JSON Schema of the --json output
    jcl-parser FILE datasets                     Dataset lifecycle analysis
    jcl-parser FILE sql                          SQL/DB2 detection
    jcl-parser FILE analyze [STEPNAME]           Program profile analysis
    jcl-parser FILE paths                        RC feasibility path analysis
    jcl-parser DIR [lineage] [dot|mermaid]       Cross-job dataset lineage
    jcl-parser DIR lint [--sarif]                Lint every job of a directory
    jcl-parser DIR --validate [--sarif]          Validate every file of a directory

Lint reads the nearest pyproject.toml's [tool.jcl-parser.lint] table (or
--config) and honours ``//* jcl-lint: disable=CODE`` comments; the separate
``jcl-lint PATH...`` command lints several files at once.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .checks import (
    FileReport,
    as_finding,
    exit_code,
    format_reports,
    lint_paths,
    reports_to_dict,
    reports_to_sarif,
    resolve_lint_config,
    validate_paths,
)
from .dataset_lifecycle import analyze_dataset_lifecycle, validate_dataset_lifecycle
from .errors import (
    CircularProcedureError,
    ErrorSeverity,
    ExplosionDepthError,
    JCLStructureError,
    JCLSyntaxError,
    JCLValidationError,
    ParseError,
    ProcedureNotFoundError,
    UndefinedSymbolError,
    ValidationError,
)
from .jcl_file_type import detect_file_type
from .lineage import JobStream, LineageReport, load_job_stream
from .lint import LintConfig, LintConfigError, all_rules, lint_job, to_sarif
from .lint.config import parse_severity
from .metrics import compute_metrics
from .model import (
    DDStatement,
    Job,
    Procedure,
    Step,
    iter_execution_steps,
)
from .parser import parse_jcl, validate_jcl
from .proc_loader import JCLLIBProcedureLoader
from .profiling import ProfilingResult
from .program_profiles import analyze_job, analyze_step
from .rc_analysis import FeasibilityReport, compute_feasible_paths
from .serialization import (
    JOB_JSON_SCHEMA,
    dd_to_dict,
    job_to_dict,
    procedure_to_dict,
    step_or_conditional_to_dict,
    step_to_dict,
)
from .sql_detector import detect_sql_in_job
from .utils import is_positional_key, read_source, split_source_lines


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code.

    An operating-system error (``FILE`` is a directory, unreadable, ...) is
    reported as ``Error: ...`` on stderr with exit code 1, not a traceback.
    """
    try:
        return _main(argv)
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _main(argv: list[str] | None = None) -> int:
    """:func:`main` without the OS-error guard."""
    # --lint-list / --json-schema don't require FILE — handle before argparse
    _argv = argv if argv is not None else sys.argv[1:]
    if "--lint-list" in _argv:
        return _cmd_lint_list()
    if "--json-schema" in _argv:
        print(json.dumps(JOB_JSON_SCHEMA, indent=2))
        return 0

    # Intermixed: flags may sit between FILE and the query tokens
    # ("FILE --explode steps"); plain parse_args() hands the whole positional
    # run to FILE/query before the flag and then rejects "steps".
    arg_parser = _build_arg_parser()
    if not _argv:
        # A bare `jcl-parser` used to print only "the following arguments
        # are required: FILE"; show the queries and examples instead.
        arg_parser.print_help()
        return 2
    args = arg_parser.parse_intermixed_args(argv)
    if args.profile_output and not args.profile:
        arg_parser.error("--profile-output requires --profile")  # exits 2
    _apply_format(args)

    source: Path | str
    if args.file == "-":
        # "-" reads the JCL from stdin (issue #132).
        source = _read_stdin()
    else:
        source = Path(args.file)
        if not source.exists():
            print(f"Error: file not found: {source}", file=sys.stderr)
            return 1
        if source.is_dir():
            return _cmd_directory(source, args)

    if args.validate:
        return _cmd_validate(
            source,
            json_output=args.json_output,
            proc_path=args.proc_path,
            sarif=args.sarif,
            fail_on=_validate_fail_on(args),
        )

    # --- detect mode (no parse needed) ---
    if (
        args.query
        and args.query[0].lower() == "detect"
        and not _names_job_item(source, args, args.query[0])
    ):
        return _cmd_detect(source, args.json_output)

    loaded = _load_job(source, args)
    if loaded is None:
        return 1
    job, prof = loaded
    if prof is None:
        return _run_query(job, args, source)
    return _run_query_with_profile(job, args, prof, source)


def _apply_format(args: argparse.Namespace) -> None:
    """``--format json|sarif`` sets the older ``--json`` / ``--sarif`` flags."""
    if args.format == "json":
        args.json_output = True
    elif args.format == "sarif":
        args.sarif = True


def _read_stdin() -> str:
    """The JCL piped on stdin, decoded like a file (``FILE`` is ``-``)."""
    return read_source(getattr(sys.stdin, "buffer", sys.stdin))


def _names_job_item(source: Path | str, args: argparse.Namespace, token: str) -> bool:
    """True if *token* (a pre-parse query word such as ``DETECT``) names a step
    or DD of the job, so it is looked up rather than run (issue #133).

    Only an all-uppercase token can name one; the file is parsed quietly to
    find out, and a file that does not parse names nothing.
    """
    if token != token.upper():
        return False
    try:
        job = _parse_file(source, args.proc_path)
    except (JCLSyntaxError, JCLValidationError, JCLStructureError):
        return False
    return _is_step_or_dd_name(job, token)


def _is_step_or_dd_name(job: Job, token: str) -> bool:
    """True if *token*, exactly as typed, is the name of a step or DD in *job*.

    JCL names are uppercase, so ``SQL`` can name a step while ``sql`` is
    always the query word; an exact-case name wins over the word (#133).
    """
    if job.get_step(token) is not None:
        return True
    return any(
        dd.name == token
        for step in iter_execution_steps(job.steps)
        for dd in step.dd_statements
    )


#: The query words ``jcl-parser FILE <word>`` understands, for typo hints.
_QUERY_WORDS = (
    "steps",
    "procs",
    "detect",
    "metrics",
    "lint",
    "datasets",
    "sql",
    "analyze",
    "paths",
    "lineage",
)

_HELP_EPILOG = """\
queries (the words after FILE):
  (none)              job summary; with --json the whole parse as JSON
  steps               every step, the program or PROC it runs, its DDs
  procs [PROCNAME]    inline/external PROCs; --explode shows the expansion
  STEP                one step in detail        e.g. STEP010
  STEP.DDNAME         one DD statement          e.g. STEP010.SYSIN
  DDNAME              that DD in every step     e.g. SYSOUT
  detect              is the file a JOB, a PROC, or neither
  metrics             step, DD, PROC and dataset counts, complexity
  lint                lint rules (--lint-list lists them; --sarif for CI)
  datasets            dataset lifecycle: created, read, deleted, passed
  sql                 DB2 / SQL usage by step
  analyze [STEP]      what each utility step (SORT, IDCAMS, ...) does
  paths               which steps can run, from the COND / IF logic

  FILE may be a directory: 'lineage [dot|mermaid]' (the default) maps
  datasets across its jobs, 'lint' and --validate check every file
  (--glob picks them). FILE '-' reads the JCL from stdin.

examples:
  jcl-parser PAYROLL.jcl
  jcl-parser PAYROLL.jcl steps --explode --proc-path ./proclib
  jcl-parser PAYROLL.jcl STEP010.SYSIN
  jcl-parser PAYROLL.jcl lint --fail-on warning
  jcl-parser PAYROLL.jcl --validate --format json
  jcl-parser jobs/ lineage mermaid > lineage.mmd
  jcl-lint jobs/*.jcl --format sarif -o jcl.sarif   (several files, for CI)

exit codes:
  0  success
  1  the file could not be read or parsed, a name was not found, or a check
     reported something (--validate errors -- or findings at --fail-on or
     above when it is given --, lint findings at --fail-on or above,
     dataset / SQL findings)
  2  the command line was rejected

defaults:
  lint reads [tool.jcl-parser.lint] from the nearest pyproject.toml (or
  --config). External PROCs are loaded only with --proc-path, except by
  --validate, which falls back to the JCL_PROCLIB_PATH variable.
"""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jcl-parser",
        usage="jcl-parser FILE [QUERY ...] [options]",
        description="Parse and inspect IBM z/OS JCL: jobs, steps, DDs and PROCs.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "file",
        metavar="FILE",
        help="JCL file to parse, or a directory of jobs for 'lineage'",
    )
    parser.add_argument(
        "query",
        nargs="*",
        default=[],
        metavar="QUERY",
        help="What to show (see 'queries' below); none prints the job summary",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output as JSON"
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "sarif"),
        default=None,
        help=(
            "Output format: text (default), json (same as --json) or sarif "
            "(same as --sarif; lint and --validate only). The spelling "
            "cobol-parser and jcl-lint use"
        ),
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate the JCL and report errors"
    )
    parser.add_argument(
        "--explode",
        action="store_true",
        help="Expand procedure calls before displaying",
    )
    parser.add_argument(
        "--proc-path",
        default=None,
        help="Base path for external PROC libraries",
    )
    parser.add_argument(
        "--list-available",
        action="store_true",
        help="List PROCs available in --proc-path libraries (use with 'procs')",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--lint-list",
        action="store_true",
        help="List all available lint rule codes and descriptions, then exit",
    )
    parser.add_argument(
        "--json-schema",
        action="store_true",
        help="Print the JSON Schema of the --json job document, then exit",
    )
    parser.add_argument(
        "--glob",
        default="*",
        metavar="PATTERN",
        help="Files of a directory FILE to read (default '*'; '**/*.jcl' recurses)",
    )
    parser.add_argument(
        "--sarif",
        action="store_true",
        help="Output lint findings or --validate errors as SARIF 2.1.0",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="TOML",
        help="Lint configuration (default: nearest pyproject.toml)",
    )
    parser.add_argument(
        "--fail-on",
        choices=("info", "warning", "error"),
        default=None,
        help=(
            "Lowest severity that exits 1: for lint the default is the config, "
            "else info; for --validate it is error"
        ),
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Profile the parse and include timing/memory metrics in output",
    )
    parser.add_argument(
        "--profile-top-n",
        type=int,
        default=20,
        metavar="N",
        help="Number of top functions to include in profiling output (default: 20)",
    )
    parser.add_argument(
        "--profile-output",
        default=None,
        metavar="PATH",
        help="Write cProfile binary to PATH (.prof file)",
    )
    return parser


def _load_job(
    path: Path | str, args: argparse.Namespace
) -> tuple[Job, ProfilingResult | None] | None:
    """Parse (and with ``--explode`` explode) *path*; ``None`` after printing
    the error when that fails."""
    prof = None
    try:
        if args.profile:
            from .profiling import ProfilerContext

            ctx = ProfilerContext(
                top_n=args.profile_top_n,
                prof_output=args.profile_output,
            )
            with ctx:
                job = _parse_file(path, args.proc_path)
            assert ctx.result is not None
            prof = ctx.result
        else:
            job = _parse_file(path, args.proc_path)
    except (JCLSyntaxError, JCLValidationError, JCLStructureError) as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        return None

    if args.explode:
        try:
            job = job.explode()
        except (
            ProcedureNotFoundError,
            CircularProcedureError,
            ExplosionDepthError,
            UndefinedSymbolError,
        ) as exc:
            print(f"Explosion error: {exc}", file=sys.stderr)
            return None
    return job, prof


def _parse_file(path: Path | str, proc_path: str | None) -> Job:
    return parse_jcl(
        path,
        proc_base_path=proc_path,
        enable_external_procs=proc_path is not None,
    )


def _run_query_with_profile(
    job: Job, args: argparse.Namespace, prof: ProfilingResult, source: Path | str
) -> int:
    """:func:`_run_query`, plus the ``--profile`` metrics (issue #131).

    JSON output gains a ``profiling`` key (a JSON list is wrapped as
    ``{"result": [...], "profiling": {...}}``); text output is followed by
    a profiling block.
    """
    if not args.json_output:
        code = _run_query(job, args, source)
        _print_profiling(prof)
        return code
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = _run_query(job, args, source)
    data: Any = json.loads(buffer.getvalue()) if buffer.getvalue().strip() else {}
    if not isinstance(data, dict):
        data = {"result": data}
    data["profiling"] = prof.to_dict()
    print(json.dumps(data, indent=2))
    return code


def _print_profiling(prof: ProfilingResult) -> None:
    print()
    print("Profiling:")
    print(f"  Wall clock:  {prof.wall_clock_s:.4f} s")
    if prof.cpu_user_s is not None and prof.cpu_system_s is not None:
        print(
            f"  CPU:         {prof.cpu_user_s:.4f} s user, {prof.cpu_system_s:.4f} s system"
        )
    print(f"  Peak memory: {prof.peak_memory_mb:.2f} MB")
    if prof.prof_file:
        print(f"  cProfile:    {prof.prof_file}")
    if prof.top_functions:
        print("  Top functions (cumulative time):")
        for func in prof.top_functions:
            print(f"    {func.cumul_time_s:9.4f} s  {func.calls:7d}  {func.function}")


def _run_query(job: Job, args: argparse.Namespace, source: Path | str) -> int:
    """Answer the query tokens of *args* about *job*, parsed from *source*
    (a path, or the JCL text read from stdin)."""
    tokens = args.query  # list[str]
    json_out = args.json_output
    if not tokens:
        if json_out:
            print(json.dumps(job_to_dict(job), indent=2))
        else:
            _print_summary(job)
        return 0

    query = tokens[0]
    if _is_step_or_dd_name(job, query):
        # An exact-case step or DD name wins over a query word (#133).
        return _cmd_step_or_dd(job, query, json_out)
    command = _JOB_QUERIES.get(query.lower())
    if command is not None:
        return command(job, json_out)

    if query.lower() == "lint":
        return _cmd_lint(job, args, source)

    if query.lower() == "analyze":
        step_filter = tokens[1].upper() if len(tokens) > 1 else None
        return _cmd_analyze(job, json_out, step_filter=step_filter)

    if query.lower() == "steps":
        if json_out:
            steps = [step_or_conditional_to_dict(s) for s in job.steps]
            print(json.dumps(steps, indent=2))
        else:
            _print_steps(job)
        return 0

    if query.lower() == "procs":
        subquery = tokens[1].upper() if len(tokens) > 1 else None
        return _cmd_procs(job, args, subquery)

    return _cmd_step_or_dd(job, query, json_out)


def _cmd_procs(job: Job, args: argparse.Namespace, subquery: str | None) -> int:
    json_out = args.json_output
    # jcl-parser FILE procs PROCNAME  — single proc detail
    if subquery:
        proc = job.get_procedure(subquery)
        if proc is None:
            print(f"Procedure not found: {subquery}", file=sys.stderr)
            return 1
        if json_out:
            print(json.dumps(procedure_to_dict(proc), indent=2))
        else:
            _print_proc_detail(proc)
        return 0
    # jcl-parser FILE procs --list-available
    if args.list_available:
        return _cmd_list_available(args.proc_path, job, json_out)
    # jcl-parser FILE procs [--explode]
    if args.explode:
        if json_out:
            print(json.dumps(_explosion_audit_to_dict(job), indent=2))
        else:
            _print_explosion_audit(job)
    elif json_out:
        print(json.dumps(_procs_to_dict(job), indent=2))
    else:
        _print_procs(job, proc_path=args.proc_path)
    return 0


def _cmd_step_or_dd(job: Job, query: str, json_out: bool) -> int:
    # Try as step name first -- an exploded step name ("CALLER.PROCSTEP")
    # contains a dot itself, so this must come before the STEP.DDNAME split.
    step = job.get_step(query.upper())
    if step is None and "." in query:
        # STEP.DDNAME -- split on the *last* dot: a DD name never contains a
        # dot, but an exploded step name does ("CALLER.PROCSTEP.DDNAME").
        step_name, dd_name = query.rsplit(".", 1)
        return _print_step_dd(job, step_name, dd_name, json_out)
    if step is not None:
        if json_out:
            print(json.dumps(step_to_dict(step), indent=2))
        else:
            _print_step_detail(step)
        return 0

    # Fall back to DD name across all steps
    status = _print_dd_across_steps(job, query.upper(), json_out)
    if status != 0:
        hint = _not_found_hint(job, query)
        if hint:
            print(hint, file=sys.stderr)
    return status


def _not_found_hint(job: Job, query: str) -> str | None:
    """A "did you mean" line for a query that named no step or DD.

    A mistyped query word (``stpes``) used to read only as "No step or DD
    named 'STPES' found", which sends a new user looking for a step.
    """
    import difflib

    words = difflib.get_close_matches(query.lower(), _QUERY_WORDS, n=1, cutoff=0.6)
    names = sorted(
        {s.name for s in iter_execution_steps(job.steps) if s.name}
        | {
            dd.name
            for s in iter_execution_steps(job.steps)
            for dd in s.dd_statements
            if dd.name
        }
    )
    close = difflib.get_close_matches(query.upper(), names, n=3, cutoff=0.6)
    # JCL names are uppercase: an uppercase query is a misspelt name first,
    # a lowercase one a misspelt query word first.
    name_hint = "Did you mean: " + ", ".join(close) + "?" if close else None
    word_hint = (
        f"Did you mean the query '{words[0]}'? (see 'jcl-parser --help')"
        if words
        else None
    )
    if query == query.upper():
        return name_hint or word_hint
    return word_hint or name_hint


def _cmd_directory(path: Path, args: argparse.Namespace) -> int:
    """``jcl-parser DIR [lineage [dot|mermaid]]``: cross-job dataset lineage;
    ``DIR lint`` and ``DIR --validate`` check every file."""
    tokens = [t.lower() for t in args.query]
    if args.validate and not tokens:
        reports = validate_paths(
            [path], pattern=args.glob, proc_base_path=args.proc_path
        )
        if not reports:
            print(f"Error: no files matching {args.glob!r} in {path}", file=sys.stderr)
            return 1
        _print_reports(reports, args, "OK - no errors found.")
        return exit_code(reports, _validate_fail_on(args))
    if tokens == ["lint"] and not args.validate:
        return _cmd_lint_directory(path, args)
    if args.validate or (tokens and tokens[0] != "lineage"):
        print(
            f"Error: {path} is a directory; only 'lineage', 'lint' and "
            "--validate apply to one",
            file=sys.stderr,
        )
        return 1
    fmt = tokens[1] if len(tokens) > 1 else "text"
    if fmt not in ("text", "dot", "mermaid"):
        print(f"Error: unknown lineage format: {fmt}", file=sys.stderr)
        return 1
    stream = load_job_stream(path, args.glob, proc_base_path=args.proc_path)
    if not stream.jobs:
        print(f"Error: no JCL jobs found in {path}", file=sys.stderr)
        for job_id, message in stream.errors.items():
            print(f"  {job_id}: {message}", file=sys.stderr)
        return 1
    report = stream.lineage()
    if fmt == "dot":
        print(report.to_dot(), end="")
    elif fmt == "mermaid":
        print(report.to_mermaid(), end="")
    elif args.json_output:
        print(json.dumps({**stream.to_dict(), **report.to_dict()}, indent=2))
    else:
        _print_lineage(stream, report)
    return 0


def _cmd_lint_directory(path: Path, args: argparse.Namespace) -> int:
    config = _lint_config(args, path)
    if config is None:
        return 2
    reports = lint_paths(
        [path],
        pattern=args.glob,
        config=config,
        explode=args.explode,
        proc_base_path=args.proc_path,
    )
    if not reports:
        print(f"Error: no JCL jobs found in {path}", file=sys.stderr)
        return 1
    _print_reports(reports, args, "OK - no lint findings.")
    return exit_code(reports, config.fail_on)


def _print_reports(
    reports: list[FileReport], args: argparse.Namespace, ok_message: str
) -> None:
    if args.sarif:
        print(json.dumps(reports_to_sarif(reports), indent=2))
    elif args.json_output:
        print(json.dumps(reports_to_dict(reports), indent=2))
    else:
        print(format_reports(reports, ok_message), end="")


def _lint_config(args: argparse.Namespace, start: Path | None) -> LintConfig | None:
    """The lint configuration for *args* (``--config``, else the nearest
    pyproject.toml from *start*, then ``--fail-on``); ``None`` after
    printing the error when it cannot be read."""
    try:
        config = resolve_lint_config(args.config, start)
        if args.fail_on:
            config.fail_on = parse_severity(args.fail_on, "--fail-on")
    except (LintConfigError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return None
    return config


def _print_lineage(stream: JobStream, report: LineageReport) -> None:
    print(f"Jobs: {len(stream.jobs)}  (directory {stream.root})")
    for job_id, job in stream.jobs.items():
        print(f"  {job_id}: {job.name}")
    if stream.procedures:
        print(
            f"PROC members (used to explode the jobs): {', '.join(stream.procedures)}"
        )
    for label, entries in (("Not parsed", stream.errors), ("Note", stream.warnings)):
        for job_id, message in entries.items():
            print(f"{label}: {job_id}: {message}")
    print()
    print("Run order: " + (" -> ".join(report.run_order) or "(none)"))
    if report.cycles:
        print("Not orderable (dependency cycle): " + ", ".join(report.cycles))
    print()
    print("Dependencies:")
    for dep in report.dependencies:
        print(f"  {dep.producer} -> {dep.consumer}: {', '.join(dep.datasets)}")
    if not report.dependencies:
        print("  (none)")
    if report.external_inputs:
        print()
        print("External inputs (read, written by no job):")
        for dsn in report.external_inputs:
            print(f"  {dsn}")
    if report.final_outputs:
        print()
        print("Final outputs (written, read by no job):")
        for dsn in report.final_outputs:
            print(f"  {dsn}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _validate_fail_on(args: argparse.Namespace) -> ErrorSeverity:
    """The lowest severity that fails ``--validate``: ``--fail-on``, else ERROR.

    A WARNING alone (a duplicate step name, a PROC not found in any
    library) used to exit 1 although the help promised that only errors do.
    """
    if args.fail_on:
        return parse_severity(args.fail_on, "--fail-on")
    return ErrorSeverity.ERROR


def _validate_exit(
    errors: Sequence[ParseError | ValidationError], fail_on: ErrorSeverity
) -> int:
    """1 when a finding in *errors* is at least as severe as *fail_on*."""
    return exit_code([FileReport("", [as_finding(e) for e in errors])], fail_on)


def _cmd_validate(
    path: Path | str,
    json_output: bool = False,
    proc_path: str | None = None,
    sarif: bool = False,
    fail_on: ErrorSeverity = ErrorSeverity.ERROR,
) -> int:
    # --proc-path is the base for external PROCs and INCLUDE members, as for
    # every other command; without it JCL_PROCLIB_PATH still applies (#129).
    errors = validate_jcl(path, level="structure", proc_base_path=proc_path)
    status = _validate_exit(errors, fail_on)
    if sarif:
        uri = path.as_posix() if isinstance(path, Path) else None
        findings = [as_finding(err) for err in errors]
        print(json.dumps(to_sarif(findings, artifact_uri=uri), indent=2))
        return status
    if json_output:
        items = [
            {
                "severity": (
                    getattr(err, "severity", None) and err.severity.name or "ERROR"
                ),
                "line": getattr(err, "line_number", None),
                "message": err.message,
            }
            for err in errors
        ]
        valid = not any(i["severity"] == "ERROR" for i in items)
        print(json.dumps({"valid": valid, "errors": items}, indent=2))
        return status
    if not errors:
        print("OK - no errors found.")
        return 0
    for err in errors:
        severity = getattr(err, "severity", None)
        tag = f"[{severity.name}]" if severity else "[ERROR]"
        line = getattr(err, "line_number", None)
        loc = f" line {line}" if line else ""
        print(f"{tag}{loc} {err.message}")
    return status


def _cmd_list_available(
    proc_path: str | None, job: Job, json_output: bool = False
) -> int:
    """List all PROC names available in the proc-path libraries."""
    if not proc_path:
        print("Error: --proc-path is required for --list-available", file=sys.stderr)
        return 1
    loader = JCLLIBProcedureLoader(Path(proc_path))
    available = loader.list_all_procedures()
    if json_output:
        print(json.dumps(available, indent=2))
        return 0
    if not available:
        print(f"(no PROCs found under '{proc_path}')")
        return 0
    for lib_name, procs in available.items():
        print(f"{lib_name}:")
        for name in procs:
            used = any(p.name.upper() == name for p in job.procedures)
            marker = " *" if used else ""
            print(f"  {name}{marker}")
    print()
    used_count = sum(
        1
        for lib_procs in available.values()
        for n in lib_procs
        if any(p.name.upper() == n for p in job.procedures)
    )
    if used_count:
        print("(* = referenced by this job)")
    return 0


def _cmd_detect(path: Path | str, json_output: bool = False) -> int:
    file_type = detect_file_type(path)
    name = file_type.name  # "JCL", "PROC", or "UNKNOWN"
    if json_output:
        label = str(path) if isinstance(path, Path) else "-"
        print(json.dumps({"file_type": name, "path": label}, indent=2))
    else:
        print(name)
    return 0


def _cmd_metrics(job: Job, json_output: bool = False) -> int:
    m = compute_metrics(job)
    if json_output:
        print(json.dumps(m.to_dict(), indent=2))
    else:
        _print_metrics(m)
    return 0


def _print_metrics(m) -> None:
    fields = m.to_dict()
    width = max(len(k) for k in fields)
    for k, v in fields.items():
        print(f"  {k:<{width}}  {v}")


def _cmd_lint_list() -> int:
    rules = all_rules()
    if not rules:
        print("(no lint rules registered)")
        return 0
    width = max(len(r.code) for r in rules)
    for rule in rules:
        print(f"  {rule.code:<{width}}  {rule.description}")
    return 0


def _cmd_lint(job: Job, args: argparse.Namespace, source: Path | str) -> int:
    """``FILE lint``: exit 1 if a finding reaches the configured ``fail-on``
    severity (by default any finding does); 2 if the config is unusable."""
    path = source if isinstance(source, Path) else None
    config = _lint_config(args, path)
    if config is None:
        return 2
    text = source if isinstance(source, str) else read_source(source)
    findings = lint_job(job, config, source=text)
    failed = any(config.fails(f.severity) for f in findings)
    if args.sarif:
        uri = path.as_posix() if path is not None else None
        print(json.dumps(to_sarif(findings, artifact_uri=uri), indent=2))
    elif args.json_output:
        items = [
            {
                "code": getattr(e, "error_code", None) or "",
                "severity": e.severity.name if e.severity else "WARNING",
                "line": e.line_number,
                "message": e.message,
            }
            for e in findings
        ]
        print(json.dumps({"findings": items, "count": len(items)}, indent=2))
    else:
        _print_lint_findings(findings)
    return 1 if failed else 0


def _print_lint_findings(findings: list) -> None:
    if not findings:
        print("OK - no lint findings.")
        return
    for e in findings:
        code = getattr(e, "error_code", None) or "LINT"
        line = e.line_number
        loc = f" line {line:>4}" if line else "       "
        print(f"[{code}]{loc}: {e.message}")


def _cmd_datasets(job: Job, json_output: bool = False) -> int:
    lifecycle = analyze_dataset_lifecycle(job)
    violations = validate_dataset_lifecycle(job)
    if json_output:
        lifecycle_dict = {
            dsn: [
                {
                    "step": ev.step_name,
                    "dd": ev.dd_name,
                    "action": ev.action,
                    "disp_status": ev.disp_status,
                    "disp_normal": ev.disp_normal,
                    "line": ev.line_number,
                }
                for ev in events
            ]
            for dsn, events in lifecycle.items()
        }
        viol_list = [
            {
                "severity": e.severity.name if e.severity else "WARNING",
                "message": e.message,
                "line": e.line_number,
            }
            for e in violations
        ]
        print(
            json.dumps({"lifecycle": lifecycle_dict, "violations": viol_list}, indent=2)
        )
    else:
        _print_datasets(lifecycle, violations)
    return 1 if violations else 0


def _print_datasets(lifecycle: dict, violations: list) -> None:
    if not lifecycle:
        print("(no datasets found)")
        return
    for dsn, events in sorted(lifecycle.items()):
        print(dsn)
        for ev in events:
            disp = f"  status={ev.disp_status}" if ev.disp_status else ""
            norm = f", normal={ev.disp_normal}" if ev.disp_normal else ""
            print(
                f"  {ev.action:<12} {ev.step_name:<10} line {ev.line_number:>4}"
                f"  (dd={ev.dd_name}{disp}{norm})"
            )
        print()
    if violations:
        print(f"Violations ({len(violations)}):")
        for e in violations:
            sev = e.severity.name if e.severity else "WARNING"
            print(f"  [{sev}] {e.message}")


def _cmd_sql(job: Job, json_output: bool = False) -> int:
    results = detect_sql_in_job(job)
    hits = [r for r in results if r.has_sql]
    if json_output:
        items = [
            {
                "step": r.step_name,
                "program": r.program,
                "is_db2_program": r.is_db2_program,
                "has_sql": r.has_sql,
                "sql_categories": sorted(r.sql_categories),
                "sql_statements": [
                    {"keyword": kw, "category": cat, "dd": dd}
                    for kw, cat, dd in r.sql_statements
                ],
            }
            for r in hits
        ]
        print(json.dumps({"results": items, "count": len(items)}, indent=2))
    else:
        _print_sql_results(hits)
    return 1 if hits else 0


def _print_sql_results(hits: list) -> None:
    if not hits:
        print("(no SQL detected)")
        return
    for r in hits:
        db2_tag = " [DB2 program]" if r.is_db2_program else ""
        cats = ", ".join(sorted(r.sql_categories)) if r.sql_categories else ""
        cat_tag = f"  categories={cats}" if cats else ""
        print(
            f"  {r.step_name or '(unnamed)':<12} PGM={r.program or '(none)'}{db2_tag}{cat_tag}"
        )
        for kw, cat, dd in r.sql_statements:
            print(f"    {kw:<20} [{cat}] in DD={dd}")


def _cmd_analyze(
    job: Job, json_output: bool = False, step_filter: str | None = None
) -> int:
    if step_filter:
        step = job.get_step(step_filter)
        if step is None:
            print(f"Step not found: {step_filter}", file=sys.stderr)
            return 1
        result = analyze_step(step)
        results = [result] if result is not None else []
    else:
        results = analyze_job(job)

    if json_output:
        items = [
            {
                "step": r.step_name,
                "program": r.program,
                "summary": r.summary,
                "notes": r.notes,
                "invoked_programs": r.invoked_programs,
                "raw_control": r.raw_control,
            }
            for r in results
        ]
        print(json.dumps({"results": items}, indent=2))
    else:
        _print_analyze_results(results)
    return 0


def _print_analyze_results(results: list) -> None:
    if not results:
        print("(no program profile matches)")
        return
    for r in results:
        step_label = r.step_name or "(unnamed)"
        print(f"  {step_label:<12} PGM={r.program}")
        if r.summary:
            print(f"    {r.summary}")
        for note in r.notes:
            print(f"    note: {note}")
        print()


def _cmd_paths(job: Job, json_output: bool = False) -> int:
    report = compute_feasible_paths(job)
    if json_output:
        print(
            json.dumps(
                {
                    "unreachable_steps": report.unreachable_steps,
                    "always_skipped": report.always_skipped,
                    "contradictory_conditions": [
                        list(pair) for pair in report.contradictory_conditions
                    ],
                    "duplicate_if_branches": [
                        {"line": line, "condition": cond}
                        for line, cond in report.duplicate_if_branches
                    ],
                    "unanalysed_conditions": [
                        list(pair) for pair in report.unanalysed_conditions
                    ],
                },
                indent=2,
            )
        )
    else:
        _print_paths(report)
    return 0


def _print_paths(report: FeasibilityReport) -> None:
    if report.is_empty():
        print("(no feasibility issues found)")
        _print_unanalysed(report)
        return
    if report.unreachable_steps:
        print("Unreachable steps:")
        for s in report.unreachable_steps:
            print(f"  {s}")
    if report.always_skipped:
        print("Always skipped:")
        for s in report.always_skipped:
            print(f"  {s}")
    if report.contradictory_conditions:
        print("Contradictory conditions:")
        for a, b in report.contradictory_conditions:
            print(f"  {a}  vs  {b}")
    if report.duplicate_if_branches:
        print("Duplicate IF branches:")
        for line, cond in report.duplicate_if_branches:
            print(f"  line {line}: {cond}")
    _print_unanalysed(report)


def _print_unanalysed(report: FeasibilityReport) -> None:
    if report.unanalysed_conditions:
        print("Not analysed:")
        for cond, reason in report.unanalysed_conditions:
            print(f"  {cond}  ({reason})")


def _print_summary(job: Job) -> None:
    steps = list(iter_execution_steps(job.steps))
    print(f"Job:    {job.name}")
    if job.accounting_info:
        print(f"Acct:   {job.accounting_info}")
    if job.parameters:
        params = ", ".join(_fmt_param(k, v) for k, v in job.parameters.items())
        print(f"Params: {params}")
    print(f"Steps:  {len(steps)}")
    if job.procedures:
        print(f"Procs:  {', '.join(p.name for p in job.procedures)}")
    print()
    _print_steps(job)


def _print_steps(job: Job) -> None:
    steps = list(iter_execution_steps(job.steps))
    if not steps:
        print("(no steps)")
        return
    # Calculate column widths
    name_w = max(len(s.name or "(unnamed)") for s in steps)
    name_w = max(name_w, 4)  # min header width
    for step in steps:
        name = step.name or "(unnamed)"
        target = step.program or step.procedure or ""
        kind = "PROC" if step.is_procedure else "PGM"
        dd_count = len(step.dd_statements)
        print(f"  {name:<{name_w}}  {kind}={target:<16} DDs: {dd_count}")


def _print_procs(job: Job, proc_path: str | None = None) -> None:
    """Print PROC definitions (inline and externally-loaded)."""
    if not job.procedures:
        print("(no inline procedures)")
    else:
        for proc in job.procedures:
            tag = _proc_tag(proc)
            print(f"PROC: {proc.name}  {tag}")
            if proc.parameters:
                for k, v in proc.parameters.items():
                    print(f"  {_fmt_param(k, v)}")
            steps = list(iter_execution_steps(proc.steps))
            print(f"  Steps: {len(steps)}")
            for step in steps:
                target = step.program or step.procedure or ""
                kind = "PROC" if step.is_procedure else "PGM"
                print(f"    {step.name or '(unnamed)'}  {kind}={target}")
                for dd in step.dd_statements:
                    _print_dd_brief(dd, indent=6)
            print()
    if proc_path and not any(p.is_external for p in job.procedures):
        print(_no_external_procs_note(job, proc_path))


def _no_external_procs_note(job: Job, proc_path: str) -> str:
    """Why ``procs`` lists no PROC from *proc_path*.

    The parse already loads every PROC the job calls from *proc_path* (they
    are listed as ``[external]``), so none listed means the job calls no PROC
    that is there; ``--explode`` would not find one either.
    """
    missing = sorted(
        {
            step.procedure
            for step in iter_execution_steps(job.steps)
            if step.procedure and job.get_procedure(step.procedure) is None
        }
    )
    if missing:
        return f"Note: PROC(s) {', '.join(missing)} not found under '{proc_path}'"
    return (
        f"Note: this job calls no PROC from '{proc_path}' "
        "(procs --list-available lists the PROCs there)"
    )


def _proc_tag(proc: Procedure) -> str:
    """``[builtin]`` (bundled template), ``[external]`` or ``[inline]``."""
    if proc.is_builtin:
        return "[builtin]"
    return "[external]" if proc.is_external else "[inline]"


def _print_proc_detail(proc: Procedure) -> None:
    """Print full detail for a single PROC definition."""
    tag = _proc_tag(proc)
    print(f"PROC: {proc.name}  {tag}  (line {proc.line_number})")
    if proc.parameters:
        print("  Parameters (defaults):")
        for k, v in proc.parameters.items():
            print(f"    {_fmt_param(k, v)}")
    steps = list(iter_execution_steps(proc.steps))
    print(f"  Steps: {len(steps)}")
    for step in steps:
        target = step.program or step.procedure or ""
        kind = "PROC" if step.is_procedure else "PGM"
        print(
            f"    Step: {step.name or '(unnamed)'}  {kind}={target}  (line {step.line_number})"
        )
        if step.dd_statements:
            for dd in step.dd_statements:
                _print_dd_brief(dd, indent=6)
        else:
            print("      (no DD statements)")


def _print_explosion_audit(job: Job) -> None:
    """Print procedure expansion audit records, enriched from explosion_map."""
    audit = job.explosion_audit
    if not audit:
        print("(no procedure expansions recorded)")
        return
    proc_source = {
        p.name.upper(): "external" if p.is_external else "inline"
        for p in job.procedures
    }
    for record in audit:
        source_label = proc_source.get(record.proc_name.upper(), "external")
        tag = f"[{source_label}]"
        info = job.explosion_map.get(record.step_name)
        src_lines = (
            f"  line {info.source_line_numbers[0]}"
            if info and info.source_line_numbers
            else ""
        )
        print(
            f"Expansion: {record.step_name} -> {record.proc_name} {tag}"
            f"  (depth {record.depth}{src_lines})"
        )
        # Show EXEC overrides (what the caller supplied)
        if record.parameters:
            overrides = ", ".join(
                _fmt_param(k, v) for k, v in record.parameters.items()
            )
            print(f"  Overrides: {overrides}")
        # Show resolved parameters (merged EXEC overrides + PROC defaults + SET symbols)
        if info and info.resolved_parameters:
            resolved = ", ".join(
                _fmt_param(k, v) for k, v in info.resolved_parameters.items()
            )
            print(f"  Resolved:  {resolved}")
        if record.expanded_steps:
            print(f"  Expanded steps: {', '.join(record.expanded_steps)}")
        print()


def _print_step_detail(step: Step) -> None:
    name = step.name or "(unnamed)"
    print(f"Step: {name}  (line {step.line_number})")
    if step.program:
        print(f"  PGM={step.program}")
    if step.procedure:
        print(f"  PROC={step.procedure}")
    if step.parameters:
        for k, v in step.parameters.items():
            print(f"  {_fmt_param(k, v)}")
    if step.comments:
        for c in step.comments:
            print(f"  * {c}")
    print()
    if not step.dd_statements:
        print("  (no DD statements)")
        return
    for dd in step.dd_statements:
        _print_dd_brief(dd, indent=2)


def _print_step_dd(
    job: Job, step_name: str, dd_name: str, json_output: bool = False
) -> int:
    step = job.get_step(step_name.upper())
    if step is None:
        print(f"Step not found: {step_name}", file=sys.stderr)
        return 1
    dd = step.get_dd(dd_name.upper())
    if dd is None:
        print(
            f"DD '{dd_name.upper()}' not found in step {step_name.upper()}",
            file=sys.stderr,
        )
        return 1
    if json_output:
        print(json.dumps(dd_to_dict(dd), indent=2))
    else:
        _print_dd_detail(dd)
    return 0


def _print_dd_across_steps(job: Job, dd_name: str, json_output: bool = False) -> int:
    found_dds: list[tuple[str, DDStatement]] = []
    for step in iter_execution_steps(job.steps):
        for dd in step.dd_statements:
            if dd.name == dd_name:
                found_dds.append((step.name or "(unnamed)", dd))
    if not found_dds:
        print(
            f"No step or DD named '{dd_name}' found.",
            file=sys.stderr,
        )
        return 1
    if json_output:
        items = [{**dd_to_dict(dd), "step": step_label} for step_label, dd in found_dds]
        print(json.dumps(items, indent=2))
    else:
        for step_label, dd in found_dds:
            print(f"[{step_label}]")
            _print_dd_detail(dd)
            print()
    return 0


# ---------------------------------------------------------------------------
# DD display helpers
# ---------------------------------------------------------------------------


def _fmt_value(value: object) -> str:
    """Render a parsed parameter value back in JCL syntax.

    Lists (sublists such as ``DISP=(,CATLG,DELETE)``) are shown in
    parentheses instead of as Python ``['', 'CATLG', 'DELETE']`` reprs.
    """
    if isinstance(value, (list, tuple)):
        return "(" + ",".join(_fmt_value(v) for v in value) + ")"
    if value is True:
        return ""
    return str(value)


def _fmt_param(key: str, value: object) -> str:
    """Render one ``KEY=value`` operand; positional operands show bare."""
    if is_positional_key(key):
        return _fmt_value(value)
    if value is True:
        return key
    return f"{key}={_fmt_value(value)}"


def _print_dd_brief(dd: DDStatement, indent: int = 0) -> None:
    pad = " " * indent
    dsn = dd.dataset_name or ""
    disp = f"DISP={_fmt_value(dd.disposition)}" if dd.disposition else ""
    inline = " [inline data]" if dd.has_inline_data else ""
    sysout_val = dd.parameters.get("SYSOUT")
    sysout = f"SYSOUT={_fmt_value(sysout_val)}" if sysout_val else ""
    # Positional operands: DUMMY used to leave the line blank.
    positional = [
        _fmt_value(v) for k, v in dd.parameters.items() if is_positional_key(k)
    ]
    parts = [p for p in [*positional, dsn, disp, sysout] if p]
    detail = "  ".join(parts)
    print(f"{pad}{dd.name:<12} {detail}{inline}")


def _print_dd_detail(dd: DDStatement) -> None:
    print(f"  DD: {dd.name}  (line {dd.line_number})")
    if dd.dataset_name:
        print(f"    DSN={dd.dataset_name}")
    if dd.disposition:
        print(f"    DISP={_fmt_value(dd.disposition)}")
    sysout_val = dd.parameters.get("SYSOUT")
    if sysout_val:
        print(f"    SYSOUT={_fmt_value(sysout_val)}")
    # Show other interesting parameters
    skip_keys = {"DSN", "DSNAME", "DISP", "SYSOUT", "DCB", "SPACE", "*"}
    for k, v in dd.parameters.items():
        if k not in skip_keys:
            print(f"    {_fmt_param(k, v)}")
    dcb = _dcb_summary(dd)
    if dcb:
        print(f"    DCB=({dcb})")
    space = _space_summary(dd)
    if space:
        print(f"    SPACE=({space})")
    if dd.has_inline_data:
        print("    --- inline data ---")
        for line in split_source_lines(dd.inline_data or ""):
            print(f"    {line}")
        print("    ---")


def _dcb_summary(dd: DDStatement) -> str:
    """``RECFM=..,LRECL=..,BLKSIZE=..`` from the typed DCB (``""`` when none)."""
    dcb = dd.dcb
    if not dcb:
        return ""
    parts = []
    if dcb.recfm:
        parts.append(f"RECFM={dcb.recfm}")
    if dcb.lrecl is not None:
        parts.append(f"LRECL={dcb.lrecl}")
    if dcb.blksize is not None:
        parts.append(f"BLKSIZE={dcb.blksize}")
    return ",".join(parts)


def _space_summary(dd: DDStatement) -> str:
    """``unit,primary,secondary`` from the typed SPACE (``""`` when none)."""
    sp = dd.space
    if not sp:
        return ""
    parts = [sp.unit] if sp.unit else []
    parts += [str(n) for n in (sp.primary, sp.secondary) if n is not None]
    return ",".join(parts)


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------


def _procs_to_dict(job: Job) -> list[dict[str, Any]]:
    """Serialize PROC definitions to a list of dicts."""
    return [procedure_to_dict(proc) for proc in job.procedures]


def _explosion_audit_to_dict(job: Job) -> list[dict[str, Any]]:
    """Serialize explosion audit records, enriched with explosion_map data."""
    proc_source = {
        p.name.upper(): "external" if p.is_external else "inline"
        for p in job.procedures
    }
    result = []
    for record in job.explosion_audit:
        d = record.to_dict()
        d["source"] = proc_source.get(record.proc_name.upper(), "external")
        info = job.explosion_map.get(record.step_name)
        if info:
            d["resolved_parameters"] = info.resolved_parameters
            d["source_line_numbers"] = info.source_line_numbers
        result.append(d)
    return result


#: Query words that take only the job and ``--json``.
_JOB_QUERIES: dict[str, Callable[[Job, bool], int]] = {
    "metrics": _cmd_metrics,
    "datasets": _cmd_datasets,
    "sql": _cmd_sql,
    "paths": _cmd_paths,
}
