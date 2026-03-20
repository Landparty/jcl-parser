# JCL Parser — Algorithmic Performance Fixes

**Date:** 2026-03-20
**Status:** Approved
**Scope:** Pure algorithmic improvements to `jclparser/` — no API changes, no Cython, no dependencies added.

---

## Goals

Reduce parse time on real-world JCL files by fixing three algorithmic bottlenecks identified via static analysis. Establish pytest-benchmark baselines before the fixes so gains are measurable.

## Non-Goals

- Cython / C extensions
- Changes to public API (`parse_jcl`, `validate_jcl`, model classes)
- Fixes to explosion.py or proc_loader.py (deferred)

---

## Benchmarks (added first)

**Location:** `tests/benchmarks/test_benchmarks.py` (add fixtures to the existing file — do NOT create a new `tests/performance/` directory)
**Marker:** `benchmark` (existing marker used in `tests/benchmarks/`)
**Tool:** `pytest-benchmark` (already a dev dependency)

Three synthetic fixtures — no external files needed:

| Fixture | What it stresses | Shape |
|---|---|---|
| `large_dd_job` | Inline data multi-pass redundancy | 200-line job, 50 `DD *` blocks with inline data |
| `heavy_continuation_job` | Context re-analysis per continuation | 50 statements × 8–10 continuation lines, nested parens |
| `complex_parameters_job` | Join/append overhead per parameter | 100 statements × 10+ comma-separated keyword params |

Each benchmark calls `parse_jcl(source)`. pytest-benchmark records min/mean/stddev automatically.

Run with: `pytest -m benchmark --benchmark-only`

---

## Fix 1 — Single-Pass Inline Data Detection

**File:** `jclparser/parser.py`
**Lines affected:** 65–129

### Problem

Three separate passes over the line list:

1. **Pass 1** (`while` + inner `while`, lines 68–96): finds `DD *` / `DD DATA` statements and marks inline data lines into `inline_data_markers`
2. **Pass 2** (`for` loop, lines 104–107): builds `non_inline_lines` by filtering against `inline_data_markers`
3. **Pass 3** (`for` loop, lines 117–129): re-interleaves merged results with inline data using a stateful `inline_line_map` + `merged_idx` correlation — this is the most fragile part

The three-pass structure creates redundant bookkeeping (`inline_line_map`, `merged_idx`, the dict lookup on every line) and a brittle coordination contract between passes 2 and 3.

Note: this is not O(n²) — the inner `while` in pass 1 advances `i` past consumed inline lines. The concern is the 3-pass redundancy and the fragile `inline_line_map` state, not quadratic growth.

### Fix

Replace all three passes with a single `for` loop that simultaneously:
- Detects `DD *` / `DD DATA` (same conditions as pass 1), maintains `in_inline_data: bool` and `delimiter: str`
- Appends inline lines to `inline_data_markers` and regular lines to `non_inline_lines`

The `inline_line_map` dict and `merged_idx` state variable are eliminated entirely. After the single-pass separation, the continuation handler processes `non_inline_lines` normally. The final merged list is then rebuilt by iterating the original line list once more, substituting merged statements in sequence while reinserting inline data lines at their original positions — no index map is required because inline data line positions are recorded directly as a set during the single pass.

Output (`inline_data_markers`, `non_inline_lines`) is identical — only the traversal changes.

---

## Fix 2 — Continuation Context Caching

**File:** `jclparser/continuation_handler.py`

### Problem

In `merge_continuation_lines()`, the inner look-ahead loop calls `is_continuation_line(next_line, merged_line)` on every candidate line. This calls `_has_unclosed_context(merged_line)`, which calls `_analyze_line_context(merged_line)` — a full character-level scan of the entire accumulated `merged_line`. As continuations are appended, `merged_line` grows, so each check rescans a progressively longer string from the beginning.

For a statement spanning 10 continuations: 10 full rescans of strings of increasing length.

### Fix

Maintain a `cached_ctx: ContinuationContext` alongside `merged_line` in `merge_continuation_lines()`. After each continuation is appended, update `cached_ctx` incrementally by scanning **only the newly appended content — but starting from the cached context state**, not from a blank `ContinuationContext`.

**Critical implementation detail:** `_analyze_line_context` must accept an optional `starting_ctx: ContinuationContext = None` parameter. When provided, it initialises its scan state from `starting_ctx` rather than from `ContinuationContext()`. This is necessary because quote toggling is relative to prior state — scanning a suffix string in isolation (starting from the default `in_quotes=False`) would produce incorrect results for continuations that begin mid-quote or mid-paren. The starting context carries the correct `in_quotes` and `paren_depth` forward.

Add optional parameter to `is_continuation_line(line, previous_line, ctx=None)`: if `ctx` is provided, use it directly instead of calling `_has_unclosed_context()`. When `ctx` is supplied, it replaces **only** the `_has_unclosed_context(previous_line)` call — `_has_implicit_continuation(previous_line)` continues to use `previous_line` directly as before (it is a trivial `str.endswith(",")` check with no growing-string cost).

### Backward compatibility

Both signature changes use optional kwargs with defaults — fully backward-compatible.

---

## Fix 3 — Parameter Parsing Index Slicing

**File:** `jclparser/parser.py`
**Functions:** `_parse_parameters` (~line 708) and `_parse_list_parameter` (~line 813)

### Problem

In both functions, characters are appended one-by-one to `current_parts: list[str]`. At each comma boundary, `"".join(current_parts)` is called to materialise the parameter string — one join call per comma-separated parameter plus one at end-of-string. Each join is O(k) where k is the accumulated length.

`_parse_list_parameter` has the identical accumulation pattern and must be fixed alongside `_parse_parameters`.

### Fix

Replace `current_parts` list accumulation with index tracking in both functions:
- `start: int` records the start of the current parameter
- At each real comma boundary (`paren_depth == 0`, not in quotes): slice `param_string[start:i].strip()` directly
- After the loop: slice `param_string[start:].strip()`

`current_parts`, all `.append(char)` calls, and all `"".join(current_parts)` calls are removed from both functions. Quote tracking (`in_quotes`) and paren depth tracking remain unchanged — they are still needed to identify real comma boundaries.

---

## Implementation Order

1. Add benchmark fixtures to `tests/benchmarks/test_benchmarks.py` and run to establish baseline
2. Apply Fix 1 (single-pass inline data) — eliminates 3-pass redundancy
3. Apply Fix 2 (continuation context caching with stateful incremental update)
4. Apply Fix 3 (index slicing in `_parse_parameters` and `_parse_list_parameter`)
5. Re-run benchmarks and confirm improvement
6. Run full test suite (`pytest`) — all existing tests must pass

---

## Success Criteria

- All existing tests pass (`pytest` with no regressions)
- Benchmark numbers show measurable improvement on fixtures that directly exercise each fix:
  - `heavy_continuation_job`: measurable reduction in mean parse time (Fix 2 target)
  - `complex_parameters_job`: measurable reduction in mean parse time (Fix 3 target)
  - `large_dd_job`: reduced code complexity even if time gain is modest (Fix 1 target)
- Coverage remains ≥90%
