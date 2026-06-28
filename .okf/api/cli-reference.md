---
type: concept
title: CLI Reference
description: jcl-parser CLI subcommands and usage
timestamp: 2026-06-28
tags: [cli, api, jcl-parser]
---

# CLI Reference

The `jcl-parser` CLI is the command-line interface for the `jclparser` package, installed as the `jcl-parser` entry point.

## Subcommands

| Subcommand | Purpose |
|------------|---------|
| `steps` | List all steps in a JCL job |
| `procs` | List PROC references (inline and external) |
| `detect` | Detect file type (JCL / PROC / unknown) |
| `metrics` | Emit job metrics (step count, DD count, symbol count) |
| `lint` | Run lint rules and emit SARIF output |
| `datasets` | List all dataset names referenced |
| `sql` | Detect embedded SQL statements |
| `analyze` | Full analysis: steps + datasets + metrics |
| `paths` | Emit dependency paths between steps |

## Usage

```bash
jcl-parser <subcommand> [options] <file>

# Examples
jcl-parser steps myjob.jcl
jcl-parser lint --format sarif myjob.jcl
jcl-parser detect unknown.txt
```

## Common Flags

| Flag | Description |
|------|-------------|
| `--proclib PATH` | Base path for external PROC library lookup |
| `--format {text,json,sarif}` | Output format (subcommand-specific) |
| `--strict` | Treat warnings as errors |

# Citations

[1] [api/public-api.md](public-api.md) — importable Python API (Tier 1/2/3 tables)
[2] [core/parsing-pipeline.md](../core/parsing-pipeline.md) — what the CLI drives under the hood
