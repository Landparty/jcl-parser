# Update Log

## 2026-06-29
* **Fix**: An unresolved symbolic PDS member no longer leaves bare `()` in a dataset name. `DSN=LIB(&MEM)` with `&MEM` undefined elides to `LIB()` under non-strict substitution; `substitute_dd_statement` now strips the empty member via new `_strip_empty_member()`, collapsing to the bare PDS name `LIB`. Non-empty members and GDG generations are untouched. Tests: `tests/unit/test_explosion.py::TestSymbolicParameterSubstitution::{test_unresolved_member_leaves_no_empty_parens, test_resolved_member_is_preserved}`. Updated [advanced/proc-expansion](advanced/proc-expansion.md) §Symbol Substitution. Vendor-synced into `backend/_vendor/jcl-parser/`. (Surfaced as `BANK.PROD.DBRMLIB()` in the Resources dataset view; backend passes the DSN through verbatim.)

## 2026-06-28
* **Fix**: `explode_job` now merges *unqualified* DD overrides coded under an `EXEC PROC=` statement onto the procedure's first step instead of dropping them. The parser stores unqualified overrides on the EXEC step's own `dd_statements` (only dotted `PROCSTEP.DDNAME` overrides went to `dd_overrides`), and `_explode_step` previously ignored them — so an *added* override like `//LOANRPT DD …` on `EXEC PROC=IMSBTCH` vanished during explosion. New `apply_unqualified_dd_overrides()` replaces a same-named proc DD or appends a new one (z/OS semantics). Tests: `tests/unit/test_explosion.py::TestDDOverrides` (added vs replaced). Updated [advanced/proc-expansion](advanced/proc-expansion.md) §DD Overrides. (Motivated by the backend IMS-BMP dataset-resolution fix — see backend `.okf/log.md`.)
* **Creation**: Initialized OKF bundle from existing documentation — [index](index.md).
* **Creation**: Parsing pipeline concept — [core/parsing-pipeline](core/parsing-pipeline.md).
* **Creation**: Data model concept — [core/data-model](core/data-model.md).
* **Creation**: Public API concept — [api/public-api](api/public-api.md).
* **Creation**: PROC expansion concept — [advanced/proc-expansion](advanced/proc-expansion.md).
* **Creation**: Validation concept — [advanced/validation](advanced/validation.md).
* **Creation**: Backend contract concept — [integration/backend-contract](integration/backend-contract.md).
* **Creation**: Key invariants concept — [development/invariants](development/invariants.md).
* **Creation**: Development workflow concept — [development/workflow](development/workflow.md).
