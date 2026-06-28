# jcl-parser

Python library for parsing IBM z/OS JCL (Job Control Language) into structured `Job`, `Step`, and `DD` objects. Supports PROC expansion, validation, lint rules, SQL detection, and dataset lifecycle analysis.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-90%25%2B%20enforced-green.svg)](#commands)
[![License: EULA](https://img.shields.io/badge/license-EULA-blue.svg)](LICENSE)

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+. No runtime dependencies.

## Quick Start

```python
import jclparser

job = jclparser.parse_jcl(source)
print(job.name)
print(job.steps[0].program)
```

CLI:

```bash
jcl-parser FILE steps          # list all steps
jcl-parser FILE --validate     # validate JCL
jcl-parser FILE lint           # run lint rules
jcl-parser FILE --json         # full parse result as JSON
```

## Commands

```bash
# Tests
pytest
pytest -m unit

# Lint / format / type-check
ruff check . && ruff format .
mypy jclparser/

# Vendor sync (after changes to jclparser/)
cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/
```

## Documentation

Full reference: [`docs/index.md`](docs/index.md)

## License

Proprietary EULA — see [LICENSE](LICENSE).
