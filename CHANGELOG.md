# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **Parameter validator pack** on `ParameterValidator`, returning the same
  `ValidationResult` shape as the existing DISP/DSN validators:
  `validate_time`, `validate_region`, `validate_priority` (PRTY),
  `validate_perform`, `validate_rd`, `validate_msglevel`, `validate_dsntype`,
  and `validate_recfm`. These cover format and range/enumeration rules for
  JOB/EXEC/DD parameters that were previously stored without validation.

### Fixed

- `jclparser.utils` referenced module-level constants (`_RE_SPECIAL_CHARS`,
  `_RE_JCL_NAME_START`, `_RE_JCL_NAME_FULL`) and a lazy `_PARAMETER_PARSER`
  singleton that an earlier refactor had removed, along with the `re`,
  `collections.deque`, and `typing` imports. The affected helpers
  (`split_jcl_parameters`, `parse_jcl_parameter`, `quote_jcl_value`,
  `validate_jcl_name`, `format_jcl_line`) raised `NameError` when called; the
  constants and imports are restored and covered by tests.
- `explode_job` now threads the JCLLIB ORDER as an immutable tuple through every
  nesting level, honoring the loaders' hashable-key contract. Added regression
  tests covering nested PROC resolution across multiple libraries (including
  library-order precedence and inline-to-external nesting).

## [1.0.0] - 2026-03-31

First stable release.

### Added

**Core parsing**
- `parse_jcl()` — parses JOB, EXEC, DD, PROC/PEND, SET, IF/THEN/ELSE/ENDIF, JCLLIB ORDER statements from string, `Path`, or file-like object
- `validate_jcl()` — non-raising validation returning a list of `ParseError` objects
- `parse_statement()` — parse a single JCL line into a `Statement`
- Full continuation-line support (column-71 breaks, multi-line parameters, nested parentheses across lines)
- Inline data (`DD *`, `DD DATA`, custom `DLM=` delimiters)
- JES2/JES3 control statements (`/*JOBPARM`, `/*ROUTE`, etc.) captured in `job.jes_statements`
- GDG relative generation references (`MY.GDG(+1)`, `MY.GDG(-1)`, `MY.GDG(0)`)
- Symbol substitution (`&SYMBOL`, `&&` escape, trailing-period disambiguation)

**PROC expansion**
- `explode_job()` — expands inline and external PROC calls, resolves symbolic parameters
- External PROC loading via `JCLLIB ORDER`; filesystem layout mirrors mainframe dataset naming
- `JCL_PROCLIB_PATH` environment variable as a default proc base path
- `CircularProcedureError` on cyclic PROC references
- `ProcedureNotFoundError` when a referenced PROC cannot be resolved

**Validation & error hierarchy**
- `JCLSyntaxError` — malformed syntax (unclosed quotes, unmatched parentheses, …)
- `JCLValidationError` — semantic violations
- `JCLStructureError` — structural violations (e.g. DD before any EXEC in strict mode)
- `strict_mode=True` on `parse_jcl()` promotes validation issues to exceptions

**Structured parameters**
- DCB subparameters exposed as typed `DCBParameter` object (`recfm`, `lrecl`, `blksize`, …)
- SPACE parameters exposed as typed `SPACEParameter` object (`unit`, `primary`, `secondary`, `rlse`, …)
- `_parse_parameters` delegates comma-splitting to the canonical `ParameterParser` implementation

**Additional modules**
- `condition_parser` — parses `// IF` expressions into a typed AST (`AndCondition`, `OrCondition`, `ReturnCodeCondition`, `AbendCondition`, …)
- `sql_detector` — detects SQL/DB2 program usage in steps (`detect_sql_in_step`, `detect_sql_in_job`)
- `jcl_file_type` — heuristic detection of JCL vs PROC files (`detect_file_type`, `is_jcl_file`, `is_proc_file`)
- `system_symbols` — pluggable JCL system symbol provider (`&SYSUID`, `&SYSDATE`, …)

**Plugin system**
- `StatementPlugin` — register custom statement parsers
- `ValidationPlugin` — register custom validation rules
- `PluginRegistry` / `get_plugin_registry()` — global plugin registry
- `ParserConfig` — per-parse configuration (dialect, validation level, plugin list)

**Developer experience**
- Multi-encoding file reading (utf-8 → latin-1 → cp1252 → binary fallback)
- 1 218 tests, 92 % branch coverage (minimum enforced at 90 %)
- Four example guides under `docs/`
- Full fixture catalogue in `tests/fixtures/sample_jcl/README.md`

### Changed

- `pyproject.toml` classifier updated from *Alpha* to *Production/Stable*
- Dead lazy-import machinery (`_LAZY` / `__getattr__`) removed from `__init__.py`
- Deprecated `utils.merge_continuation_lines` now delegates to `ContinuationLineHandler` instead of re-implementing the algorithm
- File-reading logic consolidated into `utils._read_file_with_fallback`

### Fixed

- Variable shadowing in JES-statement branch of `parse_jcl` that prevented `JCLStructureError` from firing correctly in strict mode
- Unmatched-parentheses error message now includes a column-71 continuation hint

---

## [0.1.0] - 2025-01-20

Initial release — core parsing of JOB, EXEC, and DD statements; basic PROC support; plugin skeleton; Python 3.13+.
