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
- A `str` argument is always treated as JCL content, never as a file path; pass a `pathlib.Path` to read a file.
- Must raise `JCLSyntaxError | JCLValidationError | JCLStructureError | JCLParseError` on parse failures.
- Does not receive a filename (JCL parser does not use one).

### 2. Validation
```python
validation_errors = job.validate()  # list[ValidationError]
```
- Items are stringified with `str()`.
- An empty list = no findings. Items include WARNING-severity findings (`str()` marks them `[WARNING]`, after any `Line N:` prefix; `.is_warning` is `True`) — e.g. a PROC not found in-stream or in any configured library — so a non-empty list does not by itself mean the job is invalid.

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
| `job.name` | `str` | Job name from `//JOBNAME JOB` statement; `""` for a JOB-less PROC member |
| `job.steps` | `list[Step \| ConditionalBlock]` | Top-level steps in source order. An `// IF` block is a `ConditionalBlock` (no `.name`, no `.program`), and the steps inside it are only in its `then_steps` / `else_steps`. To visit every execution step, iterate `iter_execution_steps(job.steps)` (`from jclparser import iter_execution_steps`) — it flattens nested IF blocks, before and after `explode()` |
| `job.procedures` | `list[Procedure]` | Inline PROC definitions for `InlineProcedureLoader` |
| `job.validate()` | `list[ValidationError]` | Structural validation findings (errors and warnings) |
| `job.explode(...)` | `Job` | Returns exploded job; see above |
| `job.explosion_audit` | `list` | Populated on the job `explode(audit=True)` returns (empty on the original); see below |
| `job.explosion_map` | `dict` | Populated on the job `explode(audit=True)` returns |

Other `Job` fields (e.g. `job.custom_statements`, the statements of a custom type returned by a `StatementPlugin`) are not read by the adapter; see `.okf/core/data-model.md`.

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
| `step.name` | `str` | Step name; `""` for an unnamed EXEC, `STEP.PROCSTEP` for an exploded step |
| `step.program` | `str \| None` | PGM= value from EXEC statement |
| `step.is_exploded` | `bool` | True if this step was expanded from a PROC |
| `step.is_procedure` | `bool` (property) | True if step invokes a PROC (pre-explosion). There is no `step.is_proc_invocation` |
| `step.procedure` | `str \| None` | PROC name if this is a PROC call |
| `step.original_proc_call` | `str \| None` | Original PROC invocation name |
| `step.parameters` | `dict` | Step parameters |
| `step.line_number` | `int` | Source line (default `0`, never `None`) |
| `step.dd_statements` | `list[DD]` | All DD statements for this step |

## DD Object Contract

| Attribute | Type |
|-----------|------|
| `dd.name` | `str` |
| `dd.dataset_name` | `str \| None` |
| `dd.disposition` | `str \| list[str] \| None` (a string for a bare status such as `SHR`, a list for a parenthesised `DISP=(NEW,CATLG,DELETE)`) |
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

Standalone PROC files (containing `PROC...PEND` but no `JOB` statement) are detected and wrapped in a synthetic `//LEGACYLN JOB` statement before parsing, then the result is annotated with `is_procedure_definition=True`.

The wrapper's job name must be 1-8 characters. The wrapped job has no top-level steps (they live in `job.procedures`), and `job.validate()` treats in-stream procedures as the job's content, so a valid PROC wrapped this way validates clean.

---

## Pending Adapter Changes

The adapter vendors this library and lives outside this repo. Make these changes at the next vendor sync:

1. **`job.steps` holds `ConditionalBlock`s (#99).** Iterate `iter_execution_steps(job.steps)` (or skip `ConditionalBlock` elements) wherever the adapter reads step attributes off `job.steps` or `exploded_job.steps`; otherwise the first `// IF` raises `AttributeError` and the steps inside IF blocks are missed.
2. **`step.is_proc_invocation` does not exist.** Read `step.is_procedure`.
3. **PROC wrapper name (#100).** Emit `//LEGACYLN JOB`; the old `//LEGACYLENS JOB` is 10 characters, so `job.validate()` fails every wrapped PROC with "Invalid job name".
