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
| `ValidationLevel.BASIC` | `"basic"` (default) | Parse-time syntax/structure errors only |
| `ValidationLevel.STRUCTURE` | `"structure"` | Adds `job.validate()` structural rules |
| `ValidationLevel.SEMANTIC` | `"semantic"` | Adds registered `ValidationPlugin` checks: `validate_job(job)`, then `validate_step(step)` for every step (IF branches included) and `validate_dd(dd)` for each of its DDs. Findings keep the plugin's `line_number` (0 when it gives none); severity is always ERROR |

`validate_jcl()` compares `level` against the **raw strings** above. `ValidationLevel` is a
plain `Enum`, not a `StrEnum`, so passing `ValidationLevel.STRUCTURE` silently matches
nothing and degrades to basic validation — pass the string.

## What It Checks

Identifier naming (max 8 chars), dataset names (max 44 chars), JOB card present, step structure, DD structure, parameter constraints (RECFM, TIME, REGION, MSGLEVEL).

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
`UNIT=`/`SPACE=` work file (a system-named temporary dataset). A DD with none
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

The catalog check follows a *state* per dataset, not a count: a normal-termination `CATLG` on a `NEW` allocation catalogs it, a normal `DELETE` / `UNCATLG` removes it. Abnormal-termination dispositions (`DISP=(NEW,PASS,CATLG)`, `(OLD,KEEP,UNCATLG)`) never change the state seen by later steps. So the IEFBR14 "delete if it exists" idiom (`DISP=(MOD,DELETE)`, then re-create `NEW,CATLG`, then read `SHR`) is clean, and a second `NEW,CATLG` after that re-create is still a duplicate.

`validate_data_dependencies` (temporary `&&` datasets, part of `job.validate()`): `DISP=MOD` on a temporary that still exists extends it (the `&&LOADSET` object-deck accumulation of several compiles) rather than creating it twice; an explicit normal `DELETE` ends it, so a later `NEW` of the same name is a fresh creation. `NEW` while the earlier one still exists (passed) is an ERROR, as is `NEW` twice with the default normal disposition (not modelled).

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
