# Backend Integration Contract — jcl-parser

This document describes exactly what `backend/src/parsers/jcl/parser.py` (the `JCLLegacyParser` adapter) calls into `jclparser`, and what shapes it expects back.

**Adapter source:** `backend/src/parsers/jcl/parser.py`
**Import path in backend:** `from ..dependencies import parse_jcl, Job, Step, JCLParseError, JCLSyntaxError, JCLValidationError, JCLStructureError`

---

## Entry Points Called by the Adapter

### 1. Parse
```python
from jclparser import parse_jcl

job = parse_jcl(content: str)   # returns Job; a str is always JCL text, never a path
```
- Always returns a `Job` object (never `None`); unrecoverable failures raise.
- A `str` argument is always treated as JCL content, never as a file path (since `a0c30c9`); pass a `pathlib.Path` to read a file.
- Must raise `JCLSyntaxError | JCLValidationError | JCLStructureError | JCLParseError` on parse failures.
- Does not receive a filename (JCL parser does not use one).

### 2. Validation
```python
validation_errors = job.validate()  # list of validation error objects
```
- Items are stringified with `str()`.
- An empty list = no errors.

### 3. PROC explosion
```python
exploded_job = job.explode(
    max_depth=10,
    audit=True,
    strict_symbols=False,
    loader=proc_loader,  # optional, may be None
)
```
Returns an exploded `Job` or raises `JCLParseError` (e.g. `ProcedureNotFoundError`). The adapter catches `JCLParseError` and falls back to the un-exploded job gracefully.

### 4. Composite loader (for PROC precedence)
```python
from jclparser.proc_loader import CompositeProcedureLoader, InlineProcedureLoader

loader = CompositeProcedureLoader(
    [
        InlineProcedureLoader(job.procedures),
        external_loader,
    ]
)
```
Used to prepend inline PROCs ahead of a DB-sourced external loader.

### 5. Exception types
```python
from jclparser import (
    JCLParseError,
    JCLSyntaxError,
    JCLValidationError,
    JCLStructureError,
)
```
All four must be importable. The adapter catches them separately for error classification.

---

## Job Object Contract

Attributes the adapter accesses on a `Job`:

| Attribute | Type | Notes |
|-----------|------|-------|
| `job.name` | `str \| None` | Job name from `//JOBNAME JOB` statement |
| `job.steps` | `list[Step]` | All job steps |
| `job.procedures` | list | Inline PROC definitions for `InlineProcedureLoader` |
| `job.validate()` | `list` | Structural validation errors |
| `job.explode(...)` | `Job` | Returns exploded job; see above |
| `job.explosion_audit` | `list` | Present after `explode(audit=True)`; see below |
| `job.explosion_map` | `dict` | Present after `explode(audit=True)` |

**`explosion_audit` entries** — each item must have:

| Field | Type |
|-------|------|
| `.step_name` | `str` |
| `.proc_name` | `str` |
| `.parameters` | `dict` |
| `.depth` | `int` |
| `.expanded_steps` | `list` |

## Step Object Contract

Attributes the adapter accesses on a `Step`:

| Attribute | Type | Notes |
|-----------|------|-------|
| `step.name` | `str` | Step name |
| `step.program` | `str \| None` | PGM= value from EXEC statement |
| `step.is_exploded` | `bool` | True if this step was expanded from a PROC |
| `step.is_procedure` | `bool` (property) | True if step invokes a PROC (pre-explosion). Was documented as `step.is_proc_invocation`; no such attribute exists on `Step` — reading it raises `AttributeError` |
| `step.procedure` | `str \| None` | PROC name if this is a PROC call |
| `step.original_proc_call` | `str \| None` | Original PROC invocation name |
| `step.parameters` | `dict` | Step parameters |
| `step.line_number` | `int \| None` | Source line |
| `step.dd_statements` | `list[DD]` | All DD statements for this step |

## DD Object Contract

| Attribute | Type |
|-----------|------|
| `dd.name` | `str` |
| `dd.dataset_name` | `str \| None` |
| `dd.disposition` | `str \| None` |
| `dd.parameters` | `dict` |

---

## Extra Keyword Args via `parse_content()`

```python
adapter.parse_content(
    content,  # str
    filename=filename,  # str | None (not passed to jclparser)
    proc_loader=loader,  # optional external PROC loader
)
```

`proc_loader` is a custom loader (from `backend/src/services/`) that resolves external PROCs stored in the DB. The adapter chains it behind an `InlineProcedureLoader` when inline PROCs exist.

---

## Output: program_structure Shape

```python
{
    "program_info": {
        "name": str,  # job.name or "UNNAMED_JOB"
        "type": "JCL",
        "language_version": "JCL/MVS",
        "encoding": "utf-8",
        "line_count": int,
        "complexity_score": float,
    },
    "structure": {
        "sections": [...],  # job sections (from JclStructureExtractor)
        "variables": [...],  # symbolic parameters / SET variables
        "procedures": [...],  # PROC invocations
    },
    "dependencies": {
        "includes": [dict],  # PROC references — each has "proc_name"
        "calls": [str],  # program names from EXEC PGM= steps
        "databases": [dict],  # DB2 dataset references
        "procedure_definitions": [...],  # inline PROC definitions
    },
    "execution_details": [...],  # per-step detail with DD statements
    "analysis": {
        "metrics": {...},
        "issues": [...],
        "modernization_hints": [...],
    },
    # Optional top-level keys added when detected:
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

**Critical paths read by backend relationship extractors:**
- `dependencies.includes` — each dict's `"proc_name"` → `CALLS_PROC` relationship
- `dependencies.calls` — list of `str` program names → `CALLS` relationship
- `execution_details` — per-step DD statements used for dataset/file binding

---

## ParserResult Container

Same as all parsers — `backend/src/parsers/base.ParserResult`:
```python
ParserResult(
    success=bool,
    program_structure=dict,  # shape above
    error_message=str
    | None,  # prefixed: "JCL_PARSE_ERROR", "SYNTAX_ERROR", "VALIDATION_ERROR", "STRUCTURE_ERROR", etc.
    metadata=dict,  # timing, dialect="IBM_JCL", validation_errors count, etc.
)
```

---

## File Extensions Handled

`.jcl`, `.jcllib`, `.job`, `.prc`, `.proc` (and uppercase variants).

Standalone PROC files (containing `PROC...PEND` but no `JOB` statement) are detected and wrapped in a synthetic `//LEGACYLENS JOB` statement before parsing, then the result is annotated with `is_procedure_definition=True`.
