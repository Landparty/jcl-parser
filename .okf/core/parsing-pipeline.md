---
type: Pipeline
title: JCL Parsing Pipeline
description: Seven-stage pipeline that transforms raw JCL text into a structured Job object; stages 1, 2, and 4 are mandatory.
tags: [parsing, pipeline, core]
timestamp: 2026-10-04T00:00:00Z
---

# Overview

`parse_jcl(source)` drives the pipeline. Stages 1, 2, and 4 always run. Stages 3, 5, 6, and 7 are optional or separate calls.

```
Input (string / file / IO)
  → [1] read_source()                     utils.py          — a str is always content, a Path is read, a file-like is read(); file reads try utf-8 (BOM dropped) → latin-1 → cp1252
  → [2] ContinuationLineHandler.process() continuation_handler.py — merges col-71 continuations
  → [3] resolve_includes()                include_loader.py [optional] — expands // INCLUDE
  → [4] parse_jcl() core loop             parser.py         — orchestrates; statement-line parsing lives in _statement_parser.py, model assembly in _job_builder.py (JobBuilder) + _model_factories.py, post-parse passes in _post_parse.py
  → [5] ParameterParser                   parameter_ast.py  — typed param ASTs per statement
  → [6] validate_jcl()                    validators.py     [optional] — structural checks
  → [7] explode_job()                     explosion.py      [optional] — PROC + symbol expansion
  → Job object
```

# Key Behaviors

- `parse_jcl()` **never** expands PROCs — call `explode_job()` separately.
- **A `str` source is always JCL text, never a file name** (breaking change 2026-10-03, `utils._read_source_raw`). `parse_jcl("job.jcl")` parses the five characters `job.jcl`; to read a file pass `pathlib.Path("job.jcl")` (a missing `Path` raises `FileNotFoundError`) or an open file object. The old guess (one line ending in `.jcl`, containing a slash, or naming an existing file) let uploaded text such as `/etc/passwd` read a server file. Applies to everything that calls `read_source`: `parse_jcl`, `validate_jcl`, `detect_file_type`. A leading UTF-8 BOM is stripped from the content.
- In-stream data opens only on `DD *` / `DD DATA`: `utils.instream_delimiter(parameters)` is the one rule both the source pre-scan (`_merge_source_lines`) and `JobBuilder` use, so a `DLM=` on any other DD (or inside a quoted `PATH=`) no longer swallows the rest of the job (fixed 2026-10-03).
- External PROC and INCLUDE libraries are read only from `proc_base_path` or `JCL_PROCLIB_PATH`; with neither, the JCLLIB loaders read nothing (the cwd is never searched), and a member over `utils.MAX_LIBRARY_MEMBER_BYTES` (4 MiB) is refused with a warning (since 2026-10-03).
- Comment lines (`//*`) are **dropped** — there is no `job.statements` field and no
  `Statement(type="COMMENT")` in the model. The one exception is a JES3 `//*ROUTE XEQ`
  card, recorded in `job.jes_typed_statements` before the comment is discarded. See
  [development/invariants.md](../development/invariants.md) #8.
- JES control statements (`/*JOBPARM`, `/*ROUTE`) are handled in `jes_statements.py`, not in `job.steps`.
- `validate_jcl(source, level="basic")` returns a **flat `list[ParseError]`** (empty when
  valid) — not a boolean and not a `(Job, errors)` tuple. It parses with
  `strict_mode=True` internally and discards the `Job`; parse the source separately if
  you need both. `level` is a plain string — `"basic"` (syntax only), `"structure"`,
  or `"semantic"`.
- SET symbols resolve left-to-right; a SET cannot reference a later SET.
- The post-parse SET pass resolves `DD DSN=`/`DISP=`, EXEC parameters (`PARM=`), and `Step.program` / `Step.procedure` (`EXEC PGM=&NAME`, `EXEC &PROC`), including steps nested in `IF`/`ELSE`; a symbol it cannot resolve is left as written in `program`/`procedure`.
- `resolve_includes()` never expands an `// INCLUDE` record that sits inside in-stream data (`DD DATA` / `DLM=`) or a CNTL block — it locates those records with the parser's own `_merge_source_lines` scan. The JCLLIB pre-scan (`_extract_jcllib_order`) drops quotes around a library name (`ORDER=('MY.PROCLIB')`), as the main parse does.
- Column 71 is the continuation column. Never pass pre-stripped lines.
- Stage 4 is split across five modules (behavior unchanged, layout only): `parser.py` holds the public API (`parse_jcl`, `validate_jcl`, `parse_statement` re-export) and the core loop; `_statement_parser.py` holds single-line statement/parameter parsing; `_job_builder.py` holds `JobBuilder` (the per-statement-type dispatch state machine); `_model_factories.py` holds the `Statement -> Job/Step/DDStatement` factories and SET-value helpers; `_post_parse.py` holds the post-parse passes (external PROC loading, `OUTPUT=*.name` refs, SET substitution, strict DD structure). All historical `jclparser.parser` and `jclparser._job_builder` imports still work via re-exports.

# Quick Start

```python
import jclparser

job = jclparser.parse_jcl(source)  # stages 1–5 (no validation, no PROC expansion)
errors = jclparser.validate_jcl(source, level="structure")  # stage 6, list[ParseError]
exploded = jclparser.explode_job(job)  # stage 7 (call separately)
```

# Citations

[1] [core/data-model.md](data-model.md) — the Job object this pipeline produces
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — stage 7 detail
[3] [advanced/validation.md](../advanced/validation.md) — stage 6 detail
