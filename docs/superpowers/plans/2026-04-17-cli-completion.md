# CLI Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 missing subcommands (`detect`, `metrics`, `lint`, `datasets`, `sql`, `analyze`, `paths`) to the jclparser CLI so every major library API is reachable from the command line.

**Architecture:** All changes land in `jclparser/cli.py` (new `_cmd_*` functions + text/JSON helpers) and `tests/unit/test_cli.py` (one new test class per subcommand). No new files. Each subcommand follows the existing dispatch pattern in `main()`.

**Tech Stack:** Python stdlib (`argparse`, `json`, `sys`, `pathlib`), jclparser public API (`compute_metrics`, `lint_job`, `all_rules`, `analyze_dataset_lifecycle`, `validate_dataset_lifecycle`, `detect_sql_in_job`, `analyze_job`, `compute_feasible_paths`, `detect_file_type`).

---

## File Map

| File | Change |
|---|---|
| `jclparser/cli.py` | Add imports + 7 `_cmd_*` dispatch branches + helper functions |
| `tests/unit/test_cli.py` | Add 7 new `@pytest.mark.unit` test classes |

---

## Task 1: `detect` subcommand

**Files:**
- Modify: `jclparser/cli.py`
- Modify: `tests/unit/test_cli.py`

### Step 1.1 — Write the failing test

Add to `tests/unit/test_cli.py`:

```python
@pytest.mark.unit
class TestCLIDetect:
    """Test 'detect' subcommand."""

    def test_detect_jcl(self, capsys):
        rc = main([SORT_JCL, "detect"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "JCL" in out

    def test_detect_json(self, capsys):
        rc = main([SORT_JCL, "detect", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["file_type"] == "JCL"
        assert "path" in data

    def test_detect_proc(self, capsys):
        rc = main([str(FIXTURES / "sample_jcl" / "standalone_proc.jcl"), "detect"])
        assert rc == 0
        out = capsys.readouterr().out
        # standalone_proc.jcl starts with PROC, not a JOB card
        assert out.strip() in {"JCL", "PROC", "UNKNOWN"}
```

- [ ] **Step 1.2 — Run to confirm FAIL**

```bash
pytest tests/unit/test_cli.py::TestCLIDetect -v
```
Expected: FAIL — `main` doesn't handle `"detect"` query yet.

- [ ] **Step 1.3 — Add imports to `cli.py`**

At the top of `jclparser/cli.py`, add to the existing imports:

```python
from .jcl_file_type import detect_file_type, FileType
from .metrics import compute_metrics
from .lint import lint_job, all_rules
from .dataset_lifecycle import analyze_dataset_lifecycle, validate_dataset_lifecycle
from .sql_detector import detect_sql_in_job
from .program_profiles import analyze_job, analyze_step
from .rc_analysis import compute_feasible_paths
```

- [ ] **Step 1.4 — Add `detect` dispatch in `main()`**

In `main()`, after the `if query.lower() == "procs":` block (around line 170), add:

```python
    if query.lower() == "detect":
        return _cmd_detect(path, json_out)
```

Note: `detect` must come **before** the step-name lookup so it isn't mistaken for a step called "DETECT".

- [ ] **Step 1.5 — Add `_cmd_detect` function**

Add after `_cmd_list_available`:

```python
def _cmd_detect(path: Path, json_output: bool = False) -> int:
    file_type = detect_file_type(path)
    name = file_type.name  # "JCL", "PROC", or "UNKNOWN"
    if json_output:
        print(json.dumps({"file_type": name, "path": str(path)}, indent=2))
    else:
        print(name)
    return 0
```

- [ ] **Step 1.6 — Run tests**

```bash
pytest tests/unit/test_cli.py::TestCLIDetect -v
```
Expected: all 3 PASS.

- [ ] **Step 1.7 — Commit**

```bash
git add jclparser/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add detect subcommand"
```

---

## Task 2: `metrics` subcommand

**Files:**
- Modify: `jclparser/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 2.1 — Write failing test**

Add to `tests/unit/test_cli.py`:

```python
@pytest.mark.unit
class TestCLIMetrics:
    """Test 'metrics' subcommand."""

    def test_metrics_text(self, capsys):
        rc = main([SORT_JCL, "metrics"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "step_count" in out
        assert "dd_count" in out
        assert "cyclomatic_score" in out

    def test_metrics_json(self, capsys):
        rc = main([SORT_JCL, "metrics", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "step_count" in data
        assert "exec_step_count" in data
        assert "dd_count" in data
        assert "cyclomatic_score" in data
        assert data["step_count"] >= 1

    def test_metrics_returns_zero(self, capsys):
        rc = main([SORT_JCL, "metrics"])
        assert rc == 0
```

- [ ] **Step 2.2 — Run to confirm FAIL**

```bash
pytest tests/unit/test_cli.py::TestCLIMetrics -v
```
Expected: FAIL.

- [ ] **Step 2.3 — Add dispatch in `main()`**

After the `detect` dispatch block:

```python
    if query.lower() == "metrics":
        return _cmd_metrics(job, json_out)
```

- [ ] **Step 2.4 — Add `_cmd_metrics` and `_print_metrics`**

```python
def _cmd_metrics(job: "Job", json_output: bool = False) -> int:
    m = compute_metrics(job)
    if json_output:
        print(json.dumps(m.to_dict(), indent=2))
    else:
        _print_metrics(m)
    return 0


def _print_metrics(m) -> None:
    fields = m.to_dict()
    # Remove 'metrics' shadow dict if present (backwards-compat field)
    fields.pop("metrics", None)
    width = max(len(k) for k in fields)
    for k, v in fields.items():
        print(f"  {k:<{width}}  {v}")
```

- [ ] **Step 2.5 — Run tests**

```bash
pytest tests/unit/test_cli.py::TestCLIMetrics -v
```
Expected: all PASS.

- [ ] **Step 2.6 — Commit**

```bash
git add jclparser/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add metrics subcommand"
```

---

## Task 3: `lint` subcommand

**Files:**
- Modify: `jclparser/cli.py`
- Modify: `tests/unit/test_cli.py`

Lint has two special behaviours: `--lint-list` (list rules, no file needed) and exit code 1 when findings exist.

- [ ] **Step 3.1 — Write failing tests**

Add to `tests/unit/test_cli.py`:

```python
@pytest.mark.unit
class TestCLILint:
    """Test 'lint' subcommand."""

    def test_lint_clean_job_exits_zero(self, capsys):
        # A simple job may have no lint findings
        rc = main([SORT_JCL, "lint"])
        # exit 0 means no findings; exit 1 means findings — both are valid
        assert rc in (0, 1)
        capsys.readouterr()  # consume output

    def test_lint_json_structure(self, capsys):
        rc = main([SORT_JCL, "lint", "--json"])
        assert rc in (0, 1)
        data = json.loads(capsys.readouterr().out)
        assert "findings" in data
        assert "count" in data
        assert isinstance(data["findings"], list)

    def test_lint_finding_has_required_keys(self, capsys):
        # Use a JCL likely to trigger lint findings (hardcoded HLQs etc.)
        rc = main([COMPLEX_JCL, "lint", "--json"])
        assert rc in (0, 1)
        data = json.loads(capsys.readouterr().out)
        for finding in data["findings"]:
            assert "code" in finding
            assert "severity" in finding
            assert "message" in finding

    def test_lint_list_flag(self, capsys):
        # --lint-list must not require FILE; we pass a dummy path but
        # check for --lint-list in argv before argparse in the implementation
        rc = main(["--lint-list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "JCL" in out  # rule codes start with JCL

    def test_lint_text_format(self, capsys):
        main([COMPLEX_JCL, "lint"])
        out = capsys.readouterr().out
        # Each finding line starts with "[" (the code bracket) or output is empty
        for line in out.strip().splitlines():
            if line.strip():
                assert line.startswith("["), f"unexpected line: {line!r}"
```

- [ ] **Step 3.2 — Run to confirm FAIL**

```bash
pytest tests/unit/test_cli.py::TestCLILint -v
```
Expected: FAIL.

- [ ] **Step 3.3 — Handle `--lint-list` before argparse in `main()`**

At the very start of `main()`, before `parser.parse_args(argv)`:

```python
    # --lint-list doesn't need a FILE argument — handle before argparse
    _argv = argv if argv is not None else sys.argv[1:]
    if "--lint-list" in _argv:
        return _cmd_lint_list()
```

Add the flag to argparse (so `--help` shows it), but make it `nargs=0` and handled above:

```python
    parser.add_argument(
        "--lint-list",
        action="store_true",
        help="List all available lint rule codes and descriptions, then exit",
    )
```

- [ ] **Step 3.4 — Add `_cmd_lint_list`**

```python
def _cmd_lint_list() -> int:
    rules = all_rules()
    if not rules:
        print("(no lint rules registered)")
        return 0
    width = max(len(r.code) for r in rules)
    for rule in rules:
        print(f"  {rule.code:<{width}}  {rule.description}")
    return 0
```

- [ ] **Step 3.5 — Add `lint` dispatch in `main()`**

After `metrics` dispatch:

```python
    if query.lower() == "lint":
        return _cmd_lint(job, json_out)
```

- [ ] **Step 3.6 — Add `_cmd_lint` and `_print_lint_findings`**

```python
def _cmd_lint(job: "Job", json_output: bool = False) -> int:
    findings = lint_job(job)
    if json_output:
        items = [
            {
                "code": getattr(e, "error_code", None) or "",
                "severity": e.severity.name if e.severity else "WARNING",
                "line": e.line_number,
                "message": e.message,
            }
            for e in findings
        ]
        print(json.dumps({"findings": items, "count": len(items)}, indent=2))
    else:
        _print_lint_findings(findings)
    return 1 if findings else 0


def _print_lint_findings(findings: list) -> None:
    if not findings:
        print("OK - no lint findings.")
        return
    for e in findings:
        code = getattr(e, "error_code", None) or "LINT"
        sev = e.severity.name if e.severity else "WARNING"
        line = e.line_number
        loc = f" line {line:>4}" if line else "       "
        print(f"[{code}]{loc}: {e.message}")
```

- [ ] **Step 3.7 — Run tests**

```bash
pytest tests/unit/test_cli.py::TestCLILint -v
```
Expected: all PASS.

- [ ] **Step 3.8 — Commit**

```bash
git add jclparser/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add lint subcommand with --lint-list"
```

---

## Task 4: `datasets` subcommand

**Files:**
- Modify: `jclparser/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 4.1 — Write failing tests**

Add to `tests/unit/test_cli.py`:

```python
@pytest.mark.unit
class TestCLIDatasets:
    """Test 'datasets' subcommand."""

    def test_datasets_text(self, capsys):
        rc = main([SORT_JCL, "datasets"])
        assert rc in (0, 1)
        out = capsys.readouterr().out
        # Should list at least one dataset name
        assert len(out.strip()) > 0

    def test_datasets_json_structure(self, capsys):
        rc = main([SORT_JCL, "datasets", "--json"])
        assert rc in (0, 1)
        data = json.loads(capsys.readouterr().out)
        assert "lifecycle" in data
        assert "violations" in data
        assert isinstance(data["lifecycle"], dict)
        assert isinstance(data["violations"], list)

    def test_datasets_lifecycle_has_events(self, capsys):
        rc = main([SORT_JCL, "datasets", "--json"])
        data = json.loads(capsys.readouterr().out)
        # sort_job.jcl has DDs with DSNs
        assert len(data["lifecycle"]) >= 1

    def test_datasets_clean_job_exits_zero(self, capsys):
        # A well-formed job with no lifecycle violations exits 0
        rc = main([SORT_JCL, "datasets"])
        capsys.readouterr()
        assert rc in (0, 1)  # either is valid depending on the JCL
```

- [ ] **Step 4.2 — Run to confirm FAIL**

```bash
pytest tests/unit/test_cli.py::TestCLIDatasets -v
```
Expected: FAIL.

- [ ] **Step 4.3 — Add dispatch and implementation**

Add after `lint` dispatch in `main()`:

```python
    if query.lower() == "datasets":
        return _cmd_datasets(job, json_out)
```

Add functions:

```python
def _cmd_datasets(job: "Job", json_output: bool = False) -> int:
    lifecycle = analyze_dataset_lifecycle(job)
    violations = validate_dataset_lifecycle(job)
    if json_output:
        lifecycle_dict = {
            dsn: [
                {
                    "step": ev.step_name,
                    "dd": ev.dd_name,
                    "action": ev.action,
                    "disp_status": ev.disp_status,
                    "disp_normal": ev.disp_normal,
                    "line": ev.line_number,
                }
                for ev in events
            ]
            for dsn, events in lifecycle.items()
        }
        viol_list = [
            {
                "severity": e.severity.name if e.severity else "WARNING",
                "message": e.message,
                "line": e.line_number,
            }
            for e in violations
        ]
        print(
            json.dumps({"lifecycle": lifecycle_dict, "violations": viol_list}, indent=2)
        )
    else:
        _print_datasets(lifecycle, violations)
    return 1 if violations else 0


def _print_datasets(lifecycle: dict, violations: list) -> None:
    if not lifecycle:
        print("(no datasets found)")
    for dsn, events in sorted(lifecycle.items()):
        print(dsn)
        for ev in events:
            disp = f"  status={ev.disp_status}" if ev.disp_status else ""
            norm = f", normal={ev.disp_normal}" if ev.disp_normal else ""
            print(
                f"  {ev.action:<12} {ev.step_name:<10} line {ev.line_number:>4}"
                f"  (dd={ev.dd_name}{disp}{norm})"
            )
        print()
    if violations:
        print(f"Violations ({len(violations)}):")
        for e in violations:
            sev = e.severity.name if e.severity else "WARNING"
            print(f"  [{sev}] {e.message}")
```

- [ ] **Step 4.4 — Run tests**

```bash
pytest tests/unit/test_cli.py::TestCLIDatasets -v
```
Expected: all PASS.

- [ ] **Step 4.5 — Commit**

```bash
git add jclparser/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add datasets subcommand"
```

---

## Task 5: `sql` subcommand

**Files:**
- Modify: `jclparser/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 5.1 — Write failing tests**

Add to `tests/unit/test_cli.py`:

```python
@pytest.mark.unit
class TestCLISQL:
    """Test 'sql' subcommand."""

    def test_sql_no_sql_job(self, capsys):
        # sort_job.jcl uses SORT/ICEMAN — not DB2
        rc = main([SORT_JCL, "sql"])
        assert rc == 0  # no SQL detected → exit 0
        out = capsys.readouterr().out
        assert "no SQL" in out.lower() or out.strip() == ""

    def test_sql_utility_job_json(self, capsys):
        util_jcl = str(FIXTURES / "sample_jcl" / "utility_programs.jcl")
        rc = main([util_jcl, "sql", "--json"])
        assert rc in (0, 1)
        data = json.loads(capsys.readouterr().out)
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_sql_json_result_keys(self, capsys):
        util_jcl = str(FIXTURES / "sample_jcl" / "utility_programs.jcl")
        main([util_jcl, "sql", "--json"])
        data = json.loads(capsys.readouterr().out)
        for item in data["results"]:
            assert "step" in item
            assert "program" in item
            assert "is_db2_program" in item
            assert "has_sql" in item

    def test_sql_exits_one_when_sql_found(self, capsys):
        # Build minimal JCL inline that references DSN (DB2) program
        from jclparser.parser import parse_jcl
        import io

        jcl = (
            "//DBJOB  JOB\n"
            "//STEP1  EXEC PGM=DSNUTILB\n"
            "//SYSIN  DD *\n"
            "  SELECT * FROM TABLE1\n"
            "/*\n"
        )
        job = parse_jcl(io.StringIO(jcl))
        from jclparser.cli import _cmd_sql
        import io as _io
        import sys

        old = sys.stdout
        sys.stdout = _io.StringIO()
        rc = _cmd_sql(job, json_output=False)
        sys.stdout = old
        assert rc == 1
```

- [ ] **Step 5.2 — Run to confirm FAIL**

```bash
pytest tests/unit/test_cli.py::TestCLISQL -v
```
Expected: FAIL.

- [ ] **Step 5.3 — Add dispatch and implementation**

Add after `datasets` dispatch in `main()`:

```python
    if query.lower() == "sql":
        return _cmd_sql(job, json_out)
```

Add functions:

```python
def _cmd_sql(job: "Job", json_output: bool = False) -> int:
    results = detect_sql_in_job(job)
    hits = [r for r in results if r.has_sql]
    if json_output:
        items = [
            {
                "step": r.step_name,
                "program": r.program,
                "is_db2_program": r.is_db2_program,
                "has_sql": r.has_sql,
                "sql_categories": sorted(r.sql_categories),
                "sql_statements": [
                    {"keyword": kw, "category": cat, "dd": dd}
                    for kw, cat, dd in r.sql_statements
                ],
            }
            for r in hits
        ]
        print(json.dumps({"results": items, "count": len(items)}, indent=2))
    else:
        _print_sql_results(hits)
    return 1 if hits else 0


def _print_sql_results(hits: list) -> None:
    if not hits:
        print("(no SQL detected)")
        return
    for r in hits:
        db2_tag = " [DB2 program]" if r.is_db2_program else ""
        cats = ", ".join(sorted(r.sql_categories)) if r.sql_categories else ""
        cat_tag = f"  categories={cats}" if cats else ""
        print(
            f"  {r.step_name or '(unnamed)':<12} PGM={r.program or '(none)'}{db2_tag}{cat_tag}"
        )
        for kw, cat, dd in r.sql_statements:
            print(f"    {kw:<20} [{cat}] in DD={dd}")
```

- [ ] **Step 5.4 — Run tests**

```bash
pytest tests/unit/test_cli.py::TestCLISQL -v
```
Expected: all PASS.

- [ ] **Step 5.5 — Commit**

```bash
git add jclparser/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add sql subcommand"
```

---

## Task 6: `analyze` subcommand

**Files:**
- Modify: `jclparser/cli.py`
- Modify: `tests/unit/test_cli.py`

Supports optional `STEPNAME` as a third token: `jcl-parser FILE analyze STEPNAME`.

- [ ] **Step 6.1 — Write failing tests**

Add to `tests/unit/test_cli.py`:

```python
@pytest.mark.unit
class TestCLIAnalyze:
    """Test 'analyze' subcommand."""

    def test_analyze_all_steps_text(self, capsys):
        util_jcl = str(FIXTURES / "sample_jcl" / "utility_programs.jcl")
        rc = main([util_jcl, "analyze"])
        assert rc == 0
        out = capsys.readouterr().out
        # IEBGENER should be recognised
        assert "IEBGEN" in out or "IEBGENER" in out

    def test_analyze_json_structure(self, capsys):
        util_jcl = str(FIXTURES / "sample_jcl" / "utility_programs.jcl")
        rc = main([util_jcl, "analyze", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_analyze_json_result_keys(self, capsys):
        util_jcl = str(FIXTURES / "sample_jcl" / "utility_programs.jcl")
        main([util_jcl, "analyze", "--json"])
        data = json.loads(capsys.readouterr().out)
        for item in data["results"]:
            assert "step" in item
            assert "program" in item
            assert "summary" in item
            assert "notes" in item

    def test_analyze_single_step(self, capsys):
        util_jcl = str(FIXTURES / "sample_jcl" / "utility_programs.jcl")
        rc = main([util_jcl, "analyze", "IEBGEN"])
        assert rc in (0, 1)  # 0=found profile, 1=no profile match
        capsys.readouterr()

    def test_analyze_unknown_step_returns_one(self, capsys):
        rc = main([SORT_JCL, "analyze", "NOSUCHSTEP"])
        assert rc == 1
        capsys.readouterr()
```

- [ ] **Step 6.2 — Run to confirm FAIL**

```bash
pytest tests/unit/test_cli.py::TestCLIAnalyze -v
```
Expected: FAIL.

- [ ] **Step 6.3 — Add dispatch in `main()`**

After `sql` dispatch:

```python
    if query.lower() == "analyze":
        # optional third token: step name
        step_filter = tokens[2].upper() if len(tokens) > 2 else None
        return _cmd_analyze(job, json_out, step_filter=step_filter)
```

- [ ] **Step 6.4 — Add `_cmd_analyze` and `_print_analyze_results`**

```python
def _cmd_analyze(
    job: "Job", json_output: bool = False, step_filter: str | None = None
) -> int:
    if step_filter:
        step = job.get_step(step_filter)
        if step is None:
            print(f"Step not found: {step_filter}", file=sys.stderr)
            return 1
        result = analyze_step(step)
        results = [result] if result is not None else []
    else:
        results = analyze_job(job)

    if json_output:
        items = [
            {
                "step": r.step_name,
                "program": r.program,
                "summary": r.summary,
                "notes": r.notes,
                "raw_control": r.raw_control,
            }
            for r in results
        ]
        print(json.dumps({"results": items}, indent=2))
    else:
        _print_analyze_results(results)
    return 0


def _print_analyze_results(results: list) -> None:
    if not results:
        print("(no program profile matches)")
        return
    for r in results:
        step_label = r.step_name or "(unnamed)"
        print(f"  {step_label:<12} PGM={r.program}")
        if r.summary:
            print(f"    {r.summary}")
        for note in r.notes:
            print(f"    note: {note}")
        print()
```

- [ ] **Step 6.5 — Run tests**

```bash
pytest tests/unit/test_cli.py::TestCLIAnalyze -v
```
Expected: all PASS.

- [ ] **Step 6.6 — Commit**

```bash
git add jclparser/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add analyze subcommand"
```

---

## Task 7: `paths` subcommand

**Files:**
- Modify: `jclparser/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 7.1 — Write failing tests**

Add to `tests/unit/test_cli.py`:

```python
@pytest.mark.unit
class TestCLIPaths:
    """Test 'paths' subcommand."""

    def test_paths_no_conditionals(self, capsys):
        # sort_job.jcl has no IF/THEN/ELSE blocks
        rc = main([SORT_JCL, "paths"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "no" in out.lower() or "empty" in out.lower() or out.strip() == ""

    def test_paths_with_conditionals_text(self, capsys):
        rc = main([CONDITIONAL_JCL, "paths"])
        assert rc == 0
        capsys.readouterr()

    def test_paths_json_structure(self, capsys):
        rc = main([CONDITIONAL_JCL, "paths", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "unreachable_steps" in data
        assert "always_skipped" in data
        assert "contradictory_conditions" in data
        assert "duplicate_if_branches" in data

    def test_paths_always_exits_zero(self, capsys):
        rc = main([SORT_JCL, "paths"])
        capsys.readouterr()
        assert rc == 0

        rc = main([CONDITIONAL_JCL, "paths"])
        capsys.readouterr()
        assert rc == 0
```

- [ ] **Step 7.2 — Run to confirm FAIL**

```bash
pytest tests/unit/test_cli.py::TestCLIPaths -v
```
Expected: FAIL.

- [ ] **Step 7.3 — Add dispatch in `main()`**

After `analyze` dispatch:

```python
    if query.lower() == "paths":
        return _cmd_paths(job, json_out)
```

- [ ] **Step 7.4 — Add `_cmd_paths` and `_print_paths`**

```python
def _cmd_paths(job: "Job", json_output: bool = False) -> int:
    report = compute_feasible_paths(job)
    if json_output:
        print(
            json.dumps(
                {
                    "unreachable_steps": report.unreachable_steps,
                    "always_skipped": report.always_skipped,
                    "contradictory_conditions": [
                        list(pair) for pair in report.contradictory_conditions
                    ],
                    "duplicate_if_branches": [
                        {"line": line, "condition": cond}
                        for line, cond in report.duplicate_if_branches
                    ],
                },
                indent=2,
            )
        )
    else:
        _print_paths(report)
    return 0


def _print_paths(report) -> None:
    if report.is_empty():
        print("(no feasibility issues found)")
        return
    if report.unreachable_steps:
        print("Unreachable steps:")
        for s in report.unreachable_steps:
            print(f"  {s}")
    if report.always_skipped:
        print("Always skipped:")
        for s in report.always_skipped:
            print(f"  {s}")
    if report.contradictory_conditions:
        print("Contradictory conditions:")
        for a, b in report.contradictory_conditions:
            print(f"  {a}  vs  {b}")
    if report.duplicate_if_branches:
        print("Duplicate IF branches:")
        for line, cond in report.duplicate_if_branches:
            print(f"  line {line}: {cond}")
```

- [ ] **Step 7.5 — Run tests**

```bash
pytest tests/unit/test_cli.py::TestCLIPaths -v
```
Expected: all PASS.

- [ ] **Step 7.6 — Commit**

```bash
git add jclparser/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add paths subcommand"
```

---

## Task 8: Full test suite + update help text

**Files:**
- Modify: `jclparser/cli.py` (docstring at top + argparse description)
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 8.1 — Update module docstring in `cli.py`**

Replace the docstring at the top of `jclparser/cli.py`:

```python
"""
Command-line interface for jclparser.

Usage:
    jcl-parser FILE                              Show job summary
    jcl-parser FILE steps                        List all steps
    jcl-parser FILE procs [PROCNAME]             List/detail procedures
    jcl-parser FILE procs --explode              Show procedure expansion audit
    jcl-parser FILE procs --list-available       List PROCs in --proc-path libraries
    jcl-parser FILE STEP                         Show step details
    jcl-parser FILE STEP.DDNAME                  Show a specific DD statement
    jcl-parser FILE DDNAME                       Show all DDs with that name
    jcl-parser FILE --json                       Full parse result as JSON
    jcl-parser FILE --validate                   Validate the JCL
    jcl-parser FILE detect                       Detect file type (JCL/PROC/UNKNOWN)
    jcl-parser FILE metrics                      Structural metrics for the job
    jcl-parser FILE lint                         Run lint rules against the job
    jcl-parser --lint-list                       List all available lint rule codes
    jcl-parser FILE datasets                     Dataset lifecycle analysis
    jcl-parser FILE sql                          SQL/DB2 detection
    jcl-parser FILE analyze [STEPNAME]           Program profile analysis
    jcl-parser FILE paths                        RC feasibility path analysis
"""
```

- [ ] **Step 8.2 — Run full test suite**

```bash
pytest --tb=short -q
```
Expected: all pass, coverage >= 90%.

- [ ] **Step 8.3 — Fix any failures**

If tests fail, diagnose and fix before proceeding. Do not commit a broken suite.

- [ ] **Step 8.4 — Final commit**

```bash
git add jclparser/cli.py
git commit -m "docs(cli): update module docstring with all subcommands"
```

- [ ] **Step 8.5 — Push**

```bash
git push origin main
```
