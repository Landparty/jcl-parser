---
type: Subsystem
title: PROC Expansion
description: explode_job() replaces PROC invocations with their full step content and substitutes &SYMBOL parameters; always a separate call from parse_jcl().
tags: [proc, explosion, symbol-substitution, advanced]
timestamp: 2026-06-28T00:00:00Z
---

# Overview

`explode_job(job, loader, ...)` is a separate, explicit call — never called by `parse_jcl()`. It resolves PROC names through a loader chain and substitutes `&SYMBOL` parameters.

# Loader Chain (priority order)

```
1. Inline PROCs (PROC…PEND in the same JCL)      ← always wins; no override possible
2. JCLLIB filesystem  (JCL_PROCLIB_PATH env var or proc_base_path arg)
   Layout: <base_path>/<DATASET.NAME>/<PROCNAME>.jcl
3. DictProcedureLoader  (user-supplied in-memory dict)
4. builtin_procs.py   BUILTIN_UTILITY_PROCS  ← last resort
   Covers: IMS (IMSBATCH, DLIBATCH…), DB2 (DSNUPROC, DSNHICOB), COBOL (IGYWCL…)
       ↓ not found
   ProcedureNotFoundError
```

**Builtins are structural approximations, not verbatim IBM PROCs.** Safe for static analysis; must not be submitted to a real mainframe.

# Usage

```python
from jclparser import parse_jcl, explode_job, ProcedureNotFoundError

job = parse_jcl(source)
try:
    exploded = explode_job(job, max_depth=10, audit=True, strict_symbols=False)
except ProcedureNotFoundError as e:
    print(f"PROC not found: {e}")
```

# Explosion Options

| Option | Default | Effect |
|--------|---------|--------|
| `max_depth` | 10 | Raises `ExplosionDepthError` if exceeded |
| `audit` | False | Populates `job.explosion_audit` and `job.explosion_map` |
| `strict_symbols` | False | If True, raises `UndefinedSymbolError` for unknown `&SYMBOLS` |

# Audit Data (when audit=True)

```python
exploded.explosion_audit   # list of audit entries
exploded.explosion_map     # dict[step_name → proc_name]

# Each entry:
entry.step_name, entry.proc_name, entry.parameters, entry.depth, entry.expanded_steps
```

# Symbol Substitution

- `&NAME` → substituted value from symbol table
- `&&` → literal `&` (escaped ampersand)
- `&&TEMP` in a DSN means temporary dataset, not an escaped ampersand
- SET symbols resolve left-to-right

# Error Types

| Error | When |
|-------|------|
| `ProcedureNotFoundError` | PROC not in any loader |
| `CircularProcedureError` | PROC A calls PROC B which calls PROC A |
| `ExplosionDepthError` | Nesting deeper than `max_depth` |
| `UndefinedSymbolError` | `&SYMBOL` undefined (only with `strict_symbols=True`) |

# Citations

[1] [advanced/proc-expansion.md](proc-expansion.md) — full detail with loader chaining examples
[2] [core/parsing-pipeline.md](../core/parsing-pipeline.md) — stage 7 context
[3] [integration/backend-contract.md](../integration/backend-contract.md) — how the backend chains loaders
