---
title: Key Invariants
updated: 2026-09-02
sources: LegacyLens team, 2026-06-27; parser silent-drop audit, 2026-09-02
---

# Key Invariants

16 non-obvious behaviors that bite contributors. Read before touching any parsing code.

---

**1. Statement content stops at column 71.**
JCL content occupies columns 1–71. Column 72 holds the *continuation indicator* (any non-blank character when the statement continues on the next record) and columns 73–80 the sequence/identifier field. `normalize_jcl_line()` strips both from fixed-format records — an 80-column record always, and a 72-character record whose column 71 is blank and column 72 is not (a record whose sequence field was trimmed). Shorter lines are modern text-editor JCL and are never truncated. `ContinuationLineHandler` then merges multi-line statements before any parsing occurs. **Never pass pre-stripped lines** to `parse_jcl()`; doing so breaks continuation detection.

---

**2. `ConditionalBlock.condition` (raw string) is authoritative.**
The raw `condition` string is always present. `condition_ast` (parsed AST) may be `None` if `parse_condition()` returned `None` for an unparseable expression. Always read `condition` for display and logging; use `condition_ast` only when you need to traverse the AST.

---

**3. Inline PROCs always win.**
Even if a PROC with the same name exists in an external PROCLIB or in the builtin templates, the inline definition (from `PROC…PEND` within the same JCL) takes precedence. No override is possible.

---

**4. `&&` is an escaped ampersand in JCL.**
Symbol substitution replaces `&NAME` → value and `&&` → literal `&`. Handled in `explosion.py:_SYMBOL_SUB_PATTERN`. Do not mistake `&&TEMP` in a DSN for double-substitution — the leading `&&` signals a temporary dataset, not an escaped ampersand.

---

**5. Dataset names are case-insensitive on z/OS but stored as-is.**
Validation checks length (max 44 chars total, max 8 chars per qualifier) and charset, but does not uppercase. String comparisons against DSN values must account for this.

---

**6. `parse_jcl()` does not expand PROCs.**
PROC invocations remain as `Step(exec_type="PROC")` objects. Call `explode_job()` separately when you need expansion. This is intentional — parsing and expansion are independent operations.

---

**7. `validate_jcl()` returns `(Job, list)`, not a boolean.**
```python
job, errors = validate_jcl(source)  # always unpack both values
```
Check `result.errors` for `ErrorSeverity.ERROR` items to determine hard failure. Warnings and INFO entries are also in the list.

---

**8. `//` comment lines are preserved.**
Comment lines appear as `Statement(type="COMMENT")` objects in `job.statements`. They are not stripped during parsing. Code that iterates `job.statements` must handle comments.

---

**9. JES control statements are parsed separately.**
`/*JOBPARM`, `/*ROUTE`, `/*XMIT`, etc. are handled in `jes_statements.py` via `parse_jes_control()`. They are **not** in `job.steps` and are **not** part of the main `Job` model. Access them through the JES API if needed.

---

**10. SET symbols resolve left-to-right.**
A `SET` statement can reference an earlier SET symbol but not a later one, mirroring mainframe evaluation order. Code that synthesizes JCL with multiple SET statements must order them accordingly.

---

**11. Vendoring is always manual.**
Changes to `jclparser/` are **not** automatically propagated to `backend/_vendor/jcl-parser/`. You must run:
```bash
cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/
```
Forgetting this step means the backend runs on stale library code.

---

**12. `--version` reads from `jclparser.__version__`.**
The CLI reads the version string from `jclparser/__init__.py:__version__`, not from package metadata. When releasing, update **both** `__init__.py` and `pyproject.toml:version` together.

---

**13. Coverage must not drop below 90%.**
Every `pytest` run enforces `--cov-fail-under=90`. If you add a new module, add tests alongside it in the same commit. The CI will fail otherwise.

---

**14. The comment field ends the operands at the first blank.**
A statement's operand field ends at the first blank outside quotes and parentheses; the rest of the record is a free-form comment (`//STEP1 EXEC PGM=X    RUN THE THING`). `split_comment_field()` in `_statement_parser.py` removes it *before* continuation merging — a comment after a trailing comma would otherwise hide the comma and every continued operand would be lost. Two carve-outs: `IF`/`THEN`/`ELSE`/`ENDIF` are blank-delimited by syntax and are never touched, and a blank that follows a comma is treated as still inside the operand field when what comes next is a quoted string, a `(`, or a `KEY=VALUE` token (`//J JOB (ACCT), 'PGMR',CLASS=A` — illegal per z/OS, common in the wild). A removed comment that contains an `=` is reported on `job.warnings` rather than discarded quietly.

---

**15. A statement keyword in the name field is still a name.**
`OUTPUT`, `SET`, `IF`, `DATA` and every other operation keyword are legal ddnames and step names. `//OUTPUT DD SYSOUT=*` is a DD named OUTPUT, not an OUTPUT statement — a *second* token that is itself an operation keyword settles which field is which (`_is_named_statement()`). The same rule rescues a statement whose name field starts after column 3 (`//   STEP2 EXEC PGM=X`), which would otherwise look like a continuation record and be folded into the statement before it.

---

**16. `builtin_procs.py` contains non-verbatim templates.**
The built-in IBM utility PROC templates (IMS, DB2, COBOL) are **structural approximations**, not exact copies of the IBM-supplied PROCs. They are sufficient for static analysis and PROC expansion in tests, but must not be submitted to a real mainframe.

---

## See Also

- [../core/parsing-pipeline.md](../core/parsing-pipeline.md) — pipeline overview
- [../advanced/proc-expansion.md](../advanced/proc-expansion.md) — invariants 3, 4, 6
- [../advanced/validation.md](../advanced/validation.md) — invariants 7, 8
- [development-workflow.md](development-workflow.md) — invariants 11, 12, 13
