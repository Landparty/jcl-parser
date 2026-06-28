---
type: Pipeline
title: JCL Parsing Pipeline
description: Seven-stage pipeline that transforms raw JCL text into a structured Job object; stages 1, 2, and 4 are mandatory.
tags: [parsing, pipeline, core]
timestamp: 2026-06-28T00:00:00Z
---

# Overview

`parse_jcl(source)` drives the pipeline. Stages 1, 2, and 4 always run. Stages 3, 5, 6, and 7 are optional or separate calls.

```
Input (string / file / IO)
  → [1] read_source()                     utils.py          — encoding fallback EBCDIC→UTF-8
  → [2] ContinuationLineHandler.process() continuation_handler.py — merges col-71 continuations
  → [3] resolve_includes()                include_loader.py [optional] — expands // INCLUDE
  → [4] parse_jcl() core loop             parser.py         — builds Job/Step/DD/Procedure objects
  → [5] ParameterParser                   parameter_ast.py  — typed param ASTs per statement
  → [6] validate_jcl()                    validators.py     [optional] — structural checks
  → [7] explode_job()                     explosion.py      [optional] — PROC + symbol expansion
  → Job object
```

# Key Behaviors

- `parse_jcl()` **never** expands PROCs — call `explode_job()` separately.
- Comment lines (`//`) become `Statement(type="COMMENT")` in `job.statements`; they are not dropped.
- JES control statements (`/*JOBPARM`, `/*ROUTE`) are handled in `jes_statements.py`, not in `job.steps`.
- `validate_jcl()` returns `(Job, list[ParseError])` — not a boolean. Always unpack.
- SET symbols resolve left-to-right; a SET cannot reference a later SET.
- Column 71 is the continuation column. Never pass pre-stripped lines.

# Quick Start

```python
import jclparser

job = jclparser.parse_jcl(source)      # stages 1–5 (no validation, no PROC expansion)
job, errors = jclparser.validate_jcl(source)   # stages 1–6
exploded = jclparser.explode_job(job)  # stage 7 (call separately)
```

# Citations

[1] [core/parsing-pipeline.md](parsing-pipeline.md) — full pipeline doc with per-stage notes
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — stage 7 detail
[3] [advanced/validation.md](../advanced/validation.md) — stage 6 detail
