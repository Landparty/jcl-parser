# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**jclparser** is a pure Python library for parsing IBM z/OS JCL (Job Control Language). It builds a structured model of Jobs, Steps, and DD statements; validates JCL syntax and structure; expands PROCs (both inline and external); detects file type heuristically; and provides analysis tools for datasets, SQL usage, metrics, linting, and RC feasibility. No runtime dependencies.

## Backend Integration

This library is **vendored** into `backend/_vendor/jcl-parser/` — it is not installed from PyPI. Changes to this standalone repo must be manually copied before they reach the backend:
```bash
cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/
```

## Commands

```bash
# Install for development
pip install -e .[dev]

# Run all tests (includes coverage by default via pytest.ini)
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

# Lint and format
ruff check .
ruff format .
```

Coverage is enforced at 90% minimum (configured in `pyproject.toml` under `[tool.coverage.report]`). Tests always generate HTML coverage to `htmlcov/` and XML to `coverage.xml`.

## Architecture

The package is `jclparser/` — a pure Python library with no runtime dependencies. Supports Python 3.10+.

### Parsing pipeline

1. **`parser.py`** — The core. `parse_jcl()` is the main entry point. Handles continuation lines by delegating to `continuation_handler.py`, then builds the AST of `Statement` objects. Also exposes `validate_jcl()` and `parse_statement()`.

2. **`continuation_handler.py`** — Merges multi-line JCL statements before parsing. JCL uses `//` continuation lines with column-71 breaks.

3. **`model.py`** — Data model: `Job`, `Step`, `DDStatement`, `Parameter`, `Statement`, `OutputStatement`, `ConditionalBlock`, `Procedure`. These are the objects returned from parsing.

4. **`parameter_ast.py`** — Parses JCL parameter strings into a typed AST (handles nested parentheses, positional vs. keyword params, `DCB`, `SPACE`, etc.).

5. **`parameter_validators.py`** — Validates structured parameter objects (e.g., DCB field combinations, SPACE unit types, TIME, REGION, MSGLEVEL, RECFM, etc.).

6. **`validators.py`** — Higher-level validation: identifier naming rules, dataset name rules, job/step/DD structure validation.

7. **`explosion.py`** — PROC expansion (`explode_job()`). Resolves inline PROCs and substitutes symbolic parameters (`&SYMBOL`). Tracks expansion depth to detect circular references. Exposes `SymbolScope`.

8. **`proc_loader.py`** — Loads external PROCs from the filesystem. Supports `JCLLIB ORDER` statements. Loader hierarchy: `InlineProcedureLoader` → `JCLLIBProcedureLoader` → `CompositeProcedureLoader`. `create_default_loader()` wires them together.

9. **`include_loader.py`** — Loads `// INCLUDE MEMBER=name` members from JCLLIB. Mirrors PROC loader conventions. Exposes `IncludeMemberLoader`, `DictMemberLoader`, `JCLLIBMemberLoader`, and `resolve_includes()`.

10. **`system_symbols.py`** — Provides JCL system symbols (`&SYSUID`, `&SYSDATE`, etc.). Pluggable via `SystemSymbolProvider` base class; `MockSystemSymbolProvider` is used in tests.

11. **`jcl_file_type.py`** — Heuristic detection of whether a file is JCL, a PROC, or neither (`detect_file_type()`, `detect_file_type_from_content()`, `is_jcl_file()`, `is_proc_file()`).

12. **`condition_parser.py`** — Parses `// IF condition THEN` expressions into an AST (`parse_condition()`). Supports `AND`/`OR`/`NOT`, step RC comparisons, `ABEND`, and `RUN` atoms. Returns `None` for unparseable conditions; the raw string on `ConditionalBlock.condition` remains authoritative.

13. **`sql_detector.py`** — Detects SQL/DB2 program usage in steps and DD statements (`detect_sql_in_step`, `detect_sql_in_job`, `detect_sql_in_dd`, `detect_sql_in_text`, `is_db2_program`, `DB2_PROGRAMS`).

14. **`jes_statements.py`** — Typed JES2/JES3 control statement models. Promotes common `/*COMMAND` statements to dataclasses with parsed fields (`JobParmStatement`, `RouteStatement`, `XmitStatement`, etc.). Exposes `parse_jes_control()`.

15. **`dataset_lifecycle.py`** — Cross-step dataset lifecycle analysis. Tracks how datasets are created, opened, and disposed across all steps. Detects duplicate creation, forward references, and uncatalog-before-use. Exposes `DatasetEvent`, `analyze_dataset_lifecycle()`, `validate_dataset_lifecycle()`.

16. **`metrics.py`** — Structural job metrics: step counts, PROC usage, conditional nesting depth, dataset fan-in/fan-out, and a lightweight cyclomatic-style score. Exposes `JobMetrics`, `compute_metrics()`.

17. **`rc_analysis.py`** — Return-code feasibility analysis. Walks the job in execution order and determines whether IF-guarded or COND-guarded steps are reachable under any combination of predecessor RCs from a symbolic domain. Exposes `FeasibilityReport`, `compute_feasible_paths()`, `DEFAULT_RC_DOMAIN`.

18. **`program_profiles/`** — Program profile analysis. Maps known z/OS programs (SORT, IEBCOPY, IDCAMS, DB2 utilities, etc.) to structured profiles describing their purpose and DD requirements. Exposes `ProgramProfile`, `ProgramAnalysis`, `analyze_step()`, `analyze_job()`, `register_profile()`.

19. **`lint/`** — Linting rules for JCL best practices. Rules are registered via `register_lint_rule()`. Exposes `LintRule`, `LintConfig`, `lint_job()`, `lint_to_sarif()`.

20. **`plugins/`** — Extension points: `StatementPlugin` (custom statement parsing), `ValidationPlugin` (custom validation rules), `PluginRegistry`, `ParserConfig`, `ValidationLevel`. Get the global registry via `get_plugin_registry()`.

21. **`errors.py`** — Exception hierarchy: `JCLSyntaxError`, `JCLValidationError`, `JCLStructureError`, plus `UndefinedSymbolError`, `CircularProcedureError`, `ExplosionDepthError`, `ProcedureNotFoundError`. Also `ParseError`, `ValidationError`, `ErrorType`, `ErrorSeverity`.

22. **`utils.py`** — Internal parsing helpers (column splitting, identifier extraction, file reading with encoding fallback, etc.).

23. **`profiling.py`** — Parse profiling support. Used by the CLI `--profile` flag. Exposes `FunctionProfile`, `ProfilingResult`, `ProfilerContext`.

24. **`cli.py`** — CLI entry point (`jcl-parser` command). Subcommands: `steps`, `procs`, `detect`, `metrics`, `lint`, `datasets`, `sql`, `analyze`, `paths`, plus `--validate`, `--json`, `--explode`, `--proc-path`, `--profile`.

25. **`__main__.py`** — Enables `python -m jclparser` invocation (delegates to `cli.main`).

### Public API tiers (from `__init__.py`)

- **Tier 1 (stable)**: `parse_jcl`, `validate_jcl`, `parse_statement`, `parse` (alias), core model classes (`Job`, `Step`, `DDStatement`, `Parameter`, `Statement`, `OutputStatement`), core error types (`JCLSyntaxError`, `JCLValidationError`, `JCLStructureError`, `ParseError`, `ValidationError`, `ErrorType`, `ErrorSeverity`, `ValidationLevel`, `UndefinedSymbolError`, `CircularProcedureError`, `ExplosionDepthError`, `ProcedureNotFoundError`).
- **Tier 2 (advanced)**: `explode_job`, `SymbolScope`, loader classes, `ParserConfig`, `validate_*` utilities, `FileType`/`detect_file_type`/`detect_file_type_from_content`, `parse_condition` + condition AST nodes, SQL detection API, INCLUDE resolution, dataset lifecycle, JES statement types, `compute_metrics`/`JobMetrics`, `compute_feasible_paths`/`FeasibilityReport`, program profile analysis, lint API, plugin system.
- **Tier 3 (internal/backwards-compat)**: `MockSystemSymbolProvider`, individual loader types, `FunctionProfile`/`ProfilingResult` — may be removed in a future major version.

### External PROC loading

Set `JCL_PROCLIB_PATH` env var or pass `proc_base_path` to `parse_jcl()`. The filesystem layout mirrors mainframe dataset naming: `<base_path>/SYS1.PROCLIB/MYPROC.jcl`. Inline PROCs always take precedence over external ones.

## Test Structure

```
tests/
  unit/        # Individual component tests (parser API, models, validators, explosion)
  integration/ # End-to-end JCL parsing with realistic job streams
  contracts/   # API stability tests
  performance/ # Benchmarks
```

Markers: `unit`, `integration`, `contract`, `performance` (all enforced via `pyproject.toml`). Coverage minimum: **90%** — enforced on every run.

## Code Style

- Python 3.10+ type hints on all signatures
- `ruff` for linting + formatting (line-length 88); `black` not used — `ruff format` handles formatting
- `mypy` strict mode; no untyped defs
- No runtime dependencies; dev tools in `[dev]` extras only
