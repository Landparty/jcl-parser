---
type: Development Workflow
title: Development Workflow
description: Install, test, lint, mypy ratchet, CI, vendor sync, version bump, release, module inventory and task-to-file map for jcl-parser contributors.
tags: [development, workflow, testing, tooling]
timestamp: 2026-10-04T00:00:00Z
---

# Overview

Python 3.10+ (CI tests 3.10, 3.11, 3.12, 3.13), no runtime dependencies. Dev toolchain: `pytest`, `ruff`, `mypy`. Licensed AGPL-3.0-or-later (`LICENSE`).

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

Layout: `tests/unit/` (95 `test_*.py` files), `tests/integration/` (15), `tests/benchmarks/` (pytest-benchmark, not collected by default), `tests/fixtures/`. Markers (strict): `unit`, `integration`, `contract`, `performance`, `slow`, `benchmark`.

# Lint / Format / Type-check

```bash
ruff check .      # lint (line-length=88, target=py310, McCabe complexity <= 12 via C901)
ruff format .     # format (do not use black)
mypy jclparser/   # strict mode — not yet clean (82 known errors across ~25 modules, recorded in mypy-baseline.txt)
python scripts/mypy_ratchet.py           # what CI runs: fails only on errors missing from mypy-baseline.txt
python scripts/mypy_ratchet.py --update  # after fixing errors, shrink the baseline (use mypy 2.4.0, as pinned in CI)
```

When touching a file, add type annotations where missing. Do not widen the mypy config. The ratchet drops line/column numbers when comparing, so code that merely moves does not count as a new error.

# CI (`.github/workflows/ci.yml`)

| Job | Runs | What |
|-----|------|------|
| `lint` | push to `main`, PRs, dispatch | `ruff check .` + `ruff format --check .` (Python 3.13) |
| `typecheck` | push to `main`, PRs, dispatch | `scripts/mypy_ratchet.py` with `mypy==2.4.0` (Python 3.13) |
| `test` | push to `main`, PRs, dispatch | `pip install -e .[dev]` + `pytest` on Python 3.10 / 3.11 / 3.12 / 3.13 |
| `build` | PRs and dispatch only | `python -m build` (sdist + pure-Python wheel), `twine check`, install the wheel in a fresh venv and import it outside the tree |

The pre-commit hook (`.githooks/pre-commit` → `scripts/okf_staleness_check.py`) maps source paths to their `.okf/` pages; a change is covered when any mapped page, or `.okf/log.md`, is staged.

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

# Release

`release-please` (`.github/workflows/release-please.yml`, Conventional Commits, `release-please-config.json` / `.release-please-manifest.json`) opens the release PR and, when it is merged, builds an sdist plus one pure-Python `py3-none-any` wheel with `python -m build`, attaches them to the GitHub Release and publishes them to PyPI as `jcl-parser` via Trusted Publishing. `workflow_dispatch` with `target: testpypi` (the default) rehearses the publish against test.pypi.org. There is no `setup.py` and no compiled build — the closed-source Cython build was dropped on 2026-10-03. The PyPI package does not change the backend's vendoring flow.

# Module Inventory

Line counts as of 2026-10-08 (`wc -l`).

| Module | Lines | Role |
|--------|------:|------|
| `__init__.py` | 279 | Public API re-exports, `parse()` alias, `__version__` |
| `__main__.py` | 5 | `python -m jclparser` |
| `parser.py` | 633 | `parse_jcl()`, `validate_jcl()`, parse loop and its phases (`_expand_includes`, `_build_job`, `_resolve_references`, …), line-by-line validation fallback |
| `_source_scanner.py` | 367 | `_merge_source_lines()` (`_RecordClassifier` marks in-stream data / CNTL records, then continuation merge), `_instream_delimiter`, `_expects_continuation` |
| `_statement_parser.py` | 817 | Single-statement parsing, `_STATEMENT_TYPES`, `split_comment_field()`, INCLUDE/JCLLIB pre-scans |
| `_job_builder.py` | 824 | `JobBuilder` per-statement-type dispatch (`JobBuilder._HANDLERS` table) |
| `_model_factories.py` | 176 | `Statement` → `Job`/`Step`/`DDStatement` factories, SET-value helpers |
| `_post_parse.py` | 386 | External PROC loading, `OUTPUT=*.name` refs, SET substitution, strict DD structure |
| `model.py` | 985 | `Job`, `Step`, `DDStatement`, `ConditionalBlock`, `Procedure`, `Statement`, `OutputStatement`, `Parameter` |
| `explosion.py` | 1604 | `explode_job()`, `SymbolScope`, DD/EXEC overrides, `DEFAULT_MAX_STEPS` |
| `proc_loader.py` | 427 | Loader chain, `create_default_loader()` |
| `builtin_procs.py` | 246 | `BUILTIN_UTILITY_PROCS` last-resort templates |
| `include_loader.py` | 437 | `resolve_includes()`, member loaders |
| `continuation_handler.py` | 478 | `ContinuationLineHandler` |
| `parameter_ast.py` | 397 | Typed parameter AST (`DCBParameter`, `SPACEParameter`, …) |
| `parameter_validators.py` | 262 | Parameter value validators |
| `validators.py` | 439 | Structural validation |
| `condition_parser.py` | 562 | `// IF` condition AST, `NOT_RUN` |
| `dataset_lifecycle.py` | 558 | Cross-step dataset lifecycle analysis |
| `rc_analysis.py` | 502 | RC feasibility (`compute_feasible_paths`) |
| `metrics.py` | 167 | `compute_metrics` |
| `sql_detector.py` | 232 | SQL / DB2 detection |
| `jes_statements.py` | 382 | Typed JES2/JES3 control statements |
| `jcl_file_type.py` | 279 | JCL vs PROC detection |
| `system_symbols.py` | 253 | System symbol providers |
| `utils.py` | 228 | `read_source()`, `normalize_jcl_line()`, `instream_delimiter()`, `MAX_LIBRARY_MEMBER_BYTES` |
| `errors.py` | 173 | Exception hierarchy |
| `profiling.py` | 147 | `FunctionProfile`, `ProfilingResult` |
| `cli.py` | 966 | `jcl-parser` CLI |
| `lint/` (5 files) | 467 | `LintRule`, built-in rules, runner, SARIF |
| `plugins/` (2 files) | 248 | `ParserConfig`, `ValidationLevel`, plugin registry |
| `program_profiles/` (27 files) | 2411 | Known-program profiles (SORT, ICETOOL, IDCAMS, IEBGENER, DFSRRC00, …) and registry |

# Common Task → File Map

| Task | Files |
|------|-------|
| New JCL statement type | `_statement_parser.py` (keyword in `_STATEMENT_TYPES`), `_job_builder.py` (`JobBuilder._on_<type>(stmt, line_num)` handler + its `JobBuilder._HANDLERS` entry — a test fails if a type is missing), `model.py`, `__init__.py` |
| In-stream data / CNTL / continuation pre-scan bug | `_source_scanner.py` (`_RecordClassifier`, `_weave_lines`) |
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
