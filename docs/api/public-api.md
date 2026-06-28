---
title: Public API Reference
updated: 2026-06-27
sources: LegacyLens team, 2026-06-27
---

# Public API Reference

All exports are declared in `jclparser/__init__.py`. The tier system governs stability guarantees. **Only use Tier 1 for new external integrations.**

## Tier 1 — Stable

Safe to depend on. Will not be removed or signature-broken without a major version bump.

### Core Functions

| Export | Description |
|--------|-------------|
| `parse_jcl(source, ...)` | Main entry point — parses JCL string/file/IO; returns `Job` |
| `parse(source, ...)` | Alias for `parse_jcl` |
| `validate_jcl(source, ...)` | `parse_jcl` + structural validation; returns `(Job, list[ParseError])` |
| `parse_statement(line, ...)` | Parse a single JCL statement line in isolation |

### Model Classes

| Export | Description |
|--------|-------------|
| `Job` | Top-level parsed job container |
| `Step` | EXEC statement — one executable step |
| `DDStatement` | Data definition (DD) statement |
| `Parameter` | A single key/value parameter |
| `Statement` | Generic statement (comments, unknown types) |
| `OutputStatement` | OUTPUT JCL statement |

### Error / Enum Types

| Export | Description |
|--------|-------------|
| `JCLSyntaxError` | Bad JCL syntax |
| `JCLValidationError` | Structural validation failure |
| `JCLStructureError` | Structural problem (e.g. DD without EXEC) |
| `ParseError` | Generic parse error with context |
| `ValidationError` | Generic validation error |
| `UndefinedSymbolError` | Unresolved `&SYMBOL` during explosion |
| `CircularProcedureError` | PROC circular reference detected |
| `ExplosionDepthError` | Max PROC nesting depth exceeded |
| `ProcedureNotFoundError` | PROC not found in any loader |
| `ErrorType` | Enum: `SYNTAX / VALIDATION / STRUCTURE / SEMANTIC` |
| `ErrorSeverity` | Enum: `ERROR / WARNING / INFO` |
| `ValidationLevel` | Enum: `BASIC / STANDARD / STRICT` |

---

## Tier 2 — Advanced

Stable but may evolve. Do not depend on these in external integrations unless necessary.

### PROC Expansion

| Export | Description |
|--------|-------------|
| `explode_job(job, loader, ...)` | Expand all PROCs in a job; returns new `Job` |
| `SymbolScope` | Symbol substitution scope for expansion |
| `create_default_loader(...)` | Wire the full PROC loader chain |
| `DictProcedureLoader` | In-memory PROC dict |
| `CompositeProcedureLoader` | Chain multiple loaders in priority order |
| `ProcedureLoader` | ABC for implementing a custom loader |
| `BUILTIN_UTILITY_PROCS` | Dict of IBM utility PROC templates (IMS, DB2, COBOL) |
| `create_builtin_proc_loader()` | Loader wrapping the builtin templates |

### Plugin System

| Export | Description |
|--------|-------------|
| `ParserConfig` | Parser configuration object |
| `StatementPlugin` | ABC for custom statement parsers |
| `ValidationPlugin` | ABC for custom validation rules |
| `PluginRegistry` | Global plugin registration hub |
| `get_plugin_registry()` | Get the global `PluginRegistry` singleton |

### Validation Functions

| Export | Description |
|--------|-------------|
| `validate_jcl_identifier(name)` | Check a single identifier name |
| `validate_dataset_name(dsn)` | Check a dataset name |
| `validate_job_structure(job)` | Full job structure check |
| `validate_step_structure(step)` | Single step check |
| `validate_dd_statement(dd)` | DD statement check |

### File Type Detection

| Export | Description |
|--------|-------------|
| `FileType` | Enum: `JCL / PROC / UNKNOWN` |
| `detect_file_type(path)` | Detect type from filesystem path |
| `detect_file_type_from_content(s)` | Detect type from string content |
| `is_jcl_file(path)` | Boolean: is this path a JCL file? |
| `is_proc_file(path)` | Boolean: is this path a PROC file? |

### Condition Parsing

| Export | Description |
|--------|-------------|
| `parse_condition(expr)` | Parse a `// IF` condition → typed AST |
| `ConditionNode` | Abstract base for condition AST nodes |
| `ReturnCodeCondition` | RC comparison node |
| `AbendCondition` | ABEND check node |
| `RunCondition` | RUN check node |
| `NotCondition` | NOT wrapper |
| `AndCondition` | AND combinator |
| `OrCondition` | OR combinator |

### SQL / DB2 Detection

| Export | Description |
|--------|-------------|
| `SQLDetectionResult` | Result container for SQL detection |
| `detect_sql_in_step(step)` | Detect SQL/DB2 usage in one step |
| `detect_sql_in_job(job)` | Detect SQL/DB2 usage across all steps |
| `detect_sql_in_dd(dd)` | Detect SQL in a DD statement |
| `detect_sql_in_text(text)` | Detect SQL in raw text |
| `is_db2_program(name)` | Is this program name a known DB2 program? |
| `DB2_PROGRAMS` | Set of known DB2 program names |

### INCLUDE Expansion

| Export | Description |
|--------|-------------|
| `resolve_includes(...)` | Expand `// INCLUDE` statements |
| `IncludeMemberLoader` | ABC for INCLUDE member sources |
| `DictMemberLoader` | In-memory member dict |
| `JCLLIBMemberLoader` | Filesystem INCLUDE loader |

### Dataset Lifecycle

| Export | Description |
|--------|-------------|
| `DatasetEvent` | A single lifecycle event (create/open/dispose) |
| `analyze_dataset_lifecycle(job)` | Cross-step lifecycle map |
| `validate_dataset_lifecycle(job)` | Detect lifecycle anomalies |

### JES Control Statements

| Export | Description |
|--------|-------------|
| `JESControlStatement` | Base for JES2/JES3 statements |
| `JobParmStatement` | `/*JOBPARM` |
| `RouteStatement` | `/*ROUTE` |
| `XmitStatement` | `/*XMIT` |
| `parse_jes_control(line)` | Parse a `/*COMMAND` line |

### Metrics & RC Analysis

| Export | Description |
|--------|-------------|
| `JobMetrics` | Structural metrics dataclass |
| `compute_metrics(job)` | Compute cyclomatic score, fan-in/out, etc. |
| `FeasibilityReport` | RC feasibility result |
| `compute_feasible_paths(job)` | Return-code feasibility path analysis |
| `DEFAULT_RC_DOMAIN` | Default symbolic RC domain |

### Lint

| Export | Description |
|--------|-------------|
| `LintRule` | ABC for lint rules |
| `LintConfig` | Lint configuration |
| `lint_job(job, config)` | Run all registered lint rules |
| `lint_to_sarif(findings)` | Emit findings in SARIF format |
| `register_lint_rule(rule)` | Register a custom lint rule |

### Program Profiles

| Export | Description |
|--------|-------------|
| `ProgramProfile` | ABC for program analysis profiles |
| `ProgramAnalysis` | Analysis result for a matched profile |
| `register_profile(profile)` | Register a custom profile |
| `analyze_step(step)` | Profile-match one step |
| `analyze_job(job)` | Profile-match all steps |

---

## Tier 3 — Internal / Backwards-compat

May be removed without notice. Do not use in production code.

| Export | Notes |
|--------|-------|
| `MockSystemSymbolProvider` | Test helper — use `SystemSymbolProvider` base in production |
| `InlineProcedureLoader` | Prefer `create_default_loader()` |
| `JCLLIBProcedureLoader` | Prefer `create_default_loader()` |
| `FunctionProfile`, `ProfilingResult` | Profiling internals |

## See Also

- [cli-reference.md](cli-reference.md) — command-line interface
- [../core/parsing-pipeline.md](../core/parsing-pipeline.md) — how parse_jcl / validate_jcl / explode_job chain together
- [../advanced/proc-expansion.md](../advanced/proc-expansion.md) — explode_job and loader setup
- [../advanced/validation.md](../advanced/validation.md) — validation functions and error types
- [../integration/backend-contract.md](../integration/backend-contract.md) — what the backend adapter actually calls
