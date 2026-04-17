"""
Command-line interface for jclparser.

Usage:
    jcl-parser FILE                              Show job summary
    jcl-parser FILE steps                        List all steps
    jcl-parser FILE procs                        List procedure definitions
    jcl-parser FILE procs PROCNAME               Show a specific procedure
    jcl-parser FILE procs --explode              Show procedure expansion audit
    jcl-parser FILE procs --list-available       List PROCs in --proc-path libraries
    jcl-parser FILE STEP                         Show step details
    jcl-parser FILE STEP.DDNAME                  Show a specific DD statement
    jcl-parser FILE DDNAME                       Show all DDs with that name
    jcl-parser FILE --json                       Full parse result as JSON
    jcl-parser FILE --validate                   Validate the JCL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .jcl_file_type import detect_file_type, FileType
from .metrics import compute_metrics
from .lint import lint_job, all_rules
from .dataset_lifecycle import analyze_dataset_lifecycle, validate_dataset_lifecycle
from .sql_detector import detect_sql_in_job
from .program_profiles import analyze_job, analyze_step
from .rc_analysis import compute_feasible_paths
from .errors import (
    JCLSyntaxError,
    JCLValidationError,
    JCLStructureError,
    UndefinedSymbolError,
    CircularProcedureError,
    ExplosionDepthError,
    ProcedureNotFoundError,
)
from .model import (
    ConditionalBlock,
    DDStatement,
    Job,
    Procedure,
    Step,
    iter_execution_steps,
)
from .parser import parse_jcl, validate_jcl
from .proc_loader import JCLLIBProcedureLoader


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    # --lint-list doesn't require FILE — handle before argparse
    _argv = argv if argv is not None else sys.argv[1:]
    if "--lint-list" in _argv:
        return _cmd_lint_list()

    parser = argparse.ArgumentParser(
        prog="jcl-parser",
        description="Parse and inspect IBM JCL files.",
    )
    parser.add_argument("file", metavar="FILE", help="JCL file to parse")
    parser.add_argument(
        "query",
        nargs="*",
        default=[],
        help=(
            "Query: 'steps', 'procs [PROCNAME]', a step name, STEP.DDNAME, "
            "or a DD name to find across all steps"
        ),
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output as JSON"
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

    args = parser.parse_args(argv)
    path = Path(args.file)

    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1

    # --- validate mode ---
    if args.validate:
        return _cmd_validate(path, json_output=args.json_output)

    # --- detect mode (no parse needed) ---
    tokens_early = args.query
    if tokens_early and tokens_early[0].lower() == "detect":
        return _cmd_detect(path, args.json_output)

    # --- parse ---
    try:
        job = parse_jcl(
            path,
            proc_base_path=args.proc_path,
            enable_external_procs=args.proc_path is not None,
        )
    except (JCLSyntaxError, JCLValidationError, JCLStructureError) as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        return 1

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
            return 1

    # --- resolve query target ---
    tokens = args.query  # list[str]
    query = tokens[0] if tokens else None
    subquery = tokens[1].upper() if len(tokens) > 1 else None
    json_out = args.json_output

    if query is None:
        if json_out:
            print(json.dumps(_job_to_dict(job), indent=2))
        else:
            _print_summary(job)
        return 0

    if query.lower() == "metrics":
        return _cmd_metrics(job, json_out)

    if query.lower() == "lint":
        return _cmd_lint(job, json_out)

    if query.lower() == "datasets":
        return _cmd_datasets(job, json_out)

    if query.lower() == "sql":
        return _cmd_sql(job, json_out)

    if query.lower() == "analyze":
        step_filter = tokens[1].upper() if len(tokens) > 1 else None
        return _cmd_analyze(job, json_out, step_filter=step_filter)

    if query.lower() == "paths":
        return _cmd_paths(job, json_out)

    if query.lower() == "steps":
        if json_out:
            steps = [_step_or_cond_to_dict(s) for s in job.steps]
            print(json.dumps(steps, indent=2))
        else:
            _print_steps(job)
        return 0

    if query.lower() == "procs":
        # jcl-parser FILE procs PROCNAME  — single proc detail
        if subquery:
            proc = job.get_procedure(subquery)
            if proc is None:
                print(f"Procedure not found: {subquery}", file=sys.stderr)
                return 1
            if json_out:
                print(json.dumps(_proc_to_dict(proc), indent=2))
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
        else:
            if json_out:
                print(json.dumps(_procs_to_dict(job), indent=2))
            else:
                _print_procs(job, proc_path=args.proc_path)
        return 0

    # STEP.DDNAME — split on first dot only; the remainder is the full DD name
    # (JCL DD names don't contain dots, but this is safe for any input)
    if "." in query:
        step_name, dd_name = query.split(".", 1)
        return _print_step_dd(job, step_name, dd_name, json_out)

    # Try as step name first
    step = job.get_step(query.upper())
    if step is not None:
        if json_out:
            print(json.dumps(_step_to_dict(step), indent=2))
        else:
            _print_step_detail(step)
        return 0

    # Fall back to DD name across all steps
    return _print_dd_across_steps(job, query.upper(), json_out)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _cmd_validate(path: Path, json_output: bool = False) -> int:
    errors = validate_jcl(path, level="structure")
    if json_output:
        items = [
            {
                "severity": (
                    getattr(err, "severity", None)
                    and getattr(err, "severity").name
                    or "ERROR"
                ),
                "line": getattr(err, "line_number", None),
                "message": err.message,
            }
            for err in errors
        ]
        print(json.dumps({"valid": len(items) == 0, "errors": items}, indent=2))
        return 0 if not items else 1
    if not errors:
        print("OK - no errors found.")
        return 0
    for err in errors:
        severity = getattr(err, "severity", None)
        tag = f"[{severity.name}]" if severity else "[ERROR]"
        line = getattr(err, "line_number", None)
        loc = f" line {line}" if line else ""
        print(f"{tag}{loc} {err.message}")
    return 1


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


def _cmd_detect(path: Path, json_output: bool = False) -> int:
    file_type = detect_file_type(path)
    name = file_type.name  # "JCL", "PROC", or "UNKNOWN"
    if json_output:
        print(json.dumps({"file_type": name, "path": str(path)}, indent=2))
    else:
        print(name)
    return 0


def _cmd_metrics(job: "Job", json_output: bool = False) -> int:
    m = compute_metrics(job)
    if json_output:
        print(json.dumps(m.to_dict(), indent=2))
    else:
        _print_metrics(m)
    return 0


def _print_metrics(m) -> None:
    fields = m.to_dict()
    fields.pop("metrics", None)  # remove backwards-compat shadow dict
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


def _cmd_lint(job: "Job", json_output: bool = False) -> int:
    findings = lint_job(job)
    if json_output:
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
    return 1 if findings else 0


def _print_lint_findings(findings: list) -> None:
    if not findings:
        print("OK - no lint findings.")
        return
    for e in findings:
        code = getattr(e, "error_code", None) or "LINT"
        sev = e.severity.name if e.severity else "WARNING"
        line = e.line_number
        loc = f" line {line:>4}" if line else "       "
        print(f"[{code}]{loc}: {e.message}")


def _cmd_datasets(job: "Job", json_output: bool = False) -> int:
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
        print(json.dumps({"lifecycle": lifecycle_dict, "violations": viol_list}, indent=2))
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


def _cmd_sql(job: "Job", json_output: bool = False) -> int:
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
        print(f"  {r.step_name or '(unnamed)':<12} PGM={r.program or '(none)'}{db2_tag}{cat_tag}")
        for kw, cat, dd in r.sql_statements:
            print(f"    {kw:<20} [{cat}] in DD={dd}")


def _cmd_analyze(
    job: "Job", json_output: bool = False, step_filter: str | None = None
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


def _cmd_paths(job: "Job", json_output: bool = False) -> int:
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
                },
                indent=2,
            )
        )
    else:
        _print_paths(report)
    return 0


def _print_paths(report) -> None:
    if report.is_empty():
        print("(no feasibility issues found)")
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


def _print_summary(job: Job) -> None:
    steps = list(iter_execution_steps(job.steps))
    print(f"Job:    {job.name}")
    if job.accounting_info:
        print(f"Acct:   {job.accounting_info}")
    if job.parameters:
        params = ", ".join(f"{k}={v}" for k, v in job.parameters.items())
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
            tag = "[external]" if proc.is_external else "[inline]"
            print(f"PROC: {proc.name}  {tag}")
            if proc.parameters:
                for k, v in proc.parameters.items():
                    print(f"  {k}={v}")
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
        print(f"Note: external PROCs from '{proc_path}' are expanded with --explode")


def _print_proc_detail(proc: Procedure) -> None:
    """Print full detail for a single PROC definition."""
    tag = "[external]" if proc.is_external else "[inline]"
    print(f"PROC: {proc.name}  {tag}  (line {proc.line_number})")
    if proc.parameters:
        print("  Parameters (defaults):")
        for k, v in proc.parameters.items():
            print(f"    {k}={v}")
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
            overrides = ", ".join(f"{k}={v}" for k, v in record.parameters.items())
            print(f"  Overrides: {overrides}")
        # Show resolved parameters (merged EXEC overrides + PROC defaults + SET symbols)
        if info and info.resolved_parameters:
            resolved = ", ".join(
                f"{k}={v}" for k, v in info.resolved_parameters.items()
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
            print(f"  {k}={v}")
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
        print(json.dumps(_dd_to_dict(dd), indent=2))
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
        items = [
            {**_dd_to_dict(dd), "step": step_label} for step_label, dd in found_dds
        ]
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


def _print_dd_brief(dd: DDStatement, indent: int = 0) -> None:
    pad = " " * indent
    dsn = dd.dataset_name or ""
    disp = f"DISP={dd.disposition}" if dd.disposition else ""
    inline = " [inline data]" if dd.has_inline_data else ""
    sysout_val = dd.parameters.get("SYSOUT")
    sysout = f"SYSOUT={sysout_val}" if sysout_val else ""
    parts = [p for p in [dsn, disp, sysout] if p]
    detail = "  ".join(parts)
    print(f"{pad}{dd.name:<12} {detail}{inline}")


def _print_dd_detail(dd: DDStatement) -> None:
    print(f"  DD: {dd.name}  (line {dd.line_number})")
    if dd.dataset_name:
        print(f"    DSN={dd.dataset_name}")
    if dd.disposition:
        print(f"    DISP={dd.disposition}")
    sysout_val = dd.parameters.get("SYSOUT")
    if sysout_val:
        print(f"    SYSOUT={sysout_val}")
    # Show other interesting parameters
    skip_keys = {"DSN", "DISP", "SYSOUT", "DCB", "SPACE", "*"}
    for k, v in dd.parameters.items():
        if k not in skip_keys:
            print(f"    {k}={v}")
    if dd.dcb:
        dcb = dd.dcb
        parts = []
        if dcb.recfm:
            parts.append(f"RECFM={dcb.recfm}")
        if dcb.lrecl is not None:
            parts.append(f"LRECL={dcb.lrecl}")
        if dcb.blksize is not None:
            parts.append(f"BLKSIZE={dcb.blksize}")
        if parts:
            print(f"    DCB=({','.join(parts)})")
    if dd.space:
        sp = dd.space
        parts = []
        if sp.unit:
            parts.append(sp.unit)
        if sp.primary is not None:
            parts.append(str(sp.primary))
        if sp.secondary is not None:
            parts.append(str(sp.secondary))
        if parts:
            print(f"    SPACE=({','.join(parts)})")
    if dd.has_inline_data:
        print("    --- inline data ---")
        for line in (dd.inline_data or "").splitlines():
            print(f"    {line}")
        print("    ---")


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------


def _job_to_dict(job: Job) -> dict[str, Any]:
    return {
        "name": job.name,
        "accounting_info": job.accounting_info,
        "parameters": job.parameters,
        "steps": [_step_or_cond_to_dict(s) for s in job.steps],
        "procedures": [
            {
                "name": p.name,
                "parameters": p.parameters,
                "steps": [_step_or_cond_to_dict(s) for s in p.steps],
            }
            for p in job.procedures
        ],
        "set_statements": job.set_statements,
        "jcllib_order": job.jcllib_order,
        "comments": job.comments,
    }


def _step_or_cond_to_dict(item: Step | ConditionalBlock) -> dict[str, Any]:
    if isinstance(item, ConditionalBlock):
        return {
            "type": "conditional",
            "condition": item.condition,
            "then_steps": [_step_or_cond_to_dict(s) for s in item.then_steps],
            "else_steps": [_step_or_cond_to_dict(s) for s in item.else_steps],
            "line_number": item.line_number,
        }
    return _step_to_dict(item)


def _step_to_dict(step: Step) -> dict[str, Any]:
    return {
        "type": "step",
        "name": step.name,
        "program": step.program,
        "procedure": step.procedure,
        "parameters": step.parameters,
        "dd_statements": [_dd_to_dict(dd) for dd in step.dd_statements],
        "line_number": step.line_number,
        "comments": step.comments,
        "is_exploded": step.is_exploded,
        "original_proc_call": step.original_proc_call,
        "dd_overrides": {k: _dd_to_dict(v) for k, v in step.dd_overrides.items()},
    }


def _proc_to_dict(proc: Procedure) -> dict[str, Any]:
    """Serialize a single Procedure to a dict."""
    return {
        "name": proc.name,
        "source": "external" if proc.is_external else "inline",
        "line_number": proc.line_number,
        "parameters": proc.parameters,
        "steps": [_step_or_cond_to_dict(s) for s in proc.steps],
    }


def _procs_to_dict(job: Job) -> list[dict[str, Any]]:
    """Serialize PROC definitions to a list of dicts."""
    return [_proc_to_dict(proc) for proc in job.procedures]


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


def _dd_to_dict(dd: DDStatement) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": dd.name,
        "dataset_name": dd.dataset_name,
        "disposition": dd.disposition,
        "parameters": dd.parameters,
        "line_number": dd.line_number,
    }
    if dd.has_inline_data:
        d["inline_data"] = dd.inline_data
    return d
