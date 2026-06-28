# Knowledge Base Index

## core
Core parsing concepts and the output data model.

| Article | Summary | Updated |
|---------|---------|---------|
| [Parsing Pipeline](core/parsing-pipeline.md) | Full pipeline from raw JCL text to Job object; how parse_jcl / validate_jcl / explode_job chain | 2026-06-27 |
| [Data Model](core/data-model.md) | Job, Step, DDStatement, ConditionalBlock, Procedure hierarchy and field semantics | 2026-06-27 |

## api
Public API surface and command-line interface.

| Article | Summary | Updated |
|---------|---------|---------|
| [Public API Reference](api/public-api.md) | All Tier 1/2/3 exports from jclparser — functions, classes, enums, error types | 2026-06-27 |
| [CLI Reference](api/cli-reference.md) | jcl-parser subcommands (steps, lint, metrics, sql, paths, ...) and flags | 2026-06-27 |

## advanced
PROC expansion, validation, and other advanced subsystems.

| Article | Summary | Updated |
|---------|---------|---------|
| [PROC Expansion](advanced/proc-expansion.md) | explode_job(), loader chain (inline → JCLLIB → builtins), symbol substitution | 2026-06-27 |
| [Validation](advanced/validation.md) | Structural and parameter validation, error types, lint rules, dataset lifecycle | 2026-06-27 |

## integration
Backend adapter contract and vendoring details.

| Article | Summary | Updated |
|---------|---------|---------|
| [Backend Integration Contract](integration/backend-contract.md) | What the backend adapter calls, Job/Step/DD attribute contract, program_structure shape | 2026-06-27 |

## development
Contributor workflow, tooling config, and non-obvious invariants.

| Article | Summary | Updated |
|---------|---------|---------|
| [Development Workflow](development/development-workflow.md) | Install, test, lint, vendor sync, version bump, common task → file map | 2026-06-27 |
| [Key Invariants](development/invariants.md) | 14 non-obvious behaviors — column 71, PROC precedence, SET ordering, vendoring, etc. | 2026-06-27 |
