---
type: Invariants
title: Key Invariants
description: 14 non-obvious behaviors in jcl-parser that cause contributor bugs; read before touching any parsing code.
tags: [invariants, gotchas, development]
timestamp: 2026-06-28T00:00:00Z
---

# Overview

14 non-obvious behaviors that bite contributors. All are enforced by the codebase — these are things the tests won't tell you until you've already broken something.

# Invariants

1. **Column 71 is the continuation column.** Never pass pre-stripped lines to `parse_jcl()`; `ContinuationLineHandler` enforces the col-71 rule before any parsing.

2. **`ConditionalBlock.condition` (raw string) is authoritative.** `condition_ast` may be `None` if `parse_condition()` failed. Always read `condition` for display; use `condition_ast` only when traversing the AST.

3. **Inline PROCs always win.** Same-name external PROC or builtin template is ignored. No override possible.

4. **`&&` is an escaped ampersand in JCL.** Symbol substitution replaces `&NAME` → value and `&&` → `&`. `&&TEMP` in a DSN signals a temporary dataset — not double substitution.

5. **Dataset names are case-insensitive on z/OS but stored as-is.** Comparisons against DSN values must account for case variation.

6. **`parse_jcl()` does not expand PROCs.** PROC invocations stay as `Step(exec_type="PROC")`. Call `explode_job()` separately.

7. **`validate_jcl()` returns `(Job, list)`, not a boolean.** Always unpack: `job, errors = validate_jcl(source)`. Check `ErrorSeverity.ERROR` items for hard failure.

8. **`//` comment lines are preserved.** They appear as `Statement(type="COMMENT")` in `job.statements`. Code that iterates `job.statements` must handle them.

9. **JES control statements are parsed separately.** `/*JOBPARM`, `/*ROUTE`, etc. are in `jes_statements.py`, **not** in `job.steps`.

10. **SET symbols resolve left-to-right.** A SET can reference an earlier SET but not a later one.

11. **Vendoring is always manual.** Changes to `jclparser/` are not auto-propagated. Always run `cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/` after changes.

12. **`--version` reads from `jclparser.__version__`.** Update **both** `pyproject.toml:version` and `jclparser/__init__.py:__version__` together on release.

13. **Coverage must not drop below 90%.** `pytest` enforces `--cov-fail-under=90`. Add tests alongside any new module in the same commit.

14. **`builtin_procs.py` contains non-verbatim templates.** Built-in IBM utility PROCs are structural approximations for static analysis only — must not be submitted to a real mainframe.

# Citations

[1] [development/invariants.md](invariants.md) — full invariant doc with code examples
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — invariants 3, 4, 6
[3] [advanced/validation.md](../advanced/validation.md) — invariants 7, 8
[4] [development/workflow.md](workflow.md) — invariants 11, 12, 13
