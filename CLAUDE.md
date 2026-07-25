# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Docs hooks:** Run `git config core.hooksPath .githooks` once after cloning to enable the pre-commit staleness check. A Claude Code `PostToolUse` hook also fires inline on Edit/Write. See `.claude/settings.json`.
>
> **Documentation index:** [`.okf/index.md`](.okf/index.md) — OKF knowledge bundle; start here for all reference topics (pipeline, API tiers, PROC chain, invariants, task → file map, backend contract).

## Project Overview

**jclparser** is a pure Python library for parsing IBM z/OS JCL (Job Control Language). It builds a structured model of Jobs, Steps, and DD statements; validates JCL syntax and structure; expands PROCs (both inline and external); detects file type heuristically; and provides analysis tools for datasets, SQL usage, metrics, linting, and RC feasibility. No runtime dependencies.

## Backend Integration

This library is **vendored** into `backend/_vendor/jcl-parser/` — it is not installed from PyPI. Changes to this standalone repo must be manually copied before they reach the backend.

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
  → ContinuationLineHandler.process()      continuation_handler.py  [merges column-71 continuations]
  → resolve_includes()                     include_loader.py         [optional: expand // INCLUDE]
  → parse_jcl() core loop                  parser.py                 [JOB/EXEC/DD/SET/IF/PROC/OUTPUT]
  → ParameterParser                        parameter_ast.py          [typed param AST per statement]
  → validate_jcl() checks                  validators.py             [optional: structural rules]
  → explode_job()                          explosion.py              [optional: expand PROCs + &SYMBOLS]
  → Job object
```

See [`core/parsing-pipeline.md`](core/parsing-pipeline.md) for the full step-by-step data flow, [`api/public-api.md`](api/public-api.md) for all API tier tables, [`advanced/proc-expansion.md`](advanced/proc-expansion.md) for the PROC loader chain, and [`development/development-workflow.md`](development/development-workflow.md) for the common task → file map.

### Key modules

| Module | Role |
|--------|------|
| `parser.py` | Core — `parse_jcl()`, `validate_jcl()`, `parse_statement()` (public API + core loop; re-exports all historical `jclparser.parser` helpers) |
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
| `lint/` | Lint rules + SARIF output |
| `plugins/` | `StatementPlugin`, `ValidationPlugin`, `PluginRegistry` |
| `program_profiles/` | Known z/OS program analysis (SORT, IEBGENER, IDCAMS, …) |
| `cli.py` | `jcl-parser` CLI — `steps`, `procs`, `detect`, `metrics`, `lint`, `datasets`, `sql`, `analyze`, `paths` |
| `builtin_procs.py` | Last-resort IBM utility PROC templates (IMS, DB2, COBOL) |

Full inventory with line counts: [`development/development-workflow.md`](development/development-workflow.md).

### Public API tiers

- **Tier 1 (stable):** `parse_jcl`, `validate_jcl`, `parse_statement`, `parse`, core model classes, core error types.
- **Tier 2 (advanced):** `explode_job`, loader classes, `detect_file_type`, `parse_condition`, SQL detection, lint/metrics/RC-analysis APIs, plugin system.
- **Tier 3 (internal):** `MockSystemSymbolProvider`, individual loader types, `FunctionProfile`/`ProfilingResult`.

Full tables: [`api/public-api.md`](api/public-api.md).

### External PROC loading

Set `JCL_PROCLIB_PATH` env var or pass `proc_base_path` to `parse_jcl()`. Layout: `<base_path>/SYS1.PROCLIB/MYPROC.jcl`. Inline PROCs always win; builtins are the last-resort fallback.

## Key Invariants

1. **`parse_jcl()` does not expand PROCs** — call `explode_job()` separately when you need explosion.
2. **Column 71 is the continuation boundary** — content past col 71 is sequence/ignored; `ContinuationLineHandler` enforces this. Never pass pre-stripped lines.
3. **`ConditionalBlock.condition` (raw string) is authoritative** — `condition_ast` may be `None` if the expression was unparseable; always use `condition` for display.
4. **`&&` is an escaped ampersand in JCL** — symbol substitution replaces `&NAME` → value and `&&` → `&`. Handled in `explosion.py`.
5. **mypy strict is not yet clean** — known violations in `profiling.py`, `explosion.py`, and the parser modules (`parser.py` / `_statement_parser.py` / `_post_parse.py`). Add annotations when touching a file; never widen the config.
6. **Coverage floor is 90%** — every `pytest` run enforces it. Add tests alongside any new module.

Full list (14 invariants): [`development/invariants.md`](development/invariants.md).

## Test Structure

```
tests/
  unit/        # ~80 files — individual component tests
  integration/ # ~15 files — end-to-end JCL parsing with realistic job streams
  benchmarks/  # pytest-benchmark perf tests (excluded from default runs via norecursedirs)
```

Markers (enforced via `pyproject.toml`): `unit`, `integration`, `contract`, `performance`, `slow`, `benchmark`.

## Code Style

- Python 3.10+ type hints on all new/changed signatures.
- `ruff` for linting + formatting (line-length 88). `black` is not used — `ruff format` handles formatting.
- No runtime dependencies; dev tools live in the `[dev]` extra.
