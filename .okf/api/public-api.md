---
type: API Reference
title: jclparser Public API
description: All exports from jclparser/__init__.py, organized by stability tier; only Tier 1 should be used in new external integrations.
tags: [api, stability, exports]
timestamp: 2026-06-28T00:00:00Z
---

# Overview

Three stability tiers govern the API. **Only Tier 1 is safe for new external integrations.**

# Tier 1 — Stable

Will not be removed or signature-broken without a major version bump.

## Core Functions

| Export | Description |
|--------|-------------|
| `parse_jcl(source, ...)` | Main entry — parses JCL string/file/IO; returns `Job` |
| `parse(source, ...)` | Alias for `parse_jcl` |
| `validate_jcl(source, ...)` | `parse_jcl` + structural checks; returns `(Job, list[ParseError])` |
| `parse_statement(line, ...)` | Parse a single JCL statement line in isolation |

## Model Classes

`Job`, `Step`, `DDStatement`, `Parameter`, `Statement`, `OutputStatement`

## Error / Enum Types

`JCLSyntaxError`, `JCLValidationError`, `JCLStructureError`, `ParseError`, `ValidationError`, `UndefinedSymbolError`, `CircularProcedureError`, `ExplosionDepthError`, `ProcedureNotFoundError`, `ErrorType`, `ErrorSeverity`, `ValidationLevel`

# Tier 2 — Advanced

Stable but may evolve. Key groups:

| Group | Key Exports |
|-------|-------------|
| PROC Expansion | `explode_job`, `SymbolScope`, `create_default_loader`, `DictProcedureLoader`, `CompositeProcedureLoader`, `ProcedureLoader`, `BUILTIN_UTILITY_PROCS` |
| Plugin System | `ParserConfig`, `StatementPlugin`, `ValidationPlugin`, `PluginRegistry`, `get_plugin_registry` |
| Validation | `validate_jcl_identifier`, `validate_dataset_name`, `validate_job_structure`, `validate_step_structure`, `validate_dd_statement` |
| File Type Detection | `FileType`, `detect_file_type`, `detect_file_type_from_content`, `is_jcl_file`, `is_proc_file` |
| Condition Parsing | `parse_condition`, `ConditionNode`, `ReturnCodeCondition`, `AbendCondition`, `RunCondition`, `NotCondition`, `AndCondition`, `OrCondition` |
| SQL/DB2 Detection | `SQLDetectionResult`, `detect_sql_in_step`, `detect_sql_in_job`, `detect_sql_in_dd`, `is_db2_program`, `DB2_PROGRAMS` |
| INCLUDE Expansion | `resolve_includes`, `IncludeMemberLoader`, `DictMemberLoader`, `JCLLIBMemberLoader` |
| Dataset Lifecycle | `DatasetEvent`, `analyze_dataset_lifecycle`, `validate_dataset_lifecycle` |
| JES Control | `JESControlStatement`, `JobParmStatement`, `RouteStatement`, `XmitStatement`, `parse_jes_control` |
| Metrics / RC | `JobMetrics`, `compute_metrics`, `FeasibilityReport`, `compute_feasible_paths`, `DEFAULT_RC_DOMAIN` |
| Lint | `LintRule`, `LintConfig`, `lint_job`, `lint_to_sarif`, `register_lint_rule` |
| Program Profiles | `ProgramProfile`, `ProgramAnalysis`, `register_profile`, `analyze_step`, `analyze_job` |

# Tier 3 — Internal

May be removed without notice: `MockSystemSymbolProvider`, `InlineProcedureLoader`, `JCLLIBProcedureLoader`, `FunctionProfile`, `ProfilingResult`.

# Citations

[1] [api/public-api.md](../../../api/public-api.md) — full export tables with descriptions
[2] [api/cli-reference.md](../../../api/cli-reference.md) — CLI subcommands
