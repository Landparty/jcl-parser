# Dead & Duplicate Code Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove confirmed dead code and eliminate copy-pasted logic in the `jclparser` package, replacing duplicate implementations with single authoritative versions.

**Architecture:** Six self-contained tasks ordered from zero-risk deletions through moderate refactors. Each task passes the full 1200-test suite before and after. The most impactful changes are: removing the dead lazy-import machinery in `__init__.py`, giving `JCLStructureError` a real raise site, consolidating the three comma-splitting loops, unifying the two file-reading stacks, and making the deprecated `utils.merge_continuation_lines` a thin delegating wrapper.

**Tech Stack:** Python 3.13, pytest, jclparser package under `jclparser/`

---

### Task 1: Delete dead `_LAZY` / `__getattr__` block from `__init__.py`

**Files:**
- Modify: `jclparser/__init__.py:160-191`

All symbols listed in `_LAZY` are already eagerly imported at the top of the file (lines 31–43). Python's attribute lookup finds them in `__dict__` before ever calling `__getattr__`, making this entire block dead by construction.

- [ ] **Step 1: Confirm the block is dead with a smoke test**

```bash
python -c "
import jclparser
# Every symbol in _LAZY must already be accessible before we delete anything
assert hasattr(jclparser, 'explode_job')
assert hasattr(jclparser, 'SymbolScope')
assert hasattr(jclparser, 'ProcedureLoader')
assert hasattr(jclparser, 'SystemSymbolProvider')
print('All symbols already accessible via eager imports — safe to delete _LAZY')
"
```

- [ ] **Step 2: Delete the dead block**

In `jclparser/__init__.py`, remove everything from the comment on line 160 through the end of `__getattr__` on line 191:

```python
# DELETE from here:
# Lazy import map for heavy / optional symbols not imported at the top level
_LAZY: dict = {
    ...
}


def __getattr__(name: str):
    ...
# DELETE to here (inclusive)
```

The file should end after the `parse()` convenience function on line 157.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -q --no-cov
```

Expected: `1216 passed, 2 skipped`

- [ ] **Step 4: Commit**

```bash
rtk git add jclparser/__init__.py && rtk git commit -m "refactor: remove dead lazy-import machinery from __init__.py"
```

---

### Task 2: Delete dead `SYMBOL_PATTERN` constant from `explosion.py`

**Files:**
- Modify: `jclparser/explosion.py:25-26`

`SYMBOL_PATTERN` was superseded by `_SYMBOL_SUB_PATTERN` during a refactor. It is never referenced anywhere in the codebase. The "backwards compatibility" comment is aspirational — it is not part of any public API surface.

- [ ] **Step 1: Verify zero references**

```bash
grep -rn "SYMBOL_PATTERN" jclparser/ tests/
```

Expected output: only the definition line itself (`explosion.py:26`). If any other file references it, do not delete.

- [ ] **Step 2: Delete the constant and its comment**

In `jclparser/explosion.py`, remove lines 25–26:

```python
# DELETE these two lines:
# Regex pattern for symbolic parameters (kept for backwards compatibility)
SYMBOL_PATTERN = re.compile(r'&([A-Z0-9@#$]+)')
```

Leave `_SYMBOL_SUB_PATTERN` on the next line untouched.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -q --no-cov
```

Expected: `1216 passed, 2 skipped`

- [ ] **Step 4: Commit**

```bash
rtk git add jclparser/explosion.py && rtk git commit -m "refactor: remove dead SYMBOL_PATTERN constant from explosion.py"
```

---

### Task 3: Give `JCLStructureError` a real raise site in `parser.py`

**Files:**
- Modify: `jclparser/parser.py:12-15` (imports), `jclparser/parser.py` (strict-mode block ~line 397)
- Test: `tests/unit/test_parser_api.py`

`JCLStructureError` is a Tier-1 public API export that is never raised anywhere. The right fix is to raise it — not remove it. The structural violation that best fits is: in `strict_mode=True`, a DD statement appears before any EXEC step in the job (currently the parser silently produces a job with 0 steps for this case).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_parser_api.py`:

```python
def test_dd_before_exec_strict_raises_structure_error():
    """In strict mode, a DD before any EXEC should raise JCLStructureError."""
    from jclparser.errors import JCLStructureError
    jcl = "//BADJOB   JOB (ACCT),'TEST'\n//DD1      DD DSN=MY.DATA,DISP=SHR\n"
    with pytest.raises(JCLStructureError):
        parse_jcl(jcl, strict_mode=True)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/unit/test_parser_api.py::test_dd_before_exec_strict_raises_structure_error -v --no-cov
```

Expected: `FAILED` — `JCLStructureError` is not raised yet.

- [ ] **Step 3: Add `JCLStructureError` to the imports in `parser.py`**

Change lines 12–15 of `jclparser/parser.py` from:

```python
from .errors import (
    JCLSyntaxError, JCLValidationError, ParseError,
    ErrorType, ErrorSeverity
)
```

to:

```python
from .errors import (
    JCLSyntaxError, JCLValidationError, JCLStructureError,
    ParseError, ErrorType, ErrorSeverity
)
```

- [ ] **Step 4: Raise `JCLStructureError` in the strict-mode validation block**

Find the block in `jclparser/parser.py` near line 397 that reads:

```python
    # Validate the parsed job if in strict mode
    if strict_mode:
        validation_errors = job.validate()
        if validation_errors:
```

Directly **before** that block, insert:

```python
    # In strict mode, a DD statement with no preceding EXEC is a structural error
    if strict_mode and not job.steps:
        # Check if the source contained any DD statements (orphaned DDs)
        has_dd = any(
            stmt.type == "DD"
            for stmt in job.raw_statements
            if hasattr(stmt, "type")
        )
        if has_dd:
            raise JCLStructureError(
                "DD statement found before any EXEC step. "
                "Each DD must belong to a step."
            )
```

- [ ] **Step 5: Check how `raw_statements` is stored**

```bash
grep -n "raw_statements\|self\.statements\|job\.statements" jclparser/parser.py | head -20
grep -n "raw_statements" jclparser/model.py | head -10
```

If `job.raw_statements` does not exist, use the parsed `statements` list instead. Look for the attribute name in the `Job` model and adjust the code in Step 4 to match. If the Job model stores parsed statements under a different name (e.g., `job._statements` or the parser keeps them in a local variable), use the local `statements` variable that is available in the `parse_jcl` scope before the `Job` object is returned.

The safest fallback if no statement list is available:

```python
    # In strict mode, DD statements before any EXEC are a structural error
    if strict_mode and not job.steps:
        source_content = read_source(source) if not isinstance(source, str) else source
        lines = source_content.splitlines()
        dd_lines = [l for l in lines if l.lstrip().startswith("//") and
                    len(l) > 2 and not l.lstrip().startswith("//*")]
        has_dd = any(
            len(parts := l.split()) >= 2 and parts[1].upper() == "DD"
            for parts in [l.split() for l in dd_lines]
        )
        if has_dd:
            raise JCLStructureError(
                "DD statement found before any EXEC step. "
                "Each DD must belong to a step."
            )
```

- [ ] **Step 6: Run the new test**

```bash
pytest tests/unit/test_parser_api.py::test_dd_before_exec_strict_raises_structure_error -v --no-cov
```

Expected: `PASSED`

- [ ] **Step 7: Run the full suite**

```bash
pytest -q --no-cov
```

Expected: `1217 passed, 2 skipped`

- [ ] **Step 8: Commit**

```bash
rtk git add jclparser/parser.py tests/unit/test_parser_api.py && rtk git commit -m "feat: raise JCLStructureError in strict mode for DD before EXEC"
```

---

### Task 4: Make `utils.merge_continuation_lines` delegate to `ContinuationLineHandler`

**Files:**
- Modify: `jclparser/utils.py:374-424`

The deprecated `utils.merge_continuation_lines` re-implements the same merging algorithm as `ContinuationLineHandler`. The fix: replace the full implementation with a one-liner that calls the handler and strips line numbers from the richer `List[Tuple[str, int]]` return value.

- [ ] **Step 1: Run existing continuation tests to establish baseline**

```bash
pytest tests/unit/test_continuation.py tests/unit/test_utils.py tests/unit/test_utils_comprehensive.py -q --no-cov
```

Expected: all pass. Note the exact count.

- [ ] **Step 2: Replace the body of `utils.merge_continuation_lines`**

In `jclparser/utils.py`, replace the full function body (lines 389–424, everything after the docstring) with a delegation call. The function currently looks like:

```python
def merge_continuation_lines(lines: List[str]) -> List[str]:
    """
    Merge JCL continuation lines into complete statements.
    ...
    """
    merged_lines = []
    current_parts: list[str] = []
    # ... 30+ lines of implementation ...
    return merged_lines
```

Replace with:

```python
def merge_continuation_lines(lines: List[str]) -> List[str]:
    """
    Merge JCL continuation lines into complete statements.

    .. deprecated::
        Superseded by :class:`jclparser.continuation_handler.ContinuationLineHandler`,
        which correctly handles all edge-cases defined in z/OS JCL syntax rules.
        Use that class for new code.

    Args:
        lines: List of raw JCL lines

    Returns:
        List of complete JCL statements
    """
    from .continuation_handler import merge_continuation_lines as _handler_merge
    return [merged for merged, _lineno in _handler_merge(lines)]
```

- [ ] **Step 3: Run the tests again**

```bash
pytest tests/unit/test_continuation.py tests/unit/test_utils.py tests/unit/test_utils_comprehensive.py -q --no-cov
```

Expected: same count as Step 1, all pass.

- [ ] **Step 4: Run the full suite**

```bash
pytest -q --no-cov
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
rtk git add jclparser/utils.py && rtk git commit -m "refactor: utils.merge_continuation_lines delegates to ContinuationLineHandler"
```

---

### Task 5: Consolidate file-reading into `utils._read_file` with encoding fallback

**Files:**
- Modify: `jclparser/utils.py:90-127` (`read_source`)
- Modify: `jclparser/jcl_file_type.py:211-243` (`_read_file`)

`utils.read_source` reads files using only `utf-8`. `jcl_file_type._read_file` has a superior multi-encoding fallback (`utf-8 → latin-1 → cp1252 → binary`). The fix: extract that fallback logic into a private helper `utils._read_file_with_fallback`, use it in `utils.read_source`, and have `jcl_file_type._read_file` delegate to it.

- [ ] **Step 1: Run file-type and parser tests to establish baseline**

```bash
pytest tests/unit/test_file_type.py tests/unit/test_file_type_edge_cases.py tests/integration/ -q --no-cov
```

Expected: all pass. Note the count.

- [ ] **Step 2: Add `_read_file_with_fallback` to `utils.py` and update `read_source`**

In `jclparser/utils.py`, add the following private helper immediately before `read_source` (before line 90):

```python
def _read_file_with_fallback(path: Path) -> str:
    """
    Read a file trying utf-8, latin-1, cp1252, then binary fallback.

    Args:
        path: Existing file path (caller must verify existence).

    Returns:
        File content as a string.
    """
    for encoding in ('utf-8', 'latin-1', 'cp1252'):
        try:
            with open(path, 'r', encoding=encoding) as fh:
                return fh.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Last resort: binary decode with replacement
    with open(path, 'rb') as fh:
        return fh.read().decode('utf-8', errors='ignore')
```

Then update `read_source` to use the new helper. Replace the two `with open(...)` blocks inside `read_source` (the ones that use `encoding='utf-8'`) with calls to `_read_file_with_fallback`:

```python
def read_source(source: Union[str, Path, Any]) -> str:
    """
    Resolve a JCL source (string content, file path, or file-like object) into a
    string of JCL content.

    Runtime-critical — used by the main parse path.

    Args:
        source: JCL content as string, a :class:`pathlib.Path`, or any file-like
                object with a ``read()`` method.

    Returns:
        String of JCL content.

    Raises:
        FileNotFoundError: If *source* is a path to a file that does not exist.
    """
    if isinstance(source, Path):
        if not source.exists():
            raise FileNotFoundError(f"JCL file not found: {source}")
        return _read_file_with_fallback(source)
    if isinstance(source, str):
        # Treat as a file path when it looks like one
        if source.endswith('.jcl') or (
            ('/' in source or '\\' in source) and not source.strip().startswith('//')
        ):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"JCL file not found: {path}")
            return _read_file_with_fallback(path)
        return source
    # File-like object
    content = source.read()
    if hasattr(source, 'seek'):
        source.seek(0)
    return content
```

- [ ] **Step 3: Update `jcl_file_type._read_file` to delegate**

In `jclparser/jcl_file_type.py`, replace the full body of `_read_file` (lines 211–243) with:

```python
def _read_file(path: Path) -> str:
    """
    Read content from a file path.

    Args:
        path: Path to file

    Returns:
        File content as string

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    from .utils import _read_file_with_fallback
    return _read_file_with_fallback(path)
```

- [ ] **Step 4: Run all tests**

```bash
pytest -q --no-cov
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
rtk git add jclparser/utils.py jclparser/jcl_file_type.py && rtk git commit -m "refactor: consolidate multi-encoding file reading into utils._read_file_with_fallback"
```

---

### Task 6: Consolidate comma-splitting in `parser._parse_parameters`

**Files:**
- Modify: `jclparser/parser.py:700-801` (`_parse_parameters`)

`_parse_parameters` contains an inline quote/paren-tracking loop (lines 724–752) that is the third independent copy of the splitting logic already in `ParameterParser._split_parameters` (the canonical version) and `_parse_list_parameter`. The fix: replace the inline loop with a call to `ParameterParser._split_parameters`, keeping the balance validation (unclosed quote / unmatched parens) as a lean pre-check.

Note: `_parse_list_parameter` preserves empty positional subfields (for `DISP=(,CATLG)`) — this is intentionally different behaviour and is **not** changed.

- [ ] **Step 1: Run parser tests to establish baseline**

```bash
pytest tests/unit/test_parser_api.py tests/unit/test_parser_comprehensive.py tests/unit/test_parser_edge_cases.py tests/unit/test_parser_final_push.py -q --no-cov
```

Expected: all pass. Note the count.

- [ ] **Step 2: Add a balance-checking helper just before `_parse_parameters`**

In `jclparser/parser.py`, add the following helper directly above `_parse_parameters` (before line 700):

```python
def _check_param_balance(param_string: str, line_number: int) -> None:
    """Validate that *param_string* has balanced quotes and parentheses.

    Raises JCLSyntaxError with a descriptive message on the first imbalance
    detected.  Does not return a value.
    """
    in_quotes = False
    paren_depth = 0
    i = 0
    while i < len(param_string):
        c = param_string[i]
        if c == "'":
            if in_quotes and i + 1 < len(param_string) and param_string[i + 1] == "'":
                i += 2
                continue
            in_quotes = not in_quotes
        elif c == "(" and not in_quotes:
            paren_depth += 1
        elif c == ")" and not in_quotes:
            paren_depth -= 1
        i += 1
    if in_quotes:
        raise JCLSyntaxError(
            f"Unclosed quote in parameter: {param_string}", line_number
        )
    if paren_depth != 0:
        hint = (
            " (statement may have been truncated at column 71 —"
            " use JCL continuation lines to break long statements"
            " across multiple records)"
        )
        raise JCLSyntaxError(
            f"Unmatched parentheses in parameter: {param_string}{hint}",
            line_number,
        )
```

- [ ] **Step 3: Replace the inline splitting loop in `_parse_parameters`**

In `_parse_parameters`, the section from the comment `# Enhanced parameter parsing...` through `# Check for unmatched parentheses` (approximately lines 723–766) currently looks like:

```python
    # Enhanced parameter parsing with better list and parentheses handling
    parts = []
    in_quotes = False
    paren_depth = 0
    start = 0

    i = 0
    while i < len(param_string):
        char = param_string[i]
        if char == "'":
            if in_quotes and i + 1 < len(param_string) and param_string[i + 1] == "'":
                i += 2
                continue
            in_quotes = not in_quotes
        elif char == "(" and not in_quotes:
            paren_depth += 1
        elif char == ")" and not in_quotes:
            paren_depth -= 1
        elif char == "," and not in_quotes and paren_depth == 0:
            current = param_string[start:i].strip()
            if current:
                parts.append(current)
            start = i + 1
        i += 1

    current = param_string[start:].strip()
    if current:
        parts.append(current)

    # Check for unclosed quotes
    if in_quotes:
        raise JCLSyntaxError(f"Unclosed quote in parameter: {param_string}", line_number)

    # Check for unmatched parentheses
    if paren_depth != 0:
        hint = (
            " (statement may have been truncated at column 71 —"
            " use JCL continuation lines to break long statements across multiple records)"
        )
        raise JCLSyntaxError(
            f"Unmatched parentheses in parameter: {param_string}{hint}", line_number
        )
```

Replace that entire block with:

```python
    # Validate balance then split using the canonical ParameterParser implementation
    _check_param_balance(param_string, line_number)
    global _PARAMETER_PARSER
    if _PARAMETER_PARSER is None:
        from .parameter_ast import ParameterParser
        _PARAMETER_PARSER = ParameterParser()
    parts = _PARAMETER_PARSER._split_parameters(param_string)
```

The `_PARAMETER_PARSER` module-level cache is already used by `utils.split_jcl_parameters`; check that it is also declared at module level in `parser.py` (or import from utils). If `parser.py` does not already have `_PARAMETER_PARSER = None` at module level, add:

```python
# Module-level cache for the ParameterParser singleton used in _parse_parameters
_PARAMETER_PARSER = None
```

near the top of `parser.py` (after the imports).

- [ ] **Step 4: Run the parser tests**

```bash
pytest tests/unit/test_parser_api.py tests/unit/test_parser_comprehensive.py tests/unit/test_parser_edge_cases.py tests/unit/test_parser_final_push.py -q --no-cov
```

Expected: same count as Step 1, all pass.

- [ ] **Step 5: Run the full suite**

```bash
pytest -q --no-cov
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
rtk git add jclparser/parser.py && rtk git commit -m "refactor: _parse_parameters delegates comma-splitting to ParameterParser._split_parameters"
```

---

## Self-Review

### Spec coverage check

| Finding from audit | Task that addresses it |
|---|---|
| `_LAZY` / `__getattr__` dead | Task 1 |
| `SYMBOL_PATTERN` dead | Task 2 |
| `JCLStructureError` never raised | Task 3 |
| `utils.merge_continuation_lines` re-implements handler | Task 4 |
| Source-reading duplicated between `utils` and `jcl_file_type` | Task 5 |
| Comma-splitting duplicated in `_parse_parameters` | Task 6 |
| `JCLParseError` base class exported but not catchable | **Left alone** — removing a base class from a public exception hierarchy is a breaking change; keeping it is correct practice |
| `ParameterValidator` / `validate_parameter_syntax` not in public API but tested | **Left alone** — they have direct test coverage; removing tested public symbols requires a deprecation cycle |
| `_parse_list_parameter` third copy of split loop | **Left alone** — its empty-slot preservation semantics are intentionally different; merging would change `DISP=(,CATLG)` behaviour |

### Placeholder scan

No TBDs, no "implement later", no open-ended steps. Every step contains exact file paths and complete code.

### Type consistency

- `_read_file_with_fallback(path: Path) -> str` defined in Task 5 Step 2 and called in Task 5 Steps 2 and 3 — consistent.
- `_check_param_balance(param_string: str, line_number: int) -> None` defined in Task 6 Step 2 and called in Task 6 Step 3 — consistent.
- `_PARAMETER_PARSER` cache — already used in `utils.py`; Task 6 adds the same pattern to `parser.py` — consistent.
