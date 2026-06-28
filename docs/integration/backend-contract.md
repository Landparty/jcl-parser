---
title: Backend Integration Contract
updated: 2026-06-27
sources: LegacyLens team, 2026-06-27
---

# Backend Integration Contract

Describes exactly what the backend adapter (`backend/src/parsers/jcl/parser.py`, class `JCLLegacyParser`) calls into `jclparser` and what object shapes it expects back.

This is a **stability contract** — changes to any of the attributes below are breaking changes for the backend.

## Vendoring

jcl-parser is **not installed from PyPI**. Changes to this repo must be manually copied:

```bash
cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/
```

The backend imports from `backend/_vendor/jcl-parser/`.

## Backend Import Path

```python
from ..dependencies import parse_jcl, Job, Step, JCLParseError, JCLSyntaxError, JCLValidationError, JCLStructureError
```

All four exception types must be importable. The adapter catches them separately for error classification.

## Entry Point 1: parse_jcl

```python
from jclparser import parse_jcl

job = parse_jcl(content: str)   # returns Job | None
```

- Returns `Job` on success, `None` on unrecoverable failure.
- Raises `JCLSyntaxError | JCLValidationError | JCLStructureError | JCLParseError` on parse failures.
- Does **not** receive a filename — jclparser does not use one.

## Entry Point 2: job.validate()

```python
validation_errors = job.validate()   # list of validation error objects
```

- Items are stringified with `str()` for error_message fields.
- Empty list = no errors.

## Entry Point 3: job.explode()

```python
exploded_job = job.explode(
    max_depth=10,
    audit=True,
    strict_symbols=False,
    loader=proc_loader,       # optional, may be None
)
```

The adapter catches `JCLParseError` (including `ProcedureNotFoundError`) and falls back to the un-exploded job gracefully.

## Entry Point 4: Composite Loader

```python
from jclparser.proc_loader import CompositeProcedureLoader, InlineProcedureLoader

loader = CompositeProcedureLoader([
    InlineProcedureLoader(job.procedures),  # inline PROCs always first
    external_loader,                        # DB-sourced external loader
])
```

## Adapter Entry Point: parse_content()

```python
adapter.parse_content(
    content,                   # str
    filename=filename,         # str | None — not passed to jclparser
    proc_loader=loader,        # optional external PROC loader from backend/src/services/
)
```

---

## Job Object Contract

Attributes the adapter reads on a `Job`:

| Attribute | Type | Notes |
|-----------|------|-------|
| `job.name` | `str \| None` | Job name from `//JOBNAME JOB` card |
| `job.steps` | `list[Step]` | All job steps |
| `job.procedures` | `list` | Inline PROC definitions — fed to `InlineProcedureLoader` |
| `job.validate()` | `list` | Structural validation errors |
| `job.explode(...)` | `Job` | Returns exploded job |
| `job.explosion_audit` | `list` | Present after `explode(audit=True)` |
| `job.explosion_map` | `dict` | Present after `explode(audit=True)` |

**`explosion_audit` entries** — each entry must have:

| Field | Type |
|-------|------|
| `.step_name` | `str` |
| `.proc_name` | `str` |
| `.parameters` | `dict` |
| `.depth` | `int` |
| `.expanded_steps` | `list` |

## Step Object Contract

| Attribute | Type | Notes |
|-----------|------|-------|
| `step.name` | `str` | Step name |
| `step.program` | `str \| None` | PGM= value |
| `step.is_exploded` | `bool` | True if expanded from a PROC |
| `step.is_proc_invocation` | `bool` | True if this step invokes a PROC (pre-explosion) |
| `step.procedure` | `str \| None` | PROC name if this is a PROC call |
| `step.original_proc_call` | `str \| None` | Original PROC invocation name |
| `step.parameters` | `dict` | Step parameters |
| `step.line_number` | `int \| None` | Source line number |
| `step.dd_statements` | `list[DD]` | All DD statements |

## DD Object Contract

| Attribute | Type |
|-----------|------|
| `dd.name` | `str` |
| `dd.dataset_name` | `str \| None` |
| `dd.disposition` | `str \| None` |
| `dd.parameters` | `dict` |

---

## Output Shape: program_structure

The adapter produces this dict for the backend's `ParserResult`:

```python
{
    "program_info": {
        "name": str,                  # job.name or "UNNAMED_JOB"
        "type": "JCL",
        "language_version": "JCL/MVS",
        "encoding": "utf-8",
        "line_count": int,
        "complexity_score": float,
    },
    "structure": {
        "sections": [...],            # job sections (from JclStructureExtractor)
        "variables": [...],           # symbolic parameters / SET variables
        "procedures": [...],          # PROC invocations
    },
    "dependencies": {
        "includes": [dict],           # PROC references — each has "proc_name" key
        "calls": [str],               # program names from EXEC PGM= steps
        "databases": [dict],          # DB2 dataset references
        "procedure_definitions": [...],
    },
    "execution_details": [...],       # per-step detail with DD statements
    "analysis": {
        "metrics": {...},
        "issues": [...],
        "modernization_hints": [...],
    },
    # Optional top-level keys:
    "is_batch_entry_point": bool,
    "batch_entry_metadata": dict,
    "procedure_expansion": {
        "expanded_steps": [...],
        "expansion_audit": [...],
        "expansion_map": dict,
        "original_step_count": int,
        "expanded_step_count": int,
    },
}
```

### Critical Paths for Relationship Extraction

| Path | Used by | Neo4j relationship |
|------|---------|-------------------|
| `dependencies.includes[*].proc_name` | relationship extractor | `CALLS_PROC` |
| `dependencies.calls[*]` | relationship extractor | `CALLS` |
| `execution_details[*].dd_statements` | dataset/file binder | dataset binding |

## ParserResult Container

```python
ParserResult(
    success=bool,
    program_structure=dict,          # shape above
    error_message=str | None,        # prefixed: "JCL_PARSE_ERROR", "SYNTAX_ERROR", etc.
    metadata=dict,                   # timing, dialect="IBM_JCL", validation_errors count
)
```

## File Extensions Handled

`.jcl`, `.jcllib`, `.job`, `.prc`, `.proc` (and uppercase variants).

Standalone PROC files (containing `PROC…PEND` but no `JOB` statement) are detected, wrapped in a synthetic `//LEGACYLENS JOB` statement, parsed, then annotated with `is_procedure_definition=True`.

---

## See Also

- [../core/parsing-pipeline.md](../core/parsing-pipeline.md) — parse_jcl / validate_jcl / explode_job chain
- [../advanced/proc-expansion.md](../advanced/proc-expansion.md) — CompositeProcedureLoader setup
- [../api/public-api.md](../api/public-api.md) — all importable names and tiers
- [../development/development-workflow.md](../development/development-workflow.md) — vendor sync command
