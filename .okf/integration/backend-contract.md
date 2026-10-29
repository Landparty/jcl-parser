---
type: Integration Contract
title: Backend Adapter Contract
description: Stability contract between jcl-parser and backend/src/parsers/jcl/parser.py (JCLLegacyParser); changes to listed attributes are breaking changes.
tags: [integration, backend, contract, vendoring]
timestamp: 2026-10-29T00:00:00Z
---

# Overview

jcl-parser is **not installed from PyPI**. It is vendored into `backend/_vendor/jcl-parser/`. Changes must be manually synced:

```bash
rm -rf ../backend/_vendor/jcl-parser/jclparser && cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser
```

Do not use plain `cp -r jclparser/ dest/jclparser/` — when the destination already exists, `cp -r` nests into it (`dest/jclparser/jclparser/`) and silently leaves the old files in place.

The backend imports from `backend/_vendor/jcl-parser/`.

# Entry Points the Backend Calls

## 1. parse_jcl

```python
job = parse_jcl(content: str)   # returns Job (never None); raises JCLSyntaxError | JCLValidationError | JCLStructureError | JCLParseError
```

The adapter passes uploaded **text**. A `str` is always parsed as JCL content and never opened as a file, whatever it looks like (so a one-line upload such as `/etc/passwd` cannot read a server file); to read a file, pass a `pathlib.Path`.

## 2. job.validate()

```python
validation_errors = (
    job.validate()
)  # list[ValidationError] — stringified with str() for error_message fields
```

The list also holds WARNING-severity findings (`.is_warning`; `[WARNING]` in `str()`), such as a PROC not found in any configured library, so a non-empty list does not by itself mean the job is invalid.

## 3. job.explode()

```python
exploded_job = job.explode(
    max_depth=10, audit=True, strict_symbols=False, loader=proc_loader
)
```

Catches `JCLParseError` (including `ProcedureNotFoundError`) and falls back to un-exploded job.

## 4. Loader Construction

```python
loader = CompositeProcedureLoader(
    [
        InlineProcedureLoader(job.procedures),  # inline always first
        external_loader,  # DB-sourced external loader
    ]
)
```

# Object Attribute Contract

## Job

`job.name`, `job.steps`, `job.procedures`, `job.validate()`, `job.explode(...)`, `job.explosion_audit`, `job.explosion_map`

`job.steps` is `list[Step | ConditionalBlock]`: an `// IF` block has no `.name`, and the steps inside it are only reachable through its `then_steps` / `else_steps`. Iterate `iter_execution_steps(job.steps)` (re-exported from `jclparser`) to visit every execution step.

Other `Job` fields (e.g. `job.custom_statements`) are not read by the adapter; see [core/data-model](../core/data-model.md).

## Step

`step.name`, `step.program`, `step.is_exploded`, `step.procedure`, `step.is_procedure`,
`step.original_proc_call`, `step.parameters`, `step.line_number`, `step.dd_statements`

There is no `step.is_proc_invocation`; the PROC-call test is the `step.is_procedure` property (`step.procedure is not None`).

## DD

`dd.name`, `dd.dataset_name`, `dd.disposition`, `dd.parameters`

## Explosion Audit Entry

`.step_name`, `.proc_name`, `.parameters`, `.depth`, `.expanded_steps`

# Output Shape: program_structure

The adapter produces this dict for `ParserResult`:

```python
{
    "program_info": {"name", "type": "JCL", "language_version", "encoding", "line_count", "complexity_score"},
    "structure": {"sections", "variables", "procedures"},
    "dependencies": {"includes": [{"proc_name": ...}], "calls": [str], "databases": [dict], "procedure_definitions"},
    "execution_details": [...],   # per-step detail with DD statements
    "analysis": {"metrics", "issues", "modernization_hints"},
    # Optional:
    "is_batch_entry_point": bool,
    "batch_entry_metadata": dict,
    "procedure_expansion": {"expanded_steps", "expansion_audit", "expansion_map", "original_step_count", "expanded_step_count"},
}
```

## Critical Paths for Relationship Extraction

| Path | Neo4j relationship |
|------|--------------------|
| `dependencies.includes[*].proc_name` | `CALLS_PROC` |
| `dependencies.calls[*]` | `CALLS` |
| `execution_details[*].dd_statements` | dataset binding |

# File Extensions Handled

`.jcl`, `.jcllib`, `.job`, `.prc`, `.proc` (and uppercase). Standalone PROC files are wrapped in a synthetic `//LEGACYLN JOB` statement and annotated with `is_procedure_definition=True`.

The wrapper name must be a valid 1-8 character job name. `job.validate()` treats in-stream procedures as the job's content, so a valid PROC wrapped as `//LEGACYLN JOB` + the member validates clean (no "at least one execution step" error, #100).

# Pending Backend Adapter Changes

The adapter lives outside this repo. These library-side changes need a matching adapter change at the next vendor sync:

| Change | Adapter action |
|--------|----------------|
| `job.steps` holds `ConditionalBlock`s (#99) | Iterate `iter_execution_steps(job.steps)` (or skip `ConditionalBlock` elements) wherever step attributes are read off `job.steps` / `exploded_job.steps`; otherwise the first `// IF` raises `AttributeError` and the steps inside IF blocks are missed |
| `step.is_proc_invocation` never existed | Read `step.is_procedure` |
| Synthetic PROC wrapper (#100) | Emit `//LEGACYLN JOB` instead of the 10-character `//LEGACYLENS JOB`, which fails the job-name rule |

# Citations

[1] [../../interface-contract.md](../../interface-contract.md) — the source contract this mirrors
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — loader chaining detail
[3] [api/public-api.md](../api/public-api.md) — importable names and tiers
