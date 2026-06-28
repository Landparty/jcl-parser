---
type: Data Model
title: JCL Data Model
description: Hierarchy of Job, Step, DDStatement, ConditionalBlock, and Procedure objects returned by parse_jcl().
tags: [model, core, data-model]
timestamp: 2026-06-28T00:00:00Z
---

# Overview

`parse_jcl()` returns a `Job` object. Everything else hangs off it.

# Schema

## Job

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str \| None` | From `//JOBNAME JOB` card |
| `parameters` | `dict[str, Any]` | JOB card params (CLASS, MSGCLASS, NOTIFY…) |
| `statements` | `list[Statement]` | All raw statements including comments |
| `steps` | `list[Step \| ConditionalBlock]` | Executable structure only |
| `procedures` | `list[Procedure]` | Inline `PROC…PEND` blocks |
| `output_statements` | `list[OutputStatement]` | OUTPUT statements |
| `errors` | `list[ParseError]` | Parse errors |
| `warnings` | `list[ParseError]` | Parse warnings |

## Step

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | Max 8 chars |
| `exec_type` | `"PGM" \| "PROC"` | |
| `program` | `str \| None` | PGM= value |
| `proc_name` | `str \| None` | PROC name being invoked |
| `parameters` | `dict[str, Any]` | EXEC params (PARM, COND, TIME, REGION…) |
| `dd_statements` | `list[DDStatement]` | |
| `is_exploded` | `bool` | True after `explode_job()` |
| `is_proc_invocation` | `bool` | True if step invokes a PROC (pre-explosion) |
| `original_proc_call` | `str \| None` | Set after explosion |
| `line_number` | `int \| None` | |

## DDStatement

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | DD name, max 8 chars |
| `parameters` | `dict[str, Any]` | DSN, DISP, SPACE, DCB, SYSOUT… |
| `dataset_name` | `str \| None` | DSN= value |
| `disposition` | `str \| None` | DISP= raw string |
| `is_temporary` | `bool` | True if DSN starts with `&&` |
| `is_sysout` | `bool` | True if SYSOUT= is set |
| `instream_data` | `list[str]` | Lines between `DD *` and `/*` |
| `line_number` | `int` | |

## ConditionalBlock

| Field | Type | Notes |
|-------|------|-------|
| `condition` | `str` | Raw condition — **always present, authoritative** |
| `condition_ast` | `ConditionNode \| None` | May be None if unparseable — never rely solely on this |
| `then_steps` | `list[Step \| ConditionalBlock]` | |
| `else_steps` | `list[Step \| ConditionalBlock]` | |

## Procedure

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | |
| `steps` | `list[Step]` | |
| `parameters` | `dict[str, str]` | Default symbolic parameter values |

## Condition AST Node Types

`ReturnCodeCondition`, `AbendCondition`, `RunCondition`, `NotCondition`, `AndCondition`, `OrCondition` — all importable from `jclparser`.

# Key Field Notes

- `job.statements` vs `job.steps`: `statements` is all statements including comments; `steps` is only `Step` / `ConditionalBlock` — the executable structure.
- `ConditionalBlock.condition` is always set; `condition_ast` may be `None`.
- `DDStatement.is_temporary`: `True` when `DSN=&&TEMP...` — double-`&&` signals a temporary dataset.
- Before `explode_job()`: PROC-calling steps have `exec_type="PROC"`, `is_proc_invocation=True`. After: replaced by expanded steps with `is_exploded=True`.

# Citations

[1] [core/data-model.md](data-model.md) — full data model doc
[2] [core/parsing-pipeline.md](parsing-pipeline.md) — how the Job object is built
[3] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — how `explode_job()` changes Step objects
