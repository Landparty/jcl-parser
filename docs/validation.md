# Validation & Error Handling

## Validate without parsing

`validate_jcl` returns a list of `ParseError` objects — it never raises.

```python
import jclparser

errors = jclparser.validate_jcl("my_job.jcl")

for e in errors:
    print(f"[{e.severity}] line {e.line_number}: {e.message}")

if not errors:
    print("JCL is valid")
```

## Strict mode

Strict mode turns validation problems into exceptions during parsing.

```python
from jclparser.errors import JCLSyntaxError, JCLValidationError, JCLStructureError

try:
    job = jclparser.parse_jcl("my_job.jcl", strict_mode=True)
except JCLSyntaxError as e:
    print(f"Syntax error at line {e.line_number}: {e.message}")
except JCLValidationError as e:
    print(f"Validation error: {e.message}")
except JCLStructureError as e:
    # e.g. DD statement before any EXEC step
    print(f"Structure error: {e.message}")
```

## Validate individual components

```python
# Identifier rules (1-8 chars, alphanumeric + @#$)
jclparser.validate_jcl_identifier("MYJOB")          # True
jclparser.validate_jcl_identifier("TOOLONGNAME")    # False

# Dataset name rules
jclparser.validate_dataset_name("MY.DATA.SET")      # True
jclparser.validate_dataset_name("&&TEMP")           # True  (temporary)
jclparser.validate_dataset_name("INVALID..NAME")    # False (empty qualifier)

# Structural validation
errors = jclparser.validate_job_structure(job)
errors = jclparser.validate_step_structure(step)
errors = jclparser.validate_dd_statement(dd)
```

## Error fixtures

The `tests/fixtures/sample_jcl/` directory contains JCL files with intentional
errors useful for testing your own tooling:

| File | Error |
|------|-------|
| `error_unclosed_quote.jcl` | Unclosed `'` in parameter |
| `error_unclosed_paren.jcl` | Unmatched `(` in parameter |
| `error_missing_delimiter.jcl` | `DD *` with no closing `/*` |
| `error_circular_proc.jcl` | PROCA → PROCB → PROCA cycle |
| `error_undefined_proc.jcl` | `EXEC PROC=NONEXIST` |
| `error_name_too_long.jcl` | Step name > 8 characters |
| `error_dd_without_exec.jcl` | DD before any EXEC |
