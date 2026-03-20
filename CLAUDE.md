# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

The package is `jclparser/` — a pure Python library with no runtime dependencies.

### Parsing pipeline

1. **`parser.py`** — The core. `parse_jcl()` is the main entry point. Handles continuation lines by delegating to `continuation_handler.py`, then builds the AST of `Statement` objects. Also exposes `validate_jcl()` and `parse_statement()`.

2. **`continuation_handler.py`** — Merges multi-line JCL statements before parsing. JCL uses `//` continuation lines with column-71 breaks.

3. **`model.py`** — Data model: `Job`, `Step`, `DDStatement`, `Parameter`, `Statement`. These are the objects returned from parsing.

4. **`parameter_ast.py`** — Parses JCL parameter strings into a typed AST (handles nested parentheses, positional vs. keyword params, `DCB`, `SPACE`, etc.).

5. **`parameter_validators.py`** — Validates structured parameter objects (e.g., DCB field combinations, SPACE unit types).

6. **`validators.py`** — Higher-level validation: identifier naming rules, dataset name rules, job/step/DD structure validation.

7. **`explosion.py`** — PROC expansion (`explode_job()`). Resolves inline PROCs and substitutes symbolic parameters (`&SYMBOL`). Tracks expansion depth to detect circular references.

8. **`proc_loader.py`** — Loads external PROCs from the filesystem. Supports `JCLLIB ORDER` statements. Loader hierarchy: `InlineProcedureLoader` → `JCLLIBProcedureLoader` → `CompositeProcedureLoader`. `create_default_loader()` wires them together.

9. **`system_symbols.py`** — Provides JCL system symbols (`&SYSUID`, `&SYSDATE`, etc.). Pluggable via `SystemSymbolProvider` base class; `MockSystemSymbolProvider` is used in tests.

10. **`jcl_file_type.py`** — Heuristic detection of whether a file is JCL, a PROC, or neither (`detect_file_type()`, `is_jcl_file()`, `is_proc_file()`).

11. **`condition_parser.py`** — Parses `// IF condition THEN` expressions into an AST (`parse_condition()`). Supports `AND`/`OR`/`NOT`, step RC comparisons, `ABEND`, and `RUN` atoms. Returns `None` for unparseable conditions; the raw string on `ConditionalBlock.condition` remains authoritative.

12. **`plugins/`** — Extension points: `StatementPlugin` (custom statement parsing), `ValidationPlugin` (custom validation rules), `PluginRegistry`, `ParserConfig`. Get the global registry via `get_plugin_registry()`.

13. **`errors.py`** — Exception hierarchy: `JCLSyntaxError`, `JCLValidationError`, `JCLStructureError`, plus `UndefinedSymbolError`, `CircularProcedureError`, `ExplosionDepthError`, `ProcedureNotFoundError`.

14. **`utils.py`** — Internal parsing helpers (column splitting, identifier extraction, etc.).

### Public API tiers (from `__init__.py`)

- **Tier 1 (stable)**: `parse_jcl`, `validate_jcl`, `parse_statement`, `parse` (alias), core model classes, core error types.
- **Tier 2 (advanced)**: `explode_job`, loader classes, `ParserConfig`, `validate_*` utilities, `FileType`/`detect_file_type`.
- **Tier 3 (internal/backwards-compat)**: Symbol providers, individual loader types, explosion internals — may be removed in a future major version.

### External PROC loading

Set `JCL_PROCLIB_PATH` env var or pass `proc_base_path` to `parse_jcl()`. The filesystem layout mirrors mainframe dataset naming: `<base_path>/SYS1.PROCLIB/MYPROC.jcl`. Inline PROCs always take precedence over external ones.
