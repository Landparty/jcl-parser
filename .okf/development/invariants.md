---
type: Invariants
title: Key Invariants
description: 16 non-obvious behaviors in jcl-parser that cause contributor bugs; read before touching any parsing code.
tags: [invariants, gotchas, development]
timestamp: 2026-07-24T12:00:00Z
---

# Overview

16 non-obvious behaviors that bite contributors. All are enforced by the codebase — these are things the tests won't tell you until you've already broken something.

# Invariants

1. **Column 71 is the continuation column.** Never pass pre-stripped lines to `parse_jcl()`; `ContinuationLineHandler` enforces the col-71 rule before any parsing.

2. **`ConditionalBlock.condition` (raw string) is authoritative.** `condition_ast` may be `None` if `parse_condition()` failed. Always read `condition` for display; use `condition_ast` only when traversing the AST.

3. **Inline PROCs always win.** Same-name external PROC or builtin template is ignored. No override possible.

4. **`&&` is an escaped ampersand in JCL.** Symbol substitution replaces `&NAME` → value and `&&` → `&`. `&&TEMP` in a DSN signals a temporary dataset — not double substitution.

5. **Dataset names are case-insensitive on z/OS but stored as-is.** Comparisons against DSN values must account for case variation.

6. **`parse_jcl()` does not expand PROCs.** PROC invocations stay as `Step(exec_type="PROC")`. Call `explode_job()` separately.

7. **`validate_jcl()` returns `(Job, list)`, not a boolean.** Always unpack: `job, errors = validate_jcl(source)`. Check `ErrorSeverity.ERROR` items for hard failure.

8. **`//` comment lines are dropped, not preserved.** There is no `job.statements` field and no `Statement(type="COMMENT")` anywhere in the model — `Job.comments`/`Step.comments`/`DDStatement.comments` all exist but are never populated. The one exception: a `//*ROUTE XEQ` JES3 control card is recognized and recorded in `job.jes_typed_statements` before the comment is dropped (`_job_builder.handle_comment_line`). Deliberate, not a gap — comments are documentation, not parsed content.

9. **JES control statements are parsed separately.** `/*JOBPARM`, `/*ROUTE`, etc. are in `jes_statements.py`, **not** in `job.steps`.

10. **SET symbols resolve left-to-right.** A SET can reference an earlier SET but not a later one.

11. **Vendoring is always manual.** Changes to `jclparser/` are not auto-propagated. Always run `rm -rf ../backend/_vendor/jcl-parser/jclparser && cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser` after changes — plain `cp -r` nests into `jclparser/jclparser/` and silently leaves stale files in place when the destination already exists (discovered 2026-07-24: it left the backend's vendored copy missing `_job_builder.py`/`_model_factories.py`/`_post_parse.py` for two PRs).

12. **`--version` reads from `jclparser.__version__`.** Update **both** `pyproject.toml:version` and `jclparser/__init__.py:__version__` together on release.

13. **Coverage must not drop below 90%.** `pytest` enforces `--cov-fail-under=90`. Add tests alongside any new module in the same commit.

14. **`builtin_procs.py` contains non-verbatim templates.** Built-in IBM utility PROCs are structural approximations for static analysis only — must not be submitted to a real mainframe.

15. **Every `_STATEMENT_TYPES` entry needs an explicit branch in `JobBuilder.handle_statement`.** `continuation_handler.JCL_KEYWORDS` is derived from `_STATEMENT_TYPES` for the same reason — a recognized type missing from either falls through silently: no dispatch (`SCHEDULE`, fixed 2026-07-24) or misclassified as a continuation and merged into the previous statement, corrupting it (`EXPORT`/`COMMAND`/`SCHEDULE`/`XMIT`/`THEN`/`NULL`, fixed 2026-07-24). `tests/unit/test_silent_drop_fixes.py::TestStatementDispatchCompleteness` guards the dispatch side structurally — it will fail the next time someone adds a type to `_STATEMENT_TYPES` without a matching branch.

16. **Known limitation: a nameless, indented statement using an operation keyword this parser doesn't recognize at all is ambiguous.** `ContinuationLineHandler` and `_statement_parser.parse_statement()` both use the same first-keyword heuristic (not true z/OS column-field parsing) to decide "continuation of the previous statement" vs. "a new statement of an unknown type" — for a genuinely unrecognized keyword there is no reliable way to tell, so it is either merged into the previous statement (corrupting it) or dropped, with no warning either way. This is *not* the same failure as a keyword this parser does support (see invariant 15, which is fully fixed) — it is inherent to the heuristic and would need real column-based parsing to close. Named statements with unrecognized keywords are unaffected (they always survive with a warning — see `TestDanglingCommaDoesNotSwallowNextStatement`).

# Citations

[1] [development/invariants.md](invariants.md) — full invariant doc with code examples
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — invariants 3, 4, 6
[3] [advanced/validation.md](../advanced/validation.md) — invariants 7, 8
[4] [development/workflow.md](workflow.md) — invariants 11, 12, 13
[5] [../../tests/unit/test_silent_drop_fixes.py](../../tests/unit/test_silent_drop_fixes.py) — invariants 15, 16 and the silent-data-loss fix history generally
