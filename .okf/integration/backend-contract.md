---
type: Integration Contract
title: Backend Adapter Contract
description: Stability contract between jcl-parser and backend/src/parsers/jcl/parser.py (JCLLegacyParser); changes to listed attributes are breaking changes.
tags: [integration, backend, contract, vendoring]
timestamp: 2026-07-24T12:00:00Z
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
job = parse_jcl(content: str)   # returns Job | None; raises JCLSyntaxError | JCLValidationError | JCLStructureError | JCLParseError
```

## 2. job.validate()

```python
validation_errors = job.validate()   # list — stringified with str() for error_message fields
```

## 3. job.explode()

```python
exploded_job = job.explode(max_depth=10, audit=True, strict_symbols=False, loader=proc_loader)
```

Catches `JCLParseError` (including `ProcedureNotFoundError`) and falls back to un-exploded job.

## 4. Loader Construction

```python
loader = CompositeProcedureLoader([
    InlineProcedureLoader(job.procedures),  # inline always first
    external_loader,                        # DB-sourced external loader
])
```

# Object Attribute Contract

## Job

`job.name`, `job.steps`, `job.procedures`, `job.validate()`, `job.explode(...)`, `job.explosion_audit`, `job.explosion_map`

## Step

`step.name`, `step.program`, `step.is_exploded`, `step.is_proc_invocation`, `step.procedure`, `step.original_proc_call`, `step.parameters`, `step.line_number`, `step.dd_statements`

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

`.jcl`, `.jcllib`, `.job`, `.prc`, `.proc` (and uppercase). Standalone PROC files are wrapped in a synthetic JOB statement and annotated with `is_procedure_definition=True`.

# Citations

[1] [integration/backend-contract.md](backend-contract.md) — full contract doc
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — loader chaining detail
[3] [api/public-api.md](../api/public-api.md) — importable names and tiers
