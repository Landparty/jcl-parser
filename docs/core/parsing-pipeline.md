---
title: Parsing Pipeline
updated: 2026-06-27
sources: LegacyLens team, 2026-06-27
---

# Parsing Pipeline

The jcl-parser pipeline transforms raw JCL text into a structured `Job` object through up to seven stages. Only stages [1], [2], and [4] are mandatory; the others are optional.

## Quick Start

```python
import jclparser

job = jclparser.parse_jcl(source)   # stages 1–4 (no validation, no PROC expansion)
print(job.name)
print(job.steps[0].program)
```

## Full Pipeline

```
Input: JCL string / file / IO stream
         │
         ▼
[1] read_source()                          utils.py
    Reads string/file; encoding fallback EBCDIC → UTF-8
         │
         ▼
[2] ContinuationLineHandler.process()      continuation_handler.py
    Merges multi-line JCL statements.
    JCL uses column-71 breaks on // continuation lines.
    Tracks quote/paren depth to avoid premature merges.
    CRITICAL: never pass pre-stripped lines — col 71 rule is enforced here.
         │
         ▼
[3] resolve_includes()                     include_loader.py  [optional]
    Expands // INCLUDE MEMBER=name from JCLLIB
         │
         ▼
[4] parse_jcl() core loop                  parser.py
    Dispatches each merged line by statement type:

    Statement type  → Action
    ─────────────────────────────────────────────
    JOB             → Build Job object; parse JOB params
    EXEC (PGM=)     → Build Step with program name
    EXEC (PROC)     → Build Step invoking a PROC
    DD              → Build DDStatement via parameter_ast.py
    SET             → Record symbol into symbol table (left-to-right)
    // IF           → parse_condition() → ConditionalBlock
    PROC / PEND     → Build inline Procedure
    OUTPUT          → Build OutputStatement
    // (comment)    → Preserve as Statement(type="COMMENT")
         │
         ▼
[5] ParameterParser                        parameter_ast.py
    Parses raw parameter strings into typed ASTs.
    Handles: DCBParameter, SPACEParameter, nested parens,
    positional vs. keyword params, quoted strings.
         │
         ▼
[6] validate_jcl()  [optional]             validators.py, parameter_validators.py
    Post-parse structural checks:
    - Identifier naming rules (max 8 chars, valid charset)
    - Dataset name rules (qualifiers, max 44 chars)
    - Job/Step/DD structure rules
    - Parameter value constraints (RECFM, TIME, REGION, MSGLEVEL, ...)
    NOTE: returns Job + errors list, NOT a boolean.
          Check result.errors for ErrorSeverity.ERROR items.
         │
         ▼
[7] explode_job()   [optional]             explosion.py
    PROC expansion. Resolves PROCs and substitutes &SYMBOL params.
    Uses ProcedureLoader chain: inline → JCLLIB → builtins.
    Detects circular references; enforces max depth.
    NOTE: parse_jcl() does NOT call this. You must call explode_job() separately.
         │
         ▼
Output: Job object
```

## Key Behavioral Notes

- **`parse_jcl()` never expands PROCs.** Call `explode_job(job)` if you need PROC expansion.
- **`//` comment lines are not dropped.** They become `Statement(type="COMMENT")` in `job.statements`.
- **JES control statements** (`/*JOBPARM`, `/*ROUTE`, etc.) are parsed separately in `jes_statements.py` — they are not in `job.steps`.
- **SET symbols resolve left-to-right** — a SET can reference an earlier SET but not a later one.
- **Column 71 is the continuation column.** `ContinuationLineHandler` handles this before any parsing. Passing pre-stripped lines will break continuation detection.

## Running Validation

```python
from jclparser import validate_jcl, ErrorSeverity

job, errors = validate_jcl(source)
hard_errors = [e for e in errors if e.severity == ErrorSeverity.ERROR]
```

## Running PROC Expansion

```python
from jclparser import parse_jcl, explode_job

job = parse_jcl(source)
exploded = explode_job(job, max_depth=10)   # raises ProcedureNotFoundError if unresolvable
```

## See Also

- [data-model.md](data-model.md) — what the `Job`, `Step`, `DDStatement` objects look like
- [../advanced/proc-expansion.md](../advanced/proc-expansion.md) — PROC loader chain detail
- [../advanced/validation.md](../advanced/validation.md) — full validation reference
- [../api/public-api.md](../api/public-api.md) — API tier tables
