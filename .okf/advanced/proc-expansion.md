---
type: Subsystem
title: PROC Expansion
description: explode_job() replaces PROC invocations with their full step content and substitutes &SYMBOL parameters; always a separate call from parse_jcl().
tags: [proc, explosion, symbol-substitution, advanced]
timestamp: 2026-10-29T00:00:00Z
---

# Overview

`explode_job(job, loader, ...)` is a separate, explicit call — never called by `parse_jcl()`. It resolves PROC names through a loader chain and substitutes `&SYMBOL` parameters.

# Loader Chain (priority order)

`create_default_loader(inline_procedures, base_path=None, include_jcllib=True, include_builtins=True)` builds a `CompositeProcedureLoader` of:

```
1. InlineProcedureLoader (PROC…PEND in the same JCL)  ← always wins; no override possible
2. JCLLIBProcedureLoader  (JCL_PROCLIB_PATH env var or proc_base_path arg;
   with neither, NO files are read -- the cwd is never searched implicitly)
   Searches the JCLLIB ORDER libraries, then DEFAULT_SYSTEM_PROCLIBS
   (SYS1.PROCLIB) -- also with no JCLLIB at all (issue #116)
   Layout: <base_path>/<DATASET.NAME>/<PROCNAME>.jcl
   Members over utils.MAX_LIBRARY_MEMBER_BYTES (4 MiB) are refused (warning)
3. builtin_procs.py   BUILTIN_UTILITY_PROCS  ← last resort (create_builtin_proc_loader)
   Covers: IMS (IMSBATCH, DLIBATCH…), DB2 (DSNUPROC, DSNHICOB), COBOL (IGYWCL…)
       ↓ not found
   ProcedureNotFoundError
```

`DictProcedureLoader` (an in-memory `{name: JCL text}` dict) is **not** in the default chain — compose it yourself, e.g. `CompositeProcedureLoader([InlineProcedureLoader(job.procedures), DictProcedureLoader(d), ...])` (keep the inline loader first), and pass it as `proc_loader=`.

**Builtins are structural approximations, not verbatim IBM PROCs.** Safe for static analysis; must not be submitted to a real mainframe.

**What `parse_jcl()` loads** (#116): with `enable_external_procs` (the default) it attaches the default chain to the job, JCLLIB or not, whenever the job names a JCLLIB, `proc_base_path` is given, or a PROC call is not in-stream (otherwise `explode_job()`'s own default chain is identical, so building it is skipped), and adds every PROC the chain finds to `job.procedures` (so a builtin such as `IGYWCL` and `<base>/SYS1.PROCLIB/MYPROC.jcl` resolve with no JCLLIB). A PROC still not found is a strict-parse error only when the job has a `JCLLIB ORDER`; with none it may be in the JES PROCLIB. Either way a lenient parse reports it once, as a WARNING from `job.validate()` (`validators.validate_procedure_references`, reported by `validate_jcl` at `structure`/`semantic`), not on `job.warnings`. With a `JCLLIB ORDER`, `validate_jcl` (which parses strict) reports the strict-parse ERROR `Procedure 'X' not found. Searched in: ...` instead. With `enable_external_procs=False` strict mode still raises for any PROC that is not in-stream.

**Which loader `explode_job()` uses:** the caller's `proc_loader=` if given; else, when `parse_jcl()` attached one, a `CompositeProcedureLoader` of the job's inline PROCs followed by the loader `parse_jcl()` attached to the job (`job._proc_loader`); else `create_default_loader(job.procedures)`. So an external PROC called from inside another external PROC (or from an IF block) is found in the same libraries as the top-level ones. `parse_jcl()`'s pre-loading of external PROCs also walks `IF`/`THEN`/`ELSE` blocks (`iter_execution_steps`), not just top-level steps.

**Symbols in `JCLLIB ORDER=`** (#128): as on z/OS, the `// SET` symbols in effect at the JCLLIB statement — only SETs coded before it, including ones before the JOB statement — are substituted into each library name (`ORDER=(&LIB)`, `&HLQ..PROCLIB`) when the builder records `job.jcllib_order` (`_model_factories._resolve_jcllib_library`), so PROC loading and `explode_job()` see the resolved names. System symbols (`&SYSUID`) are not resolved there: a library that still holds an unresolved `&symbol` stays as written and adds a `job.warnings` entry. The INCLUDE pre-scan (`_extract_jcllib_order`) substitutes the same earlier SETs, without the warning. The base-path guard below still applies to the substituted name (`SET LIB='../OUT'` is skipped).

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

Signature: `explode_job(job, proc_loader=None, max_depth=10, max_steps=DEFAULT_MAX_STEPS, audit=True,
system_provider=None, strict_symbols=False)`. The `Job.explode()` method takes the same
options but names the loader `loader=`, not `proc_loader=`.

| Option | Default | Effect |
|--------|---------|--------|
| `proc_loader` | `None` | Loader chain; `None` builds the default chain below |
| `max_depth` | `10` | Raises `ExplosionDepthError` if nesting exceeds it |
| `max_steps` | `DEFAULT_MAX_STEPS` = `10_000` (`0` = unlimited) | Cap on total expanded steps; raises `JCLStructureError` if exceeded. Counted per plain step as it is produced (an `on_step` hook threaded through `_explode_step`), so a PROC fan-out stops at the limit instead of being built first. z/OS allows 255 steps per job |
| `audit` | **`True`** | Populates `job.explosion_audit` (left `[]` when False); `job.explosion_map` is filled either way |
| `system_provider` | `None` | `SystemSymbolProvider` for `&SYSUID`-style system symbols; `None` uses `system_symbols.get_default_provider()` (a `MockSystemSymbolProvider` unless `set_default_provider()` was called) |
| `strict_symbols` | `False` | If True, raises `UndefinedSymbolError` for unknown `&SYMBOLS` |

# Audit Data (when audit=True)

```python
exploded.explosion_audit  # list[ExplosionRecord], one per PROC expansion (nested ones too)
exploded.explosion_map  # dict[calling step name → ProcExpansionInfo] (named calls only)

# Each ExplosionRecord (to_dict() for JSON):
#   step_name, proc_name, parameters, depth, timestamp, expanded_steps

# Each ProcExpansionInfo:
#   original_statement, proc_definition, resolved_parameters,
#   source_line_numbers, expanded_step_names
```

# Symbol Substitution

- `&NAME` → substituted value from symbol table
- `&&` → literal `&` (escaped ampersand) — also when the `&&` comes from a symbol's value (`SET X='A&&B'` / `PROC Y='A&&B'` then `PARM='&X'` → `A&B`): the nested pass that resolves symbols inside a value keeps `&&`, and the top-level replacer collapses it exactly once afterwards (`A&&&&B` → `A&&B`, matching a plain step). DSN contexts pass `collapse_double_amp=False`, so neither form touches a DSN (#127)
- `&&TEMP` in a DSN means temporary dataset, not an escaped ampersand
- A DSN that is one bare single-`&` reference (`DSN=&TEMP`, `DSN=&TEMP(MEM)`) with no symbol of that name is kept as written — the single-ampersand spelling of a temporary dataset name — instead of being blanked with an undefined-symbol warning (`_dsn_keep_undefined`). `strict_symbols=True` still raises for it.
- SET symbols resolve left-to-right; a step read before a SET redefined a symbol expands its PROC with the value in effect at that step (`Step.set_symbols`)
- **SETs coded inside a PROC body** are kept on `Procedure.set_statements`, not in `job.set_statements`, and apply only when that PROC is expanded (`expand_proc_invocation` builds the expansion scope's SET table as `{**job SETs, **procedure.set_statements}`). They never leak into job steps, even when the PROC is never called. Precedence inside a PROC expansion: **EXEC overrides > PROC-statement defaults > the PROC's own SETs > job SETs > system symbols**. A cataloged PROC's SETs are kept too (with PROC/PEND the parser records them on the `Procedure`; a member with no PROC/PEND gets its wrapper job's SETs). Parsed on its own, a JOB-less member also exposes its procedures' SETs on the synthetic job's `set_statements`. Inside the PROC a SET is in effect from where it is coded: a PROC step read before a later SET in the same body redefined a symbol keeps the earlier value (its `Step.set_symbols` snapshot, applied per step by `_proc_step_scope`).
- **EXEC override values are substituted**: symbolic values on the calling `EXEC procname` (`HLQ=&SYSUID`) are resolved against the job scope before expansion. **Keyword overrides and override / added DDs of a job-level call** (`PARM.PS1='&HLQ'`, `//PS1.IN DD DSN=&HLQ..X`) are merged into the procedure, so they resolve in the **called PROC's scope** -- EXEC values > PROC defaults > the PROC's SETs > job SETs > system symbols -- in `explosion._resolve_call_in_proc_scope` (#126). The PROC SETs used are those in effect at the procstep the override names (`Step.set_symbols` via `_proc_step_scope`); an unqualified override or added DD goes to the first procstep: `//R EXEC P,HLQ=TEST,PARM.S1='&HLQ'` gives `PARM='TEST'`, whether or not the job has an unrelated `// SET`. A symbol undefined there is left as written with one `exploded_job.warnings` entry (never blanked, so `PARM.S1='&X'` cannot nullify the PROC's PARM); `strict_symbols=True` raises `UndefinedSymbolError`. `parse_jcl()` (`_post_parse._resolve_proc_call_set_symbols`) resolves only the job SETs the PROC cannot shadow in them (not the call's symbolic-parameter names, the PROC's defaults or its SETs), none at all when the PROC is not in `job.procedures` yet (e.g. it only comes from `explode_job(proc_loader=...)`), and blanks nothing on a PROC-call step. An `EXEC procname` nested in a PROC is resolved the same way, in the PROC it calls, with the calling PROC's symbols (EXEC values, defaults, SETs at that step) as the fallback below the called PROC's own (`expand_proc_invocation(nested_call_scopes=...)`, `_flattened_caller_scope`); its symbolic values still resolve in the calling PROC. An EXEC keyword collapses `&&` → `&`; a symbolic parameter value keeps `&&`, since it may carry a temporary dataset name (`TMP='&&WORK'`). The same rule applies to an `EXEC procname` nested inside a PROC.
- `// INCLUDE MEMBER=&M` resolves `&M` against the `// SET` values seen so far (`resolve_includes` tracks them across nesting levels); an unset symbol is left as written. A SET continued onto the next `//` record (operand field ending in a comma) is merged before its symbols are recorded (`include_loader._continue_operands`, #180). An INCLUDE left unexpanded warns `INCLUDE member &M uses a symbol with no SET value before it` when its name still holds an undefined symbol, and `INCLUDE member MEMB (from &M) not found ...` when the resolved member is missing.
- **INCLUDE in a cataloged PROC** (#153): `parse_jcl` expands INCLUDEs in the job text, in-stream PROCs included, before parsing; an external PROC is read later, so `explode_job` wraps the PROC loader in `explosion._IncludeExpandingLoader`, which expands the INCLUDEs of each external PROC's text (`Procedure.source_text`, kept by `proc_loader._build_procedure_from_content`) against the job's JCLLIB order and rebuilds the procedure. The include loader is `explode_job(include_loader=...)`, else the one `parse_jcl` used (stored on the job as `_include_loader`; the default `JCLLIBMemberLoader(base_path=proc_base_path)`). Members expanded are added to `exploded_job.includes`; a member not found is an `exploded_job.warnings` entry (`INCLUDE member X in PROC P not found; ...`), once per member. A member named by a symbol (`INCLUDE MEMBER=&MEM`) is resolved per call, in that call's scope -- EXEC values > PROC defaults > the PROC's SETs (as coded before the INCLUDE) > job SETs (`_IncludeExpandingLoader.for_call`, from `explosion._load_called_procedure`, also for a call nested in a PROC); each call with different values gets its own expansion (#160).
- With `strict_symbols=False`, an undefined `&SYMBOL` elides to `""` **and is recorded on `exploded_job.warnings`** (not just symbols undefined at `parse_jcl()` time — an `&SYMBOL` that only resolves against PROC defaults/EXEC overrides/system symbols, and is therefore only ever substituted inside `explode_job()`, warns too). This covers every DD parameter, not only DSN/DISP (`UNIT=&NOPE` warns too), with a message already recorded for the dataset name not repeated for `DSN=`. When that symbol was a PDS member — `DSN=LIB(&MEM)` → `LIB()` — `substitute_dd_statement` strips the empty `()` and collapses to the bare PDS name `LIB` (an empty member is meaningless). Non-empty members (`LIB(MEMBER)`) and GDG generations (`GDG(+1)`) are untouched.
- **Unused symbolics** (#172): a symbolic on `EXEC procname` that the PROC neither declares nor references as `&NAME` (`IEFC657I` on z/OS) adds `EXEC S1: symbol(s) MEMBER, PLIB not used by PROC MYP (IEFC657I); its defaults apply` to `exploded_job.warnings`, and `validate_jcl` / `job.validate()` report one ERROR per symbol (`validators.validate_procedure_references`). The check is `explosion.unused_proc_symbols`; EXEC keyword overrides (`PARM.PS1`, `COND`, ...) are not symbolics, and a PROC whose text has an `INCLUDE` is skipped. A symbolic referenced only in the call's overriding or added DDs (`//PS1.DD2 DD DSN=&ENV..Y`, their concatenations) or in a keyword override's value (`PARM.PS1='&X'`) counts as used, since explosion substitutes it there (#176).
- `exploded_job.warnings` also carries forward everything already on `job.warnings` from `parse_jcl()` (`explode_job()` builds a new `Job`).

# DD Overrides

DD statements coded under an `EXEC PROC=` invocation override or add to the procedure's DDs during explosion (z/OS semantics):

| Form | Stored on the EXEC step as | Applied by | Target |
|------|----------------------------|-----------|--------|
| Qualified `//PROCSTEP.DDNAME DD …` | `step.dd_overrides[key]` | `apply_dd_overrides` | the named procstep; **merges into** a matching DD, else **appends** |
| Unqualified `//DDNAME DD …` | `step.dd_statements` | `apply_unqualified_dd_overrides` | the procedure's **first** step; **merges into** a same-named DD, else **appends** |

Both paths carry an *added* DD (a name not present in the proc) onto the step — e.g. `//LOANRPT DD DSN=…` on `EXEC PROC=IMSBTCH` (unqualified), or `//PROCSTEP.NEWDD DD DSN=…` (qualified). Steps nested in a PROC's IF/ELSE blocks are valid targets for both. Both run inside `_explode_step` after the proc is expanded; nested PROC invocations propagate naturally because the merge re-runs at each recursion level. The qualified path normalizes the resulting `DDStatement.name` to the plain `DDNAME` (not the raw `PROCSTEP.DDNAME` key) so `step.get_dd("DDNAME")` finds it either way.

**Unmatched qualifiers** (#64): an override whose qualifier names no step of the procedure is ignored, with a warning. `apply_dd_overrides` appends `DD override NOPE.D names no step in PROC P` to `exploded_job.warnings` when a two-part key's PROCSTEP matches no expanded step, when a three-part key's OUTERSTEP matches none or runs a program rather than a PROC (`S.I.D` with `//S EXEC PGM=X`), and for any key of four or more parts; a three-part key forwarded to a nested PROC reports an unknown INNERSTEP against that inner PROC (`... names no step in PROC IN`). A qualified DD under an `EXEC PGM=` step has no procedure at all, so that one is reported at **parse time** on `job.warnings` (`DD override A.B names no step in PROC: step S runs PGM=X, not a procedure; override ignored`, `JobBuilder`) — it is visible without exploding, and explosion never touches a PGM step's `dd_overrides`. Regression tests: `tests/unit/test_validation_issue_fixes.py::TestDdOverrideNamingNoProcstep`.

**Merge semantics** (`_merge_dd_override`): an override changes only the parameters it codes — `//PS.D1 DD DSN=NEW` keeps the proc DD's `DISP`, `UNIT`, `DCB`, … — and `KEY=` (empty value) nullifies one. The data-source parameters (`DSN`/`DSNAME`/`SYSOUT`/`PATH`/`DUMMY`/`*`/`DATA`) are mutually exclusive, so coding any of them on the override drops the others from the proc DD (`DSN=` on the override nullifies `DUMMY`). An in-stream override (`DD *` / `DD DATA`) replaces the DD outright. Regression tests: `tests/unit/test_dd_override_merge.py`.

**DCB subparameters** (`_merge_dcb_override`): an overriding `DCB=` keeps the proc DD's DCB subparameters it does not code — `DCB=BLKSIZE=0` over `DCB=(RECFM=FB,LRECL=80)` gives `['RECFM=FB', 'LRECL=80', 'BLKSIZE=0']`; `SUB=` nullifies one; a positional model / referback (`DCB=(A.B,...)`, `DCB=*.S.DD`) on the override replaces the proc's. `DCB=` (empty) still nullifies the whole DCB.

**Concatenation members:** unnamed DDs coded after `//PROCSTEP.DDNAME DD …` override the 2nd, 3rd, … members of that DD's concatenation in order (`//  DD` with no operands leaves its member unchanged; members past the last one are added to the concatenation). The parser stores them in `step.dd_override_concatenations[key]` (`JobBuilder.concat_override_key`; a named DD ends the run); `apply_dd_overrides` applies them via `_override_concatenation_members`, and a three-part key forwards them with the override. Unnamed DDs after an *unqualified* named override (`//LIB DD …` / `//  DD …`) are applied the same way to that DD on the first proc step; after an *added* DD they stay its own concatenation. Regression tests: `tests/unit/test_override_concatenation_and_symbols.py`, `tests/unit/test_set_redefinition_and_concat_overrides.py`.

**Symbols in override DDs:** DDs coded under an `EXEC procname` (qualified overrides, their concatenation members, unqualified overrides/additions) are substituted like other DDs: `resolve_set_symbols` covers `dd_overrides` / `dd_override_concatenations` at parse time, and `explode_job` substitutes a clone of the calling step's DDs against the job scope (SET + system symbols, `allow_undefined=True` so any other `&SYM` stays as written). A qualified override coded inside a PROC (nested `EXEC procname`) is substituted with that PROC's expansion scope in `expand_proc_invocation`.

# Step References Inside a PROC

Inside a procedure, a step name in an `IF` condition (`IF (PS1.RC = 0)`) or an EXEC `COND=(4,LT,PS1)` test names the procedure's own step. `expand_proc_invocation` renames that step `PREFIX.PS1`, so it also qualifies those references (otherwise they match no exploded step, and two expansions of one PROC are indistinguishable): `ConditionalBlock.condition_ast` gets a qualified *copy* (the PROC definition's AST is shared and never mutated) and `COND` values are rewritten in both the `['4','LT','PS1']` and `['(4,LT,PS1)', ...]` forms. References to job steps are left alone. The `ConditionalBlock.condition` text of the exploded copy is qualified the same way (`PS1.RC = 0` → `PREFIX.PS1.RC = 0`, spacing and operators kept as coded, `explosion._qualify_condition_text`), so it agrees with its AST and with the JSON export, which carries only the text. The PROC definition's own block keeps its text. A reference with a symbol in the step name, or one the condition parser could not read, is qualified in the text only when it has the `NAME.RC` / `.ABEND` / `.ABENDCC` / `.RUN` shape. Regression tests: `tests/unit/test_proc_step_ref_qualification.py`.

# EXEC Parameter Overrides

EXEC keyword parameters coded on an `EXEC procname` statement (`ACCT`, `ADDRSPC`, `COND`, `DYNAMNBR`, `MEMLIMIT`, `PARM`, `PARMDD`, `PERFORM`, `RD`, `REGION`, `RLSTMOUT`, `TIME`, …) are applied to the expanded steps by `apply_exec_parameter_overrides`, called from `_explode_step` before the DD overrides:

| Form | Effect |
|------|--------|
| `KEYWORD.procstep=value` | overrides or adds the keyword on that step only; an unknown procstep is ignored with a warning on `exploded_job.warnings` |
| `PARM=` / `PARMDD=` (no procstep) | goes to the procedure's **first** step and nullifies PARM/PARMDD on every other step |
| any other keyword (no procstep) | overrides the keyword on **every** step (`TIME=` really bounds the whole procedure; per-step is the closest model) |
| `KEYWORD.procstep=` / `KEYWORD=` (empty) | nullifies the keyword |

`PARM` and `PARMDD` displace each other. Unqualified overrides are applied before qualified ones. Steps inside `IF`/`ELSE` blocks in the procedure are reached too. Symbolic parameters (`EXEC P,MBR=X`) are unaffected: their names can never be EXEC keywords. Symbols in override values are substituted first (see [Symbol Substitution](#symbol-substitution)). Regression tests: `tests/unit/test_exec_parameter_overrides.py`, `tests/unit/test_bughunt_explosion.py`.

# Error Types

| Error | When |
|-------|------|
| `ProcedureNotFoundError` | PROC not in any loader |
| `CircularProcedureError` | PROC A calls PROC B which calls PROC A |
| `ExplosionDepthError` | Nesting deeper than `max_depth` |
| `UndefinedSymbolError` | `&SYMBOL` undefined (only with `strict_symbols=True`; applies to plain steps' EXEC parameters as well as PROC steps) |
| `JCLStructureError` | A substitution would splice in more than `utils.MAX_SYMBOL_VALUE_LENGTH` (65,536) characters of symbol values (only with `strict_symbols=True`; otherwise the text is left unresolved with a warning on `exploded_job.warnings`, #70) |

**Expansion bounds.** A symbol whose value refers back to itself (`A='&A'`, directly or via other
symbols) is a cycle: during explosion (`substitute_symbols`) the reference is left as written
instead of being re-expanded. At `parse_jcl()` time a SET whose value still holds such an
unresolved reference is dropped from the substitution scope, so a statement referencing it is
blanked with a `job.warnings` entry ("unresolved symbol &A ... resolved to empty string"). Fan-out over
distinct symbols is capped by the character budget above. `JCLLIB ORDER=` libraries must stay
inside the loader's base path (checked lexically, so an operator-symlinked library still works):
an absolute or `..` library is skipped.

# Citations

[1] [api/public-api.md](../api/public-api.md) — Tier 2 loader and explosion exports
[2] [core/parsing-pipeline.md](../core/parsing-pipeline.md) — stage 7 context
[3] [integration/backend-contract.md](../integration/backend-contract.md) — how the backend chains loaders
