"""Lint and validate many JCL files at once, for CI and pre-commit.

:func:`lint_paths` and :func:`validate_paths` take files and directories and
return one :class:`FileReport` per file; :func:`reports_to_sarif`,
:func:`reports_to_dict` and :func:`format_reports` render them.  The
``jcl-lint`` console script (:func:`lint_main`) is built on them, as are
``jcl-parser DIR lint`` and ``jcl-parser DIR --validate``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .errors import (
    ErrorSeverity,
    ErrorType,
    JCLParseError,
    ParseError,
    ValidationError,
)
from .lineage import load_job_stream
from .lint import (
    PARSE_ERROR_CODE,
    LintConfig,
    LintConfigError,
    find_lint_config,
    lint_job,
    load_lint_config,
    to_sarif_files,
)
from .lint.config import parse_severity
from .model import Job
from .parser import parse_jcl, validate_jcl
from .utils import read_source

#: What a file that cannot be read or parsed raises.
_UNREADABLE = (JCLParseError, UnicodeError, ValueError, OSError)


@dataclass
class FileReport:
    """The findings for one file.

    Attributes:
        uri: The file's path as given (``/``-separated; a directory's files
            are under the directory as given), used in text output and as
            the SARIF ``artifactLocation.uri``.
        findings: Lint findings or validation errors, in source order.
    """

    uri: str
    findings: list[ValidationError] = field(default_factory=list)


def iter_source_files(directory: str | Path, pattern: str = "*") -> Iterator[Path]:
    """The files under *directory* matching the :meth:`pathlib.Path.glob`
    *pattern*, sorted, skipping hidden files and directories."""
    root = Path(directory)
    for path in sorted(root.glob(pattern)):
        rel = path.relative_to(root)
        if path.is_file() and not any(p.startswith(".") for p in rel.parts):
            yield path


def _uri(path: Path) -> str:
    return path.as_posix()


def as_finding(err: ParseError | ValidationError) -> ValidationError:
    """*err* as a :class:`~jclparser.errors.ValidationError` (what
    :func:`~jclparser.parser.validate_jcl` returns is mostly
    :class:`~jclparser.errors.ParseError`, which carries no rule code)."""
    if isinstance(err, ValidationError):
        return err
    return ValidationError(
        message=err.message,
        error_type=err.error_type,
        line_number=err.line_number or None,
        severity=err.severity,
    )


def _parse_failure(exc: Exception) -> ValidationError:
    message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return ValidationError(
        message=f"Not parsed: {message}",
        error_type=ErrorType.SYNTAX_ERROR,
        line_number=getattr(exc, "line_number", None) or None,
        severity=ErrorSeverity.ERROR,
        error_code=PARSE_ERROR_CODE,
    )


def _lint_one(path: Path, job: Job, config: LintConfig) -> FileReport:
    try:
        source = read_source(path)
    except _UNREADABLE:
        source = None
    return FileReport(_uri(path), lint_job(job, config, source=source))


def _lint_file(
    path: Path, config: LintConfig, explode: bool, proc_base_path: str | None
) -> FileReport:
    try:
        job = parse_jcl(
            path,
            proc_base_path=proc_base_path,
            enable_external_procs=proc_base_path is not None,
        )
        if explode:
            job = job.explode()
    except _UNREADABLE as exc:
        bare = _bare_member_job(path)
        if bare is None:
            return FileReport(_uri(path), [_parse_failure(exc)])
        job = bare
    return _lint_one(path, job, config)


def _bare_member_job(path: Path) -> Job | None:
    """A PROC member with no PROC statement, as a job to lint, or None."""
    from .lineage import _bare_procedure_member
    from .lint.runner import procedure_body_job
    from .model import iter_execution_steps

    proc = _bare_procedure_member(path)
    if proc is None:
        return None
    job = procedure_body_job(proc)
    # The member was read behind a one-line JOB wrapper; give the findings
    # the member's own line numbers.
    for step in iter_execution_steps(job.steps):
        step.line_number = max(step.line_number - 1, 0)
        for dd in step.dd_statements:
            dd.line_number = max(dd.line_number - 1, 0)
    return job


def _lint_member(path: Path, config: LintConfig) -> FileReport:
    """Lint a PROC member found in a directory: its PROC bodies' steps."""
    try:
        job = parse_jcl(path, enable_external_procs=False)
    except _UNREADABLE:
        bare = _bare_member_job(path)
        if bare is None:
            raise
        job = bare
    return _lint_one(path, job, config)


def _lint_directory(
    directory: Path,
    pattern: str,
    config: LintConfig,
    explode: bool,
    proc_base_path: str | None,
) -> list[FileReport]:
    # load_job_stream explodes with the directory's own PROC members; each
    # member is linted on its own too, for the steps of its PROC body.
    stream = load_job_stream(
        directory, pattern, explode=explode, proc_base_path=proc_base_path
    )
    reports = [
        _lint_one(directory / job_id, job, config)
        for job_id, job in stream.jobs.items()
    ]
    reports += [
        _lint_member(directory / member_id, config) for member_id in stream.procedures
    ]
    for job_id, message in stream.errors.items():
        failure = _parse_failure(ValueError(message))
        reports.append(FileReport(_uri(directory / job_id), [failure]))
    return sorted(reports, key=lambda r: r.uri)


def lint_paths(
    paths: Sequence[str | Path],
    *,
    pattern: str = "*",
    config: LintConfig | None = None,
    explode: bool = False,
    proc_base_path: str | None = None,
) -> list[FileReport]:
    """Lint every file in *paths*; a directory contributes its files that
    match *pattern* (and is exploded with its own PROC members, see
    :func:`~jclparser.lineage.load_job_stream`).

    ``//* jcl-lint: disable=`` comments are honoured.  A file that does not
    parse gets one :data:`~jclparser.lint.PARSE_ERROR_CODE` finding.
    """
    cfg = config or LintConfig()
    reports: list[FileReport] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            reports.extend(_lint_directory(path, pattern, cfg, explode, proc_base_path))
        else:
            reports.append(_lint_file(path, cfg, explode, proc_base_path))
    return reports


def validate_paths(
    paths: Sequence[str | Path],
    *,
    pattern: str = "*",
    proc_base_path: str | None = None,
) -> list[FileReport]:
    """:func:`~jclparser.parser.validate_jcl` (``level="structure"``) for
    every file in *paths*; a directory contributes its files that match
    *pattern*."""
    reports: list[FileReport] = []
    for raw in paths:
        path = Path(raw)
        files = list(iter_source_files(path, pattern)) if path.is_dir() else [path]
        for file in files:
            try:
                findings = [
                    as_finding(err)
                    for err in validate_jcl(
                        file, level="structure", proc_base_path=proc_base_path
                    )
                ]
            except _UNREADABLE as exc:
                findings = [_parse_failure(exc)]
            reports.append(FileReport(_uri(file), findings))
    return reports


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _severity(err: ValidationError) -> ErrorSeverity:
    return err.severity or ErrorSeverity.ERROR


def finding_to_dict(err: ValidationError) -> dict[str, Any]:
    """One finding as JSON: ``code``, ``severity``, ``line``, ``message``."""
    return {
        "code": err.error_code or "",
        "severity": _severity(err).name,
        "line": err.line_number,
        "message": err.message,
    }


def reports_to_dict(reports: Sequence[FileReport]) -> dict[str, Any]:
    """``{"files": {uri: [finding, ...]}, "count": N}`` (every file listed)."""
    return {
        "files": {r.uri: [finding_to_dict(f) for f in r.findings] for r in reports},
        "count": sum(len(r.findings) for r in reports),
    }


def reports_to_sarif(reports: Sequence[FileReport]) -> dict[str, Any]:
    """One SARIF 2.1.0 run for *reports*."""
    return to_sarif_files((r.uri, r.findings) for r in reports)


def format_reports(reports: Sequence[FileReport], ok_message: str) -> str:
    """Compiler-style text: ``FILE:LINE: SEVERITY [CODE] message`` per
    finding, then a count; *ok_message* when there are none."""
    lines = []
    for report in reports:
        for err in sorted(report.findings, key=lambda f: f.line_number or 0):
            loc = f"{report.uri}:{err.line_number}" if err.line_number else report.uri
            code = f" [{err.error_code}]" if err.error_code else ""
            lines.append(f"{loc}: {_severity(err).name}{code} {err.message}")
    count = len(lines)
    if not count:
        return ok_message + "\n"
    files = sum(1 for r in reports if r.findings)
    lines.append(f"{count} finding(s) in {files} of {len(reports)} file(s)")
    return "\n".join(lines) + "\n"


def exit_code(reports: Sequence[FileReport], fail_on: ErrorSeverity) -> int:
    """1 if any finding is at least as severe as *fail_on*, else 0."""
    threshold = LintConfig(fail_on=fail_on)
    failing = any(threshold.fails(_severity(f)) for r in reports for f in r.findings)
    return 1 if failing else 0


# ---------------------------------------------------------------------------
# Configuration lookup shared by the CLIs
# ---------------------------------------------------------------------------


def resolve_lint_config(
    explicit: str | None, start: str | Path | None = None
) -> LintConfig:
    """The lint configuration in *explicit*, else the nearest
    ``pyproject.toml`` with a ``[tool.jcl-parser.lint]`` table from *start*
    (default: the working directory), else the defaults.

    Raises:
        LintConfigError: The configuration cannot be read or is invalid.
    """
    if explicit is not None:
        return load_lint_config(explicit)
    found = find_lint_config(start if start is not None else Path.cwd())
    return load_lint_config(found) if found is not None else LintConfig()


def write_output(text: str, output: str | None) -> None:
    """Print *text*, or write it to the file *output*."""
    if output is None:
        sys.stdout.write(text)
    else:
        Path(output).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# jcl-lint
# ---------------------------------------------------------------------------


def _code_list(value: str) -> set[str]:
    return {c.strip().upper() for c in value.split(",") if c.strip()}


def _build_lint_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jcl-lint",
        description=(
            "Lint JCL files and directories. Exits 1 when a finding reaches "
            "--fail-on or a file does not parse."
        ),
    )
    parser.add_argument("paths", nargs="+", metavar="PATH", help="Files or dirs")
    parser.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    parser.add_argument("--output", "-o", metavar="FILE", help="Write to FILE")
    parser.add_argument(
        "--glob",
        default="*",
        metavar="PATTERN",
        help="Files of a directory to lint (default '*'; '**/*.jcl' recurses)",
    )
    parser.add_argument(
        "--config", metavar="TOML", help="Lint config (default: nearest pyproject)"
    )
    parser.add_argument(
        "--fail-on",
        choices=("info", "warning", "error"),
        help="Lowest severity that fails the run (default: config, else info)",
    )
    parser.add_argument("--select", metavar="CODES", help="Only these rule codes")
    parser.add_argument("--ignore", metavar="CODES", help="Skip these rule codes")
    parser.add_argument("--explode", action="store_true", help="Expand PROCs first")
    parser.add_argument("--proc-path", default=None, help="External PROC libraries")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def lint_main(argv: list[str] | None = None) -> int:
    """``jcl-lint PATH...``: lint files and directories (exit 0/1; 2 on a
    bad configuration, a missing path, or nothing to lint)."""
    args = _build_lint_parser().parse_args(argv)
    try:
        config = resolve_lint_config(args.config, args.paths[0])
        if args.fail_on:
            config.fail_on = parse_severity(args.fail_on, "--fail-on")
    except (LintConfigError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.select:
        config.enabled = _code_list(args.select)
    if args.ignore:
        config.disabled |= _code_list(args.ignore)
    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        print(f"Error: not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    reports = lint_paths(
        args.paths,
        pattern=args.glob,
        config=config,
        explode=args.explode,
        proc_base_path=args.proc_path,
    )
    if not reports:
        # A glob that matches nothing must not pass a CI run silently.
        print(f"Error: no JCL files matching {args.glob!r}", file=sys.stderr)
        return 2
    if args.format == "sarif":
        text = json.dumps(reports_to_sarif(reports), indent=2) + "\n"
    elif args.format == "json":
        text = json.dumps(reports_to_dict(reports), indent=2) + "\n"
    else:
        text = format_reports(reports, "OK - no lint findings.")
    write_output(text, args.output)
    return exit_code(reports, config.fail_on)


__all__ = [
    "FileReport",
    "as_finding",
    "exit_code",
    "finding_to_dict",
    "format_reports",
    "iter_source_files",
    "lint_main",
    "lint_paths",
    "reports_to_dict",
    "reports_to_sarif",
    "resolve_lint_config",
    "validate_paths",
]
