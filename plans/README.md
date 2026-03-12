# JCL Parser — Refactoring Plan

> Audit conducted: 2026-03-11  
> Fact-check updated: 2026-03-11  
> Package size: 15 Python files under `jclparser/`, ~4,862 lines total  
> Tests: ~40 Python test files, ~13,423 lines total

---

## Priority Action Plan

| Priority | Action | Impact |
|---|---|---|
| **P0 — Bug** | Fix `_explode_step` `job` variable bug (`explosion.py:525`) | Nested proc JCLLIB loading is silently broken |
| **P1 — Correctness** | Unify dataset / DISP validation rules behind one canonical implementation while preserving current boolean wrappers for compatibility | Removes rule drift without breaking current callers or tests |
| **P1 — Correctness** | Extract a single `_read_source()` utility shared by `parser.py`, `validate_jcl()`, and `jcl_file_type.py` | Prevents divergent source-reading bug classes |
| **P2 — Maintainability** | Define a `_STATEMENT_TYPES` constant in `parser.py` | Prevents silent parsing regressions from out-of-sync copies |
| **P2 — Maintainability** | Classify `utils.py` helpers into runtime-critical vs compatibility-only APIs, then deprecate or move low-value helpers behind wrappers | Reduces confusion without breaking the tested public surface |
| **P2 — Maintainability** | Have `Job.validate()` delegate to `validators.validate_job_structure()` | Single source of truth for validation logic |
| **P3 — Design** | Extract `_parse_parameters` into `ParameterParser` | Unifies the three independent parser implementations |
| **P3 — Design** | Review `DDStatement` convenience accessors and deprecate only the ones proven unused by public callers | Shrinks `model.py` without accidental API breakage |
| **P3 — Design** | Slim down `__init__.py` `__all__` through staged deprecation, not immediate removal | Stabilises the public API contract |
| **P4 — Tests** | Reorganise test files by feature, remove coverage-chase files | Dramatically improves long-term maintainability |

---

## Execution Guidance

To keep this plan feasible, work in phases and preserve public compatibility until the API policy is explicit.

### Phase 1 — Correctness First

- Fix the confirmed nested PROC loading bug in `explosion.py`.
- Consolidate duplicated validation logic behind compatibility wrappers.
- Extract shared `_read_source()` logic and cover it with focused tests.

### Phase 2 — Internal Consolidation

- Centralise statement type constants and positional parameter helpers.
- Unify parameter splitting logic.
- Make `Job.validate()` defer to one canonical validator path.

### Phase 3 — Public API Cleanup

- Audit which `utils.py`, model properties, and top-level exports are intentionally public.
- Deprecate legacy helpers before removal.
- Document replacement APIs before any breaking cleanup.

### Success Criteria

- No regression in the existing test suite.
- No public API removals without a deprecation path.
- One canonical implementation for source reading, parameter splitting, and validation rules.
- Internal modules have clearer boundaries and fewer duplicated parsing rules.

---

## Detailed Findings

### 1. Architectural Issues

#### 1.1 `parser.py` is a God Module (884 lines)

`parser.py` performs six unrelated responsibilities in one file:

| Responsibility | Should live in |
|---|---|
| Reading source from `str` / `Path` / `IO` | `_io.py` or `utils.py` |
| First-pass inline data detection | `inline_data.py` or `continuation_handler.py` |
| Continuation line merging | `continuation_handler.py` (already exists) |
| Statement lexing / tokenizing | `lexer.py` or `statement_parser.py` |
| Constructing model objects | `model.py` or a `builder.py` |
| External PROC loading orchestration | `proc_loader.py` (already exists) |

**Action:** Extract `_read_source()`, `_parse_parameters()`, `_parse_list_parameter()`, and the `_create_*_from_statement()` factory functions into their own modules, or collapse the factory functions into `model.py` as class methods. `parse_statement()` is the only function that truly belongs in `parser.py`.

---

#### 1.2 Source-reading logic duplicated verbatim

The identical ~20-line block for normalising input (`str` / `Path` / `IO`) appears in both `parse_jcl()` and `validate_jcl()`. A bug-fix applied to one will be missed in the other. A private `_read_source()` already exists in `jcl_file_type.py` — all three should share it.

**Action:** Extract to a single `_read_source(source) -> str` helper in `utils.py` and import it in all three call sites.

---

#### 1.3 Statement type list repeated as a magic literal 3×

The list `["JOB", "EXEC", "DD", "PROC", "PEND", "JCLLIB", "INCLUDE", "SET", "IF", "THEN", "ELSE", "ENDIF", "XMIT", "OUTPUT", "SCHEDULE", "NULL", "COMMAND", "CNTL", "ENDCNTL"]` appears three times in `parser.py`. A forgotten addition to one copy silently breaks parsing.

**Action:** Define once as a module-level constant:

```python
_STATEMENT_TYPES: frozenset[str] = frozenset({
    "JOB", "EXEC", "DD", "PROC", "PEND", "JCLLIB", "INCLUDE",
    "SET", "IF", "THEN", "ELSE", "ENDIF", "XMIT", "OUTPUT",
    "SCHEDULE", "NULL", "COMMAND", "CNTL", "ENDCNTL",
})
```

---

#### 1.4 Circular-scope patch — confirmed bug (`explosion.py:525`)

```python
procedure = proc_loader.load_procedure(
    proc_name, job.jcllib_order if 'job' in locals() else None
)
```

`job` is **never** in scope inside `_explode_step()`, so `'job' in locals()` always evaluates to `False`. As a result, `jcllib_order` is always passed as `None` during recursive procedure explosions — silently breaking JCLLIB-based proc loading for nested procs.

**Action:** Pass `jcllib_order` explicitly as a parameter to `_explode_step()`:

```python
def _explode_step(
    ...,
    jcllib_order: Optional[List[str]] = None,
) -> List[Step]:
    procedure = proc_loader.load_procedure(proc_name, jcllib_order)
```

---

### 2. Redundancy and Dead Code

#### 2.1 Three independent implementations of the same quote-aware parameter splitter

| Location | Function |
|---|---|
| `utils.py` | `split_jcl_parameters()` |
| `parser.py` | `_parse_parameters()` / `_parse_list_parameter()` |
| `parameter_ast.py` | `ParameterParser._split_parameters()` |

All three implement the same quote-depth / paren-depth tracking loop. Any edge-case fix must be applied to all three independently.

**Action:** Canonicalise to `ParameterParser._split_parameters()` (the most complete implementation) and have the other two call it.

---

#### 2.2 Two duplicate name validators

`utils.py` `validate_jcl_name()` and `validators.py` `validate_jcl_identifier()` are functionally identical. The core validation flow uses `validate_jcl_identifier()`, while `validate_jcl_name()` remains part of the tested utility surface.

`validate_jcl_name()` is not used by the main parsing flow, but it is still part of the tested utility surface.

**Action:** Keep `validate_jcl_name()` as a thin compatibility wrapper for now, or deprecate it in favor of `validate_jcl_identifier()` with an explicit migration note. Do not remove it outright in the current compatibility window.

---

#### 2.3 Two DISP / dataset validators with conflicting rules

- `validators.py` `validate_dataset_name()` enforces an **8-character** qualifier limit and disallows hyphens.
- `parameter_validators.py` `DatasetNameValidator` correctly enforces a **44-character** total limit and allows hyphens.

Both are present in the codebase today, and the boolean-returning functions in `validators.py` are part of the current tested API.

**Action:** Keep the boolean-returning functions in `validators.py`, but re-implement them as wrappers around the canonical validators in `parameter_validators.py`. That gives one rule source while preserving current imports and return types.

---

#### 2.4 Legacy utility surface in `utils.py`

The following functions in `utils.py` are not used by the main parser path, but they are still imported and exercised directly by the current test suite:

| Function | Reason superseded |
|---|---|
| `extract_inline_data()` | Parser handles inline data in-line |
| `merge_continuation_lines()` | Superseded by `ContinuationLineHandler` |
| `parse_jcl_parameter()` | Superseded by `_parse_parameters()` in `parser.py` |
| `format_jcl_line()` | Not used by the runtime parser path; currently exercised only as a utility API |

**Action:** Do not remove these helpers immediately. First decide whether they are intentionally public utility APIs. If not, move them behind compatibility wrappers or a dedicated compatibility / serialization module and deprecate them before removal.

---

#### 2.5 `Job.validate()` duplicates `validators.validate_job_structure()`

`model.py` `Job.validate()` checks name length, step uniqueness, and delegates to `_validate_step()`. `validators.py` `validate_job_structure()` does the same but also calls `validate_data_dependencies()`. Both return `List[ValidationError]` and are public API.

**Action:** Replace the body of `Job.validate()` with:

```python
def validate(self) -> List[ValidationError]:
    from .validators import validate_job_structure
    return validate_job_structure(self)
```

---

### 3. Model Design Issues

#### 3.1 `DDStatement` has many trivial property wrappers

`model.py` defines 18+ `@property` methods that each do nothing but `return self.parameters.get('KEYNAME')`. This doubles the class surface area without adding behaviour. Callers must already know the parameter key names; they can use `dd.parameters.get(...)` directly.

**Action:** Review these properties in two buckets: internal-only convenience vs public convenience API. Keep clearly valuable ones, consider deprecating low-value pass-through accessors, and prefer documentation plus `dd.parameters` for rarely used fields. Avoid abrupt removal.

---

#### 3.2 Duplicate `is_procedure` / `is_proc_invocation` properties

```python
@property
def is_procedure(self) -> bool:        # "True if step executes a procedure"
    return self.procedure is not None

@property
def is_proc_invocation(self) -> bool:  # "alias for is_procedure"
    return self.procedure is not None
```

`is_procedure` is part of the current tested model API, while `is_proc_invocation` is used internally by the explosion logic.

**Action:** Keep both for now, but implement one in terms of the other and document `is_proc_invocation` as the preferred internal name. Revisit removal only under an explicit breaking-change policy.

---

#### 3.3 Positional parameters as undocumented magic key strings

Positional parameters are stored with keys `"_pos_0"`, `"_pos_1"` etc. across `parser.py`, `model.py`, and `explosion.py`. Callers must know this implicit convention.

**Action:** Define once at module level:

```python
POSITIONAL_PARAM_PREFIX = "_pos_"

def is_positional_key(k: str) -> bool:
    return k.startswith(POSITIONAL_PARAM_PREFIX)
```

Better still, model positional parameters as a separate `List[str]` attribute on `Statement` rather than encoding them in the `parameters` dict.

---

### 4. Caching Issues

#### 4.1 `JCLLIBProcedureLoader` uses an implicit lazy-cache pattern

```python
def load_procedure(self, name, libraries=None):
    if not hasattr(self, '_cache'):   # ← initialised in method, not __init__
        self._cache = {}
```

`lru_cache` is imported at the top of `proc_loader.py` but never used. The lazy initialisation pattern works today, but it is harder to reason about than explicit cache setup in `__init__`.

**Action:** Initialise `self._cache: Dict = {}` in `__init__`, or use `@functools.lru_cache` properly via a wrapper method.

---

### 5. Public API Over-Exposure

#### 5.1 `__init__.py` re-exports many symbols including implementation internals

Top-level exports currently include `MockSystemSymbolProvider`, `EnvironmentSystemSymbolProvider`, `RuntimeSystemSymbolProvider`, `SymbolScope`, `ExplosionRecord`, `ProcExpansionInfo`, `InlineProcedureLoader`, `JCLLIBProcedureLoader`, and `CompositeProcedureLoader`. Any future renaming is a public breaking change.

Many of these exports may already be relied on by users and by the repository's own tests.

**Action:** Adopt a tiered API model through staged deprecation:

| Tier | Symbols |
|---|---|
| **Public** | `parse_jcl`, `validate_jcl`, `Job`, `Step`, `DDStatement`, `Parameter`, error hierarchy, `ValidationLevel` |
| **Advanced** | `explode_job`, `ProcedureLoader`, `SystemSymbolProvider`, `ParserConfig` |
| **Internal** (future deprecation candidates) | `SymbolScope`, `ExplosionRecord`, `InlineProcedureLoader`, `JCLLIBProcedureLoader`, Mock/Runtime/Environment providers |

---

### 6. Test Suite Health

#### 6.1 40+ test files with coverage-chase naming

The test directory contains files that are clearly incremental "hit 90% coverage" additions:

- `test_coverage_boost.py`
- `test_coverage_final.py`
- `test_final_coverage.py`
- `test_final_push_to_90.py`
- `test_push_to_90.py`
- `test_absolute_final.py`

These cause:
- **Maintenance confusion** — impossible to know which file tests what behaviour
- **Duplication** — the same code paths tested across multiple files
- **Brittleness** — changing parser behaviour requires hunting through all files

**Action:** Treat this as a medium-term cleanup, not an immediate prerequisite for refactoring. Consolidate into a feature-organised taxonomy once correctness work is complete and public API compatibility is protected:

```
tests/
  unit/
    test_parser.py          # parse_jcl(), parse_statement()
    test_model.py           # Job, Step, DDStatement
    test_validators.py      # all validators (unified)
    test_continuation.py    # ContinuationLineHandler
    test_explosion.py       # explode_job(), SymbolScope
    test_parameter_ast.py   # DCBParameter, SPACEParameter
    test_proc_loader.py     # loader chain
    test_file_type.py       # detect_file_type()
    test_errors.py          # exception hierarchy
  integration/
    test_jcl_compliance.py  # real-world JCL samples
    test_proc_loading.py    # external proc filesystem tests
```

---

### 7. Minor Issues

| Issue | Location | Fix |
|---|---|---|
| `lru_cache` imported but never used | `proc_loader.py` | Remove import |
| `Optional[Any]` type hints throughout | `explosion.py`, `model.py` | Replace with proper types |
| `source.seek(0)` "Reset for potential reuse" comment — not a real guarantee | `parser.py` | Remove seek or document the contract clearly |
| `ContinuationLineHandler` stores `self.context` in `__init__`, but the attribute is currently unused | `continuation_handler.py` | Remove the unused instance state or wire it into actual stateful processing |
| `ProcedureLoader.has_procedure()` calls `load_procedure()` and discards result — cache makes this acceptable but it should be documented | `proc_loader.py` | Add docstring note |
