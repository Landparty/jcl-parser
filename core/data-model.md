---
title: Data Model
updated: 2026-09-02
sources: LegacyLens team, 2026-06-27
---

# Data Model

The `Job` object is the root of the parse result. Every parse call returns one.

## Hierarchy

```
Job
├── name: str | None
├── parameters: dict[str, Any]         # JOB card params — CLASS, MSGCLASS, NOTIFY, ...
├── statements: list[Statement]        # All raw statement objects (pre-explosion, includes comments)
├── steps: list[Step | ConditionalBlock]
├── procedures: list[Procedure]        # Inline PROCs (PROC…PEND blocks)
├── output_statements: list[OutputStatement]
├── control_statements: list[Statement]  # COMMAND / SCHEDULE / CNTL (CNTL keeps
│                                        # its block's records in ["_records"])
├── jes_statements: list[str]           # /*JOBPARM, //*MAIN, ... raw text
├── jes_typed_statements: list[Any]     # same, promoted to typed models
├── errors: list[ParseError]
└── warnings: list[ParseError]

Step
├── name: str                          # Max 8 chars
├── exec_type: Literal["PGM", "PROC"]
├── program: str | None                # PGM= value
├── proc_name: str | None              # PROC name being invoked
├── parameters: dict[str, Any]         # EXEC params — PARM, COND, TIME, REGION, ...
├── dd_statements: list[DDStatement]
├── is_exploded: bool                  # True after explode_job()
├── is_proc_invocation: bool           # True if step invokes a PROC (pre-explosion)
├── procedure: str | None              # PROC name if this is a PROC call
├── original_proc_call: str | None     # Original PROC invocation name
└── line_number: int | None

DDStatement
├── name: str                          # DD name (max 8 chars)
├── parameters: dict[str, Any]         # DD params — DSN, DISP, SPACE, DCB, SYSOUT, ...
├── dataset_name: str | None           # DSN= value
├── disposition: str | None            # DISP= value (raw string)
├── is_temporary: bool                 # True if DSN starts with &&
├── is_sysout: bool                    # True if SYSOUT= is set
├── instream_data: list[str]           # Content between DD * and /* delimiter
└── line_number: int

ConditionalBlock
├── condition: str                     # Raw condition string — ALWAYS present, authoritative
├── condition_ast: ConditionNode | None  # Parsed AST — may be None if unparseable
├── then_steps: list[Step | ConditionalBlock]
└── else_steps: list[Step | ConditionalBlock]

Procedure
├── name: str
├── steps: list[Step]
└── parameters: dict[str, str]         # Default symbolic parameter values

Parameter
├── name: str
├── value: Any
└── line_number: int
```

## Important Field Notes

### ConditionalBlock.condition vs condition_ast

`condition` (raw string) is always set and is the authoritative value. Use it for display and logging. `condition_ast` is the parsed AST from `parse_condition()` — it may be `None` if the expression was not parseable. Never rely solely on `condition_ast`.

### DDStatement.is_temporary

`True` when `DSN=&&TEMP...` — the double-ampersand signals a temporary dataset scoped to the job (cleaned up on job end). Distinguished from `&&` as an escaped literal ampersand in other contexts.

### Step.is_exploded vs is_proc_invocation

- Before `explode_job()`: PROC-calling steps have `exec_type="PROC"`, `is_proc_invocation=True`
- After `explode_job()`: The PROC steps are replaced by the expanded steps; each expanded step has `is_exploded=True` and `original_proc_call` set

### job.statements vs job.steps

`statements` is the raw ordered list of all statements including comments. `steps` contains only `Step` and `ConditionalBlock` objects — the executable structure.

## Condition AST Node Types

```python
# All importable from jclparser
ConditionNode  # abstract base
ReturnCodeCondition  # RC(step) comparison — RC(STEP1) LT 8
AbendCondition  # ABEND(step)
RunCondition  # RUN(step)
NotCondition  # NOT(condition)
AndCondition  # condition AND condition
OrCondition  # condition OR condition
```

## Source Modules

| Class | Module |
|-------|--------|
| `Job`, `Step`, `DDStatement`, `Parameter`, `Statement`, `OutputStatement` | `jclparser/model.py` |
| `ConditionalBlock`, `Procedure` | `jclparser/model.py` |
| `ConditionNode` and subtypes | `jclparser/condition_parser.py` |
| `ParseError`, `ValidationError` | `jclparser/errors.py` |

## See Also

- [parsing-pipeline.md](parsing-pipeline.md) — how the Job object is built
- [../advanced/proc-expansion.md](../advanced/proc-expansion.md) — how explode_job() changes Step objects
- [../advanced/validation.md](../advanced/validation.md) — how errors/warnings are populated
- [../api/public-api.md](../api/public-api.md) — full export list including all model classes
