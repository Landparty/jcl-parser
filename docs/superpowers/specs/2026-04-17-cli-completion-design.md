# CLI Completion Design

**Date:** 2026-04-17  
**Status:** Approved  
**Scope:** Add 7 missing subcommands to `jclparser/cli.py`

---

## Problem

The library exposes a rich analysis surface — lint, metrics, dataset lifecycle, SQL
detection, program profiling, RC feasibility, and file-type detection — none of which
are reachable from the CLI. Users can only parse, validate, inspect steps/procs/DDs,
and explode PROCs.

## Goal

Every first-class public API function gets a corresponding CLI subcommand so the tool
is useful standalone (in CI pipelines, shell scripts, editors) without writing Python.

---

## Architecture

All changes go in `jclparser/cli.py`. No new files. The 7 subcommands are added as
additional branches in the existing `query` dispatch block in `main()`, following the
exact same pattern as `steps` and `procs`:

```
if query.lower() == "lint":   ...
if query.lower() == "metrics": ...
...
```

Each subcommand gets:
- A `_cmd_<name>` function for the logic
- A `_print_<name>` helper for text output
- A `_<name>_to_dict` helper for `--json` output

### Cross-cutting flags (all inherited, no new global flags)

| Flag | Applies to |
|---|---|
| `--json` | all subcommands |
| `--explode` | `lint`, `sql`, `analyze` (analysis benefits from expanded job) |
| `--proc-path` | `lint`, `sql`, `analyze` (needed when `--explode` loads external PROCs) |

### Lint-specific flags

| Flag | Effect |
|---|---|
| `--lint-list` | Print all available rule codes + descriptions, then exit (no FILE needed) |

---

## Subcommands

### `detect`

```
jcl-parser FILE detect
```

Uses `detect_file_type(path)`. Does **not** parse the JCL — only inspects content.
Exit 0 always (detection never fails). Text output: `JCL`, `PROC`, or `UNKNOWN`.

```
$ jcl-parser myjob.jcl detect
JCL

$ jcl-parser myjob.jcl detect --json
{"file_type": "JCL", "path": "myjob.jcl"}
```

---

### `metrics`

```
jcl-parser FILE metrics
```

Calls `compute_metrics(job)`. No `--explode` (metrics are on the raw parsed job).

Text output: aligned key=value table.

```
steps:              12
exec_steps:          9
procs_defined:       2
dd_statements:      47
max_nesting_depth:   3
has_conditionals:  true
```

JSON: the `JobMetrics` dataclass fields as a flat dict.

Exit 0 always.

---

### `lint`

```
jcl-parser FILE lint
jcl-parser FILE lint --explode
jcl-parser --lint-list
```

Calls `lint_job(job)`. Supports `--explode`. Each finding on its own line:

```
[JCL001] line  42: Hardcoded HLQ 'PROD' — use symbolic &HLQ
[JCL003] line  87: DISP=DELETE on critical dataset MY.PROD.DATA
```

JSON: `{"findings": [...], "count": N}` where each finding has `code`, `severity`,
`line`, `step`, `message`.

`--lint-list` prints all registered rules (code + one-line description) and exits 0
before parsing any file. Implementation note: check for `--lint-list` in `argv` before
argparse runs so FILE remains required for all other commands.

Exit 0 = no findings. Exit 1 = findings present.

---

### `datasets`

```
jcl-parser FILE datasets
```

Calls `analyze_dataset_lifecycle(job)` and `validate_dataset_lifecycle(job)`.

Text output: one section per dataset, listing creation/use/deletion events, then a
violations section if any exist.

```
MY.INPUT.FILE
  NEW     STEP010 line  23  (status=NEW, normal=CATLG)
  USE     STEP020 line  45
  DELETE  STEP030 line  67  (status=OLD, normal=DELETE)

MY.OUTPUT.FILE
  NEW     STEP020 line  46  (status=NEW, normal=KEEP)

Violations (1):
  [WARNING] MY.TEMP.FILE: dataset used before creation in STEP040
```

JSON: `{"lifecycle": {...}, "violations": [...]}`.

Exit 0 = no violations. Exit 1 = violations present.

---

### `sql`

```
jcl-parser FILE sql
jcl-parser FILE sql --explode
```

Calls `detect_sql_in_job(job)`. One result per step that has any SQL signal.

```
STEP010  DB2PROG    confidence=HIGH   evidence: DB2 program, DBRM DD present
STEP030  IKJEFT01   confidence=MEDIUM evidence: SYSIN contains EXEC SQL
```

JSON: list of `{step, program, confidence, evidence, is_db2_program}`.

Exit 0 = no SQL detected. Exit 1 = SQL detected (useful in compliance pipelines).

---

### `analyze`

```
jcl-parser FILE analyze
jcl-parser FILE analyze STEPNAME
jcl-parser FILE analyze --explode
```

Calls `analyze_job(job)` or `analyze_step(step, job)` for a single step.

Text output: per-step profile hit with DD mapping and any warnings.

```
STEP010  IEBGENER   input=SYSUT1  output=SYSUT2
STEP020  SORT       input=SORTIN  output=SORTOUT  work=SORTWK01..03
STEP030  IDCAMS     [no profile match]
```

Warnings (e.g., missing required DDs) printed below each step.

JSON: list of `{step, program, profile, dd_mapping, warnings}`.

Exit 0 always.

---

### `paths`

```
jcl-parser FILE paths
```

Calls `compute_feasible_paths(job)`. Shows each conditional block's feasibility
analysis — which branches are always/never/sometimes taken.

```
IF (STEP010.RC = 0) THEN   line 34
  THEN branch: feasible
  ELSE branch: feasible

IF (STEP020.RC > 4) THEN   line 58
  THEN branch: infeasible (RC domain 0-4 for STEP020)
  ELSE branch: always taken
```

JSON: the `FeasibilityReport` structure.

Exit 0 always.

---

## Error handling

All new subcommands inherit the existing top-level parse error handling. If `--explode`
is requested and explosion fails, the existing explosion error path prints the error and
returns exit 1 — no additional handling needed.

If a subcommand receives a query it doesn't understand (e.g. `jcl-parser FILE analyze
NOSUCHSTEP`), it prints to stderr and returns 1, matching existing behaviour for missing
steps/DDs.

---

## Testing

New test file: `tests/unit/test_cli.py` already exists. Add a test class per subcommand
(`TestCLILint`, `TestCLIMetrics`, etc.) with at minimum:
- Happy path (text output, exit 0)
- `--json` output (valid JSON, correct keys)
- Error/empty case (no findings, no SQL, etc.)

No new fixtures needed — use the inline JCL strings already present in `test_cli.py`.

---

## Out of scope

- Color/ANSI output
- `--sarif` flag
- Interactive mode
- Config file for lint rules
- Multiple `--proc-path` entries
