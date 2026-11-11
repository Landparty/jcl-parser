---
type: Invariants
title: Key Invariants
description: 20 non-obvious behaviors in jcl-parser that cause contributor bugs; read before touching any parsing code.
tags: [invariants, gotchas, development]
timestamp: 2026-10-29T00:00:00Z
---

# Overview

20 non-obvious behaviors that bite contributors. The codebase enforces all of them, but the tests only tell you after you have broken one. Each entry says what the rule is and, briefly, what goes wrong without it; the history of each fix is in [log](../log.md).

# Invariants

1. **Column 71 is the continuation boundary; 72 is the indicator and 73-80 the sequence field.**
   - `utils.normalize_jcl_line()` strips columns 72-80 from an 80-column record *before* `ContinuationLineHandler` merges what is left. Never pass pre-stripped lines to `parse_jcl()`: column 72 kept as content renames the next record's first operand (`SPACE=` becomes `XSPACE=`).
   - A record with text past column 80 (`utils.is_overlong_record()`) cannot be a card image: it is read whole, never cut at column 71, and a statement record of that kind is a WARNING on `Job.statement_findings`. A record of 80 columns plus trailing blanks is still a card image.
   - A 72-character `//` record whose sequence field was already trimmed loses its trailing indicator when column 71 is blank, or when column 71 leaves the operand open (trailing comma, unclosed quote) and the next record is a `//` continuation with a blank name field (#80). Callers use `utils.normalize_jcl_lines()` for that lookahead; any other 72-character editor line keeps its last character.
   - A quoted string continued from a *card image* (non-blank column 72, `utils.is_continued_card_image()`) runs through column 71 and resumes in column 16, so the blanks on both sides of the break are value text. `_merge_source_lines` / `validate_jcl` pass those record indices to `merge_continuation_lines(card_images=)`, which pads the previous record to 71 columns and takes the continuation from column 16 as written (#65). Short editor-style lines keep the blank-dropping join, and a continuation whose text starts before column 16 is left-stripped.
   - **In-stream data is exempt** (#115): `DD *` / `DD DATA` records reach `DDStatement.inline_data` as coded, columns 72-80 and tabs kept; `_merge_source_lines` weaves the raw record in for every index in `inline_data_indices` (CNTL control records stay normalized). A card image (exactly 80 columns, `utils.is_card_image()`) is kept whole, trailing blanks included; any other record has its trailing blanks trimmed, so 80 columns is what tells a card from a 72-79 character editor line.
   - Code that reads in-stream *control statements* (program profiles, SQL detection) cuts a card image to columns 1-71 with `utils.control_card_text()` and takes any other record whole; `program_profiles/_control.py` (SORT, IEBCOPY; `_sysin_text(step, card_images=True)`) applies the same rule and also reads the column-72 continuation.

2. **`ConditionalBlock.condition` (raw string) is authoritative.** `condition_ast` may be `None` if `parse_condition()` failed. Always read `condition` for display; use `condition_ast` only when traversing the AST.

3. **Inline PROCs always win.** A same-name external PROC or builtin template is ignored. No override is possible.

4. **`&&` is an escaped ampersand in JCL, except in a dataset name.** Symbol substitution replaces `&NAME` → value and `&&` → `&`, including an `&&` inside a symbol's value, collapsed once after the value's own nested symbols are resolved (#127). In a DSN (`DDStatement.dataset_name` and the `DSN` / `DSNAME` parameters) `&&TEMP` is a temporary dataset, so `substitute_dd_statement` always keeps the `&&` there, including during `explode_job()`, and `is_temporary()` stays true. A DSN that is one bare single-`&` name with no symbol of that name (`DSN=&TEMP`, the single-ampersand temporary spelling) is kept as written rather than blanked, unless `strict_symbols=True` (`is_temporary()` still keys on `&&`). Symbolic parameter values on a PROC call keep `&&` too (`TMP='&&WORK'` feeds a DSN); EXEC keyword override values collapse it.

5. **Dataset names are case-insensitive on z/OS but stored as-is.** Comparisons against DSN values must account for case.

6. **`parse_jcl()` does not expand PROCs.** A PROC invocation stays a `Step` with `step.procedure` set and `step.is_procedure` true. There is no `exec_type` and no `is_proc_invocation` attribute on the model. Call `explode_job()` separately.

7. **`validate_jcl()` returns a flat `list[ParseError]`**, not a boolean and **not** a `(Job, errors)` tuple: `errors = validate_jcl(source, level="structure")`, empty when valid. It parses internally with `strict_mode=True` minus the strict `job.validate()` raise (`_parse_jcl_core(validate_job=False)`; it reports those findings itself, #57) and throws the `Job` away, so call `parse_jcl()` separately if you need the model. `level` is a `ValidationLevel` or its string (`"basic"` / `"structure"` / `"semantic"`), defaulting to `config.validation_level`, else `"basic"`; an unknown level raises `ValueError`.

8. **`//*` comment lines are dropped, not preserved.** There is no `job.statements` field and no `Statement(type="COMMENT")`; `Job.comments` / `Step.comments` / `DDStatement.comments` exist but are never populated. The one exception: a JES3 `//*COMMAND` control card (`//*MAIN`, `//*FORMAT`, `//*ROUTE XEQ`, …, `jes_statements.JES3_COMMANDS`, command starting in column 4) is recorded in `job.jes_typed_statements` and `job.jes_statements` (`_job_builder.handle_comment_line`; not under the `jes2` dialect). This is deliberate: comments are documentation, not parsed content.

9. **JES control statements are parsed separately.** `/*JOBPARM`, `/*ROUTE`, etc. are in `jes_statements.py`, **not** in `job.steps`.

10. **SET symbols resolve left-to-right.**
    - A SET can reference an earlier SET. A SET that redefines a symbol affects only the statements after it: steps read before the redefinition carry a `Step.set_symbols` snapshot that `resolve_set_symbols` / `explode_job` resolve against. A reference to a symbol whose *first* SET comes later still resolves against the final table (historical leniency, kept).
    - A SET inside a `PROC`…`PEND` body is procedure-scoped: it is stored on `Procedure.set_statements`, never in `job.set_statements`, and applies only while that PROC is expanded. Precedence there: EXEC overrides > PROC defaults > the PROC's own SETs > job SETs > system symbols.
    - No substitution produces more than `utils.MAX_SYMBOL_VALUE_LENGTH` (65,536) characters, a safety cap rather than the z/OS 255 limit (`SET A2='&A1&A1'` chains otherwise grow without bound, #70). Past it the SET value (`_resolve_set_value`, `resolve_set_symbols`) or the referencing text (`substitute_symbols`) is left unresolved with a warning; strict parsing raises `JCLSyntaxError`, `explode_job(strict_symbols=True)` `JCLStructureError`.

11. **Vendoring is always manual.** Changes to `jclparser/` are not propagated to the backend. Run `rm -rf ../backend/_vendor/jcl-parser/jclparser && cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser` after changes. Plain `cp -r` into an existing destination nests into `jclparser/jclparser/` and silently leaves stale files in place (it once left the backend without `_job_builder.py`, `_model_factories.py` and `_post_parse.py` for two PRs).

12. **`--version` reads from `jclparser.__version__`.** It must equal `pyproject.toml:version`. release-please updates both (the `__init__.py` line carries `# x-release-please-version`), and `tests/unit/test_audit_patch_fixes.py::TestPackageMetadata` enforces the match.

13. **Coverage must not drop below 90%.** `pytest` enforces `--cov-fail-under=90`. Add tests alongside any new module in the same commit.

14. **`builtin_procs.py` contains non-verbatim templates.** The built-in IBM utility PROCs are structural approximations for static analysis only and must not be submitted to a real mainframe.

15. **Every `_STATEMENT_TYPES` entry needs an explicit entry in `JobBuilder._HANDLERS`** (the statement-type → handler table `handle_statement` dispatches through). `continuation_handler.JCL_KEYWORDS` is derived from `_STATEMENT_TYPES` for the same reason. A recognized type missing from either falls through silently: it is not dispatched, or it is misclassified as a continuation and merged into the previous statement, corrupting it. `tests/unit/test_silent_drop_fixes.py::TestStatementDispatchCompleteness` fails when a type is added to `_STATEMENT_TYPES` without a matching `_HANDLERS` entry.

16. **Known limitation: a nameless, indented statement whose operation keyword this parser does not recognize is ambiguous.** `ContinuationLineHandler` and `_statement_parser.parse_statement()` share a first-keyword heuristic (not true z/OS column-field parsing) to decide "continuation of the previous statement" vs "new statement of an unknown type", and for an unrecognized keyword there is no reliable answer. After a statement whose operand field ends with a comma (or an open quote/paren) the record is merged into that statement. After a *complete* statement it is never merged (#123): `ContinuationLineHandler.is_stray_continuation_record()` flags it, its operands are ignored, and `_merge_source_lines` adds `Line N: continuation record ignored because the statement before it does not end with a comma (missing comma?): …` to `job.warnings`. That catches the classic missing-comma slip (`DSN=PROD.MASTER` / `DISP=SHR` would otherwise become `DSN=PROD.MASTERDISP=SHR`). A complete statement whose last record is a card image continued in column 72 (`utils.is_continued_card_image()`) continues its *comment field* on the next record (IBM: "Continuing the comment field"), so that record is not reported (`merge_continuation_lines` tracks it as `comment_continued`). Closing the gap fully needs column-based parsing. Named statements with unrecognized keywords are unaffected: they survive with a warning (`TestDanglingCommaDoesNotSwallowNextStatement`).

17. **A statement's operand field ends at the first blank outside quotes and parens.**
    - Everything after it is a comment field, and `_statement_parser.split_comment_field()` removes it *before* continuation merging. Parsed as operands, a comment makes `PGM=X    RUN THE THING` a program name, and a comment after a trailing comma hides the comma, dropping every continued operand. A removed comment containing `=` is reported on `job.warnings`.
    - `IF` operands are blank-delimited, so an IF's comment field starts after its `THEN` keyword; everything after `ELSE` / `ENDIF` is comment. An IF with no `THEN` yet continues on the next blank-name-field record, joined with a blank (`ContinuationLineHandler._continues_if`). The IF's label (`//CHK1 IF ...`) is not part of `ConditionalBlock.condition`.
    - A blank after a comma still counts as inside the operands when a `KEY=VALUE` token follows (on a DD, a JOB or an `EXEC PGM=`, only when `KEY` is one of that statement's keywords, `_keywords.resuming_keywords`, so `DSN=A,   RETAIN=30 DAYS` is a comment and the next record still continues the DD; on a PROC statement or a PROC call, any `KEY` that is a name, so `A=1,      <=== THE CLASS` is a comment), or a quoted string or parenthesised group followed by `,` or the end of the record (a group must also hold no unquoted blank). So `JOB (ACCT), 'PGMR'` keeps its programmer name, while `DSN=A,   (CUSTOMER MASTER FILE)` and `DSN=A,   'CUSTOMER' MASTER` are comments (#120, `_statement_parser._resumes_operands`).
    - Inside a parenthesised list, a blank after a subparameter's comma starts a comment when the rest of the record neither resumes operands nor closes the list (`DISP=(NEW,     COMMENT` / `//   CATLG)`), including on a record that continues an open list; `DISP=(NEW, CATLG)` on one record is tolerated.

18. **Operation keywords are legal ddnames.** `//OUTPUT DD SYSOUT=*`, `//IF DD …`, `//SET DD …` are DD statements, not OUTPUT/IF/SET statements. The second token settles which field is which: if it is itself an operation keyword, the first token is a name. The same rule keeps a statement whose name field starts after column 3 (`//   STEP2 EXEC PGM=X`) from being folded into the statement before it.

19. **A JOB-less PROC member parses.** A cataloged procedure with no JOB card yields a synthetic `Job` with `name == ""` (never `None`), `is_procedure_member` true, and its PROCs and SET/EXPORT/JCLLIB/INCLUDE/OUTPUT/IF content intact (`JobBuilder._job_or_procedure_member`). Source with neither a JOB card nor a `PROC` statement is still `JCLSyntaxError("No JOB statement found")`, and so is a bare `EXEC` before any JOB card. SETs inside the member's PROC/PEND live on `Procedure.set_statements` and are also copied to the synthetic job's `set_statements` (the member has no job scope of its own).

20. **The null statement (`//` alone) ends the job.** Once a JOB statement has been seen, every record after a `//` is skipped (`JobBuilder.skip_after_null`) with one warning naming the null statement's line and the skipped range; a trailing `//` with nothing after it warns nothing. A JOB statement after it is still the "Multiple JOB statements" `JCLSyntaxError` (the parser models one job per source). A `//` before the JOB statement is ignored (#124).

# Citations

[1] [core/data-model.md](../core/data-model.md) — invariants 6, 8 (real field names)
[2] [advanced/proc-expansion.md](../advanced/proc-expansion.md) — invariants 3, 4, 6
[3] [advanced/validation.md](../advanced/validation.md) — invariants 7, 8
[4] [development/workflow.md](workflow.md) — invariants 11, 12, 13
[5] [../../tests/unit/test_silent_drop_fixes.py](../../tests/unit/test_silent_drop_fixes.py) — invariants 15, 16 and the silent-data-loss fix history generally
