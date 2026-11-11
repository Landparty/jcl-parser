---
type: Subsystem
title: Validation
description: Two independent validation layers — structural (post-parse job checks) and parameter (DD/EXEC parameter checks) — plus lint rules in SARIF format.
tags: [validation, lint, errors, advanced]
timestamp: 2026-10-29T00:00:00Z
---

# Overview

Two layers, both optional. `validate_jcl()` runs both in one call and returns a flat
`list[ParseError]` — never a boolean, and **not** a `(Job, errors)` tuple. It discards the
`Job` it parsed internally, so parse separately if you need the model as well.
Signature: `validate_jcl(source, level=None, config=None, *, proc_base_path=None,
enable_external_procs=True)`; the two keyword-only options load PROCs and INCLUDE members
exactly as for `parse_jcl()` (#129; the CLI forwards `--proc-path` for `--validate`).

# Structural Validation

Implemented in `jclparser/validators.py`.

```python
from jclparser import parse_jcl, validate_jcl, ErrorSeverity

errors = validate_jcl(source, level="structure")  # level is a plain str
hard_errors = [e for e in errors if e.severity == ErrorSeverity.ERROR]
job = parse_jcl(source)  # separate call — validate_jcl does not hand back the Job
```

Or on an already-parsed job:
```python
errors = job.validate()
```

## Validation Levels

`ValidationLevel` (in `jclparser.plugins`) has exactly three members. There is no
`STANDARD` and no `STRICT`.

| Member | `validate_jcl(level=...)` string | Description |
|--------|----------------------------------|-------------|
| `ValidationLevel.BASIC` | `"basic"` (default; `"syntax_only"` is an alias) | Parse-time syntax/structure errors, plus the ERROR-severity `job.validate()` findings — exactly what makes `parse_jcl(strict_mode=True)` fail (e.g. "Invalid DISP", #57) |
| `ValidationLevel.STRUCTURE` | `"structure"` | Every `job.validate()` finding, WARNING/INFO included. Each finding keeps its own severity and line number |
| `ValidationLevel.SEMANTIC` | `"semantic"` | Adds the `ValidationPlugin` checks **enabled by the `config=`** (`ParserConfig.enabled_plugins`, by class name, or `ALL_PLUGINS`; with no config none run): `validate_job(job)`, then `validate_step(step)` for every step (IF branches included) and `validate_dd(dd)` for each of its DDs. Findings keep the plugin's `line_number` (0 when it gives none) and its `severity` (a plugin's WARNING/INFO stays one; ERROR when it sets none) |

`level` takes a `ValidationLevel` member or its string value (case-insensitive); an
unknown level raises `ValueError`. When `level` is omitted, `config.validation_level`
is used, else `"basic"`; an explicit `level` wins over the config.

```python
from jclparser.plugins import ParserConfig, ValidationLevel

config = ParserConfig(validation_level=ValidationLevel.SEMANTIC)
config.enable_plugin("SiteRule")  # plugins are opt-in
errors = validate_jcl(source, config=config)
```

## Strict-parse fallback

`validate_jcl()` first parses strict. When that parse raises (`JCLSyntaxError`,
`JCLValidationError`, `JCLStructureError`), it stops at the first error, so a
line-by-line pass parses every merged statement on its own and checks statement
order (multiple JOBs, EXEC before JOB, EXEC with no program / procedure, DD with no
EXEC in the job). In-stream data and CNTL control records are skipped there exactly
as the parse loop skips them. The strict exception itself is always reported too
(#75), in line order and only once if the line-by-line pass
already found the same line and message -- it is often the only error naming the real
cause, e.g. "Procedure 'XYZ' not found", a malformed `DLM=`, or "No JOB statement
found". That last one is not reported for a PROC member with steps; an empty or
comment-only source does get it, so a truncated file fails the validate gate. When the failing line came
from an `// INCLUDE` member, the error carries the INCLUDE statement's line and its message
ends with `(INCLUDE member NAME, line K)` (#118). When a lenient (non-strict) parse of
the same source succeeds and has steps, its `job.validate()` findings are added as well
(the WARNING that restates a missing PROC is left out), so a PROC missing from a JCLLIB
library no longer hides duplicate names, bad DISPs and the rest.

**Files that are not JCL.** Before parsing, `validate_jcl()` returns a single ERROR
for content that is plainly not JCL: `Not a JCL file: binary content (NUL bytes)`, or
`Not a JCL file: no record starts with //` for non-blank text with no `//` record
(empty input keeps "No JOB statement found"). The line-by-line pass reports the first
20 "Invalid JCL statement (must start with //)" records and sums up the rest as one
`N more record(s) do not start with //` finding (`parser._MAX_NON_JCL_RECORD_ERRORS`),
so `jcl-parser DIR --validate --glob '**/*'` over a repository with PDFs and archives
stays small.

## What It Checks

`job.validate()` (`validators.validate_job_structure`): job name (1-8 chars, alphanumeric + `@#$`), at least one execution step, duplicate step names (WARNING: z/OS runs the job; only a reference to a duplicated name is ambiguous); per step (`validate_step_structure`) the step name, PGM= or PROC (not both), duplicate DD names (WARNING) and the operand checks of `_semantic_checks.check_step_operands` (ERROR unless noted: PARM over 100 characters, PARM with PARMDD, COND= syntax (code 0-4095, operator, at most 8 tests, not both EVEN and ONLY), a SYSOUT class longer than one character, a GDG relative generation past 999, or past 255 as a WARNING); per DD (`validate_dd_statement`) the DD name, dataset name (max 44 chars, qualifiers max 8), DISP and data source; then temporary-dataset dependencies (`validate_data_dependencies`; a `&&` dataset a called PROC creates and does not delete, such as a compile PROC's `&&LOADSET`, exists for later job steps, and a temporary first read after a call to an unavailable PROC is not reported as never created), the dataset lifecycle (`validate_dataset_lifecycle`), unresolved `OUTPUT=*.name` references and PROC calls not found (both WARNING), `IF`/`THEN`/`ELSE`/`ENDIF` statements that do not pair up (`validate_conditional_structure`, ERROR: an IF with no ENDIF, also one a PEND closes inside a PROC; an ELSE or ENDIF with no IF; a second ELSE), the misplaced or malformed statements on `Job.statement_findings` (`validate_statement_placement`; see [core/data-model](../core/data-model.md) for the list), EXEC/DD overrides naming no step of the called PROC (WARNING), temporary datasets read after the step that deleted them (WARNING), the cross-statement checks of `_semantic_checks.check_job_references` (an IF condition the parser cannot read, other than an `ABENDCC` test or one still holding a symbol; an IF or COND= test naming a step not coded before it; `RESTART=` naming no step; `CNTL=*.name` naming no CNTL statement; a new generation `(+n)` read SHR/OLD before the job creates it -- the DDs of a called PROC (in-stream or loaded, nested calls included; `_semantic_checks.called_procedure_dds`) count as the calling step's, and after a call to a PROC that is not available nothing is reported: all WARNING; two OUTPUT statements with one name in one scope: ERROR), the same step and DD checks over every in-stream PROC body and PROC member (`validate_procedure_bodies`, steps named `PROC.step`, values still holding a symbol not judged; a finding on a line the job's own checks already reported is left out), and `*.` backward references that name no DD coded before them (`validate_backward_references`, WARNING: `DSN=`, `VOL=REF=`, `DCB=`, `REFDD=` and `PGM=`; a reference into a PROC the job was not exploded for, or with a symbol in it, is not checked). A missing JOB card is a strict-parse error ("No JOB statement found"), reported by `validate_jcl`. DCB (`RECFM`, `DSORG`, `LRECL`, `BLKSIZE`) and `SPACE` values are **not** checked by either: call `dd.dcb.validate()` / `dd.space.validate()` (`parameter_ast.DCBParameter` / `SPACEParameter`, returning `list[str]`). `TIME`, `REGION` and `MSGLEVEL` values are not validated anywhere (lint `JCL-LINT-004`/`005` only flag a JOB card without `TIME=`/`REGION=`).

Step names are checked with `validators.validate_step_name`, which accepts the qualified names `explode_job()` gives PROC steps (`S1.PS1`, `S1.PS1.IS1`) when every dot-separated part is a valid identifier, so `job.validate()` on an exploded job accepts them. Exploded steps from an *unnamed* `EXEC procname` (placeholder qualifier, no `original_proc_call`) are skipped in the duplicate-step-name check; a real duplicate is still reported.

`DCBParameter.validate()`'s `DSORG` check accepts `PS`/`PO`/`DA`/`IS`/`VS`, their unmovable `U` forms (`PSU`/`POU`/`DAU`/`ISU`) and the BTAM/GAM/TCAM organizations `CX`/`GS`/`TX`/`TQ`/`TR`.

# Parameter Validation

Per-statement checks in `validators.py`; the canonical DISP and dataset-name rules live in `parameter_validators.py` (`DISPValidator`, `DatasetNameValidator`), and typed DCB/SPACE checks on the `parameter_ast.py` objects (see above).

```python
from jclparser import validate_dd_statement, validate_step_structure
from jclparser import validate_jcl_identifier, validate_dataset_name

errors = validate_dd_statement(dd)
validate_jcl_identifier("MYJOB")  # True (a plain bool)
validate_dataset_name("SYS1.PARMLIB")  # True (a plain bool)
```

`validate_dd_statement` accepts every data source z/OS does: `DSN`/`DSNAME`,
`SYSOUT`, `DUMMY` (stored as the positional `_pos_0`, and legal together with
`DSN=`), in-stream data, `DDNAME=`, `PATH=`, `SUBSYS=`, `DYNAM`, and a
work file with no DSN (a system-named temporary dataset) allocated by `UNIT=`/`SPACE=` or by
`DATACLAS=`/`STORCLAS=`/`MGMTCLAS=`/`LIKE=`/`REFDD=`/`AVGREC=` (a bare `DISP=` alone is not
a data source). A DD with none
of them is an error, as is more than one of `DSN`/`SYSOUT`/in-stream data.
Dataset names may carry a PDS member (`LIB(MEMBER)`) or GDG generation
(`GDG(+1)`), and a backward reference (`*.STEP.DD`) is accepted as is; a name
that still holds a symbol (`&SYSUID..DATA`) is not judged. An omitted DISP
status (`DISP=(,CATLG)`) is valid — it defaults to `NEW`.

# Error Object Fields

`validate_jcl()` returns `ParseError` (a frozen dataclass); `job.validate()`, `validate_dd_statement()`, `validate_dataset_lifecycle()` and `lint_job()` return `ValidationError`.

| Field | Type |
|-------|------|
| `severity` | `ErrorSeverity.ERROR / WARNING / INFO` |
| `error_type` | `ErrorType.SYNTAX_ERROR / VALIDATION_ERROR / STRUCTURE_ERROR / SEMANTIC_ERROR` |
| `message` | `str` |
| `line_number` | `int` on `ParseError` (0 = unknown); `int \| None` on `ValidationError` |
| `column_number` | `int \| None` — `ParseError` only |
| `context` | `str` (default `""`) — the problematic JCL fragment; `ParseError` only |
| `error_code` | `str \| None` — the lint rule code (`JCL-LINT-001`); `ValidationError` only |

`str(error)` on a `ValidationError` produces a human-readable message, `Line N: [WARNING] [CODE] message` (used by the backend adapter on `job.validate()` items). `ParseError` defines no `__str__`, so `str()` gives its dataclass repr; read `.message` / `.line_number`.

**Line numbers** (#119): every `job.validate()` finding about a step,
DD or the job itself carries that statement's line — the step rules (invalid step name,
no PGM/PROC, both, duplicate step name) use `Step.line_number`; the DD rules (invalid DD
name, dataset name, DISP, conflicting / missing data source, duplicate DD name) use
`DDStatement.line_number`; the job-name and "at least one execution step" rules use the
JOB statement's line; the temporary-dataset rules use the DD that creates the dataset a
second time, or the first DD that reads one never created.

**"Job must contain at least one execution step"** is not reported for a job whose
only content is in-stream PROCs (no top-level steps, `job.procedures` non-empty, #100): that is how a PROC-library member is wrapped for parsing (the
backend's synthetic `//LEGACYLN JOB`, see [backend-contract](../integration/backend-contract.md)),
and a valid PROC wrapped that way validates clean. A JOB with neither steps nor
procedures gets the error; a JOB-less PROC member (`job.is_procedure_member`)
never does.

# Exception Types (raised by parse_jcl / validate_jcl)

| Exception | Trigger |
|-----------|---------|
| `JCLSyntaxError` | Malformed or misordered JCL (e.g. "EXEC statement before JOB statement", "No JOB statement found"), and in strict mode a PROC not found with a `JCLLIB ORDER` (or with external loading disabled) |
| `JCLValidationError` | Strict mode only: `job.validate()` has ERROR findings (`Job validation failed: ...`) |
| `JCLStructureError` | Strict mode: a DD with no EXEC in a job with no steps; also an INCLUDE expansion over `max_lines` |
| `JCLParseError` | Generic parent — catches all of the above. Exported from `jclparser` (as `interface-contract.md` requires) |

# Dataset Lifecycle Validation

```python
from jclparser import validate_dataset_lifecycle, analyze_dataset_lifecycle

events = analyze_dataset_lifecycle(job)  # dict[dataset name → list[DatasetEvent]]
issues = validate_dataset_lifecycle(
    job
)  # list[ValidationError] — catches disposed-before-use, etc.
```

The catalog check follows a *state* per dataset, not a count: any normal-termination `CATLG` catalogs it (`NEW,CATLG` and also `MOD,CATLG`), a normal `DELETE` / `UNCATLG` removes it. Abnormal-termination dispositions (`DISP=(NEW,PASS,CATLG)`, `(OLD,KEEP,UNCATLG)`) never change the state seen by later steps. So the IEFBR14 "delete if it exists" idiom (`DISP=(MOD,DELETE)`, then re-create with `NEW,CATLG` or `MOD,CATLG`, then read `SHR`) is clean, and a second `NEW,CATLG` after that re-create is still a duplicate. A `MOD` use never warns "opened ... after being uncataloged" (MOD creates a missing dataset); `OLD`/`SHR` after a delete still does, unless the DD names its volume (`VOL=SER=`, or a `VOL=REF=*.step.dd` back-reference; `DatasetEvent.explicit_volume`): it reads the dataset from that volume, not through the catalog, so neither the use-after-uncatalog nor the forward-reference check applies (#186). Dispositions take effect at **step end**: every DD of a step is checked against the state before the step, and the step's normal dispositions are applied afterwards in DD order, so `//D3 DD DSN=PROD.B,DISP=(OLD,DELETE)` followed by `//D4 DD DSN=PROD.B,DISP=SHR` in the same step is clean while a `SHR` in a *later* step still warns (#65). A cataloging allocation counts within the step at once, so two `NEW,CATLG` of one dataset in one step are still a duplicate.

**Libraries and GDG generations** (#81): a DISP applies to a whole library, so `validate_dataset_lifecycle` checks the members of a PDS and the library itself as one dataset, reported under the library name: `P.L(M1),DISP=(NEW,CATLG)` then `P.L(M2),DISP=(NEW,CATLG)` is a duplicate allocation, and `P.L,DISP=(OLD,DELETE)` then `P.L(M2),DISP=SHR` is a use after uncatalog (`&&T(M)` is `&&T`, still skipped here). The parenthesised part is a member unless it is an integer: relative GDG generations (`G.H(0)`, `G.H(+1)`, `G.H(-1)`) stay separate datasets, with one spelling per number (`(+01)` = `(+1)`, `(00)` = `(-0)` = `(0)`). `analyze_dataset_lifecycle` keys its log by the name as coded (`P.L(M1)`).

A backward reference `DSN=*.STEP.DD` is recorded under the dataset of the DD it refers to, so a delete through a referback ends that dataset (`NULLFILE` and unresolvable references record no event). `IF`/`THEN`/`ELSE` branches are walked separately, each from the state before the IF, and merged at `ENDIF`: the same `NEW,CATLG` in the THEN and the ELSE branch is not a duplicate, a duplicate within one branch still is, and after `ENDIF` a dataset counts as cataloged (or uncataloged) when either branch left it so.

**Step `COND=`** (#108): a step whose `COND=` can bypass it — `COND=ONLY`, or any RC test (`COND=(4,LT)`, `COND=((0,NE,S1),EVEN)`, ...), or an unresolved `COND=&C` — is walked like a THEN branch with an empty ELSE, so after it a dataset counts as cataloged (or uncataloged) when either the run or the bypass left it so. `COND=EVEN` alone runs the step on the normal path and is treated as always running. So `//S2 EXEC PGM=IEFBR14,COND=ONLY` deleting a dataset does not make a later `SHR` of it warn "opened ... after being uncataloged", the same as `// IF ABEND THEN` around S2; a second `NEW,CATLG` inside a bypassable step is still a duplicate. Regression tests: `tests/unit/test_medium_analysis_fixes.py::TestLifecycleStepCond`.

**Concatenation members** (#166): an unnamed `//  DD` card continues the concatenation of the named DD before it, so its event carries that DD's name in `dd_name` and its position in `concatenation_member` (the named DD is member 1, the first unnamed card member 2; `0` for a named DD). Messages name it through `DatasetEvent.dd_label`: `(DD IN, concatenation member 2)`. An unnamed card with no named DD before it in the step keeps `dd_name == ""`. Tests: `tests/unit/test_issue_166_concat_member_dd_name.py`. Lint rules JCL-LINT-001/002/006/010 and the structural DD checks (`validate_dd_statement`'s DISP and data-source messages) name a member the same way through `model.dd_label(dds, dd)` (#169): `DD 'IN, concatenation member 2' in step 'S1' ...`, `Invalid DISP parameter 'FOO' on DD IN, concatenation member 3`; an unnamed card with no named DD before it is `(unnamed)`. `validate_dd_statement(dd, label=None)` keeps `dd.name` when called without a label. Tests: `tests/unit/test_issue_169_concatenation_member_labels.py`.

**PROC-call overrides on an unexploded job:** a `//PROCSTEP.DD` override under `EXEC procname` (and the unnamed concatenation members after it) lives in `Step.dd_overrides` / `dd_override_concatenations`, not `dd_statements`. Both checks — the catalog check and `validate_data_dependencies` below — read a step's DDs through `model._dataset_dds()`, which adds those overrides in source order for a PROC call, so `&&T` created by `//PS1.OUT DD DSN=&&T,DISP=(NEW,PASS)` is not "used but never created" in the next step, and a `NEW,CATLG` in an override counts toward duplicate cataloging, as on the exploded job. The event is recorded under the calling step (`S1`) with the qualified DD name (`PS1.OUT`), so a referback `*.S1.PS1.OUT` resolves to it. Overrides under an `EXEC PGM=` step are ignored, as z/OS ignores them. Regression tests: `tests/unit/test_bughunt_validation.py::TestProcCallOverrideDatasets`. The forward-reference warning ("opened DISP=OLD/SHR ... before it is allocated in a later step") only counts allocations on a path that also runs the open: an `OLD` in the THEN branch is not a forward reference to a `NEW` in the ELSE of the same IF; one in a later, separate IF still is.

`validate_data_dependencies` (temporary `&&` datasets, part of `job.validate()`): `DISP=MOD` on a temporary that still exists extends it (the `&&LOADSET` object-deck accumulation of several compiles) rather than creating it twice; an explicit normal `DELETE` ends it, and so does an *omitted* normal disposition on a `NEW` allocation (`DISP=NEW`, `DISP=(NEW,,DELETE)` — the default is DELETE), so a later `NEW` of the same name is a fresh creation. `NEW` while the earlier one still exists (`DISP=(NEW,PASS)`) is an ERROR. A temporary is keyed without its member: `&&GOSET(GO)` and `&&GOSET` are one dataset. `IF`/`THEN`/`ELSE` branches are walked like the catalog check above: each from the set of temporaries alive before the IF, merged at `ENDIF` (alive when either branch left it), so the same `&&T,DISP=(NEW,PASS)` in the THEN and the ELSE is not a duplicate (#60); a second creation within one branch, or after `ENDIF` while a branch's copy is still passed, is still an ERROR.

# Lint Rules (SARIF output)

```python
from jclparser import lint_job, lint_to_sarif, LintConfig

findings = lint_job(job, config=LintConfig())
sarif = lint_to_sarif(findings, artifact_uri="jobs/MYJOB.jcl")
```

`lint_job` also runs the rules over the steps of each PROC body coded in the job's own source (an in-stream `PROC ... PEND`, or the PROCs of a PROC member; not an external PROC loaded from elsewhere), through `lint.runner.procedure_body_job(proc)`: a JOB-less job whose steps are named `PROC.step`, so the job-card rules (004, 005) do not fire. With `--explode` the job's expanded copy and the body report the same DD; a body finding with the same code and line as one already reported is dropped (#149). `jclparser.lint.to_sarif_files([(uri, findings), ...])` renders several files as one run (what `jcl-lint` and `jcl-parser DIR lint --sarif` emit); a finding with no line but a URI points at the whole file. `informationUri` is the project's GitHub URL. TOML configuration (`load_lint_config`) and `//* jcl-lint: disable=` comments (`lint_job(..., source=text)`) are described in [api/cli-reference](../api/cli-reference.md#lint-configuration-and-suppressions).

Every result location carries `physicalLocation.artifactLocation` (SARIF 2.1.0 requires it); `artifact_uri` fills its `uri` — omit it and the `artifactLocation` is empty, which is schema-valid but gives consumers such as GitHub code scanning no file to place the result in.

Built-in rule IDs follow `JCL-LINT-NNN`. Custom rules extend the `LintRule` ABC (register with `jclparser.register_lint_rule`, which is `jclparser.lint.register_rule`; remove with `jclparser.lint.unregister_rule`). `LintConfig` takes `enabled` / `disabled` (sets of codes; empty `enabled` = every rule), `severities` (per-code `ErrorSeverity` override) and `critical_dataset_patterns`. Built-in rules (`jclparser/lint/rules.py`, `BUILTIN_RULES`):

| Code | Rule class | Default severity | Fires on |
|------|------------|------------------|----------|
| `JCL-LINT-001` | `HardcodedHLQRule` | INFO | A literal dataset name with at least two qualifiers (not `&&` temporaries, referbacks, `NULLFILE`, or names built from symbols) |
| `JCL-LINT-002` | `LiteralSysdaUnitRule` | INFO | `UNIT=SYSDA` |
| `JCL-LINT-003` | `CriticalDatasetDeleteRule` | WARNING | See below (needs `critical_dataset_patterns`) |
| `JCL-LINT-004` | `MissingJobTimeRule` | INFO | JOB card without `TIME=` (not a JOB-less PROC member) |
| `JCL-LINT-005` | `MissingJobRegionRule` | INFO | JOB card without `REGION=` (not a JOB-less PROC member) |
| `JCL-LINT-006` | `NewDatasetWithoutRlseRule` | INFO | A new (`NEW` or omitted status) non-temporary dataset whose `SPACE` has no `RLSE` |
| `JCL-LINT-007` | `DuplicateStepNameRule` | WARNING | A step name already used in the job |
| `JCL-LINT-008` | `UndefinedOutputRefRule` | WARNING | `DD OUTPUT=*.name` matching no `OUTPUT` statement |
| `JCL-LINT-009` | `CondMixedWithIfRule` | INFO | An EXEC `COND=` in a job that also has `IF`/`THEN` blocks (one finding per such step) |
| `JCL-LINT-010` | `LiteralSetValueHlqRule` | WARNING | A literal dataset name whose first qualifier equals a `SET` symbol's value (2-8 alphanumerics); names the symbol. While it runs, JCL-LINT-001 leaves those names to it |

A rule that raises yields a `JCL-LINT-000` finding (WARNING by default) instead of stopping the run. Rules 001-003 read a PROC call's `//PROCSTEP.DD` overrides too (`model._dataset_dds`).

Each SARIF `tool.driver.rules[]` entry takes its `shortDescription` and `fullDescription` from the registered rule's `description` (rules have no separate title, so both carry it); the pseudo-codes `JCL-LINT-000` (a rule raised) and `JCL-GEN-000` (finding without a code) have fixed descriptions, and a code no registered rule carries gets only `shortDescription` = its code (#88).

`JCL-LINT-003` (critical dataset, `LintConfig.critical_dataset_patterns`) fires only on `DISP=(NEW,CATLG,DELETE)` and `DISP=(NEW,KEEP,DELETE)` (an omitted status counts as `NEW`): a successful run keeps the dataset, an abend deletes it. An omitted normal disposition (`(NEW,,DELETE)`, which defaults to DELETE), `DELETE` or `PASS` does not fire, and the message shows the disposition as coded, an omitted status as `NEW` (#88).

# Citations

[1] [development/invariants.md](../development/invariants.md) — invariant 7 (validate_jcl return shape)
[2] [api/public-api.md](../api/public-api.md) — Tier 1/2 validation export table
[3] [integration/backend-contract.md](../integration/backend-contract.md) — how backend uses `job.validate()`
