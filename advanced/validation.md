---
title: Validation
updated: 2026-06-27
sources: LegacyLens team, 2026-06-27
---

# Validation

jcl-parser has two independent validation layers: **structural validation** (post-parse checks on the Job object) and **parameter validation** (checks on individual DD/EXEC parameters). Both are optional.

## Structural Validation

`validate_jcl()` is a convenience wrapper that parses and validates in one call.

```python
from jclparser import validate_jcl, ErrorSeverity

job, errors = validate_jcl(source)  # NOT a boolean return — always returns (Job, list)
hard_errors = [e for e in errors if e.severity == ErrorSeverity.ERROR]
warnings = [e for e in errors if e.severity == ErrorSeverity.WARNING]
```

Or validate an already-parsed job:
```python
errors = job.validate()  # same list
```

### What Structural Validation Checks

Implemented in `jclparser/validators.py`:

| Rule category | Examples |
|---------------|----------|
| Identifier naming | Max 8 chars, valid charset (A-Z, 0-9, @#$), must start with letter or @#$ |
| Dataset names | Max 44 chars total, max 8 chars per qualifier, valid charset |
| Job structure | JOB card required; steps must follow JOB |
| Step structure | EXEC must have PGM= or PROC=; step name max 8 chars |
| DD structure | DD must follow EXEC; DD name max 8 chars |
| Parameter constraints | RECFM valid values, TIME format, REGION format, MSGLEVEL values |

### Validation Level

```python
from jclparser import validate_jcl, ValidationLevel

job, errors = validate_jcl(source, level=ValidationLevel.STRICT)
```

| Level | Description |
|-------|-------------|
| `BASIC` | Minimum JCL syntax correctness |
| `STANDARD` | Default — common structural rules |
| `STRICT` | All rules including advisory warnings |

## Parameter Validation

`jclparser/parameter_validators.py` validates structured parameter objects built by `parameter_ast.py`.

```python
from jclparser import validate_dd_statement, validate_step_structure

errors = validate_dd_statement(dd)
errors = validate_step_structure(step)
```

Individual identifier and DSN validation:
```python
from jclparser import validate_jcl_identifier, validate_dataset_name

ok, msg = validate_jcl_identifier("MYJOB")  # True, None
ok, msg = validate_jcl_identifier("TOOLONGNAME")  # False, "max 8 chars"
ok, msg = validate_dataset_name("SYS1.PARMLIB")  # True, None
```

## Error Object

All validation errors are `ParseError` or `ValidationError` instances.

```python
error.severity  # ErrorSeverity.ERROR | WARNING | INFO
error.type  # ErrorType.SYNTAX | VALIDATION | STRUCTURE | SEMANTIC
error.message  # str description
error.line_number  # int | None
error.context  # str | None — the problematic JCL fragment
```

Stringifying: `str(error)` produces a human-readable message (used by the backend adapter).

## Error and Severity Enums

```python
from jclparser import ErrorType, ErrorSeverity

ErrorType.SYNTAX  # Bad JCL syntax
ErrorType.VALIDATION  # Structural rule violated
ErrorType.STRUCTURE  # Missing or misplaced construct
ErrorType.SEMANTIC  # Logical inconsistency

ErrorSeverity.ERROR  # Hard failure — job won't run as written
ErrorSeverity.WARNING  # Advisory — job may still run
ErrorSeverity.INFO  # Informational only
```

## Exception Types

Thrown by `parse_jcl()` and `validate_jcl()` when parsing cannot continue:

| Exception | Trigger |
|-----------|---------|
| `JCLSyntaxError` | Malformed JCL that cannot be parsed at all |
| `JCLValidationError` | Structural rule raised to exception level |
| `JCLStructureError` | Missing required structural element (e.g. JOB card absent) |
| `JCLParseError` | Generic parent — catch all JCL errors at once |

All four are importable from `jclparser` directly.

## Dataset Lifecycle Validation

Beyond structural validation, jcl-parser can check dataset lifecycle consistency across steps:

```python
from jclparser import validate_dataset_lifecycle, analyze_dataset_lifecycle

events = analyze_dataset_lifecycle(job)  # list[DatasetEvent] — lifecycle events
issues = validate_dataset_lifecycle(job)  # list[ValidationError] — anomalies
```

This catches: datasets disposed before use, missing CREATE before OPEN, temporary datasets referenced across jobs.

## Lint Rules

Lint is a higher-level validation layer with named, configurable rules in SARIF format:

```python
from jclparser import lint_job, lint_to_sarif, LintConfig

findings = lint_job(job, config=LintConfig())
sarif = lint_to_sarif(findings)
```

Custom rules:
```python
from jclparser import register_lint_rule, LintRule


class MyRule(LintRule):
    id = "CUSTOM-001"

    def check(self, job): ...


register_lint_rule(MyRule())
```

Rules are defined in `jclparser/lint/rules.py`. Built-in rule IDs follow the pattern `JCL-LINT-NNN`.

## Validation in the CLI

```bash
jcl-parser MYJOB.jcl --validate              # structural validation
jcl-parser MYJOB.jcl --validate --json       # JSON output
jcl-parser MYJOB.jcl lint                    # lint rules
```

## See Also

- [../core/parsing-pipeline.md](../core/parsing-pipeline.md) — where validation fits in the pipeline
- [../core/data-model.md](../core/data-model.md) — job.errors and job.warnings
- [../api/public-api.md](../api/public-api.md) — full Tier 1/2 validation export table
- [../integration/backend-contract.md](../integration/backend-contract.md) — how backend uses job.validate()
