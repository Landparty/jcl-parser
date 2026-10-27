---
type: concept
title: CLI Reference
description: jcl-parser CLI usage — a single FILE + positional-query interface (not subcommands), implemented in jclparser/cli.py:main().
timestamp: 2026-10-15T00:00:00Z
tags: [cli, api, jcl-parser]
---

# CLI Reference

The `jcl-parser` CLI is the command-line interface for the `jclparser` package, installed as the `jcl-parser` entry point (`jclparser/cli.py:main()`). It is **not** a subcommand-based CLI (no `argparse` subparsers) — the first positional argument is always the JCL `FILE`, and an optional second positional `query` token selects the view.

## Usage

```bash
jcl-parser FILE                          # Show job summary
jcl-parser FILE steps                    # List all steps
jcl-parser FILE procs [PROCNAME]         # List/detail procedures
jcl-parser FILE procs --explode          # Show procedure expansion audit
jcl-parser FILE procs --list-available   # List PROCs in --proc-path libraries
jcl-parser FILE STEP                     # Show step details
jcl-parser FILE STEP.DDNAME              # Show a specific DD statement
jcl-parser FILE DDNAME                   # Show all DDs with that name across steps
jcl-parser FILE --json                   # Full parse result as JSON
jcl-parser FILE --validate               # Validate the JCL (structural)
jcl-parser FILE detect                   # Detect file type (JCL/PROC/UNKNOWN)
jcl-parser FILE metrics                  # Structural metrics for the job
jcl-parser FILE lint                     # Run lint rules against the job
jcl-parser --lint-list                   # List all available lint rule codes (no FILE needed)
jcl-parser --json-schema                 # JSON Schema of the --json document (no FILE needed)
jcl-parser FILE datasets                 # Dataset lifecycle analysis
jcl-parser FILE sql                      # SQL/DB2 detection
jcl-parser FILE analyze [STEPNAME]       # Program profile analysis
jcl-parser FILE paths                    # RC feasibility path analysis
```

## Query Token (`steps` / `procs` / `detect` / `metrics` / `lint` / `datasets` / `sql` / `analyze` / `paths`)

`FILE` is always read as a file (`pathlib.Path(FILE)`; a missing file prints `Error: file not found: <FILE>` to stderr and exits 1; any other OS error, such as a directory or an unreadable file, prints `Error: <message>` to stderr and exits 1 instead of a traceback — issue #65, fixed 2026-10-04), so the 2026-10-03 "a `str` is always content" rule in `parse_jcl` does not affect the CLI. `--validate` is handled before any query token and before `detect`.

These are not argparse subcommands — they are matched case-insensitively against the first positional `query` token inside `main()`. `detect` is checked before parsing the file (no parse needed); the rest run after `parse_jcl()` (and after `--explode`, if given).

A bare step name (`jcl-parser FILE PAYSTEP`) or `STEP.DDNAME` falls through to step/DD lookup: the whole token is tried as a step name first (so exploded names like `CALL.PS` work with `--explode`), then — if it contains a dot — split on the **last** dot into step and DD (`CALL.PS.SYSIN`), else searched as a DD name across all steps. (Fixed 2026-09-27: it split on the first dot, so no exploded step or its DDs could be queried.)

`paths` prints `compute_feasible_paths` findings (unreachable / always skipped / contradictory / duplicate IF branches), then a `Not analysed:` section listing any IF whose search exceeded `rc_analysis.MAX_COMBINATIONS` (or, from the API with `include_abends=False`, that tests `RUN` / `ABEND`) (also printed after `(no feasibility issues found)`, since an unanalysed condition is not a finding). `--json` adds an `unanalysed_conditions` list of `[condition, reason]` pairs (since 2026-10-04, issue #65).

Exit codes: 0 on success; 1 for a missing or unreadable `FILE`, a parse error (`Parse error: ...`) or an `--explode` error (`Explosion error: ...`), both on stderr, an unknown `procs PROCNAME` / `analyze STEPNAME` / step / `STEP.DDNAME` / DD name, and `--list-available` without `--proc-path`. `lint` also exits 1 when it reports any finding, `datasets` when there is any lifecycle violation, and `sql` when any step has SQL; `--validate` as described below. `paths`, `metrics`, `analyze`, `detect` and `steps` always exit 0. argparse usage errors exit 2.

Flags may appear anywhere, including between `FILE` and the query (`jcl-parser FILE --json steps`); `main()` uses `parse_intermixed_args` (fixed 2026-09-27: that ordering used to exit 2 with `unrecognized arguments`).

## Flags

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON instead of text |
| `--validate` | `validate_jcl(path, level="structure", proc_base_path=<--proc-path>)`; exits 1 if it reports anything (warnings included; `job.validate()` ERRORs such as a duplicate step name are reported since #57, they used to print `OK`), else prints `OK - no errors found.` `--proc-path` is honoured since 2026-10-15 (#129): it used to be ignored, so a job calling a PROC under `--proc-path` through `JCLLIB ORDER` printed `[ERROR] line N Procedure 'X' not found` unless `JCL_PROCLIB_PATH` was set. Without `--proc-path`, `JCL_PROCLIB_PATH` still applies |
| `--explode` | Expand procedure calls (`job.explode()`) before displaying |
| `--proc-path PATH` | Base path for external PROC libraries and INCLUDE members (enables `enable_external_procs`); used by the parse and by `--validate`. Without it the parse runs with `enable_external_procs=False`, so no external PROC is loaded and `JCL_PROCLIB_PATH` is not read (unlike `--validate`). The parse already loads every PROC the job calls from it (`procs` lists them `[external]`); when none is listed, `procs` notes which called PROCs were not found there, or that the job calls none (the note used to claim they "are expanded with --explode", which they are not) |
| `--list-available` | With `procs`: list PROCs found under `--proc-path` (requires `--proc-path`) |
| `--lint-list` | List all registered lint rule codes + descriptions, then exit (no FILE required) |
| `--json-schema` | Print `JOB_JSON_SCHEMA`, the JSON Schema of the no-query `--json` document, then exit (no FILE required; added 2026-10-27). The `--json` output of the `steps`, `procs`, step and DD queries uses the same `step` / `procedure` / `dd` shapes as the schema's `$defs` |
| `--profile` | Profile the parse; the timing/memory metrics appear only as a `profiling` key in the no-query `--json` output (text output and queries do not show them) |
| `--profile-top-n N` | Number of top functions in profiling output (default 20) |
| `--profile-output PATH` | Write raw cProfile binary to PATH (`.prof` file) |
| `--version` | Print `jcl-parser <__version__>` and exit |

There is **no** `--format` flag and **no** `--strict` flag. Lint output format (text vs. SARIF) is a Python-API choice (`lint_to_sarif()`), not exposed as a CLI flag — the CLI's `lint` query only emits plain text or `--json`.

# Citations

[1] [api/public-api.md](public-api.md) — importable Python API (Tier 1/2/3 tables)
[2] [core/parsing-pipeline.md](../core/parsing-pipeline.md) — what the CLI drives under the hood
