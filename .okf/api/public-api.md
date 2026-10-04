---
type: API Reference
title: jclparser Public API
description: All exports from jclparser/__init__.py, organized by stability tier; only Tier 1 should be used in new external integrations.
tags: [api, stability, exports]
timestamp: 2026-10-04T00:00:00Z
---

# Overview

Three stability tiers govern the API. **Only Tier 1 is safe for new external integrations.**

# Tier 1 — Stable

Will not be removed or signature-broken without a major version bump.

## Core Functions

| Export | Description |
|--------|-------------|
| `parse_jcl(source, ...)` | Main entry — parses JCL text (`str`), a file (`pathlib.Path`) or an IO; returns `Job` (or `(Job, ProfilingResult)` with `enable_profiling=True`). A `str` is always content, never a file name, whatever it looks like (breaking change 2026-10-03: `parse_jcl("job.jcl")` parses the text `job.jcl`; use `parse_jcl(Path("job.jcl"))`). The same holds for `validate_jcl` and `detect_file_type` |
| `parse(source, ...)` | Alias for `parse_jcl` |
| `validate_jcl(source, level="basic")` | Strict parse + `job.validate()` findings (ERRORs only at `"basic"`, all at `"structure"`/`"semantic"`); returns a flat `list[ParseError]` (empty when valid). `level` is a plain `str`: `"basic"` / `"structure"` / `"semantic"` |
| `parse_statement(line, line_number=0)` | Parse a single JCL statement line in isolation; returns `Statement \| None` |

## Model Classes

`Job`, `Step`, `DDStatement`, `Parameter`, `Statement`, `OutputStatement`

`ConditionalBlock` and `Procedure` are part of the model but are **not** re-exported from
`jclparser` — import them from `jclparser.model`.

## Error / Enum Types

`JCLParseError` (common base), `JCLSyntaxError`, `JCLValidationError`, `JCLStructureError`, `ParseError`, `ValidationError`, `UndefinedSymbolError`, `CircularProcedureError`, `ExplosionDepthError`, `ProcedureNotFoundError`, `ErrorType`, `ErrorSeverity`, `ValidationLevel`

# Tier 2 — Advanced

Stable but may evolve. Key groups:

| Group | Key Exports |
|-------|-------------|
| PROC Expansion | `explode_job`, `SymbolScope`, `create_default_loader`, `DictProcedureLoader`, `CompositeProcedureLoader`, `ProcedureLoader`, `BUILTIN_UTILITY_PROCS`, `create_builtin_proc_loader`, `SystemSymbolProvider` (`explosion.DEFAULT_MAX_STEPS` is not re-exported) |
| Plugin System | `ParserConfig`, `StatementPlugin`, `ValidationPlugin`, `PluginRegistry`, `get_plugin_registry` (`PluginRegistry.unregister_plugin(name_or_instance)`: by class name it removes the most recently registered instance of that class — call again for earlier ones — or pass the instance itself; returns `False` when nothing matched. Several instances of one class can be registered and removed independently since 2026-09-28). **Plugins are opt-in** (2026-10-04): a registered plugin runs only when the `ParserConfig` passed to `parse_jcl` / `validate_jcl` / `parse_statement` names its class in `enabled_plugins` (or holds `ALL_PLUGINS`, `"*"`); no config means no plugins. `ParserConfig` fields: `strict_mode` (OR-ed with the `strict_mode=` keyword), `dialect` (`SUPPORTED_DIALECTS`: `standard` = JES2 `/*` and JES3 `//*` control statements both recognised; `jes2` = `//*` is only a comment; `jes3` = `/*` JES2 control statements other than `SIGNON`/`SIGNOFF` are kept as text in `job.jes_statements` but not typed, with a `job.warnings` entry; unknown → `ValueError`), `validation_level` (the `validate_jcl` default; a string is coerced), `detect_sql`. External PROC and INCLUDE members are still parsed with the default config |
| Validation | `validate_jcl_identifier`, `validate_dataset_name`, `validate_job_structure`, `validate_step_structure`, `validate_dd_statement` (step names go through `validators.validate_step_name`, which also accepts exploded `S1.PS1` names; not re-exported) |
| File Type Detection | `FileType`, `detect_file_type`, `detect_file_type_from_content`, `is_jcl_file`, `is_proc_file` |
| Condition Parsing | `parse_condition`, `ConditionNode`, `ReturnCodeCondition`, `AbendCondition`, `RunCondition`, `NotCondition`, `AndCondition`, `OrCondition` (operators include `NG`/`NL`; `evaluate()` accepts `condition_parser.NOT_RUN` — import it from `jclparser.condition_parser` — for a step that did not run, which makes its `RC`/`ABEND`/`RUN` tests false) |
| SQL/DB2 Detection | `SQLDetectionResult`, `detect_sql_in_step`, `detect_sql_in_job`, `detect_sql_in_dd`, `detect_sql_in_text`, `is_db2_program`, `DB2_PROGRAMS`. Not re-exported (import from `jclparser.sql_detector`): `NON_SQL_CONTROL_PROGRAMS` (programs whose in-stream data `detect_sql_in_step` does not scan; in `SYSTSIN` — and in unnamed DDs concatenated to it — only DB2 subcommands such as `BIND` count) and `DB2_PROCEDURES` (a step executing one of these PROCs — `DSNUPROC`, `DSNH*` — has `is_db2_program` set on an unexploded job) |
| INCLUDE Expansion | `resolve_includes`, `IncludeMemberLoader`, `DictMemberLoader`, `JCLLIBMemberLoader` |
| Dataset Lifecycle | `DatasetEvent`, `analyze_dataset_lifecycle`, `validate_dataset_lifecycle` (only a *normal* `UNCATLG`/`DELETE` counts as uncataloging; an abnormal one such as `DISP=(OLD,KEEP,UNCATLG)` does not; any normal `CATLG`, `MOD,CATLG` included, catalogs; `DSN=*.STEP.DD` referbacks are recorded under the referenced dataset; IF/THEN/ELSE branches are checked separately and merged at ENDIF — see [advanced/validation](../advanced/validation.md#dataset-lifecycle-validation)) |
| JES Control | `JESControlStatement`, `JobParmStatement`, `RouteStatement`, `XmitStatement`, `SignonStatement`, `MessageStatement`, `NetacctStatement`, `NotifyStatement`, `PriorityStatement`, `Jes3RouteXeqStatement`, `parse_jes_control` |
| Metrics / RC | `JobMetrics`, `compute_metrics` (dataset counts resolve a `DSN=*.STEP.DD` backward reference to the referenced DD's dataset and skip `NULLFILE`), `FeasibilityReport`, `compute_feasible_paths`, `DEFAULT_RC_DOMAIN` (IF conditions only — step `COND=` is not analysed; an IF's predecessors are the steps before it in execution order, and a step inside an IF branch or with `COND=` is also explored as not run, `condition_parser.NOT_RUN`). The search is exact over RCs 0..4095: each step gets one representative RC per class of the constants the condition compares it against, so `IF (S1.RC GT 4 AND S1.RC LT 8)` and `RC GT 16` are reachable; only `RC GT 4095` and contradictions are unsatisfiable. `compute_feasible_paths(rc_domain=...)` (default `DEFAULT_RC_DOMAIN` = `(0, 4, 8, 12, 16)`) only picks the *preferred* representative of each class — it does **not** limit the RCs explored (changed 2026-09-28). A step is reported `unreachable` / `always_skipped` only when **every** explored combination evaluated to a definite value: one unknown (`None`) evaluation means nothing is claimed (since 2026-10-04, issue #61). The search is bounded by its **size**, not by a step count: when the product of every named step's outcome count (RC classes × ABEND × not-run) exceeds `rc_analysis.MAX_COMBINATIONS` (250,000, about a second of evaluation), the IF is not analysed — nothing is claimed about its branches and `(condition, reason)` goes to `FeasibilityReport.unanalysed_conditions`, which `is_empty()` ignores (since 2026-10-04, issue #65; an 8-step cap used to drop named steps, and still let a condition with a few constants per step run for hours) |
| Lint | `LintRule`, `LintConfig`, `lint_job`, `lint_to_sarif`, `register_lint_rule` (`JCL-LINT-001` hard-coded HLQ skips `*.STEP.DD` referbacks and `NULLFILE`) |
| Program Profiles | `ProgramProfile`, `ProgramAnalysis`, `register_profile`, `analyze_step`, `analyze_job`. The `IKJEFT01`/`IKJEFT1A`/`IKJEFT1B` and DB2 batch (`DSNTEP2`/`DSNTEP4`/`DSNTIAD`/`DSNTIAUL`) profiles take their `embedded SQL: ...` note from `detect_sql_in_step`, so a TSO `DELETE` / `ALTER` in SYSTSIN is not SQL there either (since 2026-10-04, issue #66; they used to scan the raw SYSTSIN + SYSIN + PARM text unfiltered). `is_db2_program` still flags the IKJEFT01 wrappers as possible DB2 drivers |

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
