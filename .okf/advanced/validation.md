---
type: Subsystem
title: Validation
description: Two independent validation layers — structural (post-parse job checks) and parameter (DD/EXEC parameter checks) — plus lint rules in SARIF format.
tags: [validation, lint, errors, advanced]
timestamp: 2026-09-16T00:00:00Z
---

# Overview

Two layers, both optional. `validate_jcl()` runs both in one call and returns a flat
`list[ParseError]` — never a boolean, and **not** a `(Job, errors)` tuple. It discards the
`Job` it parsed internally, so parse separately if you need the model as well.

# Structural Validation

Implemented in `jclparser/validators.py`.

```python
from jclparser import parse_jcl, validate_jcl, ErrorSeverity

errors = validate_jcl(source, level="structure")  # level is a plain str
hard_errors = [e for e in errors if e.severity == ErrorSeverity.ERROR]
job = parse_jcl(source)  # separate call — validate_jcl does not hand back the Job
```

Or on an already-parsed job:
```python
errors = job.validate()
```

## Validation Levels

`ValidationLevel` (in `jclparser.plugins`) has exactly three members. There is no
`STANDARD` and no `STRICT`.

| Member | `validate_jcl(level=...)` string | Description |
|--------|----------------------------------|-------------|
| `ValidationLevel.BASIC` | `"basic"` (default; `"syntax_only"` is an alias) | Parse-time syntax/structure errors, plus the ERROR-severity `job.validate()` findings — exactly what makes `parse_jcl(strict_mode=True)` fail (e.g. "Duplicate step name"). Until 2026-10-04 (#57) those were lost at every level: the strict parse raised `JCLValidationError`, which fell into the syntax-only fallback, so a job with a duplicate step came back `[]` and `--validate` printed `OK` |
| `ValidationLevel.STRUCTURE` | `"structure"` | Every `job.validate()` finding, WARNING/INFO included. Each finding keeps its own severity and line number (fixed 2026-09-28; they used to be re-wrapped as ERROR at line 0, so e.g. a "Duplicate DD name" WARNING came back as an ERROR) |
| `ValidationLevel.SEMANTIC` | `"semantic"` | Adds the `ValidationPlugin` checks **enabled by the `config=`** (`ParserConfig.enabled_plugins`, by class name, or `ALL_PLUGINS`; with no config none run — opt-in since 2026-10-04): `validate_job(job)`, then `validate_step(step)` for every step (IF branches included) and `validate_dd(dd)` for each of its DDs. Findings keep the plugin's `line_number` (0 when it gives none) and its `severity` (a plugin's WARNING/INFO stays one; ERROR when it sets none — fixed 2026-09-28, it was always ERROR) |

`level` takes a `ValidationLevel` member or its string value (case-insensitive); an
unknown level raises `ValueError`. When `level` is omitted, `config.validation_level`
is used, else `"basic"`; an explicit `level` wins over the config. (Before 2026-10-04
`level` was compared to raw strings, so a `ValidationLevel` member silently degraded
to basic validation, and an unknown string did too.)

```python
from jclparser.plugins import ParserConfig, ValidationLevel

config = ParserConfig(validation_level=ValidationLevel.SEMANTIC)
config.enable_plugin("SiteRule")  # plugins are opt-in
errors = validate_jcl(source, config=config)
```

## What It Checks

Identifier naming (max 8 chars), dataset names (max 44 chars), JOB card present, step structure, DD structure, parameter constraints (RECFM, DSORG, TIME, REGION, MSGLEVEL).

Step names are checked with `validators.validate_step_name`, which accepts the qualified names `explode_job()` gives PROC steps (`S1.PS1`, `S1.PS1.IS1`) when every dot-separated part is a valid identifier, so `job.validate()` on an exploded job no longer reports "Invalid step name" for them. Exploded steps from an *unnamed* `EXEC procname` (placeholder qualifier, no `original_proc_call`) are skipped in the duplicate-step-name check; a real duplicate is still reported. Fixed 2026-09-28.

`DSORG` accepts `PS`/`PO`/`DA`/`IS`/`VS`, their unmovable `U` forms (`PSU`/`POU`/`DAU`/`ISU`) and the BTAM/GAM/TCAM organizations `CX`/`GS`/`TX`/`TQ`/`TR` (fixed 2026-09-28).

# Parameter Validation

Validates structured parameter objects built by `parameter_ast.py`.

```python
from jclparser import validate_dd_statement, validate_step_structure
from jclparser import validate_jcl_identifier, validate_dataset_name

errors = validate_dd_statement(dd)
validate_jcl_identifier("MYJOB")  # True (a plain bool)
validate_dataset_name("SYS1.PARMLIB")  # True (a plain bool)
```

`validate_dd_statement` accepts every data source z/OS does: `DSN`/`DSNAME`,
`SYSOUT`, `DUMMY` (stored as the positional `_pos_0`, and legal together with
`DSN=`), in-stream data, `DDNAME=`, `PATH=`, `SUBSYS=`, `DYNAM`, and a
work file with no DSN (a system-named temporary dataset) allocated by `UNIT=`/`SPACE=` or by
`DATACLAS=`/`STORCLAS=`/`MGMTCLAS=`/`LIKE=`/`REFDD=`/`AVGREC=` (the SMS / model forms were
reported as having no data source until 2026-09-28; a bare `DISP=` alone still is). A DD with none
of them is an error, as is more than one of `DSN`/`SYSOUT`/in-stream data.
Dataset names may carry a PDS member (`LIB(MEMBER)`) or GDG generation
(`GDG(+1)`), and a backward reference (`*.STEP.DD`) is accepted as is; a name
that still holds a symbol (`&SYSUID..DATA`) is not judged. An omitted DISP
status (`DISP=(,CATLG)`) is valid — it defaults to `NEW`.

# Error Object Fields

| Field | Type |
|-------|------|
| `severity` | `ErrorSeverity.ERROR / WARNING / INFO` |
| `type` | `ErrorType.SYNTAX / VALIDATION / STRUCTURE / SEMANTIC` |
| `message` | `str` |
| `line_number` | `int \| None` |
| `context` | `str \| None` — the problematic JCL fragment |

`str(error)` produces a human-readable message (used by the backend adapter).

# Exception Types (raised by parse_jcl / validate_jcl)

| Exception | Trigger |
|-----------|---------|
| `JCLSyntaxError` | Malformed JCL that cannot be parsed at all |
| `JCLValidationError` | Structural rule raised to exception level |
| `JCLStructureError` | Missing required structural element (e.g., JOB card absent) |
| `JCLParseError` | Generic parent — catches all of the above. Exported from `jclparser` (as `interface-contract.md` requires) |

# Dataset Lifecycle Validation

```python
from jclparser import validate_dataset_lifecycle, analyze_dataset_lifecycle

events = analyze_dataset_lifecycle(job)  # list[DatasetEvent]
issues = validate_dataset_lifecycle(
    job
)  # list[ValidationError] — catches disposed-before-use, etc.
```

The catalog check follows a *state* per dataset, not a count: any normal-termination `CATLG` catalogs it (`NEW,CATLG` and also `MOD,CATLG` — the latter since 2026-09-28), a normal `DELETE` / `UNCATLG` removes it. Abnormal-termination dispositions (`DISP=(NEW,PASS,CATLG)`, `(OLD,KEEP,UNCATLG)`) never change the state seen by later steps. So the IEFBR14 "delete if it exists" idiom (`DISP=(MOD,DELETE)`, then re-create with `NEW,CATLG` or `MOD,CATLG`, then read `SHR`) is clean, and a second `NEW,CATLG` after that re-create is still a duplicate. A `MOD` use never warns "opened ... after being uncataloged" (MOD creates a missing dataset); `OLD`/`SHR` after a delete still does. Dispositions take effect at **step end**: every DD of a step is checked against the state before the step, and the step's normal dispositions are applied afterwards in DD order, so `//D3 DD DSN=PROD.B,DISP=(OLD,DELETE)` followed by `//D4 DD DSN=PROD.B,DISP=SHR` in the same step is clean while a `SHR` in a *later* step still warns (fixed 2026-10-04, #65; the state used to change per DD). A cataloging allocation counts within the step at once, so two `NEW,CATLG` of one dataset in one step are still a duplicate.

A backward reference `DSN=*.STEP.DD` is recorded under the dataset of the DD it refers to, so a delete through a referback ends that dataset (`NULLFILE` and unresolvable references record no event). `IF`/`THEN`/`ELSE` branches are walked separately, each from the state before the IF, and merged at `ENDIF`: the same `NEW,CATLG` in the THEN and the ELSE branch is not a duplicate, a duplicate within one branch still is, and after `ENDIF` a dataset counts as cataloged (or uncataloged) when either branch left it so. Both fixed 2026-09-28.

**PROC-call overrides on an unexploded job** (fixed 2026-10-12): a `//PROCSTEP.DD` override under `EXEC procname` (and the unnamed concatenation members after it) lives in `Step.dd_overrides` / `dd_override_concatenations`, not `dd_statements`. Both checks — the catalog check and `validate_data_dependencies` below — now read a step's DDs through `model._dataset_dds()`, which adds those overrides in source order for a PROC call, so `&&T` created by `//PS1.OUT DD DSN=&&T,DISP=(NEW,PASS)` is no longer "used but never created" in the next step, and a `NEW,CATLG` in an override counts toward duplicate cataloging (both already held on the exploded job). The event is recorded under the calling step (`S1`) with the qualified DD name (`PS1.OUT`), so a referback `*.S1.PS1.OUT` resolves to it. Overrides under an `EXEC PGM=` step are ignored, as z/OS ignores them. Regression tests: `tests/unit/test_bughunt_validation.py::TestProcCallOverrideDatasets`. The forward-reference warning ("opened DISP=OLD/SHR ... before it is allocated in a later step") only counts allocations on a path that also runs the open: an `OLD` in the THEN branch is not a forward reference to a `NEW` in the ELSE of the same IF (fixed 2026-10-10); one in a later, separate IF still is.

`validate_data_dependencies` (temporary `&&` datasets, part of `job.validate()`): `DISP=MOD` on a temporary that still exists extends it (the `&&LOADSET` object-deck accumulation of several compiles) rather than creating it twice; an explicit normal `DELETE` ends it, and so does an *omitted* normal disposition on a `NEW` allocation (`DISP=NEW`, `DISP=(NEW,,DELETE)` — the default is DELETE; fixed 2026-09-28), so a later `NEW` of the same name is a fresh creation. `NEW` while the earlier one still exists (`DISP=(NEW,PASS)`) is an ERROR. A temporary is keyed without its member: `&&GOSET(GO)` and `&&GOSET` are one dataset. `IF`/`THEN`/`ELSE` branches are walked like the catalog check above: each from the set of temporaries alive before the IF, merged at `ENDIF` (alive when either branch left it), so the same `&&T,DISP=(NEW,PASS)` in the THEN and the ELSE is not a duplicate (fixed 2026-10-04, #60 — `parse_jcl(strict_mode=True)` raised on it); a second creation within one branch, or after `ENDIF` while a branch's copy is still passed, is still an ERROR.

# Lint Rules (SARIF output)

```python
from jclparser import lint_job, lint_to_sarif, LintConfig

findings = lint_job(job, config=LintConfig())
sarif = lint_to_sarif(findings, artifact_uri="jobs/MYJOB.jcl")
```

Every result location carries `physicalLocation.artifactLocation` (SARIF 2.1.0 requires it); `artifact_uri` fills its `uri` — omit it and the `artifactLocation` is empty, which is schema-valid but gives consumers such as GitHub code scanning no file to place the result in.

Built-in rule IDs follow `JCL-LINT-NNN`. Custom rules extend `LintRule` ABC.

# Citations

[1] [development/invariants.md](../development/invariants.md) — invariant 7 (validate_jcl return shape)
[2] [api/public-api.md](../api/public-api.md) — Tier 1/2 validation export table
[3] [integration/backend-contract.md](../integration/backend-contract.md) — how backend uses `job.validate()`
