---
type: Pipeline
title: JCL Parsing Pipeline
description: Seven-stage pipeline that transforms raw JCL text into a structured Job object; stages 1, 3, 4, and 5 always run.
tags: [parsing, pipeline, core]
timestamp: 2026-10-29T00:00:00Z
---

# Overview

`parse_jcl(source)` drives the pipeline. Stages 1, 3, 4, and 5 always run (stage 5 inside stage 4). Stage 2 runs only when the source has an `// INCLUDE`; stages 6 and 7 are separate calls.

```
Input (string / file / IO)
  → [1] read_source()                     utils.py          — a str is always content, a Path is read, a file-like is read(); file reads try utf-8 (BOM dropped) → cp1252 → latin-1
  → [2] resolve_includes_with_origins()   include_loader.py [optional] — expands // INCLUDE (parser._expand_includes), before continuation merging so member records are merged too
  → [3] ContinuationLineHandler.merge_continuation_lines() continuation_handler.py — merges col-71 continuations (called from _source_scanner._merge_source_lines)
  → [4] parse_jcl() core loop             parser.py         — orchestrates; the source pre-scan lives in _source_scanner.py, statement-line parsing lives in _statement_parser.py, model assembly in _job_builder.py (JobBuilder) + _model_factories.py, post-parse passes in _post_parse.py
  → [5] ParameterParser                   parameter_ast.py  — splits each statement's operands (from _statement_parser, during stage 4); typed DCB/SPACE ASTs are built lazily by dd.dcb / dd.space
  → [6] validate_jcl()                    parser.py → validators.py [optional] — structural checks
  → [7] explode_job()                     explosion.py      [optional] — PROC + symbol expansion
  → Job object
```

# Key Behaviors

- `parse_jcl()` **never** expands PROCs — call `explode_job()` separately.
- **A `str` source is always JCL text, never a file name** (`utils._read_source_raw`). `parse_jcl("job.jcl")` parses the five characters `job.jcl`; to read a file pass `pathlib.Path("job.jcl")` (a missing `Path` raises `FileNotFoundError`) or an open file object. Guessing (a one-line string that names an existing file) would let uploaded text such as `/etc/passwd` read a server file. Applies to everything that calls `read_source`: `parse_jcl`, `validate_jcl`, `detect_file_type`. A leading UTF-8 BOM is stripped from the content.
- **JES3 `//*DATASET` data** (#162): under `standard` and `jes3`, `_merge_source_lines(content, dialect)` marks the records after `//*DATASET` up to `//*ENDDATASET` (or the record starting with its `END=` terminator) as `ScannedSource.jes3_data_indices`; the parse loop hands them to `JobBuilder.handle_jes3_data`, which appends them to that statement's `Jes3ControlStatement.data` (the `END=` terminator record is not kept). They never open an implicit SYSIN and are never parsed or validated as JCL; `resolve_includes` leaves an INCLUDE among them alone. With no terminator the data runs to the end of the source and `Line N: //*DATASET has no matching //*ENDDATASET; ...` is warned. Under `jes2` `//*` is only a comment, as before.
- In-stream data opens only on `DD *` / `DD DATA`: `utils.instream_delimiter(parameters)` is the one rule both the source pre-scan (`_merge_source_lines`) and `JobBuilder` use, so a `DLM=` on any other DD (or inside a quoted `PATH=`) never opens data.
- **XMIT data is skipped, not parsed** (#117). The records after `//name XMIT` and JES2 `/*XMIT node` are a job stream for another node: they end at `/*` or the statement's `DLM=` value, never at a `//` record. The pre-scan (`_source_scanner._RecordClassifier`, `utils.is_jes_xmit`) and `JobBuilder._start_transmitted_data` share the rule (`utils.xmit_delimiter`, `utils.jes_xmit_delimiter`), so transmitted records are neither continuation-merged nor parsed (a remote `JOB` card is not a second JOB statement).
- A `//*` comment (or blank) record between the records of a continued statement is handed to the parse loop *before* that merged statement (`_merge_source_lines`), so a continued `DD *,` / `DD DATA,` … `DLM=` never reads it as its first data record or ends its data at it (#58).
- **Records break on `\n`, `\r\n` and `\r` only** — `utils.split_source_lines()` is the one splitter for source text and in-stream data (parser pre-scan, `validate_jcl`, JCLLIB/strict-DD pre-scans, `resolve_includes` via `keepends=True`, file-type detection, SQL-in-SYSIN scan, CLI data dump). Never use `str.splitlines()` on source: it also breaks on form feed, VT, `\x1c`-`\x1e`, NEL and U+2028/9, which would split a data record and shift every later line number (#62). File decoding tries cp1252 before latin-1 because latin-1 never fails (a Windows-1252 `\x85` ellipsis was read as NEL).
- Unterminated blocks are reported, not silent (#59): an in-stream `PROC` with no `PEND` in a job that has a JOB card adds `Line N: PROC <name> has no PEND; the statements after it were read as part of the procedure` to `job.warnings` (a JOB-less cataloged PROC member needs no PEND and stays silent). End of input still closes in-stream data, silently — unless the unclosed block's records include a `//name EXEC` record, which gets a "was never closed by its delimiter … swallowed JCL statements such as …" warning (`JobBuilder._unclosed_data_warning`).
- **`PEND` closes the PROC scope** (#102): an `IF` opened inside an in-stream `PROC`…`PEND` body and never closed by `ENDIF` stays attached to the procedure, is closed at `PEND`, and adds `Line N: IF block in PROC <name> has no matching ENDIF; closed at PEND (line M)` to `job.warnings` (instead of the end-of-job "no matching ENDIF" warning), so later job steps are not read into that IF. Conversely an `IF` the job opened *before* the `PROC` statement is not visible inside the body: the PROC's steps go to the procedure, and a `THEN`/`ELSE`/`ENDIF` in the body with no IF of its own is warned and ignored (`JobBuilder._innermost_if`).
- **Job-level DDs before the first step** (`SYSCHK`, `JOBCAT`, any DD other than `JOBLIB` and its concatenation, which go to `job.joblib_dds`) are attached to the first *job-level* `EXEC` — never to a step of an in-stream `PROC`…`PEND` defined in between, which would copy them into every expansion of that PROC (#103). A DD inside a PROC body before the procedure's first `EXEC` attaches to that procedure step; with no step before `PEND` it is discarded with a `PROC <name> has DD statement(s) but no EXEC step …` warning.
- External PROC and INCLUDE libraries are read only from `proc_base_path` or `JCL_PROCLIB_PATH`; with neither, the JCLLIB loaders read nothing (the cwd is never searched), and a member over `utils.MAX_LIBRARY_MEMBER_BYTES` (4 MiB) is refused with a warning.
- Comment lines (`//*`) are **dropped** — there is no `job.statements` field and no
  `Statement(type="COMMENT")` in the model. The one exception is a JES3 `//*COMMAND`
  control card (`//*MAIN`, `//*ROUTE XEQ`, …), recorded in `job.jes_typed_statements` / `job.jes_statements`. See
  [development/invariants.md](../development/invariants.md) #8.
- JES control statements (`/*JOBPARM`, `/*ROUTE`) are handled in `jes_statements.py`, not in `job.steps`.
- `validate_jcl(source, level=None, config=None, *, proc_base_path=None, enable_external_procs=True)`
  returns a **flat `list[ParseError]`** (empty when
  valid) — not a boolean and not a `(Job, errors)` tuple. It parses with
  `strict_mode=True` internally (minus the strict `job.validate()` raise; it reports
  those findings itself) and discards the `Job`; parse the source separately if
  you need both. `level` is a `ValidationLevel` or its string — `"basic"` (syntax only), `"structure"`,
  or `"semantic"` — defaulting to `config.validation_level`, else `"basic"`.
- SET symbols resolve left-to-right: a SET that redefines a symbol affects only the statements after it (`Step.set_symbols`). A reference to a symbol whose *first* SET comes later still resolves against the job's final SET table in the post-parse pass (`SET A=&B.X` then `SET B=1` gives `PARM='&A'` → `1X`), while `job.set_statements` keeps `A` as coded. See [development/invariants](../development/invariants.md) #10.
- The post-parse SET pass resolves `DD DSN=`/`DISP=`, EXEC parameters (`PARM=`), and `Step.program` / `Step.procedure` (`EXEC PGM=&NAME`, `EXEC &PROC`), including steps nested in `IF`/`ELSE`; a symbol it cannot resolve is left as written in `program`/`procedure`.
- `resolve_includes()` never expands an `// INCLUDE` record that sits inside in-stream data (`DD DATA` / `DLM=`) or a CNTL block — it locates those records with the parser's own `_merge_source_lines` scan. The JCLLIB pre-scan (`_extract_jcllib_order`) drops quotes around a library name (`ORDER=('MY.PROCLIB')`), as the main parse does.
- **Line numbers are reported against the main source, not the INCLUDE-expanded text** (#118). `parser._expand_includes` uses `resolve_includes_with_origins` and keeps an `_include_origins.IncludeLineMap`; the scan and the parse loop still run on the expanded text (in-stream / CNTL indices stay consistent), and the translation is applied in one place at the end of `_parse_jcl_core`: `IncludeLineMap.relabel_job()` rewrites `line_number` on every model object of the job (steps, DDs, overrides, IF blocks, in-stream PROCs, OUTPUT / CNTL statements; external and built-in PROCs keep their own member's numbers), `job.unresolved_output_refs` and the `Line N` prefix of `job.warnings`; `relabel_error()` does the same for the `JCLParseError` that ends a parse. A line from the main source keeps its own number; a line read from a member gets the line of the outermost `// INCLUDE` in the main source, and its message names the innermost member and the line within it: `Line 2 (INCLUDE member COMMON, line 3): ...` (`JCLParseError.include_note`; `validate_jcl` appends `(INCLUDE member COMMON, line 3)` to the `ParseError.message`). `job.validate()` findings carry the translated line but no member note.
- In-stream data records are not normalized: `inline_data` keeps columns 72-80 and tabs; an 80-column card image is kept whole, any other record loses its trailing blanks (issue #115). Control-statement readers use `utils.control_card_text()`, which cuts card images to columns 1-71.
- Column 71 is the continuation column. Never pass pre-stripped lines. A quoted string continued from an 80-column card image (non-blank column 72) keeps its blanks through column 71 and resumes in column 16 (see [development/invariants](../development/invariants.md) #1).
- **JCL has no backslash escape.** Inside a quoted string the only escape is a doubled apostrophe (`''`); `ContinuationLineHandler._analyze_line_context` treats `\` as ordinary text, so `// SET DIR='C:\'` closes its string and the next `// SET` stays a statement of its own (#122).
- Stage 4 is split across six modules: `parser.py` holds the public API (`parse_jcl`, `validate_jcl`, `parse_statement` re-export) and the core loop; `_source_scanner.py` holds the pre-scan (`_merge_source_lines`: in-stream / CNTL record classification, continuation merge); `_statement_parser.py` holds single-line statement/parameter parsing; `_job_builder.py` holds `JobBuilder` (the per-statement-type dispatch state machine); `_model_factories.py` holds the `Statement -> Job/Step/DDStatement` factories and SET-value helpers; `_post_parse.py` holds the post-parse passes (external PROC loading, `OUTPUT=*.name` refs, SET substitution, strict DD structure). All historical `jclparser.parser` and `jclparser._job_builder` imports still work via re-exports.

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
