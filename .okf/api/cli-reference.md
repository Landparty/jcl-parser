---
type: concept
title: CLI Reference
description: jcl-parser CLI usage — a single FILE (or DIR) + positional-query interface (not subcommands), implemented in jclparser/cli.py — plus the jcl-lint script.
timestamp: 2026-10-29T00:00:00Z
tags: [cli, api, jcl-parser]
---

# CLI Reference

The `jcl-parser` CLI is the command-line interface for the `jclparser` package, installed as the `jcl-parser` entry point (`jclparser/cli.py:main()`, argument parsing in `_build_arg_parser()`). It is **not** a subcommand-based CLI (no `argparse` subparsers) — the first positional argument is always the JCL `FILE`, and an optional second positional `query` token selects the view.

## Usage

```bash
jcl-parser FILE                          # Show job summary (FILE "-" reads stdin)
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
jcl-parser FILE lint [--sarif]           # Run lint rules against the job
jcl-parser --lint-list                   # List all available lint rule codes (no FILE needed)
jcl-parser --json-schema                 # JSON Schema of the --json document (no FILE needed)
jcl-parser FILE datasets                 # Dataset lifecycle analysis
jcl-parser FILE sql                      # SQL/DB2 detection
jcl-parser FILE analyze [STEPNAME]       # Program profile analysis
jcl-parser FILE paths                    # RC feasibility path analysis
jcl-parser DIR [lineage] [dot|mermaid]   # Cross-job dataset lineage of a directory of jobs
jcl-parser DIR lint [--sarif]            # Lint every job of a directory
jcl-parser DIR --validate [--sarif]      # Validate every file of a directory
jcl-lint PATH... [--format text|json|sarif] [-o FILE]   # Lint files/dirs (CI, pre-commit)
```

## Query Token (`steps` / `procs` / `detect` / `metrics` / `lint` / `datasets` / `sql` / `analyze` / `paths`)

`FILE` is always read as a file (`pathlib.Path(FILE)`, or stdin when it is `-`, decoded like a file, #132), unless it is a directory (see Directory Mode below), so the "a `str` is always content" rule of `parse_jcl` does not affect the CLI. A missing file prints `Error: file not found: <FILE>` to stderr and exits 1; any other OS error, such as an unreadable file, prints `Error: <message>` and exits 1. `--validate` is handled before any query token and before `detect`.

These are not argparse subcommands — `_run_query()` matches them case-insensitively against the first positional `query` token (the simple views through the `_JOB_QUERIES` table). `detect` is checked before parsing the file (no parse needed); the rest run after `parse_jcl()` (and after `--explode`, if given).

A token that is, **exactly as typed**, the name of a step or DD in the job wins over the query word (#133): JCL names are uppercase, so `jcl-parser FILE SQL` shows a step or DD named `SQL` when there is one, while `sql` is always the SQL query. An uppercase word that names nothing in the job still runs the query (`STEPS` lists the steps). For `DETECT` the file is parsed quietly to find out; a file that does not parse runs `detect`.

A bare step name (`jcl-parser FILE PAYSTEP`) or `STEP.DDNAME` falls through to step/DD lookup: the whole token is tried as a step name first (so exploded names like `CALL.PS` work with `--explode`), then — if it contains a dot — split on the **last** dot into step and DD (`CALL.PS.SYSIN`), else searched as a DD name across all steps.

`paths` prints `compute_feasible_paths` findings (unreachable / always skipped / contradictory / duplicate IF branches), then a `Not analysed:` section listing any IF whose search exceeded `rc_analysis.MAX_COMBINATIONS` (or, from the API with `include_abends=False`, that tests `RUN` / `ABEND`) (also printed after `(no feasibility issues found)`, since an unanalysed condition is not a finding). `--json` adds an `unanalysed_conditions` list of `[condition, reason]` pairs (#65).

Exit codes: 0 on success; 1 for a missing or unreadable `FILE`, a parse error (`Parse error: ...`) or an `--explode` error (`Explosion error: ...`), both on stderr, an unknown `procs PROCNAME` / `analyze STEPNAME` / step / `STEP.DDNAME` / DD name, and `--list-available` without `--proc-path`. `lint` also exits 1 when a finding reaches the `fail-on` severity (`--fail-on`, else the config's `fail-on`, else `info`: any finding), and 2 when the lint configuration cannot be read, `datasets` when there is any lifecycle violation, and `sql` when any step has SQL; `--validate` exits 1 when a finding is an ERROR (or at least as severe as `--fail-on` when given), as described below. `paths`, `metrics`, `analyze`, `detect` and `steps` always exit 0. argparse usage errors exit 2.

Flags may appear anywhere, including between `FILE` and the query (`jcl-parser FILE --json steps`); the CLI uses `parse_intermixed_args`.

## Directory Mode (`lineage`, `lint`, `--validate`)

When `FILE` is a directory, the default query is `lineage`: the CLI runs `load_job_stream(DIR, --glob, proc_base_path=--proc-path)` and prints the cross-job lineage: the jobs read, the PROC members found (`PROC members (used to explode the jobs): ...`, #144), files that did not parse, jobs left unexploded, the run order, jobs a dependency cycle keeps out of it, each producer → consumer dependency with its datasets, external inputs and final outputs. `lineage dot` / `lineage mermaid` print the job graph instead, and `--json` prints `JobStream.to_dict()` merged with `LineageReport.to_dict()` (`job_names`, `procedures`, `errors`, `warnings`, `jobs`, `run_order`, `cycles`, `dependencies`, `external_inputs`, `final_outputs`, `datasets`). Exit 1 with `Error: ...` on stderr for a query other than `lineage` / `lint` (or `--validate` combined with a query), an unknown graph format, or a directory with no parseable job. Jobs are always exploded for lineage (`--explode` is implied).

`DIR lint` lints every job `load_job_stream(DIR, --glob, explode=--explode, proc_base_path=--proc-path)` finds and every PROC member it lists (each member's PROC body steps, named `PROC.step`; a member with no `PROC` statement too, #149); a file that does not parse is one `JCL-PARSE-000` ERROR finding) and prints `FILE:LINE: SEVERITY [CODE] message` per finding (sorted by line), then `N finding(s) in M of K file(s)`, or `OK - no lint findings.`; `--json` prints `{"files": {path: [finding, ...]}, "count": N}` and `--sarif` one SARIF run whose results carry each file's path as `artifactLocation.uri`. Exit codes as for `FILE lint`; no job found is exit 1. `DIR --validate` runs `validate_jcl` on every file `--glob` matches (hidden files skipped) with the same three output forms; a binary file or text with no `//` record is one ERROR, not one per line (see [advanced/validation](../advanced/validation.md#strict-parse-fallback)). Exit 1 if a finding is an ERROR (or reaches `--fail-on`) or no file matches. A parse-failure message in `DIR lint` / `jcl-lint` output has non-printable characters replaced by `?` and is cut at 160 characters.

## Lint configuration and suppressions

`lint` (file or directory) and `jcl-lint` read the `[tool.jcl-parser.lint]` table of the nearest `pyproject.toml` that has one, looking from the linted path (stdin: the working directory) up through its parents; `--config TOML` names a file instead (a `pyproject.toml` contributes its table, any other file is the table itself). Keys: `select` / `ignore` (code lists), `severity` (table of code = `info` / `warning` / `error`), `critical-datasets` (JCL-LINT-003 patterns), `system-hlqs` (HLQs JCL-LINT-001 leaves alone, replacing the default list; a trailing `*` matches a prefix) and `fail-on`. An unknown key or bad value is exit 2 with `Error: ...`. On Python 3.10 reading TOML needs `tomli`. API: `jclparser.lint.load_lint_config()`, `find_lint_config()`, `lint_config_from_mapping()`.

A comment record `//* jcl-lint: disable=CODE[,CODE...]` suppresses those codes on the next statement (the next `//` record that is not a comment); `//* jcl-lint: disable-file=CODE,...` suppresses them in the whole file; `all` stands for every code. Codes are split on commas with or without blanks around them (`disable=JCL-LINT-001, JCL-LINT-002`); a blank after a code ends the list, and columns 73-80 are ignored. A `//*` record inside in-stream data (`DD *`, `DD DATA`, `DLM=`) is data and never a directive. Matching is by line number, so only the records of the linted file count (not an INCLUDE member's or a PROC's). API: `lint_job(job, config, source=text)`, `jclparser.lint.parse_suppressions()`.

## `jcl-lint`

`jcl-lint PATH...` (console script `jclparser.checks:lint_main`) lints any number of files and directories in one run, as pre-commit and CI need: `--format text|json|sarif` (same shapes as `DIR lint`), `--output/-o FILE`, `--glob` (directories), `--config`, `--fail-on`, `--select CODES` / `--ignore CODES` (comma-separated; `--ignore` adds to the config's), `--explode`, `--proc-path`. Exit 0 / 1 as for `lint`; 2 for an unusable config, a missing path, or a glob that matches nothing (so a misconfigured CI run cannot pass silently). The repository ships a pre-commit hook (`.pre-commit-hooks.yaml`, id `jcl-lint`) and a composite GitHub Action (`action.yml`: installs the action's own checkout into a venv, writes SARIF, uploads it with `github/codeql-action/upload-sarif`, fails on findings at `fail-on`, default `warning`).

## Flags

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON instead of text |
| `--format text\|json\|sarif` | The `cobol-parser` / `jcl-lint` spelling: `json` sets `--json`, `sarif` sets `--sarif` (`_apply_format`); `text` changes nothing. The old flags keep working |
| `--validate` | `validate_jcl(path, level="structure", proc_base_path=<--proc-path>)`; prints every finding (including `job.validate()` findings, #57), or `OK - no errors found.` when there are none. Exits 1 when a finding is an ERROR; a WARNING alone (a duplicate step name, a PROC not found) exits 0 unless `--fail-on warning` / `info` is given. With `--json`, `valid` is false only when an ERROR is reported. Without `--proc-path`, `JCL_PROCLIB_PATH` applies (#129) |
| `--explode` | Expand procedure calls (`job.explode()`) before displaying |
| `--proc-path PATH` | Base path for external PROC libraries and INCLUDE members (enables `enable_external_procs`); used by the parse and by `--validate`. Without it the parse runs with `enable_external_procs=False`, so no external PROC is loaded and `JCL_PROCLIB_PATH` is not read (unlike `--validate`). The parse already loads every PROC the job calls from it (`procs` lists them `[external]`, and a bundled template from `builtin_procs` `[builtin]`); when none is listed, `procs` notes which called PROCs were not found there, or that the job calls none |
| `--list-available` | With `procs`: list PROCs found under `--proc-path` (requires `--proc-path`) |
| `--lint-list` | List all registered lint rule codes + descriptions, then exit (no FILE required) |
| `--sarif` | With `lint` or `--validate` (file or directory): SARIF 2.1.0 instead of text |
| `--config TOML` | Lint configuration file (default: nearest `pyproject.toml` with `[tool.jcl-parser.lint]`) |
| `--fail-on info\|warning\|error` | Lowest severity that exits 1: for `lint` it overrides the config (default `info`); for `--validate` (file or directory) the default is `error` |
| `--glob PATTERN` | Directory mode only: the files of `DIR` to read (`Path.glob` pattern, default `*`; `'**/*.jcl'` recurses) |
| `--json-schema` | Print `JOB_JSON_SCHEMA`, the JSON Schema of the no-query `--json` document, then exit (no FILE required). The `--json` output of the `steps`, `procs`, step and DD queries uses the same `step` / `procedure` / `dd` shapes as the schema's `$defs` |
| `--profile` | Profile the parse. Text output is followed by a `Profiling:` block (wall clock, CPU when psutil is installed, peak memory, the `.prof` path, top functions); every `--json` view gains a `profiling` key, and a view whose JSON is a list (`steps`, a DD name) is wrapped as `{"result": [...], "profiling": {...}}` (#131). Peak memory is reset on entry, so it is the peak within the parse even when `tracemalloc` was already running |
| `--profile-top-n N` | Number of top functions in profiling output (default 20) |
| `--profile-output PATH` | Write raw cProfile binary to PATH (`.prof` file); requires `--profile` (usage error, exit 2, without it) |
| `--version` | Print `jcl-parser <__version__>` and exit |

`jcl-parser` has **no** `--strict` flag.

**Help and first-run behaviour.** `--help` prints the query words, examples,
exit codes and where defaults come from (`_HELP_EPILOG`); a bare `jcl-parser`
prints the same and exits 2. A query that names no step or DD keeps its
`No step or DD named 'X' found.` line (exit 1) and adds a hint from
`_not_found_hint`: a close query word (`stpes` → `Did you mean the query
'steps'?`) or close step/DD names (`STP1` → `Did you mean: STEP1?`); an
uppercase query tries names first, a lowercase one query words first.

# Citations

[1] [api/public-api.md](public-api.md) — importable Python API (Tier 1/2/3 tables)
[2] [core/parsing-pipeline.md](../core/parsing-pipeline.md) — what the CLI drives under the hood
