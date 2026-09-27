---
type: Development Workflow
title: Development Workflow
description: Install, test, lint, vendor sync, version bump, and task-to-file map for jcl-parser contributors.
tags: [development, workflow, testing, tooling]
timestamp: 2026-07-24T12:00:00Z
---

# Overview

Python 3.10+, no runtime dependencies. Dev toolchain: `pytest`, `ruff`, `mypy`.

# Diagnostic Logging

The package emits INFO/DEBUG diagnostics via the standard `logging` module under the `jclparser` logger (parser, continuation handling, PROC/INCLUDE resolution, explosion, validators, parameter AST). A `NullHandler` is attached by default so consuming applications see no output unless they opt in:

```python
import logging

logging.getLogger("jclparser").setLevel(logging.DEBUG)
logging.basicConfig()
```

All call sites use lazy `%`-formatting; `parameter_validators.py` is intentionally left quiet (hot path). Covered by `tests/unit/test_logging.py`.

# Install

```bash
pip install -e ".[dev]"
```

# Testing

```bash
pytest                                              # full suite; 90% coverage enforced
pytest -m unit                                      # unit tests only
pytest -m integration                               # integration tests only
pytest -m contract                                  # contract tests
pytest tests/unit/test_parser_api.py::Class::method # single test
```

Coverage: minimum 90% (`--cov-fail-under=90`), branch coverage enabled, HTML to `htmlcov/`, XML to `coverage.xml`. Benchmarks excluded via `norecursedirs`.

# Lint / Format / Type-check

```bash
ruff check .      # lint (line-length=88, target=py310)
ruff format .     # format (do not use black)
mypy jclparser/   # strict mode — not yet clean (known violations in profiling.py, explosion.py, and the parser modules parser.py/_statement_parser.py/_post_parse.py)
```

When touching a file, add type annotations where missing. Do not widen the mypy config.

# Vendor Sync (required after any jclparser/ change)

```bash
rm -rf ../backend/_vendor/jcl-parser/jclparser && cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser
```

There is no automated sync. Forgetting this means the backend runs stale code. Do not use plain `cp -r jclparser/ dest/jclparser/` — when `dest/jclparser` already exists, `cp -r` copies *into* it instead of overwriting it, producing a nested `dest/jclparser/jclparser/` and leaving the old files at `dest/jclparser/*` untouched with no error.

# Version Bump

release-please bumps **both** files on release: `pyproject.toml` → `version`, and
`jclparser/__init__.py` → `__version__` (via `extra-files` in `release-please-config.json`,
which rewrites the line marked `# x-release-please-version`). A manual bump must update both;
`tests/unit/test_audit_patch_fixes.py::TestPackageMetadata` fails if they differ.

CLI `--version` reads from `__init__.py`, not package metadata.

# Common Task → File Map

| Task | Files |
|------|-------|
| New JCL statement type | `_statement_parser.py` (keyword in `_STATEMENT_TYPES`), `_job_builder.py` (`JobBuilder._on_<type>` handler), `model.py`, `__init__.py` |
| Statement/parameter tokenization bug | `_statement_parser.py` (`parse_statement`, `_parse_parameters`) |
| Parse-loop / model-assembly bug | `_job_builder.py` (`JobBuilder` dispatch), `_model_factories.py` (`Statement`→model factories), `parser.py` (core loop) |
| Post-parse pass bug (external PROCs, OUTPUT refs, SET substitution) | `_post_parse.py` |
| New DD parameter | `parameter_ast.py`, `parameter_validators.py` |
| New validation rule | `validators.py` or `parameter_validators.py` |
| New lint rule | `lint/rules.py`, `lint/runner.py` |
| New builtin PROC template | `builtin_procs.py:BUILTIN_UTILITY_PROCS` |
| New program profile | new file in `program_profiles/`, register in `__init__.py` |
| New CLI subcommand | `cli.py` |
| PROC expansion bug | `explosion.py`, `proc_loader.py` |
| Continuation line bug | `continuation_handler.py` |
| New condition operator | `condition_parser.py` |
| Change `parse_jcl()` signature | `parser.py:parse_jcl()`, update `__init__.py` |
| Version bump | `pyproject.toml`, `jclparser/__init__.py:__version__` |

# Citations

[1] [development/workflow.md](workflow.md) — full workflow doc
[2] [development/invariants.md](invariants.md) — non-obvious behaviors
[3] [integration/backend-contract.md](../integration/backend-contract.md) — vendor sync and interface contract
