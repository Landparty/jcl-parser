# JCL Parser Algorithmic Performance Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three algorithmic bottlenecks in the JCL parser (inline data multi-pass, continuation context re-analysis, parameter join overhead) with benchmark baselines established first.

**Architecture:** Add synthetic benchmark fixtures to measure the hot paths; then apply three focused refactors — single-pass inline data detection in `parser.py`, incremental context caching in `continuation_handler.py`, and index-slice parameter splitting in both parse functions. All changes are internal; public API is unchanged.

**Tech Stack:** Python 3.13, pytest, pytest-benchmark

**Spec:** `docs/superpowers/specs/2026-03-20-jcl-parser-algorithmic-fixes-design.md`

---

## File Map

| File | Change |
|---|---|
| `tests/benchmarks/test_benchmarks.py` | Add 3 new benchmark fixtures |
| `tests/unit/test_algorithmic_fixes.py` | New — characterization tests for all 3 fixes |
| `jclparser/continuation_handler.py` | Fix 2 — context caching |
| `jclparser/parser.py` | Fix 1 (lines 65–129) + Fix 3 (lines 708–810, 813–862) |

---

## Task 1: Add Benchmark Fixtures (Baseline)

**Files:**
- Modify: `tests/benchmarks/test_benchmarks.py`

- [ ] **Step 1: Append the three new JCL fixture strings and benchmark functions**

Add below the last existing fixture/benchmark in `tests/benchmarks/test_benchmarks.py`:

```python
# ---------------------------------------------------------------------------
# Algorithmic-fix benchmark fixtures
# ---------------------------------------------------------------------------

_LARGE_DD_JCL = "//DDJOB    JOB CLASS=A\n" + "".join(
    f"//STEP{i:02d}   EXEC PGM=IEFBR14\n"
    f"//DD{i:02d}     DD   *\n"
    f"DATA LINE {i}\n"
    "/*\n"
    for i in range(1, 51)
)

_HEAVY_CONTINUATION_JCL = "//CONTJOB  JOB CLASS=A\n" + "".join(
    f"//STEP{i:02d}   EXEC PGM=IEFBR14\n"
    f"//DD{i:02d}     DD   DSN=MY.DATASET.{i:02d},\n"
    f"//             DISP=(NEW,CATLG,DELETE),\n"
    f"//             SPACE=(CYL,(10,5),RLSE),\n"
    f"//             DCB=(RECFM=FB,\n"
    f"//             LRECL=80,\n"
    f"//             BLKSIZE=27920,\n"
    f"//             BUFNO=10,\n"
    f"//             DSORG=PS),\n"
    f"//             UNIT=SYSDA\n"
    for i in range(1, 51)
)

_COMPLEX_PARAMS_JCL = "//PARAMJOB  JOB CLASS=A\n" + "".join(
    f"//STEP{i:03d}  EXEC PGM=IEFBR14\n"
    f"//DD{i:03d}    DD   DSN=MY.DS.{i:03d},DISP=(NEW,CATLG,DELETE),"
    f"SPACE=(CYL,(10,5),RLSE),DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920),"
    f"UNIT=SYSDA,LABEL=(1,SL),RETPD=30\n"
    for i in range(1, 101)
)


@pytest.mark.benchmark
def test_parse_large_dd_job(benchmark):
    """Benchmark: 50 DD * inline data blocks (targets inline data scan)."""
    benchmark(parse_jcl, _LARGE_DD_JCL)


@pytest.mark.benchmark
def test_parse_heavy_continuation_job(benchmark):
    """Benchmark: 50 steps × 9 continuation lines each (targets context re-analysis)."""
    benchmark(parse_jcl, _HEAVY_CONTINUATION_JCL)


@pytest.mark.benchmark
def test_parse_complex_params_job(benchmark):
    """Benchmark: 100 steps × 7 keyword parameters each (targets join overhead)."""
    benchmark(parse_jcl, _COMPLEX_PARAMS_JCL)
```

- [ ] **Step 2: Run benchmarks to capture baseline**

```bash
pytest tests/benchmarks/ --benchmark-only -v
```

Expected: All benchmark tests pass, numbers printed. Note the `mean` for `test_parse_large_dd_job`, `test_parse_heavy_continuation_job`, and `test_parse_complex_params_job` — these are your baseline.

- [ ] **Step 3: Commit**

```bash
rtk git add tests/benchmarks/test_benchmarks.py
rtk git commit -m "perf: add benchmark fixtures for three algorithmic hot paths"
```

---

## Task 2: Characterization Tests for All Three Fixes

These verify the exact behaviors we're about to refactor — if they pass before the fix they will serve as regression guards after.

**Files:**
- Create: `tests/unit/test_algorithmic_fixes.py`

- [ ] **Step 1: Create the test file**

```python
"""
Characterization tests for the three algorithmic fixes.
These exercise the specific scenarios each fix targets and act as
regression guards ensuring refactored code produces identical output.
"""
import pytest
from jclparser import parse_jcl
from jclparser.continuation_handler import ContinuationLineHandler, ContinuationContext


@pytest.mark.unit
class TestInlineDataOrdering:
    """Fix 1: DD * inline data must not be merged with surrounding statements."""

    def test_statement_after_inline_data_is_parsed(self):
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=SORT\n"
            "//SYSIN    DD   *\n"
            "  SORT FIELDS=(1,10,CH,A)\n"
            "  RECORD TYPE=F\n"
            "/*\n"
            "//SYSOUT   DD   SYSOUT=*\n"
        )
        job = parse_jcl(jcl)
        dd_names = [dd.name for dd in job.steps[0].dd_statements]
        assert "SYSIN" in dd_names
        assert "SYSOUT" in dd_names

    def test_multiple_inline_data_blocks_interleaved(self):
        """50 DD * blocks — all steps must be parsed correctly."""
        jcl = "//DDJOB    JOB CLASS=A\n" + "".join(
            f"//STEP{i:02d}   EXEC PGM=IEFBR14\n"
            f"//DD{i:02d}     DD   *\n"
            f"DATA LINE {i}\n"
            "/*\n"
            for i in range(1, 6)
        )
        job = parse_jcl(jcl)
        assert len(job.steps) == 5
        for i, step in enumerate(job.steps, 1):
            assert len(step.dd_statements) == 1
            assert step.dd_statements[0].name == f"DD{i:02d}"

    def test_custom_delimiter_inline_data(self):
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=SORT\n"
            "//SYSIN    DD   DATA,DLM=@@\n"
            "  SORT FIELDS=(1,10,CH,A)\n"
            "@@\n"
            "//SYSOUT   DD   SYSOUT=*\n"
        )
        job = parse_jcl(jcl)
        dd_names = [dd.name for dd in job.steps[0].dd_statements]
        assert "SYSOUT" in dd_names


@pytest.mark.unit
class TestContinuationContextCaching:
    """Fix 2: Context caching must produce identical merged output."""

    def test_multi_continuation_with_nested_parens(self):
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//DD1      DD   DSN=MY.DATASET,\n"
            "//              DISP=(NEW,CATLG,DELETE),\n"
            "//              SPACE=(CYL,(10,5),RLSE),\n"
            "//              DCB=(RECFM=FB,\n"
            "//              LRECL=80,\n"
            "//              BLKSIZE=27920)\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["DSN"] == "MY.DATASET"
        assert dd.parameters["DISP"] == ["NEW", "CATLG", "DELETE"]
        assert "BLKSIZE" in str(dd.parameters.get("DCB", ""))

    def test_analyze_line_context_accepts_starting_ctx(self):
        """_analyze_line_context must accept and use a starting_ctx parameter."""
        handler = ContinuationLineHandler()
        # Simulate mid-quote state: starting inside a quote
        starting = ContinuationContext(in_quotes=True, paren_depth=0)
        ctx = handler._analyze_line_context("VALUE'", starting_ctx=starting)
        # Starting in-quotes, then hits a quote -> toggles back to not-in-quotes
        assert ctx.in_quotes is False

    def test_is_continuation_line_accepts_ctx(self):
        """is_continuation_line must accept ctx kwarg and use it."""
        handler = ContinuationLineHandler()
        # Unclosed paren context: should treat indented line as continuation
        open_ctx = ContinuationContext(in_quotes=False, paren_depth=1)
        result = handler.is_continuation_line(
            "//              LRECL=80,",
            previous_line="//DD1      DD   DCB=(RECFM=FB,",
            ctx=open_ctx,
        )
        assert result is True


@pytest.mark.unit
class TestParameterIndexSlicing:
    """Fix 3: Index-slice approach must produce identical parameter dicts."""

    def test_many_keyword_params_parsed_correctly(self):
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//DD1      DD   DSN=MY.DS,DISP=(NEW,CATLG,DELETE),"
            "SPACE=(CYL,(10,5),RLSE),DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920),"
            "UNIT=SYSDA,LABEL=(1,SL),RETPD=30\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["DSN"] == "MY.DS"
        assert dd.parameters["UNIT"] == "SYSDA"
        assert dd.parameters["RETPD"] == "30"
        assert dd.parameters["DISP"] == ["NEW", "CATLG", "DELETE"]

    def test_quoted_value_with_embedded_comma(self):
        """Quoted values containing commas must not be split."""
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//DD1      DD   DSN=MY.DS,LABEL='A,B',UNIT=SYSDA\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["LABEL"] == "A,B"
        assert dd.parameters["UNIT"] == "SYSDA"

    def test_escaped_quotes_in_value(self):
        """Escaped '' inside quotes must collapse to a single quote."""
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//DD1      DD   DSN=MY.DS,LABEL='IT''S OK',UNIT=SYSDA\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["LABEL"] == "IT'S OK"
```

- [ ] **Step 2: Run the new tests — they must ALL pass before any fix is applied**

```bash
pytest tests/unit/test_algorithmic_fixes.py -v
```

Expected: All tests pass **except** the two new API tests (`test_analyze_line_context_accepts_starting_ctx` and `test_is_continuation_line_accepts_ctx`) which will raise `TypeError: unexpected keyword argument` because the new optional parameters don't exist yet. That is expected — they are written test-first for Fix 2. You will see `ERROR` (not `FAILED`) for these two tests.

- [ ] **Step 3: Commit the test file**

```bash
rtk git add tests/unit/test_algorithmic_fixes.py
rtk git commit -m "test: add characterization tests for three algorithmic fixes"
```

---

## Task 3: Fix 1 — Single-Pass Inline Data Detection

**Files:**
- Modify: `jclparser/parser.py` (lines 65–129)

- [ ] **Step 1: Replace the three-pass block with a single pass**

In `parser.py`, find and replace the entire block from the comment `# First pass: handle inline data sections` (line 65) through the end of the re-interleave loop (line 130, the blank line after `merged_idx += 1`).

Replace it with:

```python
    # Single pass: separate inline data lines from regular lines.
    # Simultaneously records which original indices are inline data
    # and builds the non-inline list for continuation merging.
    inline_data_indices: set[int] = set()
    non_inline_lines: list[str] = []
    non_inline_orig_indices: list[int] = []  # parallel to non_inline_lines
    in_inline_data = False
    delimiter = "/*"

    for i, line in enumerate(lines):
        if in_inline_data:
            inline_data_indices.add(i)
            if line.strip() == delimiter or line.strip().startswith(delimiter):
                in_inline_data = False
        else:
            if line.strip() and line.startswith("//") and not line.strip().startswith("//*"):
                upper_line = line.upper()
                if " DD " in upper_line or " DD*" in upper_line or "\tDD\t" in upper_line:
                    if (" DD *" in upper_line or " DD*" in upper_line or
                            " DD DATA" in upper_line or "\tDD\t*" in upper_line or
                            ",DLM=" in upper_line):
                        delimiter = "/*"
                        if "DLM=" in upper_line:
                            dlm_start = upper_line.index("DLM=") + 4
                            dlm_end = dlm_start
                            while dlm_end < len(upper_line) and upper_line[dlm_end] not in ",) \t\r\n":
                                dlm_end += 1
                            delimiter = line[dlm_start:dlm_end]
                        in_inline_data = True
            non_inline_lines.append(line)
            non_inline_orig_indices.append(i)

    # Merge continuation lines on the non-inline subset only.
    handler = ContinuationLineHandler()
    merged_non_inline = handler.merge_continuation_lines(non_inline_lines)

    # Recombine: build lookup of orig_idx -> merged_line for group-start lines only.
    # Continuation lines that were folded into a group are simply absent from this map
    # and will be skipped in the loop below — which is correct.
    merged_start: dict[int, str] = {}
    for merged_line, ni_line_num in merged_non_inline:
        orig_idx = non_inline_orig_indices[ni_line_num - 1]
        merged_start[orig_idx] = merged_line

    merged_lines: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        if i in inline_data_indices:
            merged_lines.append((line, i + 1))
        elif i in merged_start:
            merged_lines.append((merged_start[i], i + 1))
```

Also update the **second reference** to `inline_data_markers` at `parser.py` line 164 (inside the main parse loop). Change:

```python
if (line_num - 1) in inline_data_markers:
```

to:

```python
if (line_num - 1) in inline_data_indices:
```

The variables `inline_line_map` and `merged_idx` are eliminated by the replacement above — no further action needed for those.

- [ ] **Step 2: Run the full test suite**

```bash
pytest tests/ -x -q --no-header
```

Expected: All tests pass. Pay special attention to any inline data tests in `tests/unit/test_algorithmic_fixes.py` and `tests/unit/test_parser_comprehensive.py`.

- [ ] **Step 3: Run benchmarks to see Fix 1 impact**

```bash
pytest tests/benchmarks/ --benchmark-only --benchmark-columns=mean,stddev -v
```

Note the new mean for `test_parse_large_dd_job` vs baseline.

- [ ] **Step 4: Commit**

```bash
rtk git add jclparser/parser.py
rtk git commit -m "perf: collapse 3-pass inline data detection into single pass"
```

---

## Task 4: Fix 2 — Continuation Context Caching

**Files:**
- Modify: `jclparser/continuation_handler.py`

- [ ] **Step 1: Add `Optional` to the typing import**

Change line 7:
```python
from typing import List, Tuple
```
to:
```python
from typing import List, Optional, Tuple
```

- [ ] **Step 2: Add `starting_ctx` parameter to `_analyze_line_context`**

Replace the `_analyze_line_context` method body (currently starts at line 219) with:

```python
    def _analyze_line_context(
        self, line: str, starting_ctx: Optional[ContinuationContext] = None
    ) -> ContinuationContext:
        """
        Analyze a line to determine if it has unclosed quotes/parens.

        Args:
            line: Line to analyze
            starting_ctx: Optional starting state. When provided the scan
                continues from this context rather than from a blank state.
                Used for incremental updates in merge_continuation_lines().

        Returns:
            ContinuationContext with state information
        """
        if starting_ctx is not None:
            ctx = ContinuationContext(
                in_quotes=starting_ctx.in_quotes,
                paren_depth=starting_ctx.paren_depth,
                bracket_depth=starting_ctx.bracket_depth,
                last_char=starting_ctx.last_char,
                is_complete=False,
            )
        else:
            ctx = ContinuationContext()

        i = 0
        while i < len(line):
            char = line[i]

            if char == "'" and ctx.last_char != "\\":
                # Handle escaped quotes
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 2  # Skip escaped quote
                    continue
                ctx.in_quotes = not ctx.in_quotes

            elif not ctx.in_quotes:
                if char == "(":
                    ctx.paren_depth += 1
                elif char == ")":
                    ctx.paren_depth -= 1
                elif char == "[":
                    ctx.bracket_depth += 1
                elif char == "]":
                    ctx.bracket_depth -= 1

            ctx.last_char = char
            i += 1

        ctx.is_complete = (
            not ctx.in_quotes and ctx.paren_depth == 0 and ctx.bracket_depth == 0
        )

        return ctx
```

- [ ] **Step 3: Add `ctx` parameter to `is_continuation_line`**

Replace the `is_continuation_line` method signature and the `_has_unclosed_context` call inside it. Find:

```python
    def is_continuation_line(self, line: str, previous_line: str = "") -> bool:
```

Replace with:

```python
    def is_continuation_line(
        self, line: str, previous_line: str = "", ctx: Optional[ContinuationContext] = None
    ) -> bool:
```

Then inside the method, find:

```python
        has_implicit_continuation = self._has_implicit_continuation(previous_line)
        has_unclosed_context = self._has_unclosed_context(previous_line)
```

Replace with:

```python
        has_implicit_continuation = self._has_implicit_continuation(previous_line)
        # Use provided context if available (avoids re-scanning the full merged line).
        # ctx replaces only the _has_unclosed_context check; implicit continuation
        # still uses previous_line directly (trivial endswith check, no growing-string cost).
        if ctx is not None:
            has_unclosed_context = ctx.paren_depth > 0 or ctx.in_quotes
        else:
            has_unclosed_context = self._has_unclosed_context(previous_line)
```

- [ ] **Step 4: Update `merge_continuation_lines` to maintain `cached_ctx`**

In `merge_continuation_lines`, find and replace the entire block starting from the `# Start building merged line` comment (line 149) through `i = j` (line 190) with:

```python
            # Start building merged line
            merged_line = line.rstrip()
            # Compute initial context for this statement line once.
            cached_ctx = self._analyze_line_context(merged_line)
            j = i + 1

            # Look ahead for continuation lines
            while j < len(lines):
                next_line = lines[j]

                # Stop merging if we hit a comment or empty line
                # (Comments break continuation chains)
                if not next_line.strip() or next_line.strip().startswith("//*"):
                    break

                # Check if next line is a continuation, passing cached context
                # to avoid re-scanning the full (growing) merged_line.
                if self.is_continuation_line(next_line, merged_line, ctx=cached_ctx):
                    raw_after_slashes = (next_line[2:] if next_line.startswith("//") else next_line).lstrip()
                    had_leading_comma = raw_after_slashes.startswith(",")

                    # Extract continuation content
                    cont_content = self._extract_continuation_content(next_line)

                    # Merge with proper separator
                    stripped = merged_line.rstrip()
                    if stripped.endswith(","):
                        merged_line = stripped + cont_content
                    elif had_leading_comma:
                        merged_line = stripped + "," + cont_content
                    else:
                        merged_line = stripped + cont_content

                    # Incrementally update context: scan only the new content
                    # starting from the prior cached state (not the full merged line).
                    cached_ctx = self._analyze_line_context(cont_content, starting_ctx=cached_ctx)
                    j += 1
                else:
                    # Not a continuation, stop merging
                    break

            merged.append((merged_line, original_line_num))
            i = j
```

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -x -q --no-header
```

Expected: All tests pass, including the two Fix 2 API tests in `test_algorithmic_fixes.py` which now have the signatures they require.

- [ ] **Step 6: Run benchmarks**

```bash
pytest tests/benchmarks/ --benchmark-only --benchmark-columns=mean,stddev -v
```

Note the new mean for `test_parse_heavy_continuation_job` vs baseline.

- [ ] **Step 7: Commit**

```bash
rtk git add jclparser/continuation_handler.py
rtk git commit -m "perf: cache continuation context incrementally instead of full rescan"
```

---

## Task 5: Fix 3 — Parameter Parsing Index Slicing

**Files:**
- Modify: `jclparser/parser.py` (two functions: `_parse_parameters` ~line 708 and `_parse_list_parameter` ~line 813)

- [ ] **Step 1: Replace character-list accumulation in `_parse_parameters`**

In `_parse_parameters`, find and replace from `# Enhanced parameter parsing with better list and parentheses handling` down to and including the final `parts.append(current)` line (the accumulation after the loop, **original line ~767**).

**Do NOT touch the lines immediately following** (original lines ~769–775) — the `if in_quotes: raise JCLSyntaxError(...)` and `if paren_depth != 0: raise JCLSyntaxError(...)` checks must remain unchanged.

Replace the entire accumulation section:

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
            # Handle escaped quotes: '' inside a quoted string represents a single quote
            if in_quotes and i + 1 < len(param_string) and param_string[i + 1] == "'":
                i += 2  # Skip both quote chars; both remain in the current slice
                continue
            # Regular quote - toggle state
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
```

- [ ] **Step 2: Replace character-list accumulation in `_parse_list_parameter`**

In `_parse_list_parameter`, replace the entire function body with:

```python
def _parse_list_parameter(list_content: str) -> List[str]:
    """Parse parameter list like A,B,C or 'A','B','C'.

    Empty positional subfields are preserved so that omitted DISP subfields
    such as ``DISP=(,CATLG,DELETE)`` retain their positional meaning.
    Trailing empty elements are stripped (from trailing commas).
    """
    items = []
    in_quotes = False
    paren_depth = 0
    start = 0

    i = 0
    while i < len(list_content):
        char = list_content[i]
        if char == "'":
            # Handle escaped quotes
            if in_quotes and i + 1 < len(list_content) and list_content[i + 1] == "'":
                i += 2
                continue
            in_quotes = not in_quotes
        elif char == "(" and not in_quotes:
            paren_depth += 1
        elif char == ")" and not in_quotes:
            paren_depth -= 1
        elif char == "," and not in_quotes and paren_depth == 0:
            item = list_content[start:i].strip()
            if item.startswith("'") and item.endswith("'"):
                item = item[1:-1].replace("''", "'")
            items.append(item)  # preserve empty strings for omitted positional subfields
            start = i + 1
        i += 1

    # Append final element
    item = list_content[start:].strip()
    if item.startswith("'") and item.endswith("'"):
        item = item[1:-1].replace("''", "'")
    items.append(item)

    # Strip trailing empty elements (from trailing commas) but keep internal ones
    while items and items[-1] == "":
        items.pop()

    return items
```

- [ ] **Step 3: Run the full test suite**

```bash
pytest tests/ -x -q --no-header
```

Expected: All tests pass, including the Fix 3 characterization tests in `test_algorithmic_fixes.py`.

- [ ] **Step 4: Run benchmarks — final comparison**

```bash
pytest tests/benchmarks/ --benchmark-only --benchmark-columns=mean,stddev -v
```

Compare all three new fixture means against the baselines captured in Task 1. Expect improvement on `test_parse_heavy_continuation_job` and `test_parse_complex_params_job`. `test_parse_large_dd_job` may show modest or no change (Fix 1's benefit is code clarity, not raw speed on small inline blocks).

- [ ] **Step 5: Confirm coverage**

```bash
pytest tests/ -q --no-header
```

Expected: Coverage report shows ≥90%. Check the HTML report at `htmlcov/index.html` if it's close.

- [ ] **Step 6: Commit**

```bash
rtk git add jclparser/parser.py
rtk git commit -m "perf: replace character-list joins with index slicing in parameter parsers"
```

---

## Task 6: Final Verification

- [ ] **Step 1: Run complete test suite one final time**

```bash
pytest tests/ --no-header -q
```

Expected: All tests pass, coverage ≥90%.

- [ ] **Step 2: Summary commit with benchmark delta (optional)**

If you captured benchmark numbers, add them to a comment in `tests/benchmarks/test_benchmarks.py` or note them in the commit message for posterity.
