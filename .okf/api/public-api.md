---
type: API Reference
title: jclparser Public API
description: All exports from jclparser/__init__.py, organized by stability tier; only Tier 1 should be used in new external integrations.
tags: [api, stability, exports]
timestamp: 2026-09-16T00:00:00Z
---

# Overview

Three stability tiers govern the API. **Only Tier 1 is safe for new external integrations.**

# Tier 1 — Stable

Will not be removed or signature-broken without a major version bump.

## Core Functions

| Export | Description |
|--------|-------------|
| `parse_jcl(source, ...)` | Main entry — parses JCL text (`str`), a file (`pathlib.Path`) or an IO; returns `Job`. A `str` is never treated as a file name (since 2026-10-03) |
| `parse(source, ...)` | Alias for `parse_jcl` |
| `validate_jcl(source, level="basic")` | `parse_jcl(strict_mode=True)` + structural checks; returns a flat `list[ParseError]` (empty when valid). `level` is a plain `str`: `"basic"` / `"structure"` / `"semantic"` |
| `parse_statement(line, line_number=0)` | Parse a single JCL statement line in isolation; returns `Statement \| None` |

## Model Classes

`Job`, `Step`, `DDStatement`, `Parameter`, `Statement`, `OutputStatement`

`ConditionalBlock` and `Procedure` are part of the model but are **not** re-exported from
`jclparser` — import them from `jclparser.model`.

## Error / Enum Types

`JCLSyntaxError`, `JCLValidationError`, `JCLStructureError`, `ParseError`, `ValidationError`, `UndefinedSymbolError`, `CircularProcedureError`, `ExplosionDepthError`, `ProcedureNotFoundError`, `ErrorType`, `ErrorSeverity`, `ValidationLevel`

# Tier 2 — Advanced

Stable but may evolve. Key groups:

| Group | Key Exports |
|-------|-------------|
| PROC Expansion | `explode_job`, `SymbolScope`, `create_default_loader`, `DictProcedureLoader`, `CompositeProcedureLoader`, `ProcedureLoader`, `BUILTIN_UTILITY_PROCS` |
| Plugin System | `ParserConfig`, `StatementPlugin`, `ValidationPlugin`, `PluginRegistry`, `get_plugin_registry` (`PluginRegistry.unregister_plugin(name_or_instance)`: by class name it removes the most recently registered instance of that class — call again for earlier ones — or pass the instance itself; returns `False` when nothing matched. Several instances of one class can be registered and removed independently since 2026-09-28) |
| Validation | `validate_jcl_identifier`, `validate_dataset_name`, `validate_job_structure`, `validate_step_structure`, `validate_dd_statement` (step names go through `validators.validate_step_name`, which also accepts exploded `S1.PS1` names; not re-exported) |
| File Type Detection | `FileType`, `detect_file_type`, `detect_file_type_from_content`, `is_jcl_file`, `is_proc_file` |
| Condition Parsing | `parse_condition`, `ConditionNode`, `ReturnCodeCondition`, `AbendCondition`, `RunCondition`, `NotCondition`, `AndCondition`, `OrCondition` (operators include `NG`/`NL`; `evaluate()` accepts `condition_parser.NOT_RUN` — import it from `jclparser.condition_parser` — for a step that did not run, which makes its `RC`/`ABEND`/`RUN` tests false) |
| SQL/DB2 Detection | `SQLDetectionResult`, `detect_sql_in_step`, `detect_sql_in_job`, `detect_sql_in_dd`, `is_db2_program`, `DB2_PROGRAMS`, `NON_SQL_CONTROL_PROGRAMS` (a step executing a DB2 PROC in `sql_detector.DB2_PROCEDURES` — `DSNUPROC`, `DSNH*` — has `is_db2_program` set on an unexploded job) (programs whose in-stream data `detect_sql_in_step` does not scan; in `SYSTSIN` — and in unnamed DDs concatenated to it — only DB2 subcommands such as `BIND` count) |
| INCLUDE Expansion | `resolve_includes`, `IncludeMemberLoader`, `DictMemberLoader`, `JCLLIBMemberLoader` |
| Dataset Lifecycle | `DatasetEvent`, `analyze_dataset_lifecycle`, `validate_dataset_lifecycle` (only a *normal* `UNCATLG`/`DELETE` counts as uncataloging; an abnormal one such as `DISP=(OLD,KEEP,UNCATLG)` does not; any normal `CATLG`, `MOD,CATLG` included, catalogs; `DSN=*.STEP.DD` referbacks are recorded under the referenced dataset; IF/THEN/ELSE branches are checked separately and merged at ENDIF — see [advanced/validation](../advanced/validation.md#dataset-lifecycle-validation)) |
| JES Control | `JESControlStatement`, `JobParmStatement`, `RouteStatement`, `XmitStatement`, `parse_jes_control` |
| Metrics / RC | `JobMetrics`, `compute_metrics` (dataset counts resolve a `DSN=*.STEP.DD` backward reference to the referenced DD's dataset and skip `NULLFILE`), `FeasibilityReport`, `compute_feasible_paths`, `DEFAULT_RC_DOMAIN` (IF conditions only — step `COND=` is not analysed; an IF's predecessors are the steps before it in execution order, and a step inside an IF branch or with `COND=` is also explored as not run, `condition_parser.NOT_RUN`). The search is exact over RCs 0..4095: each step gets one representative RC per class of the constants the condition compares it against, so `IF (S1.RC GT 4 AND S1.RC LT 8)` and `RC GT 16` are reachable; only `RC GT 4095` and contradictions are unsatisfiable. `compute_feasible_paths(rc_domain=...)` (default `DEFAULT_RC_DOMAIN` = `(0, 4, 8, 12, 16)`) only picks the *preferred* representative of each class — it does **not** limit the RCs explored (changed 2026-09-28) |
| Lint | `LintRule`, `LintConfig`, `lint_job`, `lint_to_sarif`, `register_lint_rule` (`JCL-LINT-001` hard-coded HLQ skips `*.STEP.DD` referbacks and `NULLFILE`) |
| Program Profiles | `ProgramProfile`, `ProgramAnalysis`, `register_profile`, `analyze_step`, `analyze_job` |

# Tier 3 — Internal

May be removed without notice. Three of the five are **not** re-exported from the
`jclparser` top level and must be imported from their defining module:

| Name | Top-level export? | Import from |
|------|-------------------|-------------|
| `MockSystemSymbolProvider` | no | `jclparser.system_symbols` |
| `InlineProcedureLoader` | no | `jclparser.proc_loader` |
| `JCLLIBProcedureLoader` | no | `jclparser.proc_loader` |
| `FunctionProfile` | yes | `jclparser` or `jclparser.profiling` |
| `ProfilingResult` | yes | `jclparser` or `jclparser.profiling` |

# Citations

[1] [core/data-model.md](../core/data-model.md) — field-level detail for the model classes
[2] [api/cli-reference.md](cli-reference.md) — CLI subcommands
