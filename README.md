# jcl-parser

Python library for parsing IBM z/OS JCL (Job Control Language) into structured `Job`, `Step`, and `DD` objects. Supports PROC expansion, validation, lint rules, SQL detection, and dataset lifecycle analysis.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-90%25%2B%20enforced-green.svg)](#commands)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

## Install

```bash
pip install jcl-parser        # from PyPI
pip install -e ".[dev]"       # from a checkout, with the dev tools
```

Requires Python 3.10+. No runtime dependencies.

## Quick Start

```python
from pathlib import Path

import jclparser

job = jclparser.parse_jcl(Path("PAYROLL.jcl"))  # a str is always JCL text, never a path
print(job.name)
for step in jclparser.iter_execution_steps(job.steps):  # also walks IF/THEN/ELSE blocks
    print(step.name, step.program or step.procedure)

exploded = jclparser.explode_job(job)  # PROC expansion is a separate call
errors = jclparser.validate_jcl(
    Path("PAYROLL.jcl"), level="structure"
)  # list[ParseError]
print(job.to_json(indent=2))  # schema: jclparser.JOB_JSON_SCHEMA
```

CLI:

```bash
jcl-parser FILE steps          # list all steps
jcl-parser FILE --validate     # validate JCL
jcl-parser FILE lint           # run lint rules
jcl-parser FILE --json         # full parse result as JSON (job.to_dict())
jcl-parser --json-schema       # JSON Schema of that document
jcl-parser DIR                 # cross-job dataset lineage of a directory of jobs
jcl-parser DIR lineage mermaid # ... as a Mermaid graph (or `dot`)
jcl-parser DIR lint --sarif    # lint every job of a directory, as SARIF
jcl-lint jobs/ --fail-on warning --format sarif -o jcl.sarif   # CI / pre-commit
```

### Lint in CI

Configure the rules in `pyproject.toml`, and switch one off for one statement
with a comment:

```toml
[tool.jcl-parser.lint]
ignore = ["JCL-LINT-002"]
fail-on = "warning"
[tool.jcl-parser.lint.severity]
"JCL-LINT-004" = "warning"
```

```jcl
//* jcl-lint: disable=JCL-LINT-001
//MASTER   DD DSN=PROD.MASTER.FILE,DISP=SHR
```

pre-commit (`.pre-commit-config.yaml`):

```yaml
- repo: https://github.com/landparty/jcl-parser
  rev: v2.2.0   # first release with the hook
  hooks:
    - id: jcl-lint
```

GitHub Actions (findings appear in code scanning):

```yaml
permissions:
  security-events: write
steps:
  - uses: actions/checkout@v4
  - uses: landparty/jcl-parser@v2.2.0   # first release with the action
    with:
      paths: jcl
      glob: "**/*.jcl"
```

## Commands

```bash
# Tests
pytest
pytest -m unit

# Lint / format / type-check
ruff check . && ruff format .
python scripts/mypy_ratchet.py   # mypy strict against the known-error baseline, as CI runs it

# Vendor sync (after changes to jclparser/) — rm first: plain `cp -r` nests
# into dest/jclparser/jclparser/ and leaves stale files when dest exists
rm -rf ../backend/_vendor/jcl-parser/jclparser && cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser
```

## Documentation

Full reference: [`.okf/index.md`](.okf/index.md). Contributors: start with [`CLAUDE.md`](CLAUDE.md)
(commands, architecture, invariants) and [`.okf/development/invariants.md`](.okf/development/invariants.md).
Changes are listed in [`CHANGELOG.md`](CHANGELOG.md) (releases) and [`.okf/log.md`](.okf/log.md).

## License

GNU Affero General Public License v3.0 or later — Copyright © 2026 Samuel Dion. See [LICENSE](LICENSE).
