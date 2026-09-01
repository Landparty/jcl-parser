# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Docs hooks:** Run `git config core.hooksPath .githooks` once after cloning to enable the pre-commit staleness check. A Claude Code `PostToolUse` hook also fires inline on Edit/Write. See `.claude/settings.json`.
>
> **Documentation index:** [`.okf/index.md`](.okf/index.md) — OKF knowledge bundle; start here for all reference topics (pipeline, API tiers, PROC chain, invariants, task → file map, backend contract).

## Project Overview

**jclparser** is a pure Python library for parsing IBM z/OS JCL (Job Control Language). It builds a structured model of Jobs, Steps, and DD statements; validates JCL syntax and structure; expands PROCs (both inline and external); detects file type heuristically; and provides analysis tools for datasets, SQL usage, metrics, linting, and RC feasibility. No runtime dependencies.

## Backend Integration

This library is **vendored** into `backend/_vendor/jcl-parser/` — it is not installed from PyPI. Changes to this standalone repo must be manually copied before they reach the backend.

There is a *separate* PyPI package, `jcl-parser` (`pip install jcl-parser`), published as closed-source compiled wheels only (see "Release & Distribution" below) for external consumers — it does not change or replace the backend's vendoring flow above.

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

## Release & Distribution

`release-please` (`.github/workflows/release-please.yml`, driven by Conventional Commits, config in `release-please-config.json` / `.release-please-manifest.json`) automates versioning and `CHANGELOG.md` on every push to `main`. When it cuts a release, the same workflow also builds and publishes **closed-source binary wheels** to PyPI as `jcl-parser` (`pip install jcl-parser`) — mirrors the `cobol-parser` sibling repo's setup exactly (see that repo's CLAUDE.md for the original design rationale):

- `setup.py` (`JCLPARSER_CLOSED_SOURCE=1`, set only by this CI job — never by local dev or `pip install -e .`) Cythonizes every `jclparser/**/*.py` module except `__init__.py`/`__main__.py` (thin re-export/runpy stubs with no logic of their own) and `profiling.py` (see below), so the built wheel contains no readable `.py` source for anything else. `_ClosedSourceBuildPy` in `setup.py` handles the *module*-copy path; `[tool.setuptools.exclude-package-data]` in `pyproject.toml` (`"*.py"`, alongside `*.c`/`*.pyx`/`*.h`) is equally load-bearing — `include_package_data=True` drives a separate build_py *data-files* path that independently re-adds every git-tracked `.py` file unless excluded there too. Don't "simplify" that exclude-package-data entry back down to `["*.c", "*.pyx", "*.h"]`.
- `profiling.py` stays plain Python even in the closed-source build (`_UNCOMPILED_FILENAMES` in `setup.py`, `ALLOWED_PY_NAMES` in `scripts/_closed_source_checks.py`). `ProfilerContext` wraps stdlib `cProfile`, which records calls via `sys.setprofile` — a hook the CPython interpreter loop fires on Python-level call/return events, which a Cython-compiled function's own body does not dispatch through. A compiled `ProfilerContext.__enter__`/`__exit__` silently collects zero samples, and `pstats.Stats` then raises `TypeError: Cannot create ... from <cProfile.Profile ...>` — caught by `tests/unit/test_profiling.py` while building this out, which is why the exclusion exists rather than being assumed unnecessary. The tradeoff is a small amount of source disclosure (a stdlib cProfile/tracemalloc wrapper, not JCL-parsing logic) for a profiler that actually profiles.
- A stock `pip install .` / `pip install -e .` (no env var set) builds no extensions at all — normal development stays pure Python, unchanged from before this build existed. There is no `[fast]`-style accelerator extra: unlike `cobol-parser`, jclparser has no hand-tuned hot-path modules, only the one closed-source-or-nothing build mode.
- `cibuildwheel` (`[tool.cibuildwheel]` in `pyproject.toml`) builds one wheel each for manylinux x86_64, macOS arm64, and Windows AMD64, across Python 3.10-3.13 (12 wheels total). Its `test-command` runs against *every* one of those wheels in CI: `scripts/check_installed_no_leaked_source.py` (no `.py`/`.c`/`.pyx`/`.h`/`.pyi` leaked, extension modules present) followed by a closed-source-build import smoke test and a fast pytest subset — all against the installed wheel, not the source tree.
- No sdist and no pure-Python fallback wheel are published anywhere — both would ship full source of a proprietary-licensed codebase (see `LICENSE`).
- `scripts/verify_closed_source_wheel.py` builds a wheel locally with the same env var and asserts no `.py` source leaked in (via the same `scripts/_closed_source_checks.py` assertion the CI check uses), then smoke-installs it into a throwaway venv, for manual verification outside CI. Its wheel glob is `*.whl`, not `jclparser-*.whl` — the PyPI distribution name `jcl-parser` normalizes to `jcl_parser-*.whl` in the actual filename, which does not start with `jclparser`.
- Use `workflow_dispatch` with `target: testpypi` on `.github/workflows/release-please.yml` to rehearse the whole build-all-wheels-and-publish pipeline against test.pypi.org (one-time Trusted Publisher registration required there first) before trusting a real release.
- This is a wholly separate release artifact from the backend's vendoring flow (see "Backend Integration" above) — publishing to PyPI does not change how `backend/` consumes this library.
- Cython (unlike mypyc, which `setup.py` briefly attempted before this) does not require the compiled module to pass a full mypy-strict check, which matters here: several modules still have known mypy-strict violations (see "Key Invariants" above) that would otherwise block every closed-source build. One real Cython-specific gotcha did surface and was fixed: Cython caches a bare builtin name's target (e.g. a bare `open(...)` call) at first use, which is invisible to a `unittest.mock.patch("builtins.open", ...)` made afterward — `utils.py`'s `_read_file_with_fallback` now calls `builtins.open(...)` explicitly so the lookup stays a live attribute access, matching plain-Python monkeypatch semantics.

## Code Style

- Python 3.10+ type hints on all new/changed signatures.
- `ruff` for linting + formatting (line-length 88). `black` is not used — `ruff format` handles formatting.
- No runtime dependencies; dev tools live in the `[dev]` extra.
