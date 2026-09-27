---
type: Subsystem
title: PROC Expansion
description: explode_job() replaces PROC invocations with their full step content and substitutes &SYMBOL parameters; always a separate call from parse_jcl().
tags: [proc, explosion, symbol-substitution, advanced]
timestamp: 2026-09-16T00:00:00Z
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

Signature: `explode_job(job, proc_loader=None, max_depth=10, max_steps=0, audit=True,
system_provider=None, strict_symbols=False)`. The `Job.explode()` method takes the same
options but names the loader `loader=`, not `proc_loader=`.

| Option | Default | Effect |
|--------|---------|--------|
| `proc_loader` | `None` | Loader chain; `None` builds the default chain below |
| `max_depth` | `10` | Raises `ExplosionDepthError` if nesting exceeds it |
| `max_steps` | `0` (unlimited) | Cap on total expanded steps; raises `JCLStructureError` if exceeded |
| `audit` | **`True`** | Populates `job.explosion_audit` and `job.explosion_map` |
| `system_provider` | `None` | `SystemSymbolProvider` for `&SYSUID`-style system symbols |
| `strict_symbols` | `False` | If True, raises `UndefinedSymbolError` for unknown `&SYMBOLS` |

# Audit Data (when audit=True)

```python
exploded.explosion_audit  # list of audit entries
exploded.explosion_map  # dict[step_name → proc_name]

# Each entry:
entry.step_name, entry.proc_name, entry.parameters, entry.depth, entry.expanded_steps
```

# Symbol Substitution

- `&NAME` → substituted value from symbol table
- `&&` → literal `&` (escaped ampersand)
- `&&TEMP` in a DSN means temporary dataset, not an escaped ampersand
- SET symbols resolve left-to-right
- With `strict_symbols=False`, an undefined `&SYMBOL` elides to `""` **and is recorded on `exploded_job.warnings`** (not just symbols undefined at `parse_jcl()` time — an `&SYMBOL` that only resolves against PROC defaults/EXEC overrides/system symbols, and is therefore only ever substituted inside `explode_job()`, warns too; fixed 2026-07-24, previously silently discarded). When that symbol was a PDS member — `DSN=LIB(&MEM)` → `LIB()` — `substitute_dd_statement` strips the empty `()` and collapses to the bare PDS name `LIB` (an empty member is meaningless). Non-empty members (`LIB(MEMBER)`) and GDG generations (`GDG(+1)`) are untouched.
- `exploded_job.warnings` also carries forward everything already on `job.warnings` from `parse_jcl()` — `explode_job()` rebuilds a new `Job`, and prior to 2026-07-24 the rebuild silently dropped this field.

# DD Overrides

DD statements coded under an `EXEC PROC=` invocation override or add to the procedure's DDs during explosion (z/OS semantics):

| Form | Stored on the EXEC step as | Applied by | Target |
|------|----------------------------|-----------|--------|
| Qualified `//PROCSTEP.DDNAME DD …` | `step.dd_overrides[key]` | `apply_dd_overrides` | the named procstep; **merges into** a matching DD, else **appends** (fixed 2026-07-24, previously discarded when no DD of that name existed) |
| Unqualified `//DDNAME DD …` | `step.dd_statements` | `apply_unqualified_dd_overrides` | the procedure's **first** step; **merges into** a same-named DD, else **appends** |

Both paths carry an *added* DD (a name not present in the proc) onto the step — e.g. `//LOANRPT DD DSN=…` on `EXEC PROC=IMSBTCH` (unqualified), or `//PROCSTEP.NEWDD DD DSN=…` (qualified). Both run inside `_explode_step` after the proc is expanded; nested PROC invocations propagate naturally because the merge re-runs at each recursion level. The qualified path normalizes the resulting `DDStatement.name` to the plain `DDNAME` (not the raw `PROCSTEP.DDNAME` key) so `step.get_dd("DDNAME")` finds it either way.

**Merge semantics** (`_merge_dd_override`, fixed 2026-09-27): an override changes only the parameters it codes — `//PS.D1 DD DSN=NEW` keeps the proc DD's `DISP`, `UNIT`, `DCB`, … — and `KEY=` (empty value) nullifies one. The data-source parameters (`DSN`/`DSNAME`/`SYSOUT`/`PATH`/`DUMMY`/`*`/`DATA`) are mutually exclusive, so coding any of them on the override drops the others from the proc DD (`DSN=` on the override nullifies `DUMMY`). An in-stream override (`DD *` / `DD DATA`) replaces the DD outright. Before, both paths replaced the whole DD, so e.g. the proc's `DISP=SHR` vanished whenever only the dataset name was overridden. Regression tests: `tests/unit/test_dd_override_merge.py`.

# Step References Inside a PROC

Inside a procedure, a step name in an `IF` condition (`IF (PS1.RC = 0)`) or an EXEC `COND=(4,LT,PS1)` test names the procedure's own step. `expand_proc_invocation` renames that step `PREFIX.PS1`, so it also qualifies those references (fixed 2026-09-27; they previously matched no exploded step, so RC analysis could not evaluate them and two expansions of one PROC were indistinguishable): `ConditionalBlock.condition_ast` gets a qualified *copy* (the PROC definition's AST is shared and never mutated) and `COND` values are rewritten in both the `['4','LT','PS1']` and `['(4,LT,PS1)', ...]` forms. References to job steps are left alone, and the raw `ConditionalBlock.condition` string stays as coded (invariant 3). Regression tests: `tests/unit/test_proc_step_ref_qualification.py`.

# EXEC Parameter Overrides

EXEC keyword parameters coded on an `EXEC procname` statement (`ACCT`, `ADDRSPC`, `COND`, `DYNAMNBR`, `MEMLIMIT`, `PARM`, `PARMDD`, `PERFORM`, `RD`, `REGION`, `TIME`, …) are applied to the expanded steps by `apply_exec_parameter_overrides`, called from `_explode_step` before the DD overrides (fixed 2026-09-27; previously every one was silently dropped):

| Form | Effect |
|------|--------|
| `KEYWORD.procstep=value` | overrides or adds the keyword on that step only; an unknown procstep is ignored with a warning on `exploded_job.warnings` |
| `PARM=` / `PARMDD=` (no procstep) | goes to the procedure's **first** step and nullifies PARM/PARMDD on every other step |
| any other keyword (no procstep) | overrides the keyword on **every** step (`TIME=` really bounds the whole procedure; per-step is the closest model) |
| `KEYWORD.procstep=` / `KEYWORD=` (empty) | nullifies the keyword |

`PARM` and `PARMDD` displace each other. Unqualified overrides are applied before qualified ones. Steps inside `IF`/`ELSE` blocks in the procedure are reached too. Symbolic parameters (`EXEC P,MBR=X`) are unaffected: their names can never be EXEC keywords. Regression tests: `tests/unit/test_exec_parameter_overrides.py`.

# Error Types

| Error | When |
|-------|------|
| `ProcedureNotFoundError` | PROC not in any loader |
| `CircularProcedureError` | PROC A calls PROC B which calls PROC A |
| `ExplosionDepthError` | Nesting deeper than `max_depth` |
| `UndefinedSymbolError` | `&SYMBOL` undefined (only with `strict_symbols=True`; applies to plain steps' EXEC parameters as well as PROC steps) |
| `JCLStructureError` | A symbol's nested values expand to more than `_MAX_NESTED_EXPANSION_CHARS` (1,000,000) characters in one substitution |

**Expansion bounds.** A symbol whose value refers back to itself (`A='&A'`, directly or via other
symbols) is a cycle: the reference is left as written instead of being re-expanded. Fan-out over
distinct symbols is capped by the character budget above. `JCLLIB ORDER=` libraries must stay
inside the loader's base path (checked lexically, so an operator-symlinked library still works):
an absolute or `..` library is skipped.

# Citations

[1] [api/public-api.md](../api/public-api.md) — Tier 2 loader and explosion exports
[2] [core/parsing-pipeline.md](../core/parsing-pipeline.md) — stage 7 context
[3] [integration/backend-contract.md](../integration/backend-contract.md) — how the backend chains loaders
