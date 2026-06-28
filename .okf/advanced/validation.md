---
type: Subsystem
title: Validation
description: Two independent validation layers — structural (post-parse job checks) and parameter (DD/EXEC parameter checks) — plus lint rules in SARIF format.
tags: [validation, lint, errors, advanced]
timestamp: 2026-06-28T00:00:00Z
---

# Overview

Two layers, both optional. `validate_jcl()` runs both in one call. The return is always `(Job, list[ParseError])` — never a boolean.

# Structural Validation

Implemented in `jclparser/validators.py`.

```python
from jclparser import validate_jcl, ErrorSeverity

job, errors = validate_jcl(source, level=ValidationLevel.STANDARD)
hard_errors = [e for e in errors if e.severity == ErrorSeverity.ERROR]
```

Or on an already-parsed job:
```python
errors = job.validate()
```

## Validation Levels

| Level | Description |
|-------|-------------|
| `BASIC` | Minimum JCL syntax correctness |
| `STANDARD` | Default — common structural rules |
| `STRICT` | All rules including advisory warnings |

## What It Checks

Identifier naming (max 8 chars), dataset names (max 44 chars), JOB card present, step structure, DD structure, parameter constraints (RECFM, TIME, REGION, MSGLEVEL).

# Parameter Validation

Validates structured parameter objects built by `parameter_ast.py`.

```python
from jclparser import validate_dd_statement, validate_step_structure
from jclparser import validate_jcl_identifier, validate_dataset_name

errors = validate_dd_statement(dd)
ok, msg = validate_jcl_identifier("MYJOB")      # True, None
ok, msg = validate_dataset_name("SYS1.PARMLIB") # True, None
```

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
| `JCLParseError` | Generic parent — catches all four |

# Dataset Lifecycle Validation

```python
from jclparser import validate_dataset_lifecycle, analyze_dataset_lifecycle

events = analyze_dataset_lifecycle(job)  # list[DatasetEvent]
issues = validate_dataset_lifecycle(job) # list[ValidationError] — catches disposed-before-use, etc.
```

# Lint Rules (SARIF output)

```python
from jclparser import lint_job, lint_to_sarif, LintConfig

findings = lint_job(job, config=LintConfig())
sarif = lint_to_sarif(findings)
```

Built-in rule IDs follow `JCL-LINT-NNN`. Custom rules extend `LintRule` ABC.

# Citations

[1] [advanced/validation.md](../../../advanced/validation.md) — full validation doc with examples
[2] [api/public-api.md](../../../api/public-api.md) — Tier 1/2 validation export table
[3] [integration/backend-contract.md](../../../integration/backend-contract.md) — how backend uses `job.validate()`
