---
title: CLI Reference
updated: 2026-06-27
sources: LegacyLens team, 2026-06-27
---

# CLI Reference

The `jcl-parser` CLI is defined in `jclparser/cli.py` (936 lines) and registered via `jclparser.cli:main`.

```bash
jcl-parser FILE [SUBCOMMAND] [FLAGS]
# or
python -m jclparser FILE [SUBCOMMAND] [FLAGS]
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `steps` | List all job steps (name, program/PROC, line number) |
| `procs` | List PROCs referenced by the job |
| `detect` | Detect file type: JCL, PROC, or unknown |
| `metrics` | Structural metrics: step count, nesting depth, cyclomatic score, fan-in/out |
| `lint` | Run all registered lint rules; output findings |
| `datasets` | Dataset lifecycle report: create/open/dispose events across steps |
| `sql` | SQL/DB2 usage report: steps and DDs touching DB2 programs |
| `analyze` | Program profile analysis: match steps to known z/OS utility profiles |
| `paths` | Return-code feasibility paths from condition logic |

## Flags

| Flag | Description |
|------|-------------|
| `--validate` | Run structural validation and report errors |
| `--json` | Output in JSON format (all subcommands support this) |
| `--explode` | Expand PROCs before running the subcommand |
| `--proc-path PATH` | Base path for external PROC filesystems |
| `--profile` | Emit parse profiling data (timing per stage) |
| `--version` | Print `jclparser.__version__` and exit |

## Examples

```bash
# List steps
jcl-parser MYJOB.jcl steps

# Validate and show errors as JSON
jcl-parser MYJOB.jcl --validate --json

# Run lint rules
jcl-parser MYJOB.jcl lint

# Metrics report
jcl-parser MYJOB.jcl metrics

# PROC expansion + step listing
jcl-parser MYJOB.jcl steps --explode --proc-path /procs

# Dataset lifecycle
jcl-parser MYJOB.jcl datasets

# SQL/DB2 usage
jcl-parser MYJOB.jcl sql

# Detect whether a file is JCL or a PROC
jcl-parser MYFILE.jcl detect

# Return-code feasibility paths
jcl-parser MYJOB.jcl paths
```

## Version Behavior

`--version` reads from `jclparser.__version__` (not package metadata). When bumping the release, update both `jclparser/__init__.py:__version__` and `pyproject.toml:version` together.

## Implementation Notes

- The CLI uses `argparse` with subparsers. Each subcommand is a handler function in `cli.py`.
- To add a new subcommand: add an `argparse` subparser and handler function in `cli.py`.
- `--profile` emits per-stage parse timing; the profiling is implemented in `jclparser/profiling.py`.

## See Also

- [public-api.md](public-api.md) — Python API equivalents for each subcommand
- [../development/development-workflow.md](../development/development-workflow.md) — install and run commands
- [../advanced/proc-expansion.md](../advanced/proc-expansion.md) — `--explode` and `--proc-path` detail
