---
title: Documentation Audit — Fill Coverage Gaps
date: 2026-04-17
status: approved
---

# Documentation Audit Design

## Problem

The jcl-parser library has grown significantly since its initial docs were written. The following public
API surface is completely undocumented:

- The entire CLI (`jcl-parser` command + 8 subcommands)
- Metrics API (`compute_metrics`, `JobMetrics`)
- Dataset lifecycle analysis (`analyze_dataset_lifecycle`, `validate_dataset_lifecycle`, `DatasetEvent`)
- RC feasibility analysis (`compute_feasible_paths`, `FeasibilityReport`)
- Program profiles (`analyze_job`, `analyze_step`, `ProgramProfile`, `ProgramAnalysis`)
- Lint system (`lint_job`, `LintConfig`, `register_lint_rule`, `lint_to_sarif`, built-in rules)
- INCLUDE member loading (`resolve_includes`, `IncludeMemberLoader`, `DictMemberLoader`, `JCLLIBMemberLoader`)
- Typed JES2/JES3 statements (`parse_jes_control` and all typed statement classes)

The README Public API table is also out of date — it lists the original Tier 2 items but is missing everything
added since.

## Approach

Option A (approved): full sweep — create three new doc pages, update two existing ones, fix the README.

## Files to Create

### `docs/cli.md`

Full CLI reference. Structure:

1. **Installation / invocation** — `pip install -e .`, `jcl-parser --help`, `python -m jclparser`
2. **Default view** — `jcl-parser FILE` → job summary (name, params, steps, procs)
3. **`steps`** — list all execution steps with PGM/PROC and DD count
4. **`procs`** — list inline procedures; `procs PROCNAME` for detail; `--list-available` with `--proc-path`; `--explode` for expansion audit
5. **`detect`** — file-type heuristic; JSON shape `{"file_type": "JCL"|"PROC"|"UNKNOWN"}`
6. **`metrics`** — structural metrics; all fields; JSON output
7. **`lint`** — run lint rules; text format `[CODE] line N: message`; JSON `{"findings": [...], "count": N}`; `--lint-list` flag
8. **`datasets`** — dataset lifecycle; text and JSON (`{"lifecycle": {...}, "violations": [...]}`)
9. **`sql`** — SQL detection per step; JSON `{"results": [...], "count": N}`
10. **`analyze`** — program profile analysis; optional step filter (`FILE analyze STEPNAME`)
11. **`paths`** — RC feasibility; unreachable steps, always-skipped, contradictory conditions
12. **Global flags** — `--json`, `--validate`, `--explode`, `--proc-path`, `--version`, `--lint-list`
13. **Exit codes** — 0 = ok/no findings, 1 = findings/errors, 1 = file-not-found

### `docs/analysis.md`

Python API for the four analysis subsystems:

1. **Metrics** — `compute_metrics(job)` → `JobMetrics`; field-by-field table; what `cyclomatic_score` means (McCabe CC analogue: 1 + conditional_count + branch_count)
2. **Dataset lifecycle** — `analyze_dataset_lifecycle(job)` → `dict[str, list[DatasetEvent]]`; `validate_dataset_lifecycle(job)` → violations; what each action means (CREATE, OPEN, DELETE, UNCATLG); detected issues (duplicate creation, forward reference, uncatalog-before-use)
3. **RC feasibility** — `compute_feasible_paths(job)` → `FeasibilityReport`; fields: `unreachable_steps`, `always_skipped`, `contradictory_conditions`, `duplicate_if_branches`; default RC domain `{0, 4, 8, 12, 16}`; limitations (conservative, no runtime ABEND)
4. **Program profiles** — `analyze_job(job)` → `list[ProgramAnalysis]`; `analyze_step(step)` for one step; built-in profiles (SORT, IEBGENER, IEFBR14, IKJEFT01, IDCAMS); `ProgramAnalysis` fields (step_name, program, summary, notes, raw_control); how to register a custom profile with `register_profile`

### `docs/lint.md`

1. **Quick start** — `lint_job(job)` → `list[ValidationError]`; how to interpret findings
2. **Built-in rules** table:
   - `JCL-LINT-001` — Hardcoded HLQ (INFO): dataset with literal HLQ instead of `&HLQ`
   - `JCL-LINT-002` — `UNIT=SYSDA` (INFO): generic device group, prefer site-specific
   - `JCL-LINT-003` — Critical dataset with `DISP=(NEW,CATLG,DELETE)` (WARNING): data loss on failure
3. **`LintConfig`** — per-rule severity overrides; `critical_dataset_patterns` for rule 003
4. **Writing a custom rule** — subclass `LintRule`, set `code`/`description`/`default_severity`, implement `check(job, config)`, call `register_lint_rule(MyRule())`
5. **SARIF output** — `lint_to_sarif(findings)` → dict; shape overview for tool integrations

## Files to Update

### `docs/advanced-features.md`

Append two sections at the end:

**INCLUDE member loading**
- `resolve_includes(jcl_text, loader)` — resolves `// INCLUDE MEMBER=name` before parsing
- `IncludeMemberLoader` abstract interface — implement `load_member(name, libraries)`
- `DictMemberLoader` — in-memory dict, useful for tests
- `JCLLIBMemberLoader(base_path)` — filesystem loader, same naming convention as `JCLLIBProcedureLoader`
- Show end-to-end example: create loader → call `resolve_includes` → pass result to `parse_jcl`

**Typed JES2/JES3 statements**
- `parse_jes_control(stmt)` → typed object
- Table of typed classes: `JobParmStatement`, `RouteStatement`, `XmitStatement`, `SignonStatement`, `MessageStatement`, `NetacctStatement`, `NotifyStatement`, `PriorityStatement`, `Jes3RouteXeqStatement`
- Show iterating `job.jes_statements` and dispatching on type; contrast with raw string access from basic-parsing.md

### `README.md`

1. Add `docs/cli.md` row to the Documentation table: `| [CLI reference](docs/cli.md) | Command-line interface — subcommands, flags, JSON output, exit codes |`
2. Add `docs/analysis.md` row: `| [Analysis features](docs/analysis.md) | Metrics, dataset lifecycle, RC feasibility, program profiles |`
3. Add `docs/lint.md` row: `| [Lint](docs/lint.md) | Built-in lint rules, custom rules, SARIF output |`
4. Fix Public API block — add all missing Tier 2 items:
   - `compute_metrics · JobMetrics`
   - `analyze_dataset_lifecycle · validate_dataset_lifecycle · DatasetEvent`
   - `compute_feasible_paths · FeasibilityReport`
   - `analyze_job · analyze_step · ProgramProfile · ProgramAnalysis · register_profile`
   - `lint_job · LintRule · LintConfig · register_lint_rule · lint_to_sarif`
   - `resolve_includes · IncludeMemberLoader · DictMemberLoader · JCLLIBMemberLoader`
   - `parse_jes_control` and typed JES statement classes

## Quality Bar for Each Page

- Every public function shown with at least one working code example
- JSON output shapes documented for any function/command that supports `--json`
- No TBD sections — all sections are complete before implementation starts
- Consistent code style with existing docs (no import aliases, bare `print()` calls for output)

## Out of Scope

- Docstring changes inside source files — the docs are the target
- API design changes
- New features
- `docs/superpowers/` files (plans, specs)
