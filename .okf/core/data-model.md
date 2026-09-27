---
type: Data Model
title: JCL Data Model
description: Hierarchy of Job, Step, DDStatement, ConditionalBlock, and Procedure objects returned by parse_jcl().
tags: [model, core, data-model]
timestamp: 2026-09-16T00:00:00Z
---

# Overview

`parse_jcl()` returns a `Job` object. Everything else hangs off it. Every class
below is a `@dataclass` in `jclparser/model.py`; the tables list the real
dataclass fields, with `()` marking callables (methods/properties) rather than
fields — the distinction matters, `dd.is_temporary` is a bound method, not a
`bool`.

`Job`, `Step`, `DDStatement`, `Statement`, `OutputStatement` and `Parameter` are
re-exported from `jclparser`. **`ConditionalBlock` and `Procedure` are not** —
import them from `jclparser.model` if you need the names (they are reachable
without importing, via `job.steps` / `job.procedures`).

# Schema

## Job

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | From `//JOBNAME JOB` card; required, not optional |
| `parameters` | `dict[str, Any]` | JOB card params (CLASS, MSGCLASS, NOTIFY…) |
| `accounting_info` | `str \| None` | First positional (`_pos_0`) of the JOB card |
| `steps` | `list[Step \| ConditionalBlock]` | Executable structure only |
| `procedures` | `list[Procedure]` | Inline `PROC…PEND` blocks |
| `conditionals` | `list[ConditionalBlock]` | Flat list of IF/THEN/ELSE blocks |
| `set_statements` | `dict[str, str]` | SET symbol definitions |
| `jcllib_order` | `list[str]` | JCLLIB library concatenation |
| `includes` | `list[str]` | INCLUDE member references |
| `comments` | `list[str]` | Present on the model but never populated — see invariant 8 |
| `line_number` | `int` | Default `0` |
| `explosion_audit` / `explosion_map` | `list[Any]` / `dict[str, Any]` | Populated by `explode_job(audit=True)` |
| `jes_statements` | `list[str]` | `/*JOBPARM`, `/*ROUTE`… raw text |
| `jes_typed_statements` | `list[Any]` | Same cards promoted to typed models; unknown JES commands stay raw-only |
| `output_statements` | `list[OutputStatement]` | OUTPUT statements |
| `joblib_dds` | `list[DDStatement]` | JOBLIB concatenation |
| `control_statements` | `list[Statement]` | `COMMAND` / `SCHEDULE` / `CNTL` kept verbatim; a CNTL block's records live in `parameters["_records"]` |
| `sql_detections` | `dict[str, Any]` | Keyed by step name; only with `ParserConfig(detect_sql=True)` |
| `unresolved_output_refs` | `list[tuple[str, str, int]]` | `OUTPUT=*.name` refs with no definition |
| `exported_symbols` | `set[str]` | From `EXPORT SYMLIST=(...)`; `"*"` exports every SET symbol |
| `warnings` | `list[str]` | **Plain strings, not `ParseError`.** Non-fatal issues; parsing never fails on these |

There is **no** `job.statements` and **no** `job.errors` field. Parse errors are
raised as exceptions or returned by `validate_jcl()`; non-fatal issues land in
`job.warnings` as strings.

Useful accessors (not fields): `job.validate()`, `job.explode(...)`,
`job.get_step()`, `job.get_dd_statements()`, `job.get_sysin_statements()`,
`job.get_library_search_order()`, plus JOB-card properties (`job_class`,
`msgclass`, `notify`, `region`, `time`, `cond`, `restart`, `typrun`, …).

## Step

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str \| None` | Max 8 chars; may be `None` for an unnamed EXEC |
| `program` | `str \| None` | `PGM=` value |
| `procedure` | `str \| None` | PROC name being invoked (there is no `proc_name`) |
| `parameters` | `dict[str, Any]` | EXEC params (PARM, COND, TIME, REGION…) |
| `dd_statements` | `list[DDStatement]` | |
| `comments` | `list[str]` | Never populated — see invariant 8 |
| `line_number` | `int` | Default `0`, never `None` |
| `is_exploded` | `bool` | True after `explode_job()` |
| `original_proc_call` | `str \| None` | Set after explosion |
| `dd_overrides` | `dict[str, DDStatement]` | Qualified `PROCSTEP.DDNAME` overrides |
| `is_procedure()` | property → `bool` | **This is how you test for a PROC invocation.** Equivalent to `step.procedure is not None` |

There is **no** `exec_type` and **no** `is_proc_invocation` attribute anywhere in
the codebase; use `step.procedure` / `step.is_procedure`.

## DDStatement

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | DD name, max 8 chars |
| `dataset_name` | `str \| None` | `DSN=` value, or `DSNAME=` (its long form) when no `DSN=` is coded |
| `coded_dataset_name` | `str \| None` | The dataset name as coded, before SET / PROC symbol substitution (`&HLQ..DATA` while `dataset_name` reads `PROD.DATA`); `None` when the coded name had no symbols. Not part of `==` or `repr` |
| `disposition` | `str \| None` | `DISP=` raw string |
| `parameters` | `dict[str, Any]` | DSN, DISP, SPACE, DCB, SYSOUT… |
| `inline_data` | `str \| None` | Content between `DD *` and `/*`, as **one string** (there is no `instream_data` list). Data records after a step with no `DD *` / `DD DATA` ahead of them get an implicit `SYSIN` DD (`parameters={"*": True}`), as JES does, plus a `job.warnings` entry |
| `comments` | `list[str]` | Never populated — see invariant 8 |
| `line_number` | `int` | |
| `output_refs` | `list[OutputStatement]` | Resolved `OUTPUT=*.name` back-references |
| `is_temporary()` | method → `bool` | True when `dataset_name` starts with `&&`. **Call it** |
| `is_input()` / `is_output()` | methods → `bool` | Derived from DISP status tokens |
| `has_inline_data` | property → `bool` | |
| `dcb` / `space` | properties | Typed `DCBParameter` / `SPACEParameter` from `parameter_ast.py` |
| `dataclas` / `mgmtclas` / `storclas` / `dsntype` | properties → `str \| None` | SMS classes |

There is no `is_sysout` attribute — read `dd.parameters.get("SYSOUT")`.

## ConditionalBlock

| Field | Type | Notes |
|-------|------|-------|
| `condition` | `str` | Raw condition — **always present, authoritative** |
| `then_steps` | `list[Step \| ConditionalBlock]` | |
| `else_steps` | `list[Step \| ConditionalBlock]` | |
| `line_number` | `int` | |
| `condition_ast` | `ConditionNode \| None` | May be None if unparseable — never rely solely on this |

## Procedure

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | |
| `parameters` | `dict[str, Any]` | Default symbolic parameter values |
| `steps` | `list[Step \| ConditionalBlock]` | |
| `line_number` | `int` | |
| `is_external` | `bool` | True when loaded through the loader chain rather than inline |

## Statement

The generic pre-model record produced by `parse_statement()`:
`type`, `name`, `parameters`, `line_number`, `warnings`. Note `Statement` has no
`COMMENT` type — comment lines never reach the model (invariant 8).

## Condition AST Node Types

`ReturnCodeCondition`, `AbendCondition`, `RunCondition`, `NotCondition`, `AndCondition`, `OrCondition` — all importable from `jclparser`.

`parse_condition()` accepts both keyword and symbolic Boolean operators (`AND`/`&`, `OR`/`|`, `NOT`/`¬`, with `^`/`~` for `¬`) and `ABEND`/`RUN` tests written as `= TRUE` / `= FALSE`. It returns `None` rather than a partial AST whenever it cannot consume the whole expression: `ABENDCC` tests, a non-numeric RC value (`RC GT &MAX`), leftover tokens. A missing final `)` and a stray trailing `)` are tolerated. When evaluating, a condition with no step name follows IBM semantics: `RC` is the **highest** RC of the steps in `step_results`, and `ABEND` is true if **any** of them abended.

# Key Field Notes

- **Comments are dropped.** `Job.comments` / `Step.comments` / `DDStatement.comments`
  exist but are never populated, and there is no `job.statements` holding raw
  statements. The only statements kept verbatim are `COMMAND` / `SCHEDULE` /
  `CNTL`, in `job.control_statements`. See [development/invariants](../development/invariants.md) #8.
- `ConditionalBlock.condition` is always set; `condition_ast` may be `None`.
- `DDStatement.is_temporary()` is a **method**: `dd.is_temporary()`, not `dd.is_temporary`.
  `True` when `DSN=&&TEMP...` — double-`&&` signals a temporary dataset.
- Before `explode_job()`: PROC-calling steps have `procedure` set and
  `is_procedure` true. After: replaced by expanded steps with `is_exploded=True`
  and `original_proc_call` set.

# Citations

[1] [core/parsing-pipeline.md](parsing-pipeline.md) — how the Job object is built
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — how `explode_job()` changes Step objects
[3] [development/invariants.md](../development/invariants.md) — invariant 8 (comments dropped)
