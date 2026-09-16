---
type: Invariants
title: Key Invariants
description: 19 non-obvious behaviors in jcl-parser that cause contributor bugs; read before touching any parsing code.
tags: [invariants, gotchas, development]
timestamp: 2026-09-16T00:00:00Z
---

# Overview

19 non-obvious behaviors that bite contributors. All are enforced by the codebase — these are things the tests won't tell you until you've already broken something.

# Invariants

1. **Column 71 is the continuation boundary; 72 is the indicator and 73-80 the sequence field.** `utils.normalize_jcl_line()` strips columns 72-80 from an 80-column record (and the trailing indicator from a 72-character record whose sequence field was already trimmed) *before* `ContinuationLineHandler` merges what is left. Never pass pre-stripped lines to `parse_jcl()` — keeping column 72 as content renames the next record's first operand (`SPACE=` became `XSPACE=`; fixed 2026-09-02).

2. **`ConditionalBlock.condition` (raw string) is authoritative.** `condition_ast` may be `None` if `parse_condition()` failed. Always read `condition` for display; use `condition_ast` only when traversing the AST.

3. **Inline PROCs always win.** Same-name external PROC or builtin template is ignored. No override possible.

4. **`&&` is an escaped ampersand in JCL.** Symbol substitution replaces `&NAME` → value and `&&` → `&`. `&&TEMP` in a DSN signals a temporary dataset — not double substitution.

5. **Dataset names are case-insensitive on z/OS but stored as-is.** Comparisons against DSN values must account for case variation.

6. **`parse_jcl()` does not expand PROCs.** A PROC invocation stays as a `Step` with `step.procedure` set and `step.is_procedure` true — there is no `exec_type` and no `is_proc_invocation` attribute on the model. Call `explode_job()` separately.

7. **`validate_jcl()` returns a flat `list[ParseError]`** — not a boolean, and **not** a `(Job, errors)` tuple. `errors = validate_jcl(source, level="structure")`; the list is empty when valid. It parses internally with `strict_mode=True` and throws the `Job` away, so call `parse_jcl()` separately if you need the model. `level` is a plain `str` (`"basic"` / `"structure"` / `"semantic"`): `ValidationLevel` is a plain `Enum`, not a `StrEnum`, so passing a member silently matches nothing and degrades to basic validation.

8. **`//` comment lines are dropped, not preserved.** There is no `job.statements` field and no `Statement(type="COMMENT")` anywhere in the model — `Job.comments`/`Step.comments`/`DDStatement.comments` all exist but are never populated. The one exception: a `//*ROUTE XEQ` JES3 control card is recognized and recorded in `job.jes_typed_statements` before the comment is dropped (`_job_builder.handle_comment_line`). Deliberate, not a gap — comments are documentation, not parsed content.

9. **JES control statements are parsed separately.** `/*JOBPARM`, `/*ROUTE`, etc. are in `jes_statements.py`, **not** in `job.steps`.

10. **SET symbols resolve left-to-right.** A SET can reference an earlier SET but not a later one.

11. **Vendoring is always manual.** Changes to `jclparser/` are not auto-propagated. Always run `rm -rf ../backend/_vendor/jcl-parser/jclparser && cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser` after changes — plain `cp -r` nests into `jclparser/jclparser/` and silently leaves stale files in place when the destination already exists (discovered 2026-07-24: it left the backend's vendored copy missing `_job_builder.py`/`_model_factories.py`/`_post_parse.py` for two PRs).

12. **`--version` reads from `jclparser.__version__`.** Update **both** `pyproject.toml:version` and `jclparser/__init__.py:__version__` together on release.

13. **Coverage must not drop below 90%.** `pytest` enforces `--cov-fail-under=90`. Add tests alongside any new module in the same commit.

14. **`builtin_procs.py` contains non-verbatim templates.** Built-in IBM utility PROCs are structural approximations for static analysis only — must not be submitted to a real mainframe.

15. **Every `_STATEMENT_TYPES` entry needs an explicit branch in `JobBuilder.handle_statement`.** `continuation_handler.JCL_KEYWORDS` is derived from `_STATEMENT_TYPES` for the same reason — a recognized type missing from either falls through silently: no dispatch (`SCHEDULE`, fixed 2026-07-24) or misclassified as a continuation and merged into the previous statement, corrupting it (`EXPORT`/`COMMAND`/`SCHEDULE`/`XMIT`/`THEN`/`NULL`, fixed 2026-07-24). `tests/unit/test_silent_drop_fixes.py::TestStatementDispatchCompleteness` guards the dispatch side structurally — it will fail the next time someone adds a type to `_STATEMENT_TYPES` without a matching branch.

16. **Known limitation: a nameless, indented statement using an operation keyword this parser doesn't recognize at all is ambiguous.** `ContinuationLineHandler` and `_statement_parser.parse_statement()` both use the same first-keyword heuristic (not true z/OS column-field parsing) to decide "continuation of the previous statement" vs. "a new statement of an unknown type" — for a genuinely unrecognized keyword there is no reliable way to tell, so it is either merged into the previous statement (corrupting it) or dropped, with no warning either way. This is *not* the same failure as a keyword this parser does support (see invariant 15, which is fully fixed) — it is inherent to the heuristic and would need real column-based parsing to close. Named statements with unrecognized keywords are unaffected (they always survive with a warning — see `TestDanglingCommaDoesNotSwallowNextStatement`).

17. **A statement's operand field ends at the first blank outside quotes and parens.** Everything
    after it is a comment field, and `_statement_parser.split_comment_field()` removes it *before*
    continuation merging. Parsing the comment as operands made `PGM=X    RUN THE THING` a program
    name, and a comment after a trailing comma hid the comma — silently dropping every continued
    operand of that statement. `IF`/`THEN`/`ELSE`/`ENDIF` are exempt (blank-delimited by syntax), and
    a blank after a comma still counts as inside the operands when a quoted string, `(` or
    `KEY=VALUE` follows. A removed comment containing `=` is reported on `job.warnings` rather than
    vanishing. Fixed 2026-09-02.

18. **Operation keywords are legal ddnames.** `//OUTPUT DD SYSOUT=*`, `//IF DD …`, `//SET DD …` are
    valid DD statements, not OUTPUT/IF/SET statements. The second token settles which field is
    which: if it is itself an operation keyword, the first token is a name. The same rule keeps a
    statement whose name field starts after column 3 (`//   STEP2 EXEC PGM=X`) from being folded
    into the statement before it. Fixed 2026-09-02.

19. **A JOB-less member parses.** A cataloged procedure or included member with no JOB card yields a
    `Job` with `name == ""` (empty string, never `None`) and its PROCs, SET/EXPORT/JCLLIB/INCLUDE/
    OUTPUT/IF content intact — those handlers no longer short-circuit on a missing job. A bare
    `EXEC` before any JOB card is still a `JCLSyntaxError`; it is the PROC/member shape that is
    supported. Fixed 2026-09-02.

# Citations

[1] [core/data-model.md](../core/data-model.md) — invariants 6, 8 (real field names)
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — invariants 3, 4, 6
[3] [advanced/validation.md](../advanced/validation.md) — invariants 7, 8
[4] [development/workflow.md](workflow.md) — invariants 11, 12, 13
[5] [../../tests/unit/test_silent_drop_fixes.py](../../tests/unit/test_silent_drop_fixes.py) — invariants 15, 16 and the silent-data-loss fix history generally
