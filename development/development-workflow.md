---
title: Development Workflow
updated: 2026-06-27
sources: LegacyLens team, 2026-06-27
---

# Development Workflow

## Install

```bash
pip install -e ".[dev]"   # editable install with dev extras
```

Requires Python 3.10+. No runtime dependencies.

## Running Tests

```bash
# Full suite — coverage enforced at 90%
pytest

# Only unit tests
pytest -m unit

# Only integration tests
pytest -m integration

# A single test file
pytest tests/unit/test_parser_api.py

# A specific test method
pytest tests/unit/test_parser_api.py::TestClassName::test_method_name

# Contract tests
pytest -m contract

# Performance tests
pytest -m performance
```

### Coverage

- Minimum **90%** — enforced on every `pytest` run via `--cov-fail-under=90`
- Branch coverage enabled
- HTML report generated to `htmlcov/`
- XML report generated to `coverage.xml`
- Benchmark tests are excluded from coverage (`tests/benchmarks/` in `norecursedirs`)

**Never add a module without adding tests alongside it.**

## Lint, Format, Type-check

```bash
ruff check .           # lint
ruff format .          # format (replaces black)
mypy jclparser/        # type check (strict mode — not yet clean)
```

`ruff` enforces: `line-length = 88`, `target-version = "py310"`. Do not use `black` — `ruff format` handles formatting.

### mypy State

`mypy --strict` is configured but **not yet clean**. Known violations in `profiling.py`, `explosion.py`, `parser.py`. When touching a file, add type annotations where missing. Do not widen the mypy config.

## CLI Usage

```bash
jcl-parser examples/DIVIDE.jcl steps
jcl-parser examples/DIVIDE.jcl --validate --json
jcl-parser examples/DIVIDE.jcl metrics
jcl-parser examples/DIVIDE.jcl lint
```

## Vendor Sync

After any change to `jclparser/`, sync to the backend:

```bash
cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/
```

This is a **manual step** — there is no automated sync. Forgetting this means the backend runs stale code.

## Version Bumping

Update **both** files together:
1. `pyproject.toml` → `version = "X.Y.Z"`
2. `jclparser/__init__.py` → `__version__ = "X.Y.Z"`

The CLI `--version` reads from `__init__.py`, not from package metadata.

Release management is via `release-please` (`.github/workflows/release-please.yml`).

## CI

`.github/workflows/ci.yml` — runs lint + tests on push and PR. The `90%` coverage floor is enforced in CI.

## Common Task → File Map

| Task | Files |
|------|-------|
| Add a new JCL statement type | `parser.py`, `model.py`, `__init__.py` |
| Add a DD parameter | `parameter_ast.py`, `parameter_validators.py` |
| Add a validation rule | `validators.py` or `parameter_validators.py` |
| Add a lint rule | `lint/rules.py`, `lint/runner.py` |
| Add a builtin PROC template | `builtin_procs.py:BUILTIN_UTILITY_PROCS` |
| Add a program profile | new file under `program_profiles/`, register in `__init__.py` |
| Add a CLI subcommand | `cli.py` |
| Fix a PROC expansion bug | `explosion.py`, `proc_loader.py` |
| Fix a continuation line bug | `continuation_handler.py` |
| Add a condition operator | `condition_parser.py` |
| Change `parse_jcl()` signature | `parser.py:parse_jcl()`, update `__init__.py` |
| Bump version | `pyproject.toml`, `jclparser/__init__.py:__version__` |

## Configuration (pyproject.toml)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--strict-markers", "--cov=jclparser", "--cov-fail-under=90"]
norecursedirs = ["tests/benchmarks"]

[tool.ruff]
line-length = 88
target-version = "py310"

[tool.mypy]
python_version = "3.10"
strict = true
```

## See Also

- [../api/cli-reference.md](../api/cli-reference.md) — CLI subcommands and flags
- [../integration/backend-contract.md](../integration/backend-contract.md) — vendor sync and interface contract
- [invariants.md](invariants.md) — non-obvious behaviors to keep in mind while developing
