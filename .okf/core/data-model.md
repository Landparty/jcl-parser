---
type: Data Model
title: JCL Data Model
description: Hierarchy of Job, Step, DDStatement, ConditionalBlock, and Procedure objects returned by parse_jcl().
tags: [model, core, data-model]
timestamp: 2026-10-29T00:00:00Z
---

# Overview

`parse_jcl()` returns a `Job` object. Everything else hangs off it. Every class
below is a `@dataclass` in `jclparser/model.py`; the tables list the real
dataclass fields, with `()` marking callables (methods/properties) rather than
fields — the distinction matters, `dd.is_temporary` is a bound method, not a
`bool`.

`Job`, `Step`, `DDStatement`, `Statement`, `OutputStatement`, `Parameter` and
`ConditionalBlock` (with `iter_execution_steps`, #99) are
re-exported from `jclparser`. **`Procedure` is not** — import it from
`jclparser.model` if you need the name (it is reachable without importing, via
`job.procedures`).

# Schema

## Job

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | From `//JOBNAME JOB` card; required, not optional. `""` on the synthetic job of a JOB-less PROC member |
| `parameters` | `dict[str, Any]` | JOB card params (CLASS, MSGCLASS, NOTIFY…) |
| `accounting_info` | `str \| None` | First positional (`_pos_0`) of the JOB card |
| `steps` | `list[Step \| ConditionalBlock]` | Executable structure only |
| `procedures` | `list[Procedure]` | Inline `PROC…PEND` blocks |
| `conditionals` | `list[ConditionalBlock]` | Flat list of IF/THEN/ELSE blocks |
| `set_statements` | `dict[str, str]` | Job-level SET symbol definitions. A SET inside a `PROC`…`PEND` body is **not** here — it is on `Procedure.set_statements`. For a JOB-less member the synthetic job also carries its procedures' SETs |
| `jcllib_order` | `list[str]` | JCLLIB library concatenation, with the SET symbols in effect at the JCLLIB statement substituted (an entry with an unresolved `&symbol` stays as written, with a warning; #128) |
| `includes` | `list[str]` | INCLUDE member references |
| `comments` | `list[str]` | Present on the model but never populated — see invariant 8 |
| `line_number` | `int` | Default `0` |
| `explosion_audit` / `explosion_map` | `list[Any]` / `dict[str, Any]` | Populated by `explode_job(audit=True)` |
| `jes_statements` | `list[str]` | `/*JOBPARM`, `/*ROUTE`… raw text |
| `jes_typed_statements` | `list[Any]` | Same cards promoted to typed models; unknown JES commands stay raw-only. `parameters` stop at the first blank outside quotes/parens (the rest is a comment, kept in `raw`), except `//*OPERATOR` message text |
| `output_statements` | `list[OutputStatement]` | OUTPUT statements |
| `joblib_dds` | `list[DDStatement]` | JOBLIB concatenation |
| `control_statements` | `list[Statement]` | `COMMAND` / `SCHEDULE` / `CNTL` / `NOTIFY` kept verbatim; a CNTL block's records live in `parameters["_records"]` |
| `custom_statements` | `list[Statement]` | Statements whose `type` the parser has no handler for — a custom type returned by an enabled `StatementPlugin` — kept verbatim in source order (#130). Copied onto the job `explode_job` returns |
| `sql_detections` | `dict[str, Any]` | Keyed by step name; only with `ParserConfig(detect_sql=True)` |
| `unresolved_output_refs` | `list[tuple[str, str, int]]` | `OUTPUT=*.name` refs with no definition in scope: `(step_name, ref, line_number)`, see [OutputStatement](#outputstatement) |
| `conditional_errors` | `list[tuple[int, str]]` | `IF`/`THEN`/`ELSE`/`ENDIF` statements that do not pair up, as `(line_number, message)`; `job.validate()` reports each as an ERROR. Copied onto the job `explode_job` returns; not in the JSON export (`warnings` carries the same findings) |
| `exported_symbols` | `set[str]` | From `EXPORT SYMLIST=(...)`; `"*"` exports every SET symbol |
| `warnings` | `list[str]` | **Plain strings, not `ParseError`.** Non-fatal issues; parsing never fails on these |
| `is_procedure_member` | `bool` | `True` only on the synthetic `Job(name="")` returned for a JOB-less cataloged PROC member; the JOB-statement checks (job name, "at least one execution step", `JCL-LINT-004/005`) skip it. Kept by `explode_job`. Default `False` (#98) |

There is **no** `job.statements` and **no** `job.errors` field. Parse errors are
raised as exceptions or returned by `validate_jcl()`; non-fatal issues land in
`job.warnings` as strings.

Useful accessors (not fields): `job.validate()`, `job.explode(...)`,
`job.get_step()`, `job.get_dd_statements()`, `job.get_sysin_statements()`,
`job.get_library_search_order()`, plus JOB-card properties (`job_class`,
`msgclass`, `notify`, `region`, `time`, `cond`, `restart`, `typrun`, …).

## Step

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str \| None` | Max 8 chars; an unnamed EXEC gives `""` (the dataclass default is `None`). An exploded step is named `STEP.PROCSTEP` |
| `program` | `str \| None` | `PGM=` value |
| `procedure` | `str \| None` | PROC name being invoked (there is no `proc_name`) |
| `parameters` | `dict[str, Any]` | EXEC params (PARM, COND, TIME, REGION…) |
| `dd_statements` | `list[DDStatement]` | |
| `comments` | `list[str]` | Never populated — see invariant 8 |
| `line_number` | `int` | Default `0`, never `None` |
| `is_exploded` | `bool` | True after `explode_job()` |
| `original_proc_call` | `str \| None` | Set after explosion |
| `dd_overrides` | `dict[str, DDStatement]` | Qualified `PROCSTEP.DDNAME` overrides. Dataset checks on an unexploded PROC call read them too, through `model._dataset_dds(step)` |
| `dd_override_concatenations` | `dict[str, list[DDStatement]]` | Unnamed DDs coded after a qualified override (same key): overrides of that DD's later concatenation members |
| `set_symbols` | `dict[str, str] \| None` | SET table in effect when this step was read (the job's for a job-level step, the procedure's own `set_statements` for a step inside a PROC body); kept only when a later SET redefines a symbol (else `None`; always `None` on an exploded step). Not part of `==` or `repr` |
| `is_procedure()` | property → `bool` | **This is how you test for a PROC invocation.** Equivalent to `step.procedure is not None` |

There is **no** `exec_type` and **no** `is_proc_invocation` attribute anywhere in
the codebase; use `step.procedure` / `step.is_procedure`.

## DDStatement

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | DD name, max 8 chars |
| `dataset_name` | `str \| None` | `DSN=` value, or `DSNAME=` (its long form) when no `DSN=` is coded. Always text: a parenthesised `DSN=(A.B)` (tokenized to a list in `parameters`) is rendered back as coded, `"(A.B)"`, so `validate_jcl()` reports it as an invalid dataset name (#121) |
| `coded_dataset_name` | `str \| None` | The dataset name as coded, before SET / PROC symbol substitution (`&HLQ..DATA` while `dataset_name` reads `PROD.DATA`); recorded for any name containing `&` by the pass that substitutes it (the parse-time SET pass, which runs only when the job has a SET, or `explode_job`), else `None`. Not part of `==` or `repr` |
| `disposition` | `str \| list[str] \| None` | `DISP=` value as tokenized: a string for a bare status (`"SHR"`), a list for a parenthesised one (`["NEW", "CATLG", "DELETE"]`; an omitted status is `""`) |
| `parameters` | `dict[str, Any]` | DSN, DISP, SPACE, DCB, SYSOUT… |
| `inline_data` | `str \| None` | Content between `DD *` and `/*`, as **one string** (there is no `instream_data` list). Data records after a step with no `DD *` / `DD DATA` ahead of them get an implicit `SYSIN` DD (`parameters={"*": True}`), as JES does, plus a `job.warnings` entry |
| `comments` | `list[str]` | Never populated — see invariant 8 |
| `line_number` | `int` | |
| `output_refs` | `list[OutputStatement]` | Resolved `OUTPUT=*.name` back-references, by step scope (see [OutputStatement](#outputstatement)) |
| `is_temporary()` | method → `bool` | True when `dataset_name` starts with `&&`. **Call it** |
| `is_input()` / `is_output()` | methods → `bool` | Derived from the DISP **status** only: `OLD`/`SHR` → input; `NEW`/`MOD`, or an omitted status (`DISP=(,CATLG)`, default NEW) → output. Normal/abnormal dispositions do not count, so `(SHR,PASS,CATLG)` and `(OLD,KEEP,UNCATLG)` are inputs, not outputs. No DISP on a DD that names a dataset → `NEW`, so `is_output()` is `True` (z/OS default `(NEW,DELETE)`, #105). No DISP on a DUMMY, SYSOUT, `DD *`, `DSN=NULLFILE` or `DSN=*.STEP.DD` backward-reference DD → both `False` |
| `has_inline_data` | property → `bool` | |
| `dcb` / `space` | properties | Typed `DCBParameter` / `SPACEParameter` from `parameter_ast.py`. `dcb` also includes DCB subparameters coded directly on the DD (`RECFM`, `LRECL`, `BLKSIZE`, `DSORG`, `BUFNO`, `KEYLEN`, `OPTCD`) — a `DCBParameter` is synthesised when there is no `DCB=`, and a DD-level keyword overrides the same subparameter inside `DCB=`. Cached. `space.validate()` rejects a *negative* primary only: `SPACE=(TRK,0)` (the IEFBR14 `DISP=(MOD,DELETE)` delete idiom) is valid |
| `dataclas` / `mgmtclas` / `storclas` / `dsntype` | properties → `str \| None` | SMS classes |

There is no `is_sysout` attribute — read `dd.parameters.get("SYSOUT")`.

The disposition sets behind `is_input()` / `is_output()` (and `_DD_LEVEL_DCB_KEYWORDS`) are `ClassVar`s, not dataclass fields, so `dataclasses.asdict(job)` is JSON-serialisable.

## ConditionalBlock

| Field | Type | Notes |
|-------|------|-------|
| `condition` | `str` | Raw condition — **always present, authoritative** |
| `then_steps` | `list[Step \| ConditionalBlock]` | |
| `else_steps` | `list[Step \| ConditionalBlock]` | |
| `line_number` | `int` | |
| `condition_ast` | `ConditionNode \| None` | May be None if unparseable — never rely solely on this |

## Procedure

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | |
| `parameters` | `dict[str, Any]` | Default symbolic parameter values |
| `steps` | `list[Step \| ConditionalBlock]` | |
| `line_number` | `int` | |
| `is_external` | `bool` | True when loaded through the loader chain rather than inline |
| `set_statements` | `dict[str, str]` | Symbols assigned by `SET` statements coded inside the procedure body. Applied only when the procedure is expanded (above job SETs, below PROC defaults and EXEC overrides); never merged into the calling job's `set_statements`. See [advanced/proc-expansion](../advanced/proc-expansion.md#symbol-substitution) |
| `source_text` | `str \| None` | The member text an external PROC was read from (not in `repr`, equality or JSON); `explode_job` expands its INCLUDEs (#153). `None` for an in-stream PROC |

## OutputStatement

An `OUTPUT` JCL statement (JES output descriptor), in `job.output_statements`.
Properties such as `dest`, `output_class`, `copies` read `parameters`.

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | Label referenced by `DD OUTPUT=*.name` |
| `parameters` | `dict[str, Any]` | All OUTPUT parameters |
| `line_number` | `int` | Default `0` |
| `step_name` | `str \| None` | Step the statement is coded in (step-level OUTPUT); `None` for a job-level one, coded before the first EXEC. In an in-stream PROC body it is the procedure step (#85) |
| `procedure_name` | `str \| None` | In-stream PROC whose body holds the statement; `None` outside `PROC`…`PEND` (#85) |
| `type` | `str` | Always `"OUTPUT"`; not an `__init__` argument |

`OutputStatement(name, parameters, line_number)` constructs a job-level
statement. `DD OUTPUT=*.name` resolves to the OUTPUT statement of that name in the
DD's own step, else the job-level one; `*.step.name` to the one in job step `step`;
`*.step.procstep.name` to the one in step `procstep` of the in-stream PROC that job
step `step` calls (not checked when that PROC is external). A step-level OUTPUT in
another step never satisfies `*.name`: the reference lands on
`Job.unresolved_output_refs` as `(step, ref, line)`, `ref` as coded after `*.`
(`"OUT1"`, `"S1.OUT1"`), and `validate_output_references` / lint rule
`JCL-LINT-008` warn (#85).

## Statement

The generic pre-model record produced by `parse_statement()`:
`type`, `name`, `parameters`, `line_number`, `warnings`. Note `Statement` has no
`COMMENT` type — comment lines never reach the model (invariant 8).

## Condition AST Node Types

`ReturnCodeCondition`, `AbendCondition`, `RunCondition`, `NotCondition`, `AndCondition`, `OrCondition` — all importable from `jclparser`.

`parse_condition()` accepts both keyword and symbolic Boolean operators (`AND`/`&`, `OR`/`|`, `NOT`/`¬`, with `^`/`~` for `¬`) and `ABEND`/`RUN` tests written as `= TRUE` / `= FALSE`. It returns `None` rather than a partial AST whenever it cannot consume the whole expression: `ABENDCC` tests, a non-numeric RC value (`RC GT &MAX`), leftover tokens, a character outside the grammar (`S1.RC = -1`, `;`, `*`, ...), a bare `RC` / `STEP.RC` with no comparison (#63), and a bare number (`4`, `4 AND RC = 0`, #86). A missing final `)` and a stray trailing `)` are tolerated. A value-first comparison is mirrored into RC-first form: `4 LT RC` is `RC GT 4`, `4 LT S1.RC` is `S1.RC GT 4`, and `4 GT` with no RC after it is `None`. The mnemonic `NG` (not greater, → `LE`) and `NL` (not less, → `GE`) operators are accepted. When evaluating, `step_results` maps an uppercase step name to `(rc, abended)`, or to `condition_parser.NOT_RUN` for a step known not to have executed: `STEP.RC op n`, `STEP.ABEND` and `STEP.RUN` on a `NOT_RUN` step are `False` (IBM), whereas a step absent from the mapping is unknown and its `RC`/`ABEND`/`RUN` tests give `None` (#61). `NOT`/`AND`/`OR` combine `None` with Kleene three-valued logic (`None AND False` = `False`, `None OR True` = `True`, otherwise `None`). A condition with no step name follows IBM semantics: `RC` is the **highest** RC of the steps that ran, and `ABEND` is true if **any** of them abended (`NOT_RUN` steps are ignored). `NOT_RUN` is not re-exported from `jclparser`; import it from `jclparser.condition_parser`.

**Operator precedence (IBM, #101).** Per the *z/OS MVS JCL Reference*, "IF/THEN/ELSE/ENDIF statement construct" (operator table): `NOT` is evaluated first, the comparison operators second, and `AND` and `OR` third, **at the same level, left to right**. `parse_condition()` builds one left-associative chain for `AND`/`OR`, so `S1.RC = 0 | S1.RC = 4 & S2.ABEND` is `AndCondition(OrCondition(RC=0, RC=4), ABEND)` — false when S1 ended RC 0 and S2 did not abend; `AND` does **not** bind tighter than `OR` as it would in C. Parentheses group.

# Key Field Notes

- **Comments are dropped.** `Job.comments` / `Step.comments` / `DDStatement.comments`
  exist but are never populated, and there is no `job.statements` holding raw
  statements. The only statements kept verbatim are `COMMAND` / `SCHEDULE` /
  `CNTL` / `NOTIFY` (z/OS 2.3), in `job.control_statements`, and
  plugin statements of a custom type, in `job.custom_statements`. See [development/invariants](../development/invariants.md) #8.
- `ConditionalBlock.condition` is always set; `condition_ast` may be `None`.
- **JSON export**: `Job`, `Step`, `DDStatement`, `ConditionalBlock` and
  `Procedure` have `to_dict()` (and `Job.to_json(**json_kwargs)`), delegating to
  `jclparser/serialization.py`. The job document carries `schema_version` and
  validates against `JOB_JSON_SCHEMA`; it omits `condition_ast` (invariant 3),
  `explosion_audit` / `explosion_map` and `sql_detections`. See
  [api/public-api](../api/public-api.md).
- `DDStatement.is_temporary()` is a **method**: `dd.is_temporary()`, not `dd.is_temporary`.
  `True` when `DSN=&&TEMP...` — double-`&&` signals a temporary dataset.
- Before `explode_job()`: PROC-calling steps have `procedure` set and
  `is_procedure` true. After: replaced by expanded steps with `is_exploded=True`
  and `original_proc_call` set.

# Citations

[1] [core/parsing-pipeline.md](parsing-pipeline.md) — how the Job object is built
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — how `explode_job()` changes Step objects
[3] [development/invariants.md](../development/invariants.md) — invariant 8 (comments dropped)
