# Performance Profiling — Design Spec

**Date:** 2026-05-06  
**Scope:** `jcl-parser` (mirrors `cobol-parser` profiling design, independently implemented)  
**Status:** Approved

---

## Context

The JCL parser processes job control language for LegacyLens. As JCL files grow (many steps, deeply nested PROCs, large inline data), parse time and memory become relevant for SLA planning. There is currently no timing instrumentation — only structural `JobMetrics` (step counts, complexity scores). This spec adds optional, non-intrusive profiling using cProfile + psutil, returning a `ProfilingResult` tuple alongside the existing `Job` object.

---

## Architecture

### Approach

A standalone `jclparser/profiling.py` module provides `ProfilingResult`, `FunctionProfile`, and `ProfilerContext`. No changes are made to existing pipeline code — the context manager wraps only the outermost `parse_jcl()` call. This is independent of the `cobol-parser` implementation (no shared package).

### Dependencies

- **psutil** — added as `[profiling]` optional extra. Absent: `cpu_user_s`/`cpu_system_s` → `None`.
- **tracemalloc** — stdlib; always used for per-call peak memory (measures allocations within the profiled block, not process-wide RSS).
- **cProfile**, **pstats** — stdlib; always available.

---

## Data Structures

### `FunctionProfile` (dataclass)

```python
@dataclass
class FunctionProfile:
    function: str          # "filename:lineno(funcname)"
    calls: int
    total_time_s: float
    cumul_time_s: float
    per_call_total_s: float
    per_call_cumul_s: float
```

### `ProfilingResult` (dataclass)

```python
@dataclass
class ProfilingResult:
    wall_clock_s: float
    cpu_user_s: float | None
    cpu_system_s: float | None
    peak_memory_mb: float         # tracemalloc peak allocation within the profiled call
    top_functions: list[FunctionProfile]
    prof_file: str | None

    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self, compact: bool = False) -> str: ...
```

---

## Python API

### `parse_jcl()`

```python
@overload
def parse_jcl(
    source: str | Path | IO[str], ...,
    enable_profiling: Literal[False] = ...,
    top_n: int = 50,
    prof_output: str | None = None,
) -> Job: ...

@overload
def parse_jcl(
    source: str | Path | IO[str], ...,
    enable_profiling: Literal[True],
    top_n: int = 50,
    prof_output: str | None = None,
) -> tuple[Job, ProfilingResult]: ...
```

`validate_jcl()` and `parse_statement()` do **not** get profiling overloads — profiling is only meaningful at the full-job parse level.

---

## CLI

Three new flags added to all file-based CLI commands (`parse`/default, `steps`, `procs`, `metrics`, `lint`, `datasets`, `sql`, `analyze`, `paths`):

```
--profile              Enable profiling (default: off)
--profile-top-n N      Top functions in JSON output (default: 50)
--profile-output FILE  Write .prof binary to FILE
```

### JSON output (`--json --profile`)

```json
{
  "name": "MYJOB",
  "steps": [ ... ],
  "profiling": {
    "wall_clock_s": 0.019,
    "cpu_user_s": 0.016,
    "cpu_system_s": 0.003,
    "peak_memory_mb": 8.1,
    "prof_file": null,
    "top_functions": [
      { "function": "parser.py:254(parse_jcl)", "calls": 1, "cumul_time_s": 0.018, ... }
    ]
  }
}
```

### Text output (non-JSON commands)

A compact profiling block appended after the normal output:

```
--- Profiling ---
wall_clock:   0.019s
cpu_user:     0.016s
cpu_system:   0.003s
peak_memory:  8.1 MB
top functions (by cumulative time):
  0.018s  parser.py:254(parse_jcl)
  ...
```

---

## Files to Create / Modify

### New Files
- `jclparser/profiling.py` — `ProfilingResult`, `FunctionProfile`, `ProfilerContext`

### Modified Files
- `jclparser/parser.py` — add `enable_profiling`, `top_n`, `prof_output` args + overloads to `parse_jcl()`
- `jclparser/cli.py` — add `--profile`, `--profile-top-n`, `--profile-output`; merge profiling into JSON; append block for text output
- `jclparser/__init__.py` — export `ProfilingResult`, `FunctionProfile`
- `pyproject.toml` — add `psutil>=5.9` under `[project.optional-dependencies] profiling`

### Tests to Add
- `tests/unit/test_profiling.py` — `ProfilerContext`, `ProfilingResult.to_dict()`, graceful degradation
- `tests/integration/test_profiling_api.py` — `parse_jcl(..., enable_profiling=True)` returns correct tuple; metrics positive
- `tests/integration/test_profiling_cli.py` — CLI `--profile --json` produces valid JSON with `"profiling"` key

---

## Verification

1. `python -m pytest tests/unit/test_profiling.py tests/integration/test_profiling_api.py tests/integration/test_profiling_cli.py -v` — all pass
2. `parse_jcl(source, enable_profiling=True)` returns `tuple[Job, ProfilingResult]`; without flag returns plain `Job`
3. `jcl-parser FILE --json --profile` outputs JSON with `"profiling"` key
4. `jcl-parser FILE --profile --profile-output out.prof` writes valid `.prof` binary
5. `ProfilingResult.to_json()` is valid JSON; all numeric fields non-negative
6. Without psutil: `cpu_user_s`/`cpu_system_s` are `null`; no exception raised
7. `python -m pytest tests/ -v` — full suite still passes
