# Design: Extend INFO/DEBUG logging across the parse pipeline

**Date:** 2026-06-26
**Status:** Approved (pending user spec review)

## Goal

Add more diagnostic logging to `jclparser` at INFO and DEBUG levels so users who
enable logging can see what the parser is doing — without changing any parsing
behavior, adding dependencies, or producing output when logging is unconfigured.

## Background

The library already follows the standard library-logging convention:

- Each module that logs does `logger = logging.getLogger(__name__)`.
- `__init__.py` attaches a `logging.NullHandler` to the `jclparser` package
  logger, so applications that do not configure logging see nothing.
- Today only `jcl_file_type.py` (DEBUG) and `proc_loader.py` (WARNING) actually
  emit anything.

This work extends that existing pattern to the core parse pipeline, PROC/INCLUDE
resolution, and validation. The CLI is intentionally out of scope.

## Principles (non-negotiable)

1. **Match the existing convention.** `logger = logging.getLogger(__name__)` at
   module top; rely on the package `NullHandler` for silence-by-default.
2. **Lazy `%`-style formatting only** — `logger.debug("...%s", x)`, never
   f-strings or string concatenation, so disabled-level calls are cheap.
3. **No behavior change.** Logging is purely additive; no control flow, return
   values, or exceptions change.
4. **Terse, guarded hot-loop DEBUG.** At most one DEBUG line per statement in
   per-statement loops. Guard any message whose *argument* computation is
   non-trivial with `if logger.isEnabledFor(logging.DEBUG):`. Bare
   `logger.debug("literal", cheap_arg)` calls need no guard.
5. **INFO is sparse, DEBUG is rich.** INFO = a few high-level milestones per
   operation. DEBUG = detailed per-statement / per-symbol tracing.

## Scope

### 1. Core parse pipeline

**`parser.py` (`_parse_jcl_core`)**
- INFO on successful parse: `parsed job %s: %d steps, %d DD statements`.
  - Separate INFO when a PROC-only file (no JOB) is parsed.
- DEBUG: INCLUDE expansion triggered (count of members expanded); inline-data
  block detected; post-loop passes starting (SET symbol resolution, external
  PROC loading, strict-mode validation).
- DEBUG on notable parse decisions: `UNKNOWN` statement type encountered
  (currently a silent `pass` near line 526 — convert to a DEBUG log).

**`continuation_handler.py`**
- DEBUG, only when a merge actually happened:
  `merged %d continuation lines into statement at line %d`.

**`parameter_ast.py`**
- DEBUG, terse: one line per parameter-string parse with the resulting count.
  Guard with `isEnabledFor` if building the message is non-trivial.

### 2. PROC/INCLUDE resolution

**`explosion.py`**
- INFO: `exploded job %s: %d steps expanded`.
- DEBUG: each PROC expansion entered (name, depth); symbol substitutions
  (`resolved &%s -> %s`); circular-reference and depth-limit detection.

**`proc_loader.py`** (already logs WARNING)
- DEBUG: which loader resolved a PROC and from where; lookup misses before the
  fallback loader runs.

**`include_loader.py`**
- DEBUG: member resolved from which library. No INFO.

### 3. Validation

**`validators.py`**
- DEBUG: which job is being validated (`validate_job_structure` entry) and a
  count of findings on exit. No INFO (validation output is itself diagnostic).

**`parameter_validators.py`** — *intentionally not logged.* Its only entry points
are per-parameter `validate` classmethods (DISP, dataset name) invoked in the hot
path. Per the "terse, guarded" decision, adding DEBUG there would flood the log
without adding signal beyond the `validators.py` validation-level trace, so it is
left quiet.

## Out of scope

- CLI logging (`cli.py`).
- Any change to parsing/validation behavior.
- New dependencies, handlers, or logging configuration.
- Syncing into `backend/_vendor/jcl-parser/` (done separately by the user).

## Testing

Add `tests/unit/test_logging.py` using pytest's `caplog`:

1. A normal `parse_jcl` of a simple job emits the INFO summary record.
2. With the `jclparser` logger at DEBUG, a job with continuation lines and a PROC
   with symbols emits the expected DEBUG records (continuation merge, symbol
   substitution).
3. With default configuration (no handler configured by the test), the library
   does not emit output above the caller-set level — i.e. INFO-level capture
   shows no DEBUG records leaking.

Tests assert on logger name and level via `caplog.record_tuples`, keeping them
robust to exact message wording where reasonable. Coverage stays at/above the
enforced 90% gate.

## Verification

- `pytest` passes (incl. new logging tests) with coverage >= 90%.
- `pytest -m performance` benchmarks show no meaningful regression (terse,
  guarded DEBUG; lazy formatting).
- `ruff check .` and `ruff format .` clean.
