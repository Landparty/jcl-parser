# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**jclparser** is a pure Python library for parsing IBM z/OS JCL (Job Control Language). It builds a structured model of Jobs, Steps, and DD statements; validates JCL syntax and structure; expands PROCs and resolves INCLUDE members (inline and external); and layers on a suite of static-analysis features (lint rules, complexity metrics, return-code feasibility, dataset lifecycle, per-utility program profiles, and SQL/DB2 detection). It ships a CLI and has **no runtime dependencies** (the only optional dependency, `psutil`, is for profiling).

## Backend Integration

This library is **vendored** into `backend/_vendor/jcl-parser/` — it is not installed from PyPI. Changes to this standalone repo must be manually copied before they reach the backend:
```bash
cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/
```

## Commands

```bash
# Install for development
pip install -e .[dev]

# Run all tests (coverage is on by default via pyproject.toml addopts)
pytest

# Run a single test file / single test
pytest tests/unit/test_parser_api.py
pytest tests/unit/test_parser_api.py::TestClassName::test_method_name

# Run by marker
pytest -m unit
pytest -m integration
pytest -m contract

# Benchmarks live in tests/benchmarks/ and are excluded from the default run
# (norecursedirs). Run them explicitly:
pytest tests/benchmarks/ -p no:cacheprovider --no-cov

# Lint and format (matches what CI runs)
ruff check .
ruff format --check .   # use `ruff format .` to apply

# Run the CLI
jcl-parser path/to/job.jcl            # installed console script
python -m jclparser path/to/job.jcl   # equivalent module form
```

Coverage is enforced at **90% minimum** (`--cov-fail-under=90` in `addopts`, also `fail_under = 90.0` under `[tool.coverage.report]`). Every run generates terminal, HTML (`htmlcov/`), and XML (`coverage.xml`) reports. `filterwarnings = ["error", ...]` means most warnings fail the suite.

## Architecture

The package is `jclparser/` — pure Python, no runtime dependencies.

### Core parsing pipeline

1. **`parser.py`** — The core. `parse_jcl()` is the main entry point. Handles continuation lines via `continuation_handler.py`, then builds the AST of `Statement`/`Job`/`Step`/`DDStatement` objects. Also exposes `validate_jcl()` and `parse_statement()`. Supports `enable_profiling=` (see `profiling.py`) and `proc_base_path=` for external PROC loading.

2. **`continuation_handler.py`** — Merges multi-line JCL statements before parsing. JCL uses `//` continuation lines with column-71 breaks.

3. **`model.py`** — Data model: `Job`, `Step`, `DDStatement`, `Parameter`, `Statement`, `OutputStatement`, `Procedure`, `ConditionalBlock`, plus helpers like `iter_execution_steps()`.

4. **`parameter_ast.py`** — Parses JCL parameter strings into a typed AST (nested parentheses, positional vs. keyword params, `DCB`, `SPACE`, etc.).

5. **`parameter_validators.py`** — Validates structured parameter objects (DCB field combinations, SPACE unit types, …).

6. **`validators.py`** — Higher-level validation: identifier naming, dataset name rules, job/step/DD structure, data dependencies. Exposes `validate_jcl_identifier`, `validate_dataset_name`, `validate_job_structure`, `validate_step_structure`, `validate_dd_statement`.

7. **`condition_parser.py`** — Parses `// IF condition THEN` expressions into an AST (`parse_condition()`). Supports `AND`/`OR`/`NOT`, step RC comparisons, `ABEND`, and `RUN` atoms. Returns `None` for unparseable conditions; the raw string on `ConditionalBlock.condition` remains authoritative.

8. **`utils.py`** — Internal parsing helpers (column splitting, identifier extraction, etc.).

9. **`errors.py`** — Exception hierarchy: `JCLSyntaxError`, `JCLValidationError`, `JCLStructureError`, plus `UndefinedSymbolError`, `CircularProcedureError`, `ExplosionDepthError`, `ProcedureNotFoundError`. Also `ParseError`, `ValidationError`, `ErrorType`, `ErrorSeverity`, `ValidationLevel`.

### PROC / INCLUDE / symbol resolution

10. **`explosion.py`** — PROC expansion (`explode_job()`). Resolves inline PROCs and substitutes symbolic parameters (`&SYMBOL`). Tracks expansion depth to detect circular references. Exposes `SymbolScope`.

11. **`proc_loader.py`** — Loads external PROCs. Supports `JCLLIB ORDER`. Loader hierarchy: `InlineProcedureLoader` → `JCLLIBProcedureLoader` → `CompositeProcedureLoader`; `DictProcedureLoader` loads from an in-memory dict (handy for tests). `create_default_loader()` wires them together. Inline PROCs always take precedence over external ones.

12. **`include_loader.py`** — Resolves `// INCLUDE MEMBER=name` statements (`resolve_includes()`). Loaders: `IncludeMemberLoader` (abstract), `DictMemberLoader`, `JCLLIBMemberLoader`. Resolution order mirrors PROC/JCLLIB search.

13. **`system_symbols.py`** — JCL system symbols (`&SYSUID`, `&SYSDATE`, …). Pluggable via `SystemSymbolProvider`; `MockSystemSymbolProvider` is used in tests.

### Statement typing & detection

14. **`jcl_file_type.py`** — Heuristic file-type detection: `detect_file_type()`, `detect_file_type_from_content()`, `is_jcl_file()`, `is_proc_file()`, `FileType` enum.

15. **`jes_statements.py`** — Promotes common JES2 (`/*`) / JES3 (`//*ROUTE XEQ`) control statements to typed dataclasses (`JobParmStatement`, `RouteStatement`, `XmitStatement`, `SignonStatement`, etc.) via `parse_jes_control()`. Unknown commands stay as generic `Statement` (backwards compatible).

16. **`sql_detector.py`** — Detects embedded SQL in inline data and steps that run known DB2 utilities (`DB2_PROGRAMS`). API: `detect_sql_in_job/step/dd/text`, `is_db2_program`, `SQLDetectionResult`.

### Static analysis (read-only over a parsed `Job`)

17. **`metrics.py`** — `compute_metrics(job) -> JobMetrics`: step counts, PROC usage, conditional nesting depth, dataset fan-in/out, cyclomatic-style score.

18. **`rc_analysis.py`** — `compute_feasible_paths(job) -> FeasibilityReport`: walks steps in execution order and flags steps whose `IF`/`COND=` guard is unsatisfiable for every RC combination in a symbolic domain (`DEFAULT_RC_DOMAIN = {0,4,8,12,16}`). Conservative — only flags provably-dead steps.

19. **`dataset_lifecycle.py`** — `analyze_dataset_lifecycle()` / `validate_dataset_lifecycle()`: tracks dataset create/open/dispose across steps, emitting `DatasetEvent`s and diagnostics (duplicate creation, forward reference, uncatalog-before-use). Temporary `&&` datasets are handled by `validators.validate_data_dependencies` instead.

20. **`program_profiles/`** — Per-utility static analysis registry. `base.py` defines `ProgramProfile`/`ProgramAnalysis`; `registry.py` provides `register_profile`, `get_profile`, `clear_profiles`, `analyze_step`, `analyze_job`. Built-in profiles: `idcams`, `iebgener`, `iefbr14`, `ikjeft01`, `sort`.

21. **`lint/`** — Pluggable lint engine. `base.py` (`LintRule`), `config.py` (`LintConfig`), `rules.py` (`BUILTIN_RULES`), `runner.py` (`lint_job`, `all_rules`, `register_rule`/`unregister_rule`, `to_sarif`). SARIF output is supported for CI integration.

### Extensibility & tooling

22. **`plugins/`** — Extension points: `StatementPlugin` (custom statement parsing), `ValidationPlugin` (custom validation), `PluginRegistry`, `ParserConfig`, `ValidationLevel`. Global registry via `get_plugin_registry()`.

23. **`profiling.py`** — `ProfilerContext` wraps parse calls with `cProfile`, `tracemalloc`, and optional `psutil` CPU accounting (lazy import; works without psutil). Exposes `ProfilingResult` and `FunctionProfile`. Enabled via `parse_jcl(..., enable_profiling=True)` or the CLI `--profile` flag.

24. **`cli.py` / `__main__.py`** — Console entry point `jcl-parser` (also `python -m jclparser`). Subcommands/flags include job summary, `steps`, `procs [--explode|--list-available]`, `STEP`/`STEP.DDNAME`/`DDNAME` lookups, `--json`, `--validate`, `detect`, `metrics`, `lint` (`--lint-list`), `datasets`, `sql`, `analyze`, `paths`, and `--profile`. See the module docstring in `cli.py` for the full usage list.

### Public API tiers (from `__init__.py`)

- **Tier 1 (stable)**: `parse_jcl`, `validate_jcl`, `parse_statement`, `parse` (alias), core model classes, core error types, `ValidationLevel`, `__version__`.
- **Tier 2 (advanced)**: `explode_job`/`SymbolScope`, loaders (`ProcedureLoader`, `CompositeProcedureLoader`, `DictProcedureLoader`, `create_default_loader`), INCLUDE loaders + `resolve_includes`, `parse_condition` + condition node types, `validate_*` utilities, `FileType`/`detect_file_type*`, SQL detection, JES statement types, `compute_metrics`/`JobMetrics`, `compute_feasible_paths`/`FeasibilityReport`, dataset lifecycle, program profiles, lint (`lint_job`, `LintRule`, `LintConfig`, `lint_to_sarif`, `register_lint_rule`), plugins, `ParserConfig`, `ProfilingResult`/`FunctionProfile`.
- **Tier 3 (internal/backwards-compat)**: Symbol providers, individual loader types, explosion internals — may be removed in a future major version.

`__all__` in `__init__.py` is the source of truth for the exported surface; keep it in sync when adding/removing public names.

### External PROC / INCLUDE loading

Set the `JCL_PROCLIB_PATH` env var or pass `proc_base_path=` to `parse_jcl()`. The filesystem layout mirrors mainframe dataset naming: `<base_path>/SYS1.PROCLIB/MYPROC.jcl`. Inline PROCs always take precedence over external ones. INCLUDE members resolve via the same JCLLIB convention (`<base_path>/<LIBNAME>/<MEMBER>.jcl`). Test fixtures live under `tests/fixtures/proclibs/`.

## Test Structure

```
tests/
  unit/         # Individual component tests (parser API, models, validators, explosion, lint, …)
  integration/  # End-to-end JCL parsing with realistic job streams, profiling API/CLI
  benchmarks/   # pytest-benchmark perf tests — EXCLUDED from default run (norecursedirs)
  fixtures/     # Sample JCL, real-world jobs, and proclib layouts used across tests
```

Markers defined in `pyproject.toml`: `unit`, `integration`, `contract`, `performance`, `slow`, `benchmark` (`--strict-markers` is on, so undeclared markers fail). Note: there are no separate `contracts/` or `performance/` directories — contract-style tests live inside `tests/unit/` and use the `contract` marker. Coverage minimum: **90%**, enforced on every run.

When adding tests, the `/gen-test` skill scaffolds pytest tests for a module following project conventions.

## Code Style

- **Python 3.10+** (`requires-python = ">=3.10"`; CI matrix covers 3.10–3.13). Use `from __future__ import annotations` and modern type-hint syntax; annotate all signatures.
- `ruff` for linting **and** formatting (ruff's default line length is 88); `black` is not used. CI runs `ruff check .` and `ruff format --check .` — match it before pushing. There is currently no committed `[tool.ruff]` config, so ruff defaults apply.
- The package ships `py.typed` and can be optionally compiled with **mypyc** (`setup.py` calls `mypycify(...)` when mypyc is importable). Keep new modules mypyc-friendly and add them to the `modules` list in `setup.py` if they should be compiled.
- **No runtime dependencies.** Keep it that way — dev tools go in the `[dev]`/`[test]` extras, and `psutil` stays optional under the `[profiling]` extra (import it lazily).

## CI

`.github/workflows/ci.yml` runs two jobs on push/PR to `main`: a **lint** job (`ruff check` + `ruff format --check` on Python 3.13) and a **test** job (matrix 3.10–3.13, `pip install -e .[dev]` then `pytest`). Coverage gating happens inside `pytest`.
</content>
</invoke>
