# Operational Knowledge File — jcl-parser

> **Purpose:** Persistent memory for AI assistants and contributors. Load this file cold to get full situational awareness of the repo before touching any code.
>
> **Last updated:** 2026-06-27  
> **Package version:** 1.1.0  
> **Canonical path:** `docs/OKF.md`

---

## 1. Identity

| Field | Value |
|-------|-------|
| Package name | `jclparser` |
| Install command | `pip install -e ".[dev]"` |
| CLI entry point | `jcl-parser` (maps to `jclparser.cli:main`) |
| Python requirement | 3.10+ |
| Runtime dependencies | **None** — pure Python library |
| License | Proprietary |
| Repository | `https://github.com/Landparty/jcl-parser` |
| Vendored into | `backend/_vendor/jcl-parser/` in the parent `legacylens` monorepo |

**What this is:** A pure-Python library that parses IBM z/OS JCL (Job Control Language) into structured Python objects. Builds a model of Jobs, Steps, and DD statements; validates syntax and structure; expands PROCs; detects file type; and provides analysis tools for datasets, SQL, metrics, linting, and return-code feasibility.

---

## 2. Repository Layout

```
jcl-parser/
├── jclparser/                  # Main package (26+ modules)
│   ├── __init__.py             # Public API — all three tiers exported here
│   ├── __main__.py             # Enables `python -m jclparser`
│   ├── parser.py               # Core: parse_jcl(), validate_jcl(), parse_statement()  [1545 lines]
│   ├── continuation_handler.py # Merges multi-line JCL before parsing                  [300 lines]
│   ├── model.py                # Data model: Job, Step, DDStatement, Parameter, etc.    [896 lines]
│   ├── parameter_ast.py        # Typed param-string AST (DCB, SPACE, nested parens)     [365 lines]
│   ├── parameter_validators.py # Validates structured parameter objects                 [245 lines]
│   ├── validators.py           # Higher-level: identifiers, DSN rules, structure        [366 lines]
│   ├── explosion.py            # PROC expansion: explode_job(), SymbolScope             [761 lines]
│   ├── proc_loader.py          # External PROC loading from filesystem / JCLLIB         [402 lines]
│   ├── include_loader.py       # // INCLUDE MEMBER= resolution                         [294 lines]
│   ├── builtin_procs.py        # Last-resort IBM utility PROC templates                [246 lines]
│   ├── system_symbols.py       # JCL system symbols (&SYSUID, &SYSDATE, etc.)          [210 lines]
│   ├── jcl_file_type.py        # Heuristic: is this file JCL, a PROC, or neither?      [275 lines]
│   ├── condition_parser.py     # // IF condition → typed AST                           [450 lines]
│   ├── sql_detector.py         # SQL/DB2 usage detection in steps                      [~200 lines]
│   ├── jes_statements.py       # Typed JES2/JES3 control statement models               [276 lines]
│   ├── dataset_lifecycle.py    # Cross-step dataset create/open/dispose analysis        [286 lines]
│   ├── metrics.py              # Structural job metrics (cyclomatic score, fan-in/out)  [~200 lines]
│   ├── rc_analysis.py          # Return-code feasibility: compute_feasible_paths()      [230 lines]
│   ├── errors.py               # Exception hierarchy                                    [180 lines]
│   ├── utils.py                # Internal helpers (column splitting, file reading)      [~150 lines]
│   ├── profiling.py            # Parse profiling (used by CLI --profile)                [~150 lines]
│   ├── cli.py                  # CLI entry point: jcl-parser command                    [936 lines]
│   ├── lint/                   # Linting subsystem
│   │   ├── __init__.py
│   │   ├── base.py             # LintRule abstract base
│   │   ├── config.py           # LintConfig
│   │   ├── rules.py            # Built-in rules (JCL-LINT-001 through NNN)
│   │   └── runner.py           # lint_job(), lint_to_sarif(), register_lint_rule()
│   ├── plugins/                # Extension point system
│   │   ├── __init__.py
│   │   └── base.py             # StatementPlugin, ValidationPlugin, PluginRegistry, ParserConfig
│   └── program_profiles/       # Known z/OS program analysis
│       ├── __init__.py
│       ├── base.py             # ProgramProfile, ProgramAnalysis
│       ├── registry.py         # register_profile(), analyze_step(), analyze_job()
│       ├── _invoked.py         # Internal: invoked-program lookup helpers
│       ├── sort.py             # SORT / SYNCSORT profile
│       ├── iebgener.py         # IEBGENER profile
│       ├── iefbr14.py          # IEFBR14 profile
│       ├── idcams.py           # IDCAMS profile
│       ├── ikjeft01.py         # IKJEFT01 (TSO) profile
│       ├── dfsrrc00.py         # IMS DFSRRC00 profile
│       └── db2_batch.py        # DB2 batch program profiles
│
├── tests/
│   ├── unit/                   # ~80 test files — individual component tests
│   ├── integration/            # ~15 test files — end-to-end pipeline tests
│   └── benchmarks/             # pytest-benchmark perf tests (excluded from default runs)
│
├── tests/fixtures/
│   ├── sample_jcl/             # ~45 JCL fixture files (basic to edge cases)
│   ├── real_world/             # ~25 realistic production JCL examples
│   └── proclibs/               # External PROC filesystem fixtures
│       ├── SYS1.PROCLIB/
│       └── USER.PROCLIB/
│
├── docs/
│   ├── OKF.md                  # This file — operational knowledge
│   ├── basic-parsing.md        # Getting-started guide
│   ├── advanced-features.md    # Condition parsing, SQL detection, plugins
│   ├── proc-expansion.md       # PROC expansion guide
│   ├── validation.md           # Validation reference
│   └── superpowers/
│       ├── specs/              # Feature design specs (brainstorming output)
│       └── plans/              # Implementation plans
│
├── examples/
│   └── DIVIDE.jcl              # Sample JCL file
│
├── CLAUDE.md                   # AI instructions for this repo
├── README.md                   # Project overview
├── CHANGELOG.md                # Release history (release-please managed)
├── pyproject.toml              # Build, pytest, coverage, ruff, mypy config
├── setup.py                    # Legacy setup (kept for editable installs)
└── .github/
    └── workflows/
        ├── ci.yml              # CI: lint + test on push/PR
        └── release-please.yml  # Automated release management
```

---

## 3. Parsing Pipeline (Data Flow)

```
Input: JCL string / file / IO stream
         │
         ▼
[1] read_source()                          (utils.py)
    Reads string/file with encoding fallback (EBCDIC → UTF-8)
         │
         ▼
[2] ContinuationLineHandler.process()      (continuation_handler.py)
    Merges multi-line statements. JCL uses // continuation lines
    with column-71 breaks; columns 1-71 carry content.
    Tracks quote depth and paren depth to avoid premature merges.
         │
         ▼
[3] resolve_includes()                     (include_loader.py)   [optional]
    Expands // INCLUDE MEMBER=name statements by loading from JCLLIB
         │
         ▼
[4] parse_jcl() core loop                  (parser.py)
    Processes each merged statement line:
    - Identifies statement type: JOB / EXEC / DD / PROC / PEND /
      JCLLIB / INCLUDE / SET / EXPORT / IF / THEN / ELSE / ENDIF / OUTPUT / *
    - JOB  → builds Job object, parses JOB parameters
    - EXEC → builds Step (PGM=) or Step invoking PROC
    - DD   → builds DDStatement, parses DD parameters via parameter_ast.py
    - SET  → records symbol into symbol table
    - IF   → parse_condition() → ConditionalBlock
    - PROC/PEND → builds inline Procedure
    - OUTPUT → builds OutputStatement
         │
         ▼
[5] parameter_ast.ParameterParser          (parameter_ast.py)
    Parses raw parameter strings into typed ASTs.
    Handles: DCBParameter, SPACEParameter, nested parens,
    positional vs. keyword params, quoted strings.
         │
         ▼
[6] Validators (optional)                  (validators.py, parameter_validators.py)
    validate_jcl() runs post-parse structural checks:
    - Identifier naming rules (max 8 chars, valid charset)
    - Dataset name rules (qualifiers, max 44 chars)
    - Job/Step/DD structure rules
    - Parameter value constraints (RECFM, TIME, REGION, MSGLEVEL, etc.)
         │
         ▼
[7] explode_job()                          (explosion.py)   [optional]
    PROC expansion: resolves PROCs inline and substitutes &SYMBOL params.
    Uses ProcedureLoader chain (inline → JCLLIB → builtin_procs fallback).
    Detects circular references; enforces max expansion depth.
         │
         ▼
Output: Job object (with nested Steps, DDStatements, Procedures,
        ConditionalBlocks, OutputStatements)
```

---

## 4. Public API Tiers

All exports are declared in `jclparser/__init__.py`. The tier system governs stability guarantees.

### Tier 1 — Stable (safe to depend on)

| Export | Module | Description |
|--------|--------|-------------|
| `parse_jcl(source, ...)` | `parser.py` | Main entry point — returns `Job` |
| `parse(source, ...)` | `__init__.py` | Alias for `parse_jcl` |
| `validate_jcl(source, ...)` | `parser.py` | Parse + structural validation |
| `parse_statement(line, ...)` | `parser.py` | Parse a single statement line |
| `Job` | `model.py` | Top-level job model |
| `Step` | `model.py` | Execution step (EXEC statement) |
| `DDStatement` | `model.py` | Data definition statement |
| `Parameter` | `model.py` | Single parameter key/value |
| `Statement` | `model.py` | Generic statement |
| `OutputStatement` | `model.py` | OUTPUT JCL statement |
| `JCLSyntaxError` | `errors.py` | Bad JCL syntax |
| `JCLValidationError` | `errors.py` | Structural validation failure |
| `JCLStructureError` | `errors.py` | Structure problem |
| `ParseError` | `errors.py` | Generic parse error (with context) |
| `ValidationError` | `errors.py` | Generic validation error |
| `ErrorType` | `errors.py` | Enum: SYNTAX/VALIDATION/STRUCTURE/SEMANTIC |
| `ErrorSeverity` | `errors.py` | Enum: ERROR/WARNING/INFO |
| `ValidationLevel` | `plugins/base.py` | Enum: BASIC/STANDARD/STRICT |
| `UndefinedSymbolError` | `errors.py` | Unresolved &SYMBOL |
| `CircularProcedureError` | `errors.py` | PROC circular reference |
| `ExplosionDepthError` | `errors.py` | Max PROC nesting depth exceeded |
| `ProcedureNotFoundError` | `errors.py` | PROC not found in any loader |

### Tier 2 — Advanced (stable but may evolve)

| Export | Module | Description |
|--------|--------|-------------|
| `explode_job(job, loader, ...)` | `explosion.py` | Expand all PROCs in a job |
| `SymbolScope` | `explosion.py` | Symbol substitution scope |
| `create_default_loader(...)` | `proc_loader.py` | Wire PROC loader chain |
| `DictProcedureLoader` | `proc_loader.py` | In-memory PROC dict |
| `CompositeProcedureLoader` | `proc_loader.py` | Chain multiple loaders |
| `ProcedureLoader` | `proc_loader.py` | ABC for custom loaders |
| `BUILTIN_UTILITY_PROCS` | `builtin_procs.py` | Dict of IBM utility PROC templates |
| `create_builtin_proc_loader()` | `builtin_procs.py` | Loader for builtin templates |
| `ParserConfig` | `plugins/base.py` | Parser configuration object |
| `StatementPlugin` | `plugins/base.py` | Custom statement parser ABC |
| `ValidationPlugin` | `plugins/base.py` | Custom validation rule ABC |
| `PluginRegistry` | `plugins/base.py` | Plugin registration hub |
| `get_plugin_registry()` | `plugins/__init__.py` | Global registry singleton |
| `validate_jcl_identifier(...)` | `validators.py` | Single identifier name check |
| `validate_dataset_name(...)` | `validators.py` | Dataset name check |
| `validate_job_structure(...)` | `validators.py` | Full job structure check |
| `validate_step_structure(...)` | `validators.py` | Single step check |
| `validate_dd_statement(...)` | `validators.py` | DD statement check |
| `FileType` | `jcl_file_type.py` | Enum: JCL / PROC / UNKNOWN |
| `detect_file_type(path)` | `jcl_file_type.py` | Detect type from filesystem |
| `detect_file_type_from_content(s)` | `jcl_file_type.py` | Detect type from string |
| `is_jcl_file(path)` | `jcl_file_type.py` | Boolean JCL check |
| `is_proc_file(path)` | `jcl_file_type.py` | Boolean PROC check |
| `parse_condition(expr)` | `condition_parser.py` | // IF condition → typed AST |
| `ConditionNode`, `ReturnCodeCondition`, `AbendCondition`, `RunCondition`, `NotCondition`, `AndCondition`, `OrCondition` | `condition_parser.py` | Condition AST node types |
| `SQLDetectionResult` | `sql_detector.py` | Result of SQL detection |
| `detect_sql_in_step(step)` | `sql_detector.py` | Detect SQL in one step |
| `detect_sql_in_job(job)` | `sql_detector.py` | Detect SQL in all steps |
| `detect_sql_in_dd(dd)` | `sql_detector.py` | Detect SQL in a DD |
| `detect_sql_in_text(text)` | `sql_detector.py` | Detect SQL in raw text |
| `is_db2_program(name)` | `sql_detector.py` | Is program name a known DB2 program? |
| `DB2_PROGRAMS` | `sql_detector.py` | Set of known DB2 program names |
| `resolve_includes(...)` | `include_loader.py` | Expand // INCLUDE statements |
| `IncludeMemberLoader` | `include_loader.py` | ABC for INCLUDE member sources |
| `DictMemberLoader` | `include_loader.py` | In-memory member dict |
| `JCLLIBMemberLoader` | `include_loader.py` | Filesystem INCLUDE loader |
| `DatasetEvent` | `dataset_lifecycle.py` | A single lifecycle event |
| `analyze_dataset_lifecycle(job)` | `dataset_lifecycle.py` | Cross-step lifecycle map |
| `validate_dataset_lifecycle(job)` | `dataset_lifecycle.py` | Lifecycle issue detection |
| `JESControlStatement`, `JobParmStatement`, `RouteStatement`, `XmitStatement`, etc. | `jes_statements.py` | Typed JES2/JES3 models |
| `parse_jes_control(line)` | `jes_statements.py` | Parse a `/*COMMAND` line |
| `JobMetrics` | `metrics.py` | Computed metrics dataclass |
| `compute_metrics(job)` | `metrics.py` | Compute structural metrics |
| `FeasibilityReport` | `rc_analysis.py` | RC feasibility result |
| `compute_feasible_paths(job)` | `rc_analysis.py` | RC path analysis |
| `DEFAULT_RC_DOMAIN` | `rc_analysis.py` | Default symbolic RC domain |
| `ProgramProfile` | `program_profiles/base.py` | Profile ABC |
| `ProgramAnalysis` | `program_profiles/base.py` | Analysis result |
| `register_profile(profile)` | `program_profiles/registry.py` | Add a custom profile |
| `analyze_step(step)` | `program_profiles/registry.py` | Profile-match one step |
| `analyze_job(job)` | `program_profiles/registry.py` | Profile-match all steps |
| `LintRule` | `lint/base.py` | Lint rule ABC |
| `LintConfig` | `lint/config.py` | Lint configuration |
| `lint_job(job, config)` | `lint/runner.py` | Run all lint rules |
| `lint_to_sarif(findings)` | `lint/runner.py` | SARIF output format |
| `register_lint_rule(rule)` | `lint/runner.py` | Register a custom rule |

### Tier 3 — Internal / Backwards-compat (may be removed)

| Export | Notes |
|--------|-------|
| `MockSystemSymbolProvider` | Test helper; use `SystemSymbolProvider` base in production |
| `InlineProcedureLoader`, `JCLLIBProcedureLoader` | Individual loader types; prefer `create_default_loader()` |
| `FunctionProfile`, `ProfilingResult` | Profiling internals |

---

## 5. Data Model Hierarchy

```
Job
├── name: str
├── parameters: dict[str, Any]    # JOB card params (CLASS, MSGCLASS, NOTIFY, ...)
├── statements: list[Statement]   # Raw statement objects (pre-explosion)
├── steps: list[Step | ConditionalBlock]
├── procedures: list[Procedure]   # Inline PROCs (pre-PEND)
├── output_statements: list[OutputStatement]
├── errors: list[ParseError]
└── warnings: list[ParseError]

Step
├── name: str                      # Max 8 chars
├── exec_type: Literal["PGM", "PROC"]
├── program: str | None            # PGM= value
├── proc_name: str | None          # PROC name being invoked
├── parameters: dict[str, Any]     # EXEC params (PARM, COND, TIME, REGION, ...)
├── dd_statements: list[DDStatement]
└── line_number: int

DDStatement
├── name: str                      # DD name (max 8 chars)
├── parameters: dict[str, Any]     # DD params (DSN, DISP, SPACE, DCB, SYSOUT, ...)
├── dataset_name: str | None       # DSN= value
├── disposition: str | None        # DISP= value (raw)
├── is_temporary: bool             # DSN starts with &&
├── is_sysout: bool                # SYSOUT= is set
├── instream_data: list[str]       # /* delimited inline data
└── line_number: int

ConditionalBlock
├── condition: str                 # Raw condition string (authoritative)
├── condition_ast: ConditionNode | None  # Parsed AST (may be None if unparseable)
├── then_steps: list[Step | ConditionalBlock]
└── else_steps: list[Step | ConditionalBlock]

Procedure
├── name: str
├── steps: list[Step]
└── parameters: dict[str, str]    # Default symbolic parameter values

Parameter
├── name: str
├── value: Any
└── line_number: int
```

---

## 6. PROC Loading Chain

When `explode_job()` needs to resolve a PROC, it tries loaders in this order:

```
1. Inline PROCs (PROC…PEND in the job itself)
        │ not found
        ▼
2. JCLLIB ORDER datasets (filesystem under JCL_PROCLIB_PATH or proc_base_path)
   Layout: <base_path>/<DATASET.NAME>/<PROCNAME>.jcl
        │ not found
        ▼
3. DictProcedureLoader (user-supplied dict, if any)
        │ not found
        ▼
4. builtin_procs.py — BUILTIN_UTILITY_PROCS last-resort fallback
   Covers: IMSBATCH, DLIBATCH, DBBBATCH, IMSMSG, DFSMPR (IMS)
           DSNUPROC, DSNHICOB (DB2)
           IGYWCL, IGYWCLG, COBUCL (COBOL)
   Toggle: create_default_loader(include_builtins=True/False)
        │ not found
        ▼
   ProcedureNotFoundError
```

**Environment variable:** `JCL_PROCLIB_PATH` sets the default PROC base path.

---

## 7. Test Structure

### Organization

```
tests/
├── unit/        # ~80 files — test individual modules in isolation
│   ├── test_parser_api.py           # parse_jcl / validate_jcl surface API
│   ├── test_explosion.py            # PROC expansion
│   ├── test_condition_parser.py     # // IF AST
│   ├── test_parameter_ast.py        # Parameter string parsing
│   ├── test_validators.py           # Validation rules
│   ├── test_cli.py                  # CLI subcommands
│   ├── test_logging.py              # jclparser logger behavior
│   └── ... (many more)
├── integration/ # ~15 files — full pipeline with realistic JCL
│   ├── test_full_pipeline.py        # End-to-end: parse → validate → explode
│   ├── test_real_world_jcl.py       # Real-world fixture files
│   └── ... (many more)
└── benchmarks/  # excluded from default pytest run (norecursedirs)
    └── test_benchmarks.py
```

### Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.unit` | Single-component isolation test |
| `@pytest.mark.integration` | Multi-component / end-to-end |
| `@pytest.mark.contract` | API contract validation |
| `@pytest.mark.performance` | Speed/memory assertions |
| `@pytest.mark.slow` | Takes longer than usual |
| `@pytest.mark.benchmark` | pytest-benchmark (excluded from default) |

### Coverage

- **Minimum: 90%** — enforced on every `pytest` run via `--cov-fail-under=90`
- Branch coverage is enabled
- HTML report: `htmlcov/` | XML report: `coverage.xml`
- Benchmark tests are excluded from coverage measurement (`norecursedirs = ["tests/benchmarks"]`)

---

## 8. CLI Reference

```
jcl-parser [file] [flags]

Subcommands:
  steps     List job steps
  procs     List PROCs used
  detect    Detect file type (JCL / PROC / unknown)
  metrics   Structural metrics (step count, nesting, fan-in/out)
  lint      Run lint rules; output findings
  datasets  Dataset lifecycle report
  sql       SQL/DB2 usage report
  analyze   Program profile analysis
  paths     RC feasibility paths

Flags:
  --validate          Run structural validation
  --json              JSON output
  --explode           Expand PROCs before analysis
  --proc-path PATH    Base path for external PROCs
  --profile           Emit parse profiling data
  --version           Print package version (reads from __version__)
```

---

## 9. Configuration Reference

All tooling config lives in `pyproject.toml`.

### pytest

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--strict-markers", "--cov=jclparser", "--cov-fail-under=90", ...]
norecursedirs = ["tests/benchmarks"]
filterwarnings = ["error", "ignore::UserWarning", "ignore::DeprecationWarning"]
```

### ruff

```toml
[tool.ruff]
line-length = 88
target-version = "py310"
```

No `black` — `ruff format` handles formatting.

### mypy

```toml
[tool.mypy]
python_version = "3.10"
strict = true
```

**Known state:** `mypy jclparser/` is **not yet strict-clean**. Backlog of violations mostly in `profiling.py`, `explosion.py`, `parser.py` (missing annotations, generic type args). Add annotations when touching a file; do not widen the config.

---

## 10. Logging

The library uses Python's standard `logging` module under the `jclparser` logger hierarchy.

```python
import logging
logging.getLogger("jclparser").setLevel(logging.DEBUG)
logging.basicConfig()
```

- `NullHandler` is attached by default (per library convention — no output unless configured).
- Key sub-loggers: `jclparser.parser`, `jclparser.explosion`, `jclparser.continuation_handler`, `jclparser.proc_loader`.
- INFO: high-level pipeline events (job parsed, PROC resolved, include expanded).
- DEBUG: per-statement detail, symbol substitution, loader fallback decisions.

---

## 11. Key Invariants and Non-Obvious Behaviors

1. **Column 71 is the continuation column.** JCL content occupies columns 1–71; column 72 is sometimes a sequence number. `ContinuationLineHandler` enforces this — never pass pre-stripped lines.

2. **`ConditionalBlock.condition` is authoritative.** The raw string is always present; `condition_ast` may be `None` if `parse_condition()` returns `None` (unparseable expression). Always read `condition` for display; use `condition_ast` only when you need the AST.

3. **Inline PROCs always win.** Even if a PROC with the same name exists externally or in builtins, the inline definition takes precedence.

4. **`&&` is an escaped ampersand in JCL.** Symbol substitution replaces `&NAME` → value and `&&` → `&`. Handled in `explosion.py:_SYMBOL_SUB_PATTERN`.

5. **Dataset names are case-insensitive on z/OS but stored as-is.** Validation checks length (max 44 chars, max 8 per qualifier) and charset, but does not uppercase.

6. **`parse_jcl()` does not explode PROCs by default.** Call `explode_job()` separately, or pass the result through the CLI `--explode` flag.

7. **`validate_jcl()` returns a `Job` + errors list, not a boolean.** Callers should check `result.errors` for `ErrorSeverity.ERROR` items.

8. **`//` comment lines are preserved in the statement list.** They appear as `Statement(type="COMMENT")` objects; they are not stripped.

9. **JES control statements (`/*JOBPARM`, `/*ROUTE`, etc.) are parsed separately.** `jes_statements.py` handles them; they are not part of the main `Job.steps` model.

10. **`set_symbols` in `parser.py` are resolved left-to-right within a job.** A SET can reference an earlier SET symbol but not a later one. Mirrors mainframe evaluation order.

11. **Vendoring:** Changes to this repo must be manually copied to `backend/_vendor/jcl-parser/` in the parent monorepo. No automated sync:
    ```bash
    cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/
    ```

12. **`--version` in the CLI reads from `jclparser.__version__`**, not from the package metadata. Update `__init__.py:__version__` and `pyproject.toml:version` together when releasing.

13. **Coverage must not drop below 90%.** Every `pytest` run enforces this. If adding a module, add tests before or alongside it.

14. **`builtin_procs.py` contains non-verbatim templates.** These are structural approximations, not exact IBM PROC copies. Sufficient for static analysis; not authoritative for production submission.

---

## 12. Common Task → File Mapping

| Task | Files to touch |
|------|---------------|
| Add a new JCL statement type | `parser.py` (dispatch loop), `model.py` (if new model class), `__init__.py` (if exported) |
| Add a DD parameter | `parameter_ast.py`, `parameter_validators.py`, `tests/unit/test_parameter_ast.py` |
| Add a validation rule | `validators.py` or `parameter_validators.py`, `tests/unit/test_validators.py` |
| Add a lint rule | `lint/rules.py` (new `LintRule` subclass), `lint/runner.py` (register it), tests |
| Add a builtin PROC template | `builtin_procs.py:BUILTIN_UTILITY_PROCS` dict |
| Add a program profile | New file under `program_profiles/`, import and register in `program_profiles/__init__.py` |
| Add a CLI subcommand | `cli.py` (argparse subparser + handler function) |
| Fix a PROC expansion bug | `explosion.py`, possibly `proc_loader.py` |
| Fix a continuation line bug | `continuation_handler.py` |
| Add a condition operator | `condition_parser.py`, `tests/unit/test_condition_parser.py` |
| Add an INCLUDE member source | `include_loader.py` (new `IncludeMemberLoader` subclass) |
| Change what `parse_jcl()` accepts | `parser.py:parse_jcl()`, update overloads, update `__init__.py` docs |
| Add public API | `__init__.py` (add to `__all__` under correct tier), add tests |
| Bump version | `pyproject.toml:version`, `jclparser/__init__.py:__version__` |

---

## 13. Development Workflow

```bash
# Install (from repo root)
pip install -e ".[dev]"

# Run full test suite (coverage enforced at 90%)
pytest

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run a single test file
pytest tests/unit/test_parser_api.py

# Run a single test by name
pytest tests/unit/test_parser_api.py::TestClassName::test_method_name

# Lint
ruff check .

# Format
ruff format .

# Type check
mypy jclparser/

# CLI usage
jcl-parser examples/DIVIDE.jcl steps
jcl-parser examples/DIVIDE.jcl --validate --json
jcl-parser examples/DIVIDE.jcl metrics

# After making changes, sync to backend vendor
cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/
```

---

## 14. External PROC Filesystem Layout

```
<base_path>/
└── SYS1.PROCLIB/
│   └── SORTPROC.jcl
└── USER.PROCLIB/
    └── MYPROC.jcl
    └── PARMPRC.jcl
```

- Dataset directory names mirror mainframe naming conventions (dots preserved).
- The loader looks for `<PROCNAME>.jcl` within each dataset directory.
- Set via `JCL_PROCLIB_PATH` env var or `proc_base_path=` argument to `parse_jcl()`.

---

## 15. Recent Significant Changes (as of 2026-06-27)

| Commit | Change |
|--------|--------|
| `48c7f3f` | INFO/DEBUG logging added across the parse pipeline |
| `68363c4` | Spec for parser logging feature |
| `e9ddf6b` | Documentation and dev tool configuration enhancements |
| `040add4` | Removed redundant, duplicated, and dead code |
| `44f0666` | Released v1.1.0 |
| `#30` | Code review: redundancy reduction |
| `#27` | release-please: v1.1.0 automated release |

---

*This file should be updated whenever a module is added, renamed, or has its public API changed, or when a major architectural decision is made. It is intentionally exhaustive — brevity belongs in other docs.*
