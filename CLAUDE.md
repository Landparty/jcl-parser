# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Docs hooks:** Run `git config core.hooksPath .githooks` once after cloning to enable the pre-commit staleness check. A Claude Code `PostToolUse` hook also fires inline on Edit/Write. See `.claude/settings.json`.
>
> **Documentation index:** [`.okf/index.md`](.okf/index.md) — OKF knowledge bundle; start here for all reference topics (pipeline, API tiers, PROC chain, invariants, task → file map, backend contract).
>
> **One doc tree only.** `.okf/` is the only documentation tree. A stale pre-OKF copy
> (`index.md`, `log.md`, `core/`, `api/`, … at the repo root) was deleted on 2026-10-03 after doc
> updates twice landed there instead of the bundle; do not recreate it.

## Project Overview

**jclparser** is a pure Python library for parsing IBM z/OS JCL (Job Control Language). It builds a structured model of Jobs, Steps, and DD statements; validates JCL syntax and structure; expands PROCs (both inline and external); detects file type heuristically; and provides analysis tools for datasets, SQL usage, metrics, linting, and RC feasibility. No runtime dependencies.

## Backend Integration

This library is **vendored** into `backend/_vendor/jcl-parser/` — it is not installed from PyPI. Changes to this standalone repo must be manually copied before they reach the backend.

There is a *separate* PyPI package, `jcl-parser` (`pip install jcl-parser`), published as an ordinary sdist plus a pure-Python wheel (see "Release & Distribution" below) for external consumers — it does not change or replace the backend's vendoring flow above.

**Interface contract:** [`interface-contract.md`](interface-contract.md) — documents exactly which functions/classes the backend adapter calls, what attributes it reads off the `Job`/`Step`/`DD` objects, and what the `program_structure` dict it produces looks like. Read this before changing public API shapes.

## Commands

```bash
# Install for development
pip install -e .[dev]

# Run all tests (coverage enforced at 90% minimum)
pytest

# Run a single test file
pytest tests/unit/test_parser_api.py

# Run a single test by name
pytest tests/unit/test_parser_api.py::TestClassName::test_method_name

# Run by marker
pytest -m unit
pytest -m integration
pytest -m contract
pytest -m performance

# Lint, format, type-check
ruff check .
ruff format .
mypy jclparser/   # strict mode — currently reports known violations (typing cleanup WIP)
python scripts/mypy_ratchet.py   # what CI runs: fails only on errors not in mypy-baseline.txt

# Vendor sync — run after any change to jclparser/
# (plain `cp -r jclparser/ dest/jclparser/` nests into dest/jclparser/jclparser/
# and silently leaves stale files in place when dest already exists)
rm -rf ../backend/_vendor/jcl-parser/jclparser && cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser
```

Coverage always generates HTML to `htmlcov/` and XML to `coverage.xml`.

## Architecture

The package is `jclparser/` — pure Python, no runtime dependencies. Supports Python 3.10+.

### Parsing pipeline

```
Input (string / file / IO)
  → read_source()                          utils.py
  → resolve_includes_with_origins()        include_loader.py         [optional: expand // INCLUDE]
  → merge_continuation_lines()             continuation_handler.py  [merges column-71 continuations]
  → parse_jcl() core loop                  parser.py                 [JOB/EXEC/DD/SET/IF/PROC/OUTPUT]
  → ParameterParser                        parameter_ast.py          [operand split; DCB/SPACE AST on access]
  → validate_jcl() checks                  parser.py → validators.py [optional: structural rules]
  → explode_job()                          explosion.py              [optional: expand PROCs + &SYMBOLS]
  → Job object
```

See [`.okf/core/parsing-pipeline.md`](.okf/core/parsing-pipeline.md) for the full step-by-step data flow, [`.okf/api/public-api.md`](.okf/api/public-api.md) for all API tier tables, [`.okf/advanced/proc-expansion.md`](.okf/advanced/proc-expansion.md) for the PROC loader chain, and [`.okf/development/workflow.md`](.okf/development/workflow.md) for the common task → file map.

### Key modules

| Module | Role |
|--------|------|
| `parser.py` | Core — `parse_jcl()`, `validate_jcl()`, `parse_statement()` (public API + core loop; re-exports all historical `jclparser.parser` helpers) |
| `_source_scanner.py` | Source pre-scan — `_merge_source_lines()` marks in-stream data / CNTL records and merges continuations |
| `_statement_parser.py` | Single-statement line parsing — `parse_statement()`, parameter tokenization, `_STATEMENT_TYPES`, INCLUDE/JCLLIB pre-scans |
| `_job_builder.py` | `JobBuilder` — per-statement-type dispatch state machine for the core loop (re-exports the helpers below for backward compatibility) |
| `_model_factories.py` | `Statement`→model factories (`_create_job/step/dd_from_statement`) and SET-value resolution helpers |
| `_post_parse.py` | Post-parse passes — external PROC loading, `OUTPUT=*.name` refs, SET substitution, strict DD structure |
| `model.py` | Data model — `Job`, `Step`, `DDStatement`, `ConditionalBlock`, `Procedure` |
| `explosion.py` | PROC expansion — `explode_job()`, `SymbolScope` |
| `proc_loader.py` | External PROC loading — `create_default_loader()`, loader chain |
| `continuation_handler.py` | Merges multi-line JCL statements (column-71 breaks) |
| `parameter_ast.py` | Typed parameter string AST (DCB, SPACE, nested parens) |
| `validators.py` / `parameter_validators.py` | Structural + parameter validation rules |
| `condition_parser.py` | `// IF` condition → typed AST |
| `errors.py` | Exception hierarchy |
| `lint/` | Lint rules + SARIF output, `[tool.jcl-parser.lint]` TOML config, `//* jcl-lint: disable=` suppressions |
| `plugins/` | `StatementPlugin`, `ValidationPlugin`, `PluginRegistry` |
| `program_profiles/` | Known z/OS program analysis (SORT, IEBGENER, IDCAMS, …) |
| `serialization.py` | JSON export — `job_to_dict()`, `JOB_JSON_SCHEMA`, `SCHEMA_VERSION` (also `Job.to_dict()`) |
| `lineage.py` | Cross-job dataset lineage — `load_job_stream()`, `build_lineage()` (run order, dependencies, DOT/Mermaid) |
| `cli.py` | `jcl-parser` CLI — `steps`, `procs`, `detect`, `metrics`, `lint`, `datasets`, `sql`, `analyze`, `paths`; `DIR lineage`, `DIR lint`, `DIR --validate` |
| `checks.py` | Multi-file lint/validate for CI — `lint_paths()`, `validate_paths()`, SARIF/JSON/text renderers, the `jcl-lint` script |
| `builtin_procs.py` | Last-resort IBM utility PROC templates (IMS, DB2, COBOL) |

Full inventory with line counts: [`.okf/development/workflow.md`](.okf/development/workflow.md).

### Public API tiers

- **Tier 1 (stable):** `parse_jcl`, `validate_jcl`, `parse_statement`, `parse`, core model classes, core error types.
- **Tier 2 (advanced):** `explode_job`, loader classes, `detect_file_type`, `parse_condition`, SQL detection, lint/metrics/RC-analysis APIs, plugin system, JSON export (`job_to_dict`, `JOB_JSON_SCHEMA`).
- **Tier 3 (internal):** `MockSystemSymbolProvider`, individual loader types, `FunctionProfile`/`ProfilingResult`.

Full tables: [`.okf/api/public-api.md`](.okf/api/public-api.md).

### External PROC loading

Set `JCL_PROCLIB_PATH` env var or pass `proc_base_path` to `parse_jcl()`. Layout: `<base_path>/SYS1.PROCLIB/MYPROC.jcl`. Inline PROCs always win; builtins are the last-resort fallback.

## Key Invariants

1. **`parse_jcl()` does not expand PROCs** — call `explode_job()` separately when you need explosion.
2. **Column 71 is the continuation boundary** — column 72 is the continuation indicator, 73-80 the sequence field; `normalize_jcl_line()` strips both from fixed-format records and `ContinuationLineHandler` merges what is left. Never pass pre-stripped lines.
3. **`ConditionalBlock.condition` (raw string) is authoritative** — `condition_ast` may be `None` if the expression was unparseable; always use `condition` for display.
4. **`&&` is an escaped ampersand in JCL** — symbol substitution replaces `&NAME` → value and `&&` → `&`, except in a dataset name, where `&&TEMP` is a temporary dataset and is kept. Handled in `explosion.py`.
5. **mypy strict is not yet clean** — 77 known violations across 23 modules (most in `explosion.py` and `model.py`), listed in `mypy-baseline.txt`. Add annotations when touching a file; never widen the config. CI's `typecheck` job runs `scripts/mypy_ratchet.py`, which fails only on errors missing from `mypy-baseline.txt`; after fixing errors, shrink it with `python scripts/mypy_ratchet.py --update` (mypy 2.4.0, as pinned in CI).
6. **Coverage floor is 90%** — every `pytest` run enforces it. Add tests alongside any new module.
7. **A statement's operand field ends at the first blank** outside quotes/parens — the rest is a comment field, stripped before continuation merging (`split_comment_field()`). `IF`/`THEN`/`ELSE`/`ENDIF` are exempt.

Full list (20 invariants): [`.okf/development/invariants.md`](.okf/development/invariants.md).

## Test Structure

```
tests/
  unit/        # ~120 files — individual component tests
  integration/ # ~15 files — end-to-end JCL parsing with realistic job streams
  benchmarks/  # pytest-benchmark perf tests (excluded from default runs via norecursedirs)
```

Markers (enforced via `pyproject.toml`): `unit`, `integration`, `contract`, `performance`, `slow`, `benchmark`.

## Release & Distribution

jcl-parser is free software under the **GNU AGPL v3.0 or later** (`LICENSE`), the same license as the `cobol-parser`, `pl1-parser` and `hlasm-parser` sibling repos.

`release-please` (`.github/workflows/release-please.yml`, driven by Conventional Commits, config in `release-please-config.json` / `.release-please-manifest.json`) automates versioning and `CHANGELOG.md` on every push to `main`. When it cuts a release, the same workflow builds an sdist and one pure-Python (`py3-none-any`) wheel with `python -m build`, attaches them to the GitHub Release, and publishes them to PyPI as `jcl-parser` via Trusted Publishing:

- There are no compiled modules and no `setup.py`; `pyproject.toml` is the whole build configuration. The CI `build` job (PRs only) builds both distributions, runs `twine check`, and installs the wheel into a fresh venv to import it outside the source tree.
- Use `workflow_dispatch` with `target: testpypi` on `.github/workflows/release-please.yml` to rehearse the publish against test.pypi.org (one-time Trusted Publisher registration required there first, environment `pypi`) before trusting a real release.
- This is a wholly separate release artifact from the backend's vendoring flow (see "Backend Integration" above) — publishing to PyPI does not change how `backend/` consumes this library.
- A few modules keep small Cython-compatibility idioms from the retired closed-source build (`utils.py` calls `builtins.open(...)`, `rc_analysis.py` avoids a mixed-size tuple ternary, `dataset_lifecycle.py` avoids a key-view union). They are harmless in pure Python; leave them unless you are rewriting that code anyway.

## Code Style

- Python 3.10+ type hints on all new/changed signatures.
- `ruff` for linting + formatting (line-length 88). `black` is not used — `ruff format` handles formatting.
- **Complexity gate:** `ruff` enforces McCabe complexity <= 12 (`C901`). Functions that predate the gate carry `# noqa: C901 -- complexity baseline` (none left in the parsing pipeline); split one when you touch it and drop its marker. Never add a new marker — extract helpers instead.
- No runtime dependencies; dev tools live in the `[dev]` extra.
