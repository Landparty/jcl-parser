# Performance Profiling — jcl-parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional cProfile-based profiling to `parse_jcl()`, returning a `ProfilingResult` tuple alongside the standard `Job` output.

**Architecture:** A standalone `jclparser/profiling.py` module provides `FunctionProfile`, `ProfilingResult`, and `ProfilerContext` — identical in interface to the cobol-parser implementation but independently deployed. The `ProfilerContext` wraps the `parse_jcl()` body via a helper `_parse_jcl_core()`, keeping the public function signature stable. No existing pipeline code is modified. CLI flags `--profile`, `--profile-top-n`, and `--profile-output` merge profiling data into JSON output.

**Tech Stack:** Python 3.10+, `cProfile`/`pstats` (stdlib), `tracemalloc` (stdlib), `psutil>=5.9` (optional extra), `pytest`, `ruff`, `black`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| **Create** | `jclparser/profiling.py` | `FunctionProfile`, `ProfilingResult`, `ProfilerContext` |
| **Create** | `tests/unit/test_profiling.py` | Unit tests for profiling module |
| **Create** | `tests/integration/test_profiling_api.py` | End-to-end API tests |
| **Create** | `tests/integration/test_profiling_cli.py` | CLI `--profile` tests |
| **Modify** | `jclparser/parser.py` | Extract `_parse_jcl_core()`, add overloads to `parse_jcl()` |
| **Modify** | `jclparser/__init__.py` | Export `ProfilingResult`, `FunctionProfile` |
| **Modify** | `jclparser/cli.py` | Add `--profile`, `--profile-top-n`, `--profile-output` flags |
| **Modify** | `pyproject.toml` | Add `profiling = ["psutil>=5.9"]` optional extra |

---

## Task 1: Create `jclparser/profiling.py`

**Files:**
- Create: `jclparser/profiling.py`
- Create: `tests/unit/test_profiling.py`

- [ ] **Step 1.1: Write failing unit tests**

Create `tests/unit/test_profiling.py`:

```python
"""Unit tests for jclparser.profiling module."""
from __future__ import annotations

import json
import os
import time

import pytest

from jclparser.profiling import FunctionProfile, ProfilingResult, ProfilerContext


# ---------------------------------------------------------------------------
# FunctionProfile
# ---------------------------------------------------------------------------

def test_function_profile_to_dict():
    fp = FunctionProfile(
        function="parser.py:254(parse_jcl)",
        calls=1,
        total_time_s=0.002,
        cumul_time_s=0.018,
        per_call_total_s=0.002,
        per_call_cumul_s=0.018,
    )
    d = fp.to_dict()
    assert d["function"] == "parser.py:254(parse_jcl)"
    assert d["calls"] == 1
    assert d["total_time_s"] == pytest.approx(0.002)
    assert d["cumul_time_s"] == pytest.approx(0.018)


# ---------------------------------------------------------------------------
# ProfilingResult
# ---------------------------------------------------------------------------

def test_profiling_result_to_dict_with_cpu():
    fp = FunctionProfile("f.py:1(fn)", 1, 0.002, 0.018, 0.002, 0.018)
    result = ProfilingResult(
        wall_clock_s=0.019,
        cpu_user_s=0.016,
        cpu_system_s=0.003,
        peak_memory_mb=8.1,
        top_functions=[fp],
        prof_file=None,
    )
    d = result.to_dict()
    assert d["wall_clock_s"] == pytest.approx(0.019)
    assert d["cpu_user_s"] == pytest.approx(0.016)
    assert d["cpu_system_s"] == pytest.approx(0.003)
    assert d["peak_memory_mb"] == pytest.approx(8.1)
    assert d["prof_file"] is None
    assert len(d["top_functions"]) == 1


def test_profiling_result_to_dict_none_cpu():
    result = ProfilingResult(
        wall_clock_s=0.019,
        cpu_user_s=None,
        cpu_system_s=None,
        peak_memory_mb=8.1,
        top_functions=[],
        prof_file=None,
    )
    d = result.to_dict()
    assert d["cpu_user_s"] is None
    assert d["cpu_system_s"] is None


def test_profiling_result_to_json_valid():
    result = ProfilingResult(0.019, None, None, 8.1, [], None)
    parsed = json.loads(result.to_json())
    assert parsed["wall_clock_s"] == pytest.approx(0.019)
    assert parsed["cpu_user_s"] is None


def test_profiling_result_to_json_compact():
    result = ProfilingResult(0.1, None, None, 1.0, [], None)
    compact = result.to_json(compact=True)
    pretty = result.to_json(compact=False)
    assert "\n" not in compact
    assert len(compact) < len(pretty)


# ---------------------------------------------------------------------------
# ProfilerContext
# ---------------------------------------------------------------------------

def test_profiler_context_produces_result():
    ctx = ProfilerContext(top_n=10)
    with ctx:
        _ = sum(range(10_000))
    assert ctx.result is not None


def test_profiler_context_wall_clock_positive():
    ctx = ProfilerContext(top_n=10)
    with ctx:
        time.sleep(0.01)
    assert ctx.result.wall_clock_s >= 0.005


def test_profiler_context_peak_memory_non_negative():
    ctx = ProfilerContext(top_n=10)
    with ctx:
        _ = list(range(1_000))
    assert ctx.result.peak_memory_mb >= 0.0


def test_profiler_context_top_n_respected():
    ctx = ProfilerContext(top_n=3)
    with ctx:
        _ = sum(range(100_000))
    assert len(ctx.result.top_functions) <= 3


def test_profiler_context_top_n_zero_gives_empty():
    ctx = ProfilerContext(top_n=0)
    with ctx:
        _ = sum(range(1_000))
    assert ctx.result.top_functions == []


def test_profiler_context_function_profile_fields():
    ctx = ProfilerContext(top_n=50)
    with ctx:
        _ = [x * 2 for x in range(5_000)]
    fp = ctx.result.top_functions[0]
    assert fp.calls >= 1
    assert fp.cumul_time_s >= 0.0
    assert "(" in fp.function and ")" in fp.function


def test_profiler_context_writes_prof_file(tmp_path):
    prof_path = str(tmp_path / "test.prof")
    ctx = ProfilerContext(top_n=5, prof_output=prof_path)
    with ctx:
        _ = sum(range(1_000))
    assert os.path.exists(prof_path)
    assert ctx.result.prof_file == prof_path


def test_profiler_context_no_prof_file_by_default():
    ctx = ProfilerContext(top_n=5)
    with ctx:
        pass
    assert ctx.result.prof_file is None


def test_profiler_context_nested_tracemalloc_safe():
    """ProfilerContext must not stop an outer tracemalloc session."""
    import tracemalloc
    tracemalloc.start()
    try:
        ctx = ProfilerContext(top_n=5)
        with ctx:
            _ = list(range(100))
        assert tracemalloc.is_tracing()
    finally:
        tracemalloc.stop()
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```
python -m pytest tests/unit/test_profiling.py -v
```

Expected: `ModuleNotFoundError: No module named 'jclparser.profiling'`

- [ ] **Step 1.3: Create `jclparser/profiling.py`**

```python
"""Performance profiling support for jclparser.

ProfilerContext wraps any parse call with cProfile, tracemalloc, and
optional psutil CPU accounting. Import psutil lazily so the package remains
usable without it.
"""
from __future__ import annotations

import cProfile
import io
import json
import pstats
import time
import tracemalloc
from dataclasses import dataclass
from typing import Any

try:
    import psutil as _psutil

    _PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PSUTIL_AVAILABLE = False


@dataclass
class FunctionProfile:
    """Timing profile for a single function from cProfile."""

    function: str  # "filename:lineno(funcname)"
    calls: int
    total_time_s: float
    cumul_time_s: float
    per_call_total_s: float
    per_call_cumul_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "calls": self.calls,
            "total_time_s": self.total_time_s,
            "cumul_time_s": self.cumul_time_s,
            "per_call_total_s": self.per_call_total_s,
            "per_call_cumul_s": self.per_call_cumul_s,
        }


@dataclass
class ProfilingResult:
    """Structured profiling output from a profiled parse call."""

    wall_clock_s: float
    cpu_user_s: float | None
    cpu_system_s: float | None
    peak_memory_mb: float
    top_functions: list[FunctionProfile]
    prof_file: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "wall_clock_s": self.wall_clock_s,
            "cpu_user_s": self.cpu_user_s,
            "cpu_system_s": self.cpu_system_s,
            "peak_memory_mb": self.peak_memory_mb,
            "prof_file": self.prof_file,
            "top_functions": [f.to_dict() for f in self.top_functions],
        }

    def to_json(self, compact: bool = False) -> str:
        if compact:
            return json.dumps(self.to_dict(), separators=(",", ":"))
        return json.dumps(self.to_dict(), indent=2)


class ProfilerContext:
    """Context manager that profiles a parse call with cProfile + tracemalloc."""

    def __init__(self, top_n: int = 50, prof_output: str | None = None) -> None:
        self._top_n = top_n
        self._prof_output = prof_output
        self._profiler = cProfile.Profile()
        self._wall_start: float = 0.0
        self._cpu_before: Any = None
        self._was_tracing: bool = False
        self.result: ProfilingResult | None = None

    def __enter__(self) -> "ProfilerContext":
        self._was_tracing = tracemalloc.is_tracing()
        if not self._was_tracing:
            tracemalloc.start()

        self._wall_start = time.perf_counter()

        if _PSUTIL_AVAILABLE:
            self._cpu_before = _psutil.Process().cpu_times()

        self._profiler.enable()
        return self

    def __exit__(self, *_: Any) -> None:
        self._profiler.disable()
        wall_clock_s = time.perf_counter() - self._wall_start

        _, peak_bytes = tracemalloc.get_traced_memory()
        if not self._was_tracing:
            tracemalloc.stop()
        peak_memory_mb = peak_bytes / (1024 * 1024)

        cpu_user_s: float | None = None
        cpu_system_s: float | None = None
        if _PSUTIL_AVAILABLE and self._cpu_before is not None:
            cpu_after = _psutil.Process().cpu_times()
            cpu_user_s = max(0.0, cpu_after.user - self._cpu_before.user)
            cpu_system_s = max(0.0, cpu_after.system - self._cpu_before.system)

        if self._prof_output:
            self._profiler.dump_stats(self._prof_output)

        top_functions: list[FunctionProfile] = []
        if self._top_n > 0:
            stream = io.StringIO()
            stats = pstats.Stats(self._profiler, stream=stream)
            sorted_entries = sorted(
                stats.stats.items(),
                key=lambda kv: kv[1][3],
                reverse=True,
            )[: self._top_n]
            for (filename, lineno, funcname), (cc, nc, tt, ct, _) in sorted_entries:
                top_functions.append(
                    FunctionProfile(
                        function=f"{filename}:{lineno}({funcname})",
                        calls=nc,
                        total_time_s=tt,
                        cumul_time_s=ct,
                        per_call_total_s=tt / nc if nc else 0.0,
                        per_call_cumul_s=ct / cc if cc else 0.0,
                    )
                )

        self.result = ProfilingResult(
            wall_clock_s=wall_clock_s,
            cpu_user_s=cpu_user_s,
            cpu_system_s=cpu_system_s,
            peak_memory_mb=peak_memory_mb,
            top_functions=top_functions,
            prof_file=self._prof_output,
        )
```

- [ ] **Step 1.4: Run unit tests — expect all pass**

```
python -m pytest tests/unit/test_profiling.py -v
```

Expected: all tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add jclparser/profiling.py tests/unit/test_profiling.py
git commit -m "feat: add profiling module with ProfilerContext, ProfilingResult, FunctionProfile"
```

---

## Task 2: Add `psutil` optional dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 2.1: Add `profiling` extra to `pyproject.toml`**

In `pyproject.toml`, find `[project.optional-dependencies]` and add:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "coverage[toml]>=7.0",
    "pytest-cov>=4.0",
    "pytest-benchmark>=4.0",
    "tomli>=1.1.0; python_version < '3.11'",
]
test = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "tomli>=1.1.0; python_version < '3.11'",
]
profiling = [
    "psutil>=5.9",
]
```

- [ ] **Step 2.2: Install the optional extra**

```
pip install -e ".[profiling]"
```

Expected: `psutil` installed, no errors.

- [ ] **Step 2.3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add psutil optional dependency under [profiling] extra"
```

---

## Task 3: Add profiling overloads to `parse_jcl()`

**Files:**
- Modify: `jclparser/parser.py`
- Create: `tests/integration/test_profiling_api.py`

- [ ] **Step 3.1: Write failing integration tests**

Create `tests/integration/test_profiling_api.py`:

```python
"""Integration tests: parse_jcl() with profiling."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jclparser import parse_jcl
from jclparser.profiling import ProfilingResult

_SIMPLE = """\
//MYJOB   JOB (ACCT),'Test Job',CLASS=A,MSGCLASS=X
//STEP1   EXEC PGM=IEFBR14
//SYSPRINT DD  SYSOUT=*
"""


def test_parse_without_profiling_returns_job():
    job = parse_jcl(_SIMPLE)
    assert not isinstance(job, tuple)
    assert job.name == "MYJOB"


def test_parse_with_profiling_returns_tuple():
    out = parse_jcl(_SIMPLE, enable_profiling=True)
    assert isinstance(out, tuple) and len(out) == 2
    job, profiling = out
    assert job.name == "MYJOB"
    assert isinstance(profiling, ProfilingResult)


def test_parse_profiling_wall_clock_positive():
    _, profiling = parse_jcl(_SIMPLE, enable_profiling=True)
    assert profiling.wall_clock_s > 0


def test_parse_profiling_peak_memory_non_negative():
    _, profiling = parse_jcl(_SIMPLE, enable_profiling=True)
    assert profiling.peak_memory_mb >= 0.0


def test_parse_profiling_top_functions_non_empty():
    _, profiling = parse_jcl(_SIMPLE, enable_profiling=True)
    assert len(profiling.top_functions) > 0


def test_parse_profiling_top_n_respected():
    _, profiling = parse_jcl(_SIMPLE, enable_profiling=True, top_n=3)
    assert len(profiling.top_functions) <= 3


def test_parse_profiling_prof_file(tmp_path):
    prof_path = str(tmp_path / "jcl.prof")
    _, profiling = parse_jcl(_SIMPLE, enable_profiling=True, prof_output=prof_path)
    import os
    assert os.path.exists(prof_path)
    assert profiling.prof_file == prof_path


def test_parse_profiling_to_dict():
    _, profiling = parse_jcl(_SIMPLE, enable_profiling=True)
    d = profiling.to_dict()
    assert "wall_clock_s" in d
    assert "peak_memory_mb" in d
    assert "top_functions" in d


def test_parse_profiling_to_json():
    _, profiling = parse_jcl(_SIMPLE, enable_profiling=True)
    data = json.loads(profiling.to_json())
    assert data["wall_clock_s"] > 0
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```
python -m pytest tests/integration/test_profiling_api.py -v
```

Expected: `TypeError` — `parse_jcl()` doesn't accept `enable_profiling`.

- [ ] **Step 3.3: Add overloads and extract `_parse_jcl_core()` in `jclparser/parser.py`**

Add to the imports at the top of `jclparser/parser.py`:

```python
from typing import IO, Literal, overload
from jclparser.profiling import ProfilerContext, ProfilingResult
```

(Replace any existing `from typing import IO` with the extended version.)

Find the existing `parse_jcl()` function (line 112 onwards). Extract its entire body into a new private function `_parse_jcl_core()` with the identical signature, then replace `parse_jcl()` with the overloaded dispatcher:

```python
@overload
def parse_jcl(
    source: str | Path | IO,
    strict_mode: bool = ...,
    config: "ParserConfig | None" = ...,
    proc_base_path: "str | Path | None" = ...,
    enable_external_procs: bool = ...,
    include_loader: "IncludeMemberLoader | None" = ...,
    enable_profiling: Literal[False] = ...,
    top_n: int = ...,
    prof_output: str | None = ...,
) -> "Job": ...


@overload
def parse_jcl(
    source: str | Path | IO,
    strict_mode: bool = ...,
    config: "ParserConfig | None" = ...,
    proc_base_path: "str | Path | None" = ...,
    enable_external_procs: bool = ...,
    include_loader: "IncludeMemberLoader | None" = ...,
    enable_profiling: Literal[True] = ...,
    top_n: int = ...,
    prof_output: str | None = ...,
) -> "tuple[Job, ProfilingResult]": ...


def parse_jcl(
    source: str | Path | IO,
    strict_mode: bool = False,
    config: "ParserConfig | None" = None,
    proc_base_path: "str | Path | None" = None,
    enable_external_procs: bool = True,
    include_loader: "IncludeMemberLoader | None" = None,
    enable_profiling: bool = False,
    top_n: int = 50,
    prof_output: str | None = None,
) -> "Job | tuple[Job, ProfilingResult]":
    """
    Parse JCL script from various input sources into structured Job object.

    Args:
        source: JCL script content as string, file path, or file-like object
        strict_mode: Enable strict parsing mode
        config: Optional parser configuration
        proc_base_path: Base directory for external PROC libraries
        enable_external_procs: Enable loading PROCs from file system via JCLLIB ORDER
        include_loader: Optional IncludeMemberLoader for INCLUDE MEMBER= resolution.
        enable_profiling: When True, returns (Job, ProfilingResult) tuple.
        top_n: Maximum functions in ProfilingResult.top_functions.
        prof_output: If set, write cProfile .prof binary to this path.

    Returns:
        Job, or (Job, ProfilingResult) when enable_profiling=True.

    Raises:
        JCLSyntaxError: Invalid JCL syntax encountered
        JCLValidationError: Valid syntax but semantic errors
        FileNotFoundError: When source is path to non-existent file
    """
    if enable_profiling:
        ctx = ProfilerContext(top_n=top_n, prof_output=prof_output)
        with ctx:
            job = _parse_jcl_core(
                source,
                strict_mode=strict_mode,
                config=config,
                proc_base_path=proc_base_path,
                enable_external_procs=enable_external_procs,
                include_loader=include_loader,
            )
        return job, ctx.result  # type: ignore[return-value]
    return _parse_jcl_core(
        source,
        strict_mode=strict_mode,
        config=config,
        proc_base_path=proc_base_path,
        enable_external_procs=enable_external_procs,
        include_loader=include_loader,
    )
```

Then rename the original `parse_jcl` body to `_parse_jcl_core` with the same signature (minus `enable_profiling`, `top_n`, `prof_output`):

```python
def _parse_jcl_core(
    source: str | Path | IO,
    strict_mode: bool = False,
    config: "ParserConfig | None" = None,
    proc_base_path: "str | Path | None" = None,
    enable_external_procs: bool = True,
    include_loader: "IncludeMemberLoader | None" = None,
) -> "Job":
    """Internal parse implementation (body of the original parse_jcl)."""
    # ... [entire original parse_jcl body, unchanged] ...
```

- [ ] **Step 3.4: Run integration tests — expect all pass**

```
python -m pytest tests/integration/test_profiling_api.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 3.5: Verify existing tests still pass**

```
python -m pytest tests/ -v --ignore=tests/integration/test_profiling_api.py --ignore=tests/unit/test_profiling.py -x -q
```

Expected: no regressions.

- [ ] **Step 3.6: Commit**

```bash
git add jclparser/parser.py
git commit -m "feat: extract _parse_jcl_core(), add profiling overloads to parse_jcl()"
```

---

## Task 4: Export `ProfilingResult` and `FunctionProfile` from `jclparser/__init__.py`

**Files:**
- Modify: `jclparser/__init__.py`

- [ ] **Step 4.1: Add exports**

In `jclparser/__init__.py`, add alongside the existing imports:

```python
from jclparser.profiling import ProfilingResult, FunctionProfile
```

Place it after the `from .parser import parse_jcl, validate_jcl, parse_statement` line.

- [ ] **Step 4.2: Verify import**

```
python -c "from jclparser import ProfilingResult, FunctionProfile; print('ok')"
```

Expected: `ok`

- [ ] **Step 4.3: Commit**

```bash
git add jclparser/__init__.py
git commit -m "feat: export ProfilingResult and FunctionProfile from jclparser public API"
```

---

## Task 5: Add `--profile` CLI flags and merge into JSON output

**Files:**
- Modify: `jclparser/cli.py`
- Create: `tests/integration/test_profiling_cli.py`

- [ ] **Step 5.1: Write failing CLI tests**

Create `tests/integration/test_profiling_cli.py`:

```python
"""Integration tests: jcl-parser CLI --profile flag."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str) -> tuple[int, str, str]:
    cmd = [sys.executable, "-m", "jclparser.cli", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def _get_sample() -> Path:
    samples = list(Path(__file__).parent.parent.glob("**/*.jcl"))
    if not samples:
        # Fallback: create a minimal inline JCL file for testing
        p = Path(__file__).parent / "_sample_test.jcl"
        p.write_text("//MYJOB   JOB (ACCT),'Test',CLASS=A\n//STEP1   EXEC PGM=IEFBR14\n")
        return p
    return samples[0]


def test_profile_flag_adds_profiling_key():
    sample = _get_sample()
    rc, stdout, stderr = _run_cli(str(sample), "--json", "--profile")
    assert rc == 0, f"CLI failed: {stderr}"
    data = json.loads(stdout)
    assert "profiling" in data, f"No 'profiling' key: {list(data.keys())}"


def test_profile_section_has_required_fields():
    sample = _get_sample()
    rc, stdout, _ = _run_cli(str(sample), "--json", "--profile")
    assert rc == 0
    profiling = json.loads(stdout)["profiling"]
    for field in ("wall_clock_s", "cpu_user_s", "cpu_system_s", "peak_memory_mb",
                  "top_functions", "prof_file"):
        assert field in profiling, f"Missing field: {field}"


def test_profile_wall_clock_positive():
    sample = _get_sample()
    rc, stdout, _ = _run_cli(str(sample), "--json", "--profile")
    assert rc == 0
    assert json.loads(stdout)["profiling"]["wall_clock_s"] > 0


def test_profile_top_n_flag():
    sample = _get_sample()
    rc, stdout, _ = _run_cli(str(sample), "--json", "--profile", "--profile-top-n", "3")
    assert rc == 0
    assert len(json.loads(stdout)["profiling"]["top_functions"]) <= 3


def test_profile_output_flag(tmp_path):
    sample = _get_sample()
    prof_path = str(tmp_path / "out.prof")
    rc, stdout, _ = _run_cli(str(sample), "--json", "--profile", "--profile-output", prof_path)
    assert rc == 0
    import os
    assert os.path.exists(prof_path)
    assert json.loads(stdout)["profiling"]["prof_file"] == prof_path


def test_without_profile_no_profiling_key():
    sample = _get_sample()
    rc, stdout, _ = _run_cli(str(sample), "--json")
    assert rc == 0
    assert "profiling" not in json.loads(stdout)
```

- [ ] **Step 5.2: Run tests to confirm they fail**

```
python -m pytest tests/integration/test_profiling_cli.py -v
```

Expected: failures because `--profile` doesn't exist.

- [ ] **Step 5.3: Add `--profile`, `--profile-top-n`, `--profile-output` to `argparse` in `cli.py`**

In `jclparser/cli.py`, inside `main()`, after the existing `parser.add_argument("--version", ...)` call, add:

```python
parser.add_argument(
    "--profile",
    action="store_true",
    default=False,
    help="Enable performance profiling; adds 'profiling' key to JSON output.",
)
parser.add_argument(
    "--profile-top-n",
    type=int,
    default=50,
    metavar="N",
    dest="profile_top_n",
    help="Number of top functions to include in profiling output (default: 50).",
)
parser.add_argument(
    "--profile-output",
    default=None,
    metavar="FILE",
    dest="profile_output",
    help="Write cProfile .prof binary to FILE (for use with snakeviz).",
)
```

- [ ] **Step 5.4: Replace the `parse_jcl()` call in `main()` to use profiling when requested**

In `main()` (currently around line 130–135), the parse call is:

```python
job = parse_jcl(
    path,
    proc_base_path=args.proc_path,
    enable_external_procs=args.proc_path is not None,
)
```

Replace with:

```python
_profiling_result = None
if args.profile:
    job, _profiling_result = parse_jcl(
        path,
        proc_base_path=args.proc_path,
        enable_external_procs=args.proc_path is not None,
        enable_profiling=True,
        top_n=args.profile_top_n,
        prof_output=args.profile_output,
    )
else:
    job = parse_jcl(
        path,
        proc_base_path=args.proc_path,
        enable_external_procs=args.proc_path is not None,
    )
```

- [ ] **Step 5.5: Merge `_profiling_result` into JSON output**

In `main()` at line 158–163, the primary full-job JSON output is:

```python
if query is None:
    if json_out:
        print(json.dumps(_job_to_dict(job), indent=2))
    else:
        _print_summary(job)
    return 0
```

Replace the `if json_out:` branch with:

```python
if query is None:
    if json_out:
        job_dict = _job_to_dict(job)
        if _profiling_result is not None:
            job_dict["profiling"] = _profiling_result.to_dict()
        print(json.dumps(job_dict, indent=2))
    else:
        _print_summary(job)
    return 0
```

This is the only output site that uses the full job dict and is covered by `--json` without a subcommand. Other subcommands (`steps`, `procs`, `metrics`, etc.) output sub-sections — profiling is only injected into the root-level `--json` output.

- [ ] **Step 5.6: Run CLI tests**

```
python -m pytest tests/integration/test_profiling_cli.py -v
```

Expected: all tests pass.

- [ ] **Step 5.7: Run full test suite**

```
python -m pytest tests/ -v -q
```

Expected: all tests pass.

- [ ] **Step 5.8: Commit**

```bash
git add jclparser/cli.py tests/integration/test_profiling_cli.py
git commit -m "feat: add --profile, --profile-top-n, --profile-output CLI flags"
```

---

## Verification Checklist

- [ ] `python -m pytest tests/unit/test_profiling.py tests/integration/test_profiling_api.py tests/integration/test_profiling_cli.py -v` — all pass
- [ ] `parse_jcl(src, enable_profiling=True)` returns `tuple[Job, ProfilingResult]`
- [ ] `parse_jcl(src)` returns plain `Job` (no tuple)
- [ ] `jcl-parser FILE --json --profile` outputs JSON with `"profiling"` key
- [ ] `jcl-parser FILE --json --profile --profile-output out.prof` creates `out.prof`
- [ ] `python -c "import pstats; pstats.Stats('out.prof').print_stats()"` succeeds
- [ ] `ProfilingResult.to_json()` is valid JSON; all float fields non-negative
- [ ] Without psutil: `cpu_user_s` and `cpu_system_s` are `None`, no exception raised
- [ ] `python -m pytest tests/ -v -q` — full suite passes
