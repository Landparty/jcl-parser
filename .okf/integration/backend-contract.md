---
type: Integration Contract
title: Backend Adapter Contract
description: Stability contract between jcl-parser and backend/src/parsers/jcl/parser.py (JCLLegacyParser); changes to listed attributes are breaking changes.
tags: [integration, backend, contract, vendoring]
timestamp: 2026-10-15T00:00:00Z
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

The adapter passes uploaded **text**. Since 2026-10-03 (`fix!`, commit a0c30c9) a `str` is always parsed as JCL content and never opened as a file, whatever it looks like — before, a one-line upload such as `/etc/passwd` or `X.jcl` was read from the server's filesystem. Code that passed a file *name* as a `str` must now pass `pathlib.Path`.

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

> **Correction (2026-10-15, issue #99):** `job.steps` is `list[Step | ConditionalBlock]`,
> not `list[Step]` as `interface-contract.md` used to say. An `// IF` block is a
> `ConditionalBlock` with no `.name`, and the steps inside it are only reachable through
> its `then_steps` / `else_steps`, so an adapter reading `step.name` on every element
> raises `AttributeError` on the first IF and never sees the steps inside it. Iterate
> `iter_execution_steps(job.steps)` instead — re-exported from `jclparser` (with
> `ConditionalBlock`) since this fix. Update the backend adapter at the next vendor sync.

Other `Job` fields (e.g. `job.custom_statements`, added 2026-10-15) are not read by the adapter; see [core/data-model](../core/data-model.md).

## Step

`step.name`, `step.program`, `step.is_exploded`, `step.procedure`, `step.is_procedure`,
`step.original_proc_call`, `step.parameters`, `step.line_number`, `step.dd_statements`

> **Correction (2026-09-16):** this contract, and `interface-contract.md` at the repo
> root, previously listed `step.is_proc_invocation`. **No such attribute exists on
> `Step`** — and none ever has in this repo's history, so any adapter code reading it
> raises `AttributeError`. The equivalent is the `step.is_procedure` property
> (`step.procedure is not None`). Verify the backend adapter against this before the
> next vendor sync.

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

> **Correction (2026-10-15, issue #100):** the wrapper was documented as `//LEGACYLENS JOB`,
> a 10-character job name that fails the 1-8 character rule, so `job.validate()` reported
> every wrapped PROC as invalid ("Invalid job name 'LEGACYLENS'" plus "Job must contain at
> least one execution step", since the PROC's steps live in `job.procedures`). The
> documented name is now the 8-character `LEGACYLN`, and `validate_job_structure` treats
> in-stream procedures as the job's content: a job with no top-level steps but at least one
> entry in `job.procedures` gets no "at least one execution step" error. A valid PROC
> wrapped as `//LEGACYLN JOB` + the member now gives `job.validate() == []`
> (`tests/unit/test_medium_validation_fixes.py::TestIssue100WrappedProcMember`).
> **The backend adapter lives outside this repo and still emits `//LEGACYLENS JOB`; update
> it to `//LEGACYLN JOB` at the next vendor sync.**

# Citations

[1] [../../interface-contract.md](../../interface-contract.md) — the source contract this mirrors
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — loader chaining detail
[3] [api/public-api.md](../api/public-api.md) — importable names and tiers
