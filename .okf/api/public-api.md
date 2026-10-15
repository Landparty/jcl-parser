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

`Job`, `Step`, `DDStatement`, `Parameter`, `Statement`, `OutputStatement`, `ConditionalBlock`

`iter_execution_steps(job.steps)` yields every `Step`, flattening `// IF` blocks: `job.steps`
is `list[Step | ConditionalBlock]`, so code that needs every execution step must use it
(re-exported with `ConditionalBlock` since 2026-10-15, issue #99).
`Job.is_procedure_member` is `True` for the synthetic `Job(name="")` returned for a JOB-less
PROC member; `job.validate()` and the JOB-card lint rules skip the JOB-statement checks for it
(issue #98).

`Procedure` is part of the model but is **not** re-exported from `jclparser` — import it from
`jclparser.model`.

## Error / Enum Types

`JCLParseError` (common base), `JCLSyntaxError`, `JCLValidationError`, `JCLStructureError`, `ParseError`, `ValidationError`, `UndefinedSymbolError`, `CircularProcedureError`, `ExplosionDepthError`, `ProcedureNotFoundError`, `ErrorType`, `ErrorSeverity`, `ValidationLevel`

# Tier 2 — Advanced

Stable but may evolve. Key groups:

| Group | Key Exports |
|-------|-------------|
| PROC Expansion | `explode_job`, `SymbolScope`, `create_default_loader`, `DictProcedureLoader`, `CompositeProcedureLoader`, `ProcedureLoader`, `BUILTIN_UTILITY_PROCS`, `create_builtin_proc_loader`, `SystemSymbolProvider` (`explosion.DEFAULT_MAX_STEPS` is not re-exported) |
| Plugin System | `ParserConfig`, `StatementPlugin`, `ValidationPlugin`, `PluginRegistry`, `get_plugin_registry` (`PluginRegistry.unregister_plugin(name_or_instance)`: by class name it removes the most recently registered instance of that class — call again for earlier ones — or pass the instance itself; returns `False` when nothing matched. Several instances of one class can be registered and removed independently since 2026-09-28). **Plugins are opt-in** (2026-10-04): a registered plugin runs only when the `ParserConfig` passed to `parse_jcl` / `validate_jcl` / `parse_statement` names its class in `enabled_plugins` (or holds `ALL_PLUGINS`, `"*"`); no config means no plugins. `ParserConfig` fields: `strict_mode` (OR-ed with the `strict_mode=` keyword), `dialect` (`SUPPORTED_DIALECTS`: `standard` = JES2 `/*` and JES3 `//*` control statements both recognised; `jes2` = `//*` is only a comment; `jes3` = `/*` JES2 control statements other than `SIGNON`/`SIGNOFF` are kept as text in `job.jes_statements` but not typed, with a `job.warnings` entry; unknown → `ValueError`), `validation_level` (the `validate_jcl` default; a string is coerced), `detect_sql`. External PROC and INCLUDE members are still parsed with the default config. **What a `StatementPlugin` returns** (2026-10-15, #130): a `Statement` with a built-in `type` (`EXEC`, `DD`, …) is processed like a native statement; any other (custom) type is kept verbatim, in source order, in `job.custom_statements` (it used to be dropped without a trace). `StatementPlugin.statement_types` is advisory metadata naming the types the plugin returns — the parser does not dispatch on it (`can_parse` selects the plugin) |
| Validation | `validate_jcl_identifier`, `validate_dataset_name`, `validate_job_structure`, `validate_step_structure`, `validate_dd_statement` (step names go through `validators.validate_step_name`, which also accepts exploded `S1.PS1` names; not re-exported) |
| File Type Detection | `FileType`, `detect_file_type`, `detect_file_type_from_content`, `is_jcl_file`, `is_proc_file` |
| Condition Parsing | `parse_condition`, `ConditionNode`, `ReturnCodeCondition`, `AbendCondition`, `RunCondition`, `NotCondition`, `AndCondition`, `OrCondition` (operators include `NG`/`NL`; `evaluate()` accepts `condition_parser.NOT_RUN` — import it from `jclparser.condition_parser` — for a step that did not run, which makes its `RC`/`ABEND`/`RUN` tests false) |
| SQL/DB2 Detection | `SQLDetectionResult`, `detect_sql_in_step(step, procedure=None)` (on an unexploded PROC call it also scans the `//PROCSTEP.DD` overrides, each read as input to the program of the procstep it names in `procedure` -- `detect_sql_in_job` passes the called PROC -- else to the program a PROC in `sql_detector.PROCEDURE_PROGRAMS` runs, e.g. `DSNUPROC` -> `DSNUTILB`; issues #94, #106), `detect_sql_in_job`, `detect_sql_in_dd`, `detect_sql_in_text`, `is_db2_program`, `DB2_PROGRAMS`. Not re-exported (import from `jclparser.sql_detector`): `NON_SQL_CONTROL_PROGRAMS` (programs whose in-stream data `detect_sql_in_step` does not scan; in `SYSTSIN` — and in unnamed DDs concatenated to it — only DB2 subcommands such as `BIND` count) `DB2_PROCEDURES` (a step executing one of these PROCs — `DSNUPROC`, `DSNH*` — has `is_db2_program` set on an unexploded job), and `DB2_UTILITY_CONTROL_PROGRAMS` (`DSNUTILB`: its in-stream data is DB2 utility control statements, so only `EXEC SQL ... ENDEXEC` utility statements contribute SQL — the `EXEC SQL` marker and the SQL keywords between it and `ENDEXEC`, on the same line or not; `RUNSTATS ... UPDATE ALL` / `MODIFY RECOVERY ... DELETE AGE(90)` are not DML; scanner `detect_sql_in_utility_statements(text)`) |
| INCLUDE Expansion | `resolve_includes`, `IncludeMemberLoader`, `DictMemberLoader`, `JCLLIBMemberLoader` |
| Dataset Lifecycle | `DatasetEvent`, `analyze_dataset_lifecycle`, `validate_dataset_lifecycle` (only a *normal* `UNCATLG`/`DELETE` counts as uncataloging; an abnormal one such as `DISP=(OLD,KEEP,UNCATLG)` does not; any normal `CATLG`, `MOD,CATLG` included, catalogs; `DSN=*.STEP.DD` referbacks are recorded under the referenced dataset; IF/THEN/ELSE branches are checked separately and merged at ENDIF; members of one PDS are checked as the library, GDG relative generations stay separate (#81) — see [advanced/validation](../advanced/validation.md#dataset-lifecycle-validation)) |
| JES Control | `JESControlStatement`, `JobParmStatement`, `RouteStatement`, `XmitStatement`, `SignonStatement`, `MessageStatement`, `NetacctStatement`, `NotifyStatement`, `PriorityStatement`, `Jes3RouteXeqStatement`, `parse_jes_control` |
| Metrics / RC | `JobMetrics`, `compute_metrics` (dataset counts resolve a `DSN=*.STEP.DD` backward reference to the referenced DD's dataset and skip `NULLFILE`), `FeasibilityReport`, `compute_feasible_paths`, `DEFAULT_RC_DOMAIN` (IF conditions only — step `COND=` is not analysed; an IF's predecessors are the steps before it in execution order, and a step inside an IF branch or with `COND=` is also explored as not run, `condition_parser.NOT_RUN`; with `include_abends=True` (the default) so is every step after the first in execution order, since any predecessor may abend and z/OS then bypasses it, so the abend-recovery test `IF NOT S1.RUN` / `S1.RUN = FALSE` is reachable (since 2026-10-13, issue #86; only the job's first step is certain to run); with `include_abends=False` abends are not modelled, so an IF testing `RUN` or `ABEND` (any polarity) is not judged and goes to `unanalysed_conditions` with that reason; on an unexploded job a `STEP.PROCSTEP` test of a PROC call is too, since the PROC's steps are not in the job). The search is exact over RCs 0..4095: each step gets one representative RC per class of the constants the condition compares it against, so `IF (S1.RC GT 4 AND S1.RC LT 8)` and `RC GT 16` are reachable; only `RC GT 4095` and contradictions are unsatisfiable. `compute_feasible_paths(rc_domain=...)` (default `DEFAULT_RC_DOMAIN` = `(0, 4, 8, 12, 16)`) only picks the *preferred* representative of each class — it does **not** limit the RCs explored (changed 2026-09-28). A step is reported `unreachable` / `always_skipped` only when **every** explored combination evaluated to a definite value: one unknown (`None`) evaluation means nothing is claimed (since 2026-10-04, issue #61). The search is bounded by its **size**, not by a step count: when the product of every named step's outcome count (RC classes × ABEND × not-run) exceeds `rc_analysis.MAX_COMBINATIONS` (250,000, about a second of evaluation), the IF is not analysed — nothing is claimed about its branches and `(condition, reason)` goes to `FeasibilityReport.unanalysed_conditions`, which `is_empty()` ignores (since 2026-10-04, issue #65; an 8-step cap used to drop named steps, and still let a condition with a few constants per step run for hours). `duplicate_if_branches` lists a nested IF whose condition text repeats an *enclosing* IF's (sibling IFs are not compared) only when nothing between the two can change the result: no step runs between them, or the condition has no unqualified `RC`/`ABEND`/`RUN` atom (those cover every step run so far) and none of the steps it names runs between them (since 2026-10-15, issue #109; `IF RC = 0` re-tested after another step used to be reported) |
| Lint | `LintRule`, `LintConfig`, `lint_job`, `lint_to_sarif`, `register_lint_rule` (`JCL-LINT-001` hard-coded HLQ skips `*.STEP.DD` referbacks and `NULLFILE`) |
| Program Profiles | `ProgramProfile`, `ProgramAnalysis`, `register_profile`, `analyze_step`, `analyze_job`. The `IKJEFT01`/`IKJEFT1A`/`IKJEFT1B` and DB2 batch (`DSNTEP2`/`DSNTEP4`/`DSNTIAD`/`DSNTIAUL`) profiles take their `embedded SQL: ...` note from `detect_sql_in_step`, so a TSO `DELETE` / `ALTER` in SYSTSIN is not SQL there either (since 2026-10-04, issue #66; they used to scan the raw SYSTSIN + SYSIN + PARM text unfiltered). `is_db2_program` still flags the IKJEFT01 wrappers as possible DB2 drivers. Copy / sort profiles (since 2026-10-13, issue #82): `IEBCOPY` reports the `INDD` -> `OUTDD` pairs of its SYSIN `COPY` / `COPYMOD` / `COPYGRP` statements (abbreviations, `INDD=(A,(B,R))` lists, separate `INDD=` statements; `SELECT` / `EXCLUDE MEMBER=` lists as `select members ...` / `exclude members ...` notes) and falls back to SYSUT1 -> SYSUT2 only with no copy statement; `IEBGENER` / `ICEGENER` / `IEBCOPY` report every dataset of a concatenated input DD; `SORT` reports `input:` for every dataset of SORTIN and SORTIN01-SORTIN99, reads each control statement as label / operation / operands with the rest of the line a remark (comma and column-72 continuations, `*` comment cards; `program_profiles/_control.py`), and reports `SORT`/`MERGE FIELDS=COPY` and `OPTION COPY` as a `COPY` note with summary `<program>: copy with N control clauses`. Since 2026-10-15 (issue #110) `SORT` also reports `output:` for each `OUTFIL`'s DDs — `FNAMES=dd` / `FNAMES=(a,b)` as named, `FILES=x` as `SORTOFx`, `SORTOUT` for an `OUTFIL` naming neither — and `input:` for the `JOINKEYS` files: `SORTJNF1` / `SORTJNF2` for `FILE=F1` / `FILE=F2`, or the DD named by `F1=` / `F2=`. `FTP` (since 2026-10-15, issue #111) reads its commands from the `INPUT` DD, and from `SYSIN` only when there is no `INPUT` DD (an `INPUT` naming a dataset gives a `commands from INPUT: <dsn>` note). The host is the first `PARM=` operand (after any `/`-ended LE options) or, without one, the first input line (`OPEN <host>` note); the line after it is the login reply, of which only the user ID is reported (`USER <id>`) — the password is never put in `notes` (`raw_control` still holds the raw command text) |

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
