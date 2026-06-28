---
title: PROC Expansion
updated: 2026-06-27
sources: LegacyLens team, 2026-06-27
---

# PROC Expansion

`explode_job()` replaces PROC invocations in a job with their full step content, substituting `&SYMBOL` parameters along the way. It is intentionally separate from `parse_jcl()` — always a distinct, explicit call.

## Loader Chain

When `explode_job()` needs to resolve a PROC name, it tries loaders in this exact order:

```
1. Inline PROCs (PROC…PEND blocks within the same JCL file)
        │ not found
        ▼
2. JCLLIB ORDER datasets (filesystem under JCL_PROCLIB_PATH or proc_base_path)
   Layout: <base_path>/<DATASET.NAME>/<PROCNAME>.jcl
        │ not found
        ▼
3. DictProcedureLoader (user-supplied in-memory dict, if any)
        │ not found
        ▼
4. builtin_procs.py — BUILTIN_UTILITY_PROCS last-resort fallback
   Covers:
     IMS:   IMSBATCH, DLIBATCH, DBBBATCH, IMSMSG, DFSMPR
     DB2:   DSNUPROC, DSNHICOB
     COBOL: IGYWCL, IGYWCLG, COBUCL
        │ not found
        ▼
   ProcedureNotFoundError
```

**Inline always wins.** If the same PROC name exists both inline and externally, the inline definition is used — no override possible.

## Basic Usage

```python
from jclparser import parse_jcl, explode_job, ProcedureNotFoundError

job = parse_jcl(source)
try:
    exploded = explode_job(job, max_depth=10)
except ProcedureNotFoundError as e:
    print(f"PROC not found: {e}")
```

## External PROCs from Filesystem

```python
from jclparser import parse_jcl, explode_job
from jclparser.proc_loader import create_default_loader

job = parse_jcl(source)
loader = create_default_loader(proc_base_path="/path/to/procs")
exploded = explode_job(job, loader=loader)
```

Expected filesystem layout:
```
/path/to/procs/
├── SYS1.PROCLIB/
│   └── SORTPROC.jcl
└── USER.PROCLIB/
    ├── MYPROC.jcl
    └── PARMPRC.jcl
```

Set the path once via the `JCL_PROCLIB_PATH` environment variable instead of passing it on every call.

## In-Memory PROCs (Dict)

```python
from jclparser.proc_loader import DictProcedureLoader

procs = {"MYPROC": "//MYPROC PROC\n//STEP1 EXEC PGM=MYPGM\n//PEND"}
loader = DictProcedureLoader(procs)
exploded = explode_job(job, loader=loader)
```

## Chaining Loaders

```python
from jclparser.proc_loader import CompositeProcedureLoader, InlineProcedureLoader, create_default_loader

base_loader = create_default_loader(proc_base_path="/procs")
loader = CompositeProcedureLoader([
    InlineProcedureLoader(job.procedures),   # inline wins
    base_loader,
])
exploded = explode_job(job, loader=loader)
```

This is exactly what the backend adapter does — it chains an `InlineProcedureLoader` ahead of a DB-sourced external loader.

## Explosion Options

```python
exploded = explode_job(
    job,
    loader=loader,
    max_depth=10,           # default — raises ExplosionDepthError if exceeded
    audit=True,             # populates job.explosion_audit and job.explosion_map
    strict_symbols=False,   # if True, raise UndefinedSymbolError for unknown &SYMBOLS
)
```

## Audit Data

When `audit=True`, the exploded job gains two attributes:

```python
exploded.explosion_audit   # list of audit entries
exploded.explosion_map     # dict of step → PROC mapping

# Each audit entry has:
entry.step_name         # str
entry.proc_name         # str
entry.parameters        # dict — symbol substitutions applied
entry.depth             # int — nesting depth
entry.expanded_steps    # list — steps produced by this expansion
```

## Symbol Substitution

- `&NAME` → substituted value from the symbol table
- `&&` → literal `&` (escaped ampersand)
- Substitution is handled in `explosion.py:_SYMBOL_SUB_PATTERN`
- SET symbols resolve left-to-right within the job (a SET can reference earlier SET symbols but not later ones)
- With `strict_symbols=False` (default): unknown symbols are left as-is
- With `strict_symbols=True`: unknown symbols raise `UndefinedSymbolError`

## Error Types

| Error | When raised |
|-------|-------------|
| `ProcedureNotFoundError` | PROC name not found in any loader |
| `CircularProcedureError` | PROC A calls PROC B which calls PROC A |
| `ExplosionDepthError` | Nesting deeper than `max_depth` |
| `UndefinedSymbolError` | `&SYMBOL` not defined (only with `strict_symbols=True`) |

## Builtin PROC Templates

`builtin_procs.py` contains structural approximations of IBM utility PROCs. These are **not exact IBM PROC copies** — sufficient for static analysis, not for production mainframe submission.

Toggle builtins:
```python
loader = create_default_loader(
    proc_base_path="/procs",
    include_builtins=True,   # default — include IBM utility templates as fallback
)
```

## CLI

```bash
jcl-parser MYJOB.jcl steps --explode --proc-path /procs
```

## See Also

- [../core/parsing-pipeline.md](../core/parsing-pipeline.md) — where explode_job() fits in the pipeline
- [../core/data-model.md](../core/data-model.md) — Step.is_exploded and explosion_audit
- [../api/public-api.md](../api/public-api.md) — full Tier 2 loader API table
- [../integration/backend-contract.md](../integration/backend-contract.md) — how the backend adapter chains loaders
