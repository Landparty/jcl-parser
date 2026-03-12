# JCL Parser — Refactoring TODO

> Generated: 2026-03-11  
> Based on audit findings in `plans/README.md`  
> Run tests after every task: `cd src; pytest` (from repo root: `pytest`)

---

## How to use this list

Work strictly in priority order (P0 → P1 → P2 → P3 → P4).  
Each task has a **verification step** — do not mark a task done until it passes.  
All changes must leave the test suite green: `pytest` with zero failures.

---

## P0 — Bug Fix (do this first, before anything else)

### TASK-01 · Fix the `_explode_step` `jcllib_order` bug in `explosion.py`

**File:** `jclparser/explosion.py` · **Line:** ~525  
**Risk:** Low — surgical one-line fix  
**Dependency:** None

**What is broken:**

```python
# CURRENT (broken) — 'job' is never in scope inside _explode_step
procedure = proc_loader.load_procedure(
    proc_name, job.jcllib_order if 'job' in locals() else None
)
```

`'job' in locals()` always returns `False` inside `_explode_step`, so `None` is always
passed as the library list. Any nested proc that relies on JCLLIB for loading is silently
broken: it will raise `ProcedureNotFoundError` or silently skip the proc.

**Steps:**

1. Open `jclparser/explosion.py`.

2. Locate `_explode_step` (currently starting around line 487). Confirm the function
   signature:
   ```python
   def _explode_step(
       step: Step,
       proc_loader: ProcedureLoader,
       base_scope: SymbolScope,
       call_chain: List[str],
       depth: int,
       max_depth: int,
       audit_records: Optional[List[ExplosionRecord]],
       expansion_map: Dict[str, ProcExpansionInfo],
       strict_symbols: bool
   ) -> List[Step]:
   ```

3. Add `jcllib_order: Optional[List[str]] = None` as the **last** parameter:
   ```python
   def _explode_step(
       step: Step,
       proc_loader: ProcedureLoader,
       base_scope: SymbolScope,
       call_chain: List[str],
       depth: int,
       max_depth: int,
       audit_records: Optional[List[ExplosionRecord]],
       expansion_map: Dict[str, ProcExpansionInfo],
       strict_symbols: bool,
       jcllib_order: Optional[List[str]] = None,   # ← add this
   ) -> List[Step]:
   ```

4. Inside `_explode_step`, replace the broken `load_procedure` call:
   ```python
   # BEFORE
   procedure = proc_loader.load_procedure(
       proc_name, job.jcllib_order if 'job' in locals() else None
   )

   # AFTER
   procedure = proc_loader.load_procedure(proc_name, jcllib_order)
   ```

5. Locate the **caller** of `_explode_step` inside `explode_job()`. It currently passes
   no `jcllib_order` argument. Thread the job's value through:
   ```python
   # BEFORE (inside explode_job's for-step loop)
   expanded = _explode_step(
       step=step,
       proc_loader=proc_loader,
       base_scope=base_scope,
       call_chain=[],
       depth=0,
       max_depth=max_depth,
       audit_records=explosion_audit if audit else None,
       expansion_map=explosion_map,
       strict_symbols=strict_symbols
   )

   # AFTER
   expanded = _explode_step(
       step=step,
       proc_loader=proc_loader,
       base_scope=base_scope,
       call_chain=[],
       depth=0,
       max_depth=max_depth,
       audit_records=explosion_audit if audit else None,
       expansion_map=explosion_map,
       strict_symbols=strict_symbols,
       jcllib_order=job.jcllib_order or None,   # ← add this
   )
   ```

6. Locate the **recursive call** to `_explode_step` inside `_explode_step` itself
   (used when expanding nested procs). Add the same forwarding:
   ```python
   nested = _explode_step(
       step=expanded_step,
       proc_loader=proc_loader,
       base_scope=base_scope,
       call_chain=new_call_chain,
       depth=depth + 1,
       max_depth=max_depth,
       audit_records=audit_records,
       expansion_map=expansion_map,
       strict_symbols=strict_symbols,
       jcllib_order=jcllib_order,   # ← forward it
   )
   ```

7. **Verify:** Run `pytest tests/test_explosion.py tests/test_external_proc_loading.py -v`.
   All tests must pass. Then run the full suite: `pytest`.

---

## P1 — Correctness

### TASK-02 · Unify dataset/DISP validation behind `parameter_validators.py`

**Files:** `jclparser/validators.py`, `jclparser/parameter_validators.py`  
**Risk:** Low — wrapping only, no rule deletion  
**Dependency:** TASK-01 (green suite required before continuing)

**What is inconsistent:**

| Location | Rule |
|---|---|
| `validators.py` `validate_dataset_name()` | 8-char qualifier max, hyphens disallowed |
| `parameter_validators.py` `DatasetNameValidator` | 44-char total max, hyphens allowed (correct per IBM spec) |

**Steps:**

1. Open `jclparser/validators.py`. Read the current body of `validate_dataset_name()`.

2. Replace the body with a thin wrapper that delegates to `DatasetNameValidator`:
   ```python
   def validate_dataset_name(dsn: str) -> bool:
       """
       Validate dataset name format.

       Compatibility wrapper — canonical rules live in
       `parameter_validators.DatasetNameValidator`.
       """
       from .parameter_validators import DatasetNameValidator
       result = DatasetNameValidator.validate(dsn)
       return result.is_valid
   ```

3. Open `jclparser/validators.py` and find the `validate_disposition()` function (if it
   exists) or any DISP validation logic. If a local DISP rule implementation exists,
   replace its body with a delegate to `ParameterValidator.validate_disp()`:
   ```python
   def validate_disposition(disp: str) -> bool:
       """Compatibility wrapper — canonical rules in parameter_validators."""
       from .parameter_validators import ParameterValidator
       result = ParameterValidator.validate_disp(disp)
       return result.is_valid
   ```

4. Run the validator-specific tests to confirm no regression:
   ```
   pytest tests/test_parameter_validators.py tests/test_dd_all_parameters.py -v
   ```

5. Run the full suite: `pytest`. Fix any failures before proceeding.

---

### TASK-03 · Extract a shared `_read_source()` helper

**Files:** `jclparser/utils.py`, `jclparser/parser.py`, `jclparser/jcl_file_type.py`  
**Risk:** Medium — touches two public functions (`parse_jcl`, `validate_jcl`)  
**Dependency:** TASK-02

**What is duplicated:**

The ~20-line block that resolves `str | Path | IO` into a `str` content value appears
verbatim in _both_ `parse_jcl()` and `validate_jcl()`. A bug fix in one is silently
missed in the other. `jcl_file_type.py` has its own private `_read_source()` that is
not shared.

**Steps:**

1. Open `jclparser/utils.py` and append a new public helper at the bottom of the file:
   ```python
   def read_source(source: Union[str, "Path", Any]) -> str:
       """
       Normalise a JCL source argument into a plain string.

       Accepts:
         - str  : returned as-is if it looks like JCL content (starts with
                  '//' or has no path separators), otherwise treated as a
                  file path and read from disk.
         - Path : read from disk; raises FileNotFoundError if missing.
         - IO   : read via .read(); seeks back to 0 if seekable.

       Returns:
           Content string.

       Raises:
           FileNotFoundError: If a path argument points to a missing file.
       """
       from pathlib import Path as _Path
       if isinstance(source, _Path):
           if not source.exists():
               raise FileNotFoundError(f"JCL file not found: {source}")
           with open(source, 'r', encoding='utf-8') as fh:
               return fh.read()
       elif isinstance(source, str):
           if (source.endswith('.jcl') or
                   (('/' in source or '\\' in source)
                    and not source.strip().startswith('//'))):
               path = _Path(source)
               if not path.exists():
                   raise FileNotFoundError(f"JCL file not found: {path}")
               with open(path, 'r', encoding='utf-8') as fh:
                   return fh.read()
           return source
       else:
           content = source.read()
           if hasattr(source, 'seek'):
               source.seek(0)
           return content
   ```
   Add the necessary `Union` import if not already present in `utils.py`: it only needs
   `from typing import Union` plus the standard-library `Any`.

2. Open `jclparser/parser.py`. In `parse_jcl()`, **replace** the entire
   `if isinstance(source, Path)` … `source.seek(0)` block with:
   ```python
   from .utils import read_source
   content = read_source(source)
   ```
   Keep everything _after_ that block (the `raw_lines = content.splitlines()` line and
   onwards) unchanged.

3. In `validate_jcl()`, **replace** the second (fallback) source-reading block (the one
   that starts with `if isinstance(source, Path):` inside the except handler) with:
   ```python
   from .utils import read_source
   try:
       content = read_source(source)
   except FileNotFoundError as exc:
       errors.append(ParseError(
           error_type=ErrorType.SYNTAX_ERROR,
           message=str(exc),
           line_number=0,
           severity=ErrorSeverity.ERROR
       ))
       return errors
   ```

4. Open `jclparser/jcl_file_type.py`. If a `_read_source()` private function exists,
   replace its body with a call to `utils.read_source()` and update its imports, or
   inline the call at the single usage point if it is called only once.

5. Run `pytest tests/test_jcl_file_type.py tests/test_parser_api.py -v`, then the full
   suite: `pytest`.

---

## P2 — Maintainability

### TASK-04 · Define a single `_STATEMENT_TYPES` constant in `parser.py`

**File:** `jclparser/parser.py`  
**Risk:** Low  
**Dependency:** TASK-03

**What is duplicated:**

The same list of 19 JCL statement type strings appears **three times** in `parse_statement()`:
- Line ~624 as `statement_types_no_name`
- Line ~652 as `statement_types`
- Line ~683 as `valid_types`

**Steps:**

1. Open `jclparser/parser.py`. Near the top of the file (after the imports, before the
   first `def`), add:
   ```python
   _STATEMENT_TYPES: frozenset[str] = frozenset({
       "JOB", "EXEC", "DD", "PROC", "PEND", "JCLLIB", "INCLUDE",
       "SET", "IF", "THEN", "ELSE", "ENDIF", "XMIT", "OUTPUT",
       "SCHEDULE", "NULL", "COMMAND", "CNTL", "ENDCNTL",
   })
   ```

2. Inside `parse_statement()`:
   - Replace `statement_types_no_name = [...]` with a reference to the constant:
     ```python
     if first_token not in _STATEMENT_TYPES:
     ```
   - Replace `statement_types = [...]` and the `if first_token.upper() in statement_types:` check:
     ```python
     if first_token.upper() in _STATEMENT_TYPES:
     ```
   - Replace `valid_types = [...]` and the `if statement_type not in valid_types:` check:
     ```python
     if statement_type not in _STATEMENT_TYPES:
     ```
   Delete all three local list variables (`statement_types_no_name`, `statement_types`,
   `valid_types`).

3. Run `pytest tests/test_parser_api.py tests/test_parser_comprehensive.py -v`, then the
   full suite: `pytest`.

---

### TASK-05 · Classify and annotate `utils.py` helpers

**File:** `jclparser/utils.py`  
**Risk:** None (documentation/annotation only — no code deletion)  
**Dependency:** TASK-04

**Goal:** Make it clear to future maintainers which helpers are runtime-critical vs.
legacy utilities that are candidates for deprecation, without removing anything yet.

**Steps:**

1. Open `jclparser/utils.py`. Add a module-level docstring block (or expand the existing
   one) that classifies each public function:
   ```
   Runtime-critical (used by the main parse path):
     normalize_jcl_line, is_continuation_line, read_source,
     quote_jcl_value, unquote_jcl_value

   Public utility API (used externally, not on the hot path):
     split_jcl_parameters, parse_jcl_parameter,
     validate_jcl_name, format_jcl_line,
     extract_inline_data, merge_continuation_lines
   ```

2. For each **public utility** function that is superseded by a better implementation
   elsewhere, add a deprecation note in its docstring. Do **not** add a
   `DeprecationWarning` call yet — only the note. Examples:

   - `merge_continuation_lines()`:
     ```
     .. deprecated::
         Use :class:`jclparser.continuation_handler.ContinuationLineHandler` instead.
         This function will be removed in a future release.
     ```
   - `parse_jcl_parameter()`:
     ```
     .. deprecated::
         Use ``_parse_parameters()`` in ``parser.py`` or
         :class:`jclparser.parameter_ast.ParameterParser` instead.
     ```
   - `extract_inline_data()`:
     ```
     .. deprecated::
         Inline data is now handled directly inside ``parse_jcl()``.
     ```

3. For `validate_jcl_name()`, add a note pointing to `validate_jcl_identifier()` in
   `validators.py` (the canonical implementation):
   ```
   .. note::
       Identical to ``validators.validate_jcl_identifier()``.
       Consider using that function directly.
   ```

4. Run `pytest` — this task should not change behaviour so no tests should change.

---

### TASK-06 · Make `Job.validate()` delegate to `validators.validate_job_structure()`

**File:** `jclparser/model.py`  
**Risk:** Low — `validate_job_structure()` is a superset of the current `Job.validate()`  
**Dependency:** TASK-05

**What is inconsistent:**

`Job.validate()` in `model.py` performs its own name-length, step-uniqueness, and
`_validate_step` checks but **does not** call `validate_data_dependencies()`.
`validators.validate_job_structure()` does all of the above **and** calls
`validate_data_dependencies()`. Both are public API.

**Steps:**

1. Open `jclparser/model.py` and locate `Job.validate()` (around line 602).

2. Note the existing body for reference, then replace it with:
   ```python
   def validate(self) -> List[ValidationError]:
       """
       Validate job structure and data dependencies.

       Delegates to :func:`jclparser.validators.validate_job_structure`
       which is the single canonical implementation.
       """
       from .validators import validate_job_structure
       return validate_job_structure(self)
   ```

3. Keep the private `_validate_step()` method in place — `validators.py` still calls it
   indirectly via `validate_step_structure()`. Do **not** delete it yet.

4. Run `pytest tests/test_model_api.py tests/test_model_comprehensive.py -v`, then the
   full suite: `pytest`. Any test that previously relied on the _old_ behaviour of
   `validate()` **not** calling `validate_data_dependencies()` may now surface new
   validation errors; fix such tests by adjusting expectations, not by reverting the
   delegation.

---

## P3 — Design

### TASK-07 · Canonicalise parameter splitting to `ParameterParser._split_parameters()`

**Files:** `jclparser/utils.py`, `jclparser/parser.py`, `jclparser/parameter_ast.py`  
**Risk:** Medium — changes internal parsing paths; full test suite is the safety net  
**Dependency:** TASK-06

**What exists today:**

| File | Function | Status |
|---|---|---|
| `parameter_ast.py` | `ParameterParser._split_parameters()` | Most complete — handles quotes + parens |
| `utils.py` | `split_jcl_parameters()` | Handles quotes + parens, slightly different quote logic |
| `parser.py` | `_parse_parameters()` / `_parse_list_parameter()` | Inline, no quote depth |

**Steps:**

1. Open `jclparser/parameter_ast.py`. Confirm `ParameterParser._split_parameters()` is
   complete (it handles both paren-depth and quote-depth tracking). It is the canonical
   version.

2. Open `jclparser/utils.py`. Replace the body of `split_jcl_parameters()` with a
   delegate:
   ```python
   def split_jcl_parameters(param_string: str) -> List[str]:
       """
       Split JCL parameter string into individual parameters.

       .. deprecated::
           Internal callers should use
           :meth:`jclparser.parameter_ast.ParameterParser._split_parameters` directly.
           This wrapper is retained for backwards compatibility.
       """
       from .parameter_ast import ParameterParser
       return ParameterParser()._split_parameters(param_string)
   ```

3. Open `jclparser/parser.py`. Locate `_parse_parameters()` (the internal parameter
   parsing function). Identify the comma-splitting loop inside it. Replace that loop
   with a call to `ParameterParser._split_parameters()`:
   ```python
   from .parameter_ast import ParameterParser
   _pp = ParameterParser()
   param_parts = _pp._split_parameters(parameters_part)
   ```
   Leave all the key/value assignment logic that follows the split intact.

4. Do the same for `_parse_list_parameter()` if it has its own comma-splitting loop.

5. Run `pytest tests/test_parameter_ast.py tests/test_parameter_integration.py 
   tests/test_dd_all_parameters.py -v`, then the full suite: `pytest`.

---

### TASK-08 · Fix `JCLLIBProcedureLoader` lazy-cache anti-pattern

**File:** `jclparser/proc_loader.py`  
**Risk:** Very low — purely internal, tests cover the behaviour  
**Dependency:** TASK-07

**What is wrong:**

```python
def load_procedure(self, name, libraries=None):
    if not hasattr(self, '_cache'):   # ← initialised on first call, not in __init__
        self._cache = {}
```

The `lru_cache` import at the top of `proc_loader.py` is unused.

**Steps:**

1. Open `jclparser/proc_loader.py`. Locate `JCLLIBProcedureLoader.__init__()`.

2. Add explicit cache initialisation:
   ```python
   def __init__(self, base_path: Optional[Path] = None):
       if base_path is None:
           env_path = os.environ.get('JCL_PROCLIB_PATH')
           base_path = Path(env_path) if env_path else Path.cwd()
       self.base_path = Path(base_path)
       self._cache: Dict = {}   # ← add this line
   ```

3. Remove the `if not hasattr(self, '_cache'): self._cache = {}` guard from
   `load_procedure()`.

4. At the top of the file, remove the unused `from functools import lru_cache` import
   (it is used only by `CompositeProcedureLoader`, which already imports it correctly via
   `@lru_cache` decorator — confirm this before removing).

5. Add a docstring note to `has_procedure()`:
   ```python
   def has_procedure(self, name: str, libraries=None) -> bool:
       """
       Check if a procedure can be loaded.

       Note: calls load_procedure() and discards the result; the internal
       cache makes repeated calls cheap.
       """
       return self.load_procedure(name, libraries) is not None
   ```

6. Run `pytest tests/test_external_proc_loading.py tests/test_external_proc_edge_cases.py -v`,
   then the full suite: `pytest`.

---

### TASK-09 · Define positional parameter key constants

**Files:** `jclparser/parser.py`, `jclparser/model.py`, `jclparser/explosion.py`  
**Risk:** Low (additive constant, replaces magic string literals)  
**Dependency:** TASK-08

**What is implicit:**

Three modules independently check `k.startswith("_pos_")` or use `"_pos_0"`, `"_pos_1"`
as magic strings. There is no single named constant.

**Steps:**

1. Open `jclparser/utils.py`. Add two constants after the existing imports:
   ```python
   #: Prefix used to store positional (keyword-less) JCL parameters in dicts.
   POSITIONAL_PARAM_PREFIX: str = "_pos_"

   def is_positional_key(key: str) -> bool:
       """Return True if the parameter key represents a positional parameter."""
       return key.startswith(POSITIONAL_PARAM_PREFIX)
   ```

2. In `jclparser/parser.py`, replace every bare `"_pos_"` string literal and
   `k.startswith("_pos_")` expression with the imported constant/helper:
   ```python
   from .utils import POSITIONAL_PARAM_PREFIX, is_positional_key
   # e.g.:
   if is_positional_key(k):  ...
   params[f"{POSITIONAL_PARAM_PREFIX}{idx}"] = value
   ```

3. Do the same in `jclparser/explosion.py` and `jclparser/model.py` wherever `"_pos_"`
   appears as a literal.

4. Run the full suite: `pytest`.

---

### TASK-10 · Implement `is_proc_invocation` in terms of `is_procedure` in `Step`

**File:** `jclparser/model.py`  
**Risk:** None (logic is identical — only removes code duplication)  
**Dependency:** TASK-09

**What is duplicated:**

```python
@property
def is_procedure(self) -> bool:
    """True if step executes a procedure"""
    return self.procedure is not None

@property
def is_proc_invocation(self) -> bool:
    """True if step is a procedure invocation (alias for is_procedure)"""
    return self.procedure is not None   # ← exact copy
```

**Steps:**

1. Open `jclparser/model.py`. Locate the `Step` class.

2. Change `is_proc_invocation` to delegate:
   ```python
   @property
   def is_proc_invocation(self) -> bool:
       """
       True if step is a procedure invocation.

       Preferred internal name; externally ``is_procedure`` is the stable API.
       """
       return self.is_procedure
   ```

3. Run `pytest` — no test should change behaviour.

---

### TASK-11 · Review and document `DDStatement` property wrappers

**File:** `jclparser/model.py`  
**Risk:** None (no deletion — annotation only in this task)  
**Dependency:** TASK-10

**What exists:**

`DDStatement` exposes 18+ `@property` methods that each do nothing but
`return self.parameters.get('KEYNAME')`. These double the class surface without
adding behaviour.

**Steps:**

1. Open `jclparser/model.py`. List every `@property` in `DDStatement` that is a
   single-line `return self.parameters.get(...)` call.

2. Group them into two buckets and annotate each with a comment tag:

   - **Keep** (clearly valuable, commonly used): `dsn`, `disp`, `unit`, `vol`,
     `space`, `dcb`, `sysout`, `dummy`, `is_input`, `is_output`.
     No changes needed for these.

   - **Deprecation candidate** (low-value pass-through — can use
     `dd.parameters.get(...)` directly): any property that wraps an obscure or rarely
     used parameter key. Add a deprecation note in its docstring:
     ```
     .. deprecated::
         Use ``dd.parameters.get('KEYNAME')`` directly.
         This property will be removed in a future release.
     ```

3. Do **not** remove any properties in this task. The goal is only to mark intent so a
   later breaking-change release can safely drop them.

4. Run `pytest` — no test should change.

---

### TASK-12 · Adopt a tiered `__all__` in `__init__.py`

**File:** `jclparser/__init__.py`  
**Risk:** None (additive comments; no symbols removed)  
**Dependency:** TASK-11

**Goal:** Distinguish public surface from advanced/internal symbols so consumers know
what they can rely on.

**Steps:**

1. Open `jclparser/__init__.py`. Read the current `__all__` list.

2. Restructure `__all__` into three clearly labelled sections using inline comments:
   ```python
   __all__ = [
       # ── Tier 1: Stable public API ─────────────────────────────────────────
       'parse_jcl',
       'validate_jcl',
       'parse_statement',
       'Job', 'Step', 'DDStatement', 'Parameter', 'Statement',
       'JCLSyntaxError', 'JCLValidationError', 'JCLStructureError',
       'ParseError', 'ValidationError', 'ErrorType', 'ErrorSeverity',
       'ValidationLevel',

       # ── Tier 2: Advanced / power-user API ────────────────────────────────
       'explode_job',
       'ProcedureLoader', 'CompositeProcedureLoader', 'create_default_loader',
       'SystemSymbolProvider', 'ParserConfig',
       'SymbolScope',
       'validate_jcl_identifier', 'validate_dataset_name',
       'validate_job_structure', 'validate_step_structure',
       'validate_dd_statement',
       'FileType', 'detect_file_type', 'is_jcl_file', 'is_proc_file',

       # ── Tier 3: Internal / deprecation candidates ─────────────────────────
       # These are exported for backwards compatibility.
       # They may be removed in a future major version.
       'MockSystemSymbolProvider',
       'EnvironmentSystemSymbolProvider',
       'RuntimeSystemSymbolProvider',
       'get_default_provider', 'set_default_provider',
       'ExplosionRecord', 'ProcExpansionInfo',
       'InlineProcedureLoader', 'JCLLIBProcedureLoader',
       'SymbolScope',
       'UndefinedSymbolError', 'ExplosionDepthError',
       'CircularProcedureError', 'ProcedureNotFoundError',
       'substitute_symbols',
       'StatementPlugin', 'ValidationPlugin', 'PluginRegistry',
       'get_plugin_registry',
   ]
   ```
   Adjust to match the actual current exports exactly — do not add or remove symbols,
   only reorganise and comment.

3. Run `pytest` — no test should change.

---

## P4 — Test Suite Health

### TASK-13 · Create the target test directory structure

**Directory:** `tests/`  
**Risk:** None (new empty directories only)  
**Dependency:** TASK-12

**Steps:**

1. Create the target layout (empty `__init__.py` files where needed):
   ```
   tests/
     unit/
       __init__.py
     integration/
       __init__.py
   ```
   Run `pytest` to confirm the empty directories do not break collection.

---

### TASK-14 · Consolidate coverage-chase test files

**Files:** The six files named after "coverage" and "final push"  
**Risk:** Medium — must not delete tests that cover production code  
**Dependency:** TASK-13

**Files to consolidate:**
- `tests/test_coverage_boost.py`
- `tests/test_coverage_final.py`
- `tests/test_final_coverage.py`
- `tests/test_final_push_to_90.py`
- `tests/test_push_to_90.py` *(if present)*
- `tests/test_absolute_final.py`

**Steps:**

1. For each file above, run:
   ```
   pytest <filename> -v --collect-only
   ```
   Note the test function names and what code paths each test exercises.

2. Cross-reference against the canonical test files listed in step 4 below. Any test in
   the coverage-chase files that is **not duplicated** elsewhere must be moved, not
   deleted.

3. Create (or append to) the appropriate canonical test file:

   | Theme of the orphan test | Destination |
   |---|---|
   | `parse_jcl`, `parse_statement` | `tests/unit/test_parser.py` *(new)* |
   | `Job`, `Step`, `DDStatement` model | `tests/unit/test_model.py` *(new)* |
   | All validators                | `tests/unit/test_validators.py` *(new)* |
   | Continuation handling         | `tests/unit/test_continuation.py` *(new)* |
   | Explosion / SymbolScope       | `tests/unit/test_explosion.py` — **keep and rename existing `tests/test_explosion.py`** |
   | DCBParameter / SPACEParameter | `tests/unit/test_parameter_ast.py` — **keep and rename existing** |
   | Proc loaders                  | `tests/unit/test_proc_loader.py` *(new)* |
   | File-type detection           | `tests/unit/test_file_type.py` — **keep and rename existing `tests/test_jcl_file_type.py`** |
   | JCL compliance samples        | `tests/integration/test_jcl_compliance.py` — **keep existing** |
   | External proc filesystem      | `tests/integration/test_proc_loading.py` *(new from existing files)* |

4. After moving all orphan tests, run `pytest tests/unit/ tests/integration/ -v` to
   confirm they all pass.

5. Delete the now-empty coverage-chase files only after confirming no unique tests were
   lost:
   ```
   git diff --stat   # confirm only deletions of the six files listed above
   pytest            # full suite must still be green
   ```

---

### TASK-15 · Reorganise remaining scattered test files

**Files:** All remaining `tests/test_*.py` at the top level  
**Risk:** Low — move only, no logic changes  
**Dependency:** TASK-14

**Mapping (top-level → unit/ or integration/):**

| Current file | Destination |
|---|---|
| `test_parser_api.py` | `tests/unit/test_parser.py` (merge) |
| `test_parser_comprehensive.py` | `tests/unit/test_parser.py` (merge) |
| `test_parser_edge_cases.py` | `tests/unit/test_parser.py` (merge) |
| `test_model_api.py` | `tests/unit/test_model.py` (merge) |
| `test_model_comprehensive.py` | `tests/unit/test_model.py` (merge) |
| `test_parameter_ast.py` | `tests/unit/test_parameter_ast.py` (rename/move) |
| `test_parameter_validators.py` | `tests/unit/test_validators.py` (merge) |
| `test_parameter_integration.py` | `tests/integration/test_parameters.py` (new) |
| `test_continuation_enhanced.py` | `tests/unit/test_continuation.py` (rename/move) |
| `test_explosion.py` | `tests/unit/test_explosion.py` (rename/move) |
| `test_explosion_edge_cases.py` | `tests/unit/test_explosion.py` (merge) |
| `test_proc_loader.py` *(if exists)* | `tests/unit/test_proc_loader.py` (rename/move) |
| `test_external_proc_loading.py` | `tests/integration/test_proc_loading.py` (rename/move) |
| `test_external_proc_edge_cases.py` | `tests/integration/test_proc_loading.py` (merge) |
| `test_jcl_file_type.py` | `tests/unit/test_file_type.py` (rename/move) |
| `test_jcl_file_type_edge_cases.py` | `tests/unit/test_file_type.py` (merge) |
| `test_jcl_compliance.py` | `tests/integration/test_jcl_compliance.py` (rename/move) |
| `test_validators.py` *(if exists)* | `tests/unit/test_validators.py` (merge) |
| `test_integration.py` | `tests/integration/test_jcl_compliance.py` (merge candidates) |
| `test_job_parameters.py` | `tests/unit/test_parser.py` (merge) |
| `test_exec_parameters.py` | `tests/unit/test_parser.py` (merge) |
| `test_dd_basic_parameters.py` | `tests/unit/test_model.py` (merge) |
| `test_dd_all_parameters.py` | `tests/unit/test_model.py` (merge) |
| `test_dd_label_parameter.py` | `tests/unit/test_model.py` (merge) |
| `test_dd_sms_parameters.py` | `tests/unit/test_model.py` (merge) |
| `test_comprehensive_parsing.py` | `tests/unit/test_parser.py` (merge) |
| `test_edge_cases_coverage.py` | Distribute per theme above |
| `test_fixture_edge_cases.py` | Distribute per theme above |
| `test_missing_statements.py` | `tests/unit/test_parser.py` (merge) |

**Steps:**

1. Work file-by-file. For each source file:
   a. Open both the source and destination files.
   b. Copy the test functions into the destination, deduplicating any that are
      already present (same assertion logic, different name is still a duplicate).
   c. After the copy, run `pytest <destination_file> -v` to confirm nothing broke.
   d. Delete the source file.
   e. Run `pytest` (full suite) to confirm green.

2. After all moves are complete, update `pytest.ini` / `pyproject.toml` if the
   `testpaths` setting references the old flat layout.

3. Final verification:
   ```
   pytest --tb=short -q
   ```
   Must show zero failures and the same number of tests as before the reorganisation.

---

## Success Checklist

Before closing out the refactoring, confirm:

- [ ] `pytest` passes with **zero failures** after every completed task.
- [ ] No public API symbol has been silently removed (deprecations are OK).
- [ ] `_STATEMENT_TYPES` is defined exactly once in `parser.py`.
- [ ] `_read_source` / `read_source` logic exists in exactly one place.
- [ ] Dataset name and DISP validation rules have one canonical implementation.
- [ ] `Job.validate()` delegates to `validators.validate_job_structure()`.
- [ ] `JCLLIBProcedureLoader._cache` is initialised in `__init__`.
- [ ] `_explode_step` accepts and forwards `jcllib_order` correctly.
- [ ] Test files are organised by feature, not by coverage percentages.
- [ ] Coverage is maintained or improved (`pytest --cov=jclparser --cov-report=term-missing`).
