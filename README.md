# jcl-parser

A Python library for parsing IBM JCL (Job Control Language) into structured objects.

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://python.org)
[![Coverage](https://img.shields.io/badge/coverage-92%25-green.svg)](#testing)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Install

```bash
git clone https://github.com/Landparty/jcl-parser.git
cd jcl-parser
pip install -e .[dev]
```

## Quick start

```python
import jclparser

jcl = """
//MYJOB    JOB (ACCT),'My Job',CLASS=A
//STEP1    EXEC PGM=SORT
//SORTIN   DD  DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD  DSN=OUTPUT.DATA,DISP=(NEW,CATLG,DELETE)
//SYSIN    DD  *
  SORT FIELDS=(1,10,CH,A)
/*
"""

job = jclparser.parse_jcl(jcl)

print(job.name)                     # MYJOB
print(job.steps[0].program)         # SORT
print(job.steps[0].get_dd("SORTIN").dataset_name)  # INPUT.DATA
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Basic parsing](docs/basic-parsing.md) | Parse from string, file, or file object; navigate Job / Step / DD |
| [Validation & errors](docs/validation.md) | `validate_jcl`, strict mode, error types, error fixtures |
| [PROC expansion](docs/proc-expansion.md) | Inline and external PROCs, `explode()`, file-type detection |
| [Advanced features](docs/advanced-features.md) | Condition parsing, SQL detection, plugins, structured DCB/SPACE |

## Testing

```bash
pytest                        # run all tests (coverage enforced at 87 %)
pytest -m unit                # unit tests only
pytest -m integration         # integration tests only
ruff check . && ruff format . # lint and format
```

Test fixtures live in `tests/fixtures/` — see the [fixtures README](tests/fixtures/sample_jcl/README.md) for a full catalogue including error cases and real-world examples.

## Public API

```
Tier 1 (stable)   parse_jcl · validate_jcl · parse_statement
                  Job · Step · DDStatement · Parameter · Statement
                  JCLSyntaxError · JCLValidationError · JCLStructureError

Tier 2 (advanced) explode_job · detect_file_type · parse_condition
                  detect_sql_in_job · ProcedureLoader · ParserConfig
                  validate_jcl_identifier · validate_dataset_name

Tier 3 (internal) MockSystemSymbolProvider · InlineProcedureLoader · …
                  (may be removed in a future major version)
```

## License

MIT — see [LICENSE](LICENSE).
