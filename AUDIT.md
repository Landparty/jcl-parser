# jclparser — Codebase Audit & Refactor Plan

**Date:** 2026-09-27 · **Commit audited:** `55f4339` (main) · **Scope:** `jclparser/` (61 modules, 13.8k LOC), `tests/` (103 files, 27.5k LOC), build/CI/docs.
**Status:** Every finding below was reproduced with a script or command, except where marked
**requires validation**. The audit itself changed no production code.

> **This is a point-in-time audit of commit `55f4339` (2026-09-27).** The findings below are kept
> as written; file and line references point at that commit and many have since moved. The
> table that follows is the current status of every finding.

## Status (2026-10-29)

| ID | Status | Where it was resolved / what is left |
|---|---|---|
| C1–C6, H1, H2, H5, M3 | Resolved | Same PR as the audit; regression tests in `tests/unit/test_audit_patch_fixes.py` |
| H3 | Resolved | `scripts/okf_staleness_check.py` maps sources to `.okf/` pages |
| H4 | Resolved | CI `typecheck` job runs `scripts/mypy_ratchet.py` against `mypy-baseline.txt`; the closed-source build was dropped (pure-Python wheel, CI `build` job) |
| H6 | Resolved | `max_steps` is counted per produced step; `DEFAULT_MAX_STEPS = 10_000` |
| H7 | **Open** (partly done) | In-stream detection is shared (`utils.instream_delimiter`, `_source_scanner._RecordClassifier`); the five quote/paren scanners are still separate. Roadmap item "shared tokenizer" |
| H8 | Resolved | `ruff` enforces McCabe ≤ 12 (`C901`); no `noqa: C901` baseline marker is left in `jclparser/` |
| M1 | Resolved | #122 |
| M2 | Resolved for card images | #65: a quoted string continued from an 80-column card keeps its column-71 blank; short editor lines keep the blank-dropping join by design |
| M4 | Resolved | `validate_jcl` keeps each finding's severity and line |
| M5 | Resolved | `strict_mode`, `dialect`, `enabled_plugins`, `validation_level` and `detect_sql` are all read |
| M6 | Resolved | A `str` source is always content (2026-10-03) |
| M7 | Resolved | Root doc tree deleted; `.okf/` is the only tree |
| M8 | **Open** (partly done) | Assertion-less `try/except Exception: pass` tests now assert (2026-10-29); the `*_coverage` / `*_comprehensive` files are not consolidated and there are no Hypothesis tests (roadmap item 6) |
| M9 | **Open** | Only about 530 of about 2,970 tests carry a marker; benchmarks do not run in CI |
| M10 | **Open** (partly done) | ruff and mypy are pinned; actions are still pinned by tag, not by commit hash |
| M11 | Resolved | Directory argument (lineage / lint / validate), stdin, step names that equal a query word (#133), intermixed flags |
| L1 | **Open** | `JOB (ACCT),'X=Y'` still gives `{"'X": "Y'"}` |
| L2 | Not re-checked | |
| L3 | Open (by design) | Columns 72-80 are the sequence field and are dropped without a warning |
| L4 | Resolved | `Step.dynamnbr` / `Step.perform` return `None` for symbolic or list values |
| L5 | Resolved | Plugins can be unregistered per instance; registries are still process-global |
| L6 | **Open** (partly done) | The cp1252 fallback now runs before latin-1; the INCLUDE loader still tries only the uppercase member name |
| L7 | **Open** | A nested `EXEC &INNER` inside a PROC is not substituted (`ProcedureNotFoundError: &INNER`) |
| L8 | Partly done | The current directory is never searched; the `JCL_PROCLIB_PATH` lookup is still duplicated in `proc_loader.py` and `include_loader.py` |
| L9 | Not re-checked | |
| L10 | Partly done | Author email is real; the classifier still says `Production/Stable`; the closed-source checks are gone |
| L11 | Resolved | `_registry` removed (2026-10-29) |
| L12 | Resolved | #134 |
| L13 | **Open** | No `DeprecationWarning` mechanism yet |
| L14 | Resolved | CLAUDE.md invariant 5 lists the real baseline (77 errors in 23 modules) |

## How this was measured

| Check | Result |
|---|---|
| `pytest` (Python 3.11) | **2342 passed, 2 skipped**, 11.4 s, **94.85 %** branch coverage (floor 90 %) |
| `ruff check .` / `ruff format --check .` | Clean (169 files) |
| `mypy jclparser/` (strict, mypy 2.3.1) | **95 errors in 28 files** (worst: `explosion.py` 20, `model.py` 17, `parser.py` 7, `cli.py` 7, `profiling.py` 7) |
| Runtime dependencies | None (`pyproject.toml:30`), so there is no runtime supply-chain exposure |
| Outdated tooling (`pip list --outdated`) | Only `setuptools` (68 → 84) locally. Dev floors are very loose: `ruff>=0.1`, `mypy>=1.0` (`pyproject.toml:37-38`) |
| Churn: commits touching each file since 2026-01-01 / `fix:` commits | `explosion.py` 20 / 12, `parser.py` 15 / 7, `_job_builder.py` 8 / 5, `continuation_handler.py` 9 / 4, `utils.py` 9 / 4. 35 of 95 non-merge commits are fixes |
| Complexity (AST branch count; see table below) | 9 functions exceed McCabe 15 (`ruff --select C901`) |
| Profiling (cProfile plus `tests/benchmarks`) | Parse time grows linearly: 10k lines 0.20 s, 20k 0.42 s, 40k 0.80 s. No hot-path problem |
| Fuzzing | 30,000 random or garbled inputs through `parse_jcl` and `validate_jcl` produced no unexpected exceptions. Targeted inputs found the crashes listed below |

**Security scope note.** This is a parsing library. It has no authentication, payments, network I/O or
PII storage. For this library the security-sensitive surface is **reading files from the host
filesystem** (the PROC, INCLUDE and source loaders) and **resource exhaustion from untrusted JCL**.
The audit concentrated on those two areas.

---

## 1. Executive summary

- **The core is solid.** The suite has 2.3k passing tests at 95 % coverage, parse time scales linearly, 30k fuzzed inputs caused no crashes, and there are no runtime dependencies. The problems are at the edges, not in the main parsing loop.
- **Untrusted JCL can make the parser read files outside the configured PROCLIB base.** `JCLLIB ORDER=(/abs/path)` or `ORDER=(../x)` bypasses the path guard (C1).
- **Untrusted JCL can exhaust memory and CPU.** Self-including INCLUDE members and self-referencing symbols grow exponentially: 186 bytes of input produce 43 MB of output (C2, C3).
- **Some valid JCL is silently misparsed.** A quoted `DLM='$)'` drops the rest of the job, and an indented `/*` inside `DD *` data ends the data early (C4, C5). Both happen without any warning.
- **Release metadata and tooling have drifted.** `__version__` says 1.1.0 while the package is 1.4.0. The backend contract promises an import that fails. The pre-commit docs hook checks a file that doesn't exist. CI never runs mypy (H1–H4).

---

## 2. Critical issues (fix before next release)

### C1. `JCLLIB ORDER` bypasses the PROCLIB path guard (arbitrary file read)
- **Where:** `jclparser/proc_loader.py:209`. `library_path = self.base_path / library` is never checked to be inside `base_path`. The guard at `:230` only checks the candidate file against `library_path` itself. An absolute `library` replaces the base path entirely, because of how `pathlib` joins paths.
- **Evidence:** an end-to-end `parse_jcl` + `explode_job` run on JCL containing `//L JCLLIB ORDER=(/tmp/…/outside)` loaded `EVIL.jcl` from outside the base and exploded it (`[('S.S1', 'STOLEN')]`). The same happens with `ORDER=(../outside)`.
- **Impact:** any JCL-shaped file on the host can be pulled into the model, and the lookup doubles as a file-existence probe. Non-JCL files such as `/etc/passwd` fail to parse and are not returned.
- **Fix:** after `:209`, `if not is_within_directory(library_path, self.base_path): return None`, plus a regression test. **Effort:** under 1 hour.

### C2. INCLUDE expansion grows exponentially and has no cycle detection
- **Where:** `jclparser/include_loader.py:193-221`. The only bound is `max_depth=8`: there is no set of visited members and no cap on output size. `parse_jcl` runs this automatically whenever the input contains INCLUDE (`parser.py:331-345`).
- **Evidence:** a member that includes itself k times:

  | k | Input | Output | Time |
  |---|---|---|---|
  | 2 | 94 B | 512 lines | — |
  | 4 | 140 B | 87,382 lines | — |
  | 6 | 186 B | 2,015,540 lines (43.7 MB) | 0.9 s |

  k = 10 is about 10⁸ lines, enough to exhaust memory.
- **Fix:** keep a stack of members currently being expanded and reject recursion with a dedicated error. Cap total expanded lines and bytes. **Effort:** 1–2 hours.

### C3. Self-referencing symbols grow exponentially
- **Where:** `jclparser/explosion.py:309-323`. Nested resolution recurses to `_MAX_NESTED_SUBSTITUTION = 8` and duplicates every reference at each level. The cycle is never reported.
- **Evidence:** `A='&A&A&A&A&A&A'` resolves to 21.8 M characters in 5.4 s. Through an inline `//P PROC A='&A&A&A&A&A'`, a DSN becomes 4.3 M characters in 3.8 s.
- **Fix:** track the symbols being resolved, warn or raise on a cycle, and cap the length of a resolved value. **Effort:** 1–2 hours.

### C4. A quoted `DLM=` containing `)` or `,` silently drops the rest of the job
- **Where:** the delimiter is computed twice, differently: `parser.py:279-285` (`_instream_delimiter` stops scanning at `)`) and `_job_builder.py:356-359` (uses the parsed value).
- **Evidence:** a job with `//SYSUT1 DD *,DLM='$)'`, then data, then `$)`, then another DD and step `S2`. The result is `[('S1', ['SYSUT1'])]` with `warnings == []`. `SYSUT2` and `S2` are gone.
- **Fix:** compute the delimiter once, from `_parse_parameters`, and share it between both passes. **Effort:** about 2 hours with tests.

### C5. An indented `/*` inside `DD *` data ends the data early
- **Where:** `parser.py:140` and `_job_builder.py:156` both test `line.strip().startswith(delimiter)`. On z/OS the delimiter only counts in columns 1–2.
- **Evidence:** `SYSTSIN DD *` followed by `  /* comment */` and `  RUN PROG`. The result is `SYSTSIN` with data `''`, plus an invented `SYSIN` DD holding `'  RUN PROG'`. This case is common: C, REXX and SQL comments in SYSIN all start with `/*`.
- **Fix:** match against the unstripped line (`line.startswith(delimiter)`). **Effort:** about 30 minutes with tests.

### C6. `RecursionError` escapes `parse_jcl` and `validate_jcl`
- **Where:** `jclparser/condition_parser.py:361-380, 496`. `parse_condition` catches only `ValueError`, `TypeError`, `IndexError` and `AttributeError`.
- **Evidence:** an `IF` nested about 600 parentheses deep (spread across continuation records), or about 2,000 chained `NOT`s, raises a raw `RecursionError` from both entry points.
- **Fix:** catch `RecursionError` (so the call returns `condition_ast = None` as documented), or cap nesting depth. **Effort:** 15 minutes.

---

## 3. High-priority refactors

| ID | Issue | Evidence | Fix | Effort |
|---|---|---|---|---|
| H1 | **Version mismatch.** `__version__ = "1.1.0"` (`jclparser/__init__.py:23`), but `pyproject.toml:7` and `.release-please-manifest.json` say 1.4.0 | `python -m jclparser --version` prints `jcl-parser 1.1.0`. `release-please-config.json` has no `extra-files` entry for `__init__.py` | Use `importlib.metadata.version("jcl-parser")`, or add `extra-files` | 30 min |
| H2 | **Backend contract is broken.** `interface-contract.md:53-61` says `JCLParseError` "must be importable" from `jclparser` | `ImportError: cannot import name 'JCLParseError'`. The class exists at `errors.py:51` but isn't re-exported | Add it to `__init__`/`__all__` (preferred, since it is the base class the backend catches), or correct the contract | 15 min |
| H3 | **Pre-commit docs hook checks a file that doesn't exist.** `scripts/okf_staleness_check.py:17-31` maps every path to `docs/OKF.md` | `docs/` contains only `superpowers/`. The hook (`.githooks/pre-commit`) fails any commit touching `jclparser/` or `tests/`, so contributors have to use `--no-verify`. This probably explains why doc updates kept landing in the wrong tree (see CLAUDE.md) | Map sources to `.okf/**` pages and exempt `.okf/` | 1 h |
| H4 | **CI doesn't type-check, and the closed-source build job is weak.** No workflow runs mypy, although strict mode reports 95 errors. `ci.yml:45-60` only runs `build_ext --inplace`: no leak check, no tests against compiled code, and not on push to main | Workflow files; mypy output above | Add a mypy job that ratchets against a baseline. Run `scripts/verify_closed_source_wheel.py`, or a pytest subset, after `build_ext` | 2–3 h |
| H5 | **`explode_job` ignores `strict_symbols` for the EXEC parameters of plain steps.** `explosion.py:1108-1112` doesn't pass `strict=` (compare `:1104`, `:1118`) | A plain step with `PARM='&NOPE'` is silently blanked to `''`. Inside a PROC the same statement raises `UndefinedSymbolError` | Pass the flag. Then extract one `_substitute_step()` helper to replace the three near-duplicate walkers (`_process_steps` `:1073`, `_process_proc_steps` `:460`, `_explode_nested` `:1315`) that let this drift happen | 5 min fix; 2–3 h refactor |
| H6 | **`max_steps` doesn't bound PROC fan-out.** `_check_step_limit` runs only after a whole top-level `_explode_step` tree is built (`explosion.py:1080-1094`). The default is `0` (unlimited) | 6 calls × 5 levels: `max_steps=10` tripped only after 7,776 steps had been built | Check the counter before each append inside the recursion, and choose a non-zero default | 1 h |
| H7 | **Two separate in-stream state machines, and five quote/paren scanners that disagree.** In-stream data: `parser._merge_source_lines` (`:94-258`) and `JobBuilder.consume_inline_data`/`_on_dd`. Scanners: `_find_comment_start`, `_check_param_balance`, `_parse_list_parameter`, `ParameterParser._split_parameters`, `_analyze_line_context` | C4 is direct proof of the drift. M1 below is another scanner disagreement | Move to one tokenizer for quotes and parentheses, and one in-stream detector used by both passes. This is the highest-leverage structural change in the repo | 3–5 days |
| H8 | **Functions that are too long or too complex.** Ranked by branch count / lines: `cli.main` (39 / 214, `cli.py:63-276`), `validate_jcl` (34 / 180, `parser.py:571-750`), `_merge_source_lines` (34 / 165, `parser.py:94-258`), `_parse_jcl_core` (28 / 162, `parser.py:314-475`), `parse_statement` (25 / 139, `_statement_parser.py:250-388`), `_explode_step` (22 / 160, `explosion.py:1182-1341`), `explode_job` (16 / 180, `explosion.py:1000-1179`) | Churn data: `explosion.py` and `parser.py` carry 19 of the 35 fix commits | Split along the natural seams: subcommand dispatch table in the CLI, per-level validators, and the explosion helper from H5. Add `C901` to ruff with a baseline | 3–4 days, incremental |

---

## 4. Medium-priority improvements

| ID | Issue | Location / evidence | Effort |
|---|---|---|---|
| M1 | **Resolved (#122):** `\'` is treated as an escape (JCL has no backslash escape), so the next statement is merged into a quoted value | `continuation_handler.py:359`. `SET DIR='C:\'` followed by `SET HLQ=PROD` gives `DIR = "'C:\\'SET HLQ=PROD"` | 15 min |
| M2 | A blank in column 71 inside a quoted continuation is lost | `utils.py:75` (rstrip) and `continuation_handler.py:218,272`. `PARM='WORD1 …` + `WORD2'` gives `'WORD1WORD2'` | 2 h |
| M3 | `DLM=(AB)` crashes with `AttributeError` | `_job_builder.py:358`: `'list' object has no attribute 'startswith'` | 15 min |
| M4 | `validate_jcl` reports every WARNING as ERROR and drops line numbers | `parser.py:592-598, 607-612`. `job.validate()` returns WARNING, while `validate_jcl(level="structure")` returns `('ERROR', 0, …)` | 15 min |
| M5 | Most `ParserConfig` fields are silently ignored: `strict_mode`, `dialect`, `enabled_plugins`, `validation_level` | `plugins/__init__.py:32-36`. Only `detect_sql` is read (`parser.py:449`). `parse_jcl(bad, config=ParserConfig(strict_mode=True))` doesn't raise, unlike `strict_mode=True` | 2–4 h (wire up or deprecate) |
| M6 | A one-line string that names an existing file is read as a path, and error messages echo the file's content | `utils.py:173-186`. `parse_jcl("/tmp/…/secret")` raises `JCLSyntaxError: … TOP SECRET NOT JCL`. This is a risk if the backend ever passes untrusted one-line input | 1 h (API change: prefer an explicit `Path`) |
| M7 | **Resolved (2026-10-03, URL 2026-10-15):** Stale duplicate doc tree still tracked, and README links to it | The root `index.md`, `log.md`, `core/`, `api/`, `advanced/`, `development/` and `integration/` all differ from their `.okf/` twins. `README.md:54` links to the root `index.md`. The `Documentation` URL (`pyproject.toml:54`) points at `docs/`, which has no user docs | 30 min (`git rm`, relink) |
| M8 | Tests written to raise coverage rather than check behaviour | 22 tests have no assertion, e.g. `tests/unit/test_parser_final_push.py:11-23` wraps `parse_jcl` in `try/except Exception: pass`. 17 files are named `*_coverage`, `*_comprehensive` or `final_push`, and overlap others (`test_utils.py`, `test_utils_comprehensive.py`, `test_utils_coverage.py`). There are no property-based or fuzz tests | 1–2 days (consolidate; add Hypothesis for `ContinuationLineHandler` and `ParameterParser`) |
| M9 | About 72 % of tests have no marker, so `pytest -m unit` runs only 500 of 2344. Benchmarks never run in CI, and no baseline is committed, although the `.claude/agents/regression-detector.md` agent expects one | `pyproject.toml` markers and `norecursedirs` | 1 h |
| M10 | Supply-chain hygiene in CI | Actions are pinned by tag, not commit hash (`actions/checkout@v4`, `release-please-action@v4`); `pypa/gh-action-pypi-publish@release/v1` is a moving branch. `pip install ruff` is unpinned (`ci.yml:23`). Jobs in `release-please.yml` inherit workflow-level `pull-requests: write` and `issues: write` they don't need | 2 h |
| M11 | CLI robustness | A directory argument crashes with `IsADirectoryError` (`cli.py:135` checks `exists()`, not `is_file()`). Only 3 exception types are caught (`:173`). Steps named `SQL` or `PATHS` can't be looked up, because subcommand words are checked first (`:205-273`). `FILE --json lint` exits 2 (`nargs="*"` mixed with options). `assert` is used for control flow (`:166`) | 3 h |

---

## 5. Low-priority nice-to-haves

- **L1.** A quoted positional containing `=` is read as a keyword: `JOB (ACCT),'X=Y'` gives `{"'X": "Y'"}` (`_statement_parser.py:509-510`).
- **L2.** The same "suspect comment" warning is emitted twice (`continuation_handler.py:215` and `:260`).
- **L3.** Lines over 71 columns are truncated without a warning, even when the discarded text isn't a sequence field (`utils.py:68-69`).
- **L4.** `Step.dynamnbr` and `Step.perform` raise `ValueError` or `TypeError` on symbolic or list values (`model.py:544, 570`). `DDStatement`'s parsed-parameter cache goes stale after an in-place edit of `parameters` (`model.py:272-284`).
- **L5.** `PluginRegistry` keys plugins by class name, so after registering two instances of one class, one can't be unregistered (`plugins/__init__.py:62-72`). Registries are process-global with no locking (`lint/runner.py:21`, `program_profiles/registry.py:19`, `plugins/__init__.py:108`); thread-safety **requires validation**.
- **L6.** The include loader ignores lowercase file names despite its docstring (`include_loader.py:142-155`; `proc_loader.py:217-226` does try them). The cp1252 and binary fallbacks in `utils.py:100-108` can never run, because latin-1 decodes every byte first.
- **L7.** A nested `EXEC &INNER` inside a PROC is never symbol-substituted (`explosion.py:483-490, 1233`). Whether z/OS allows a symbolic PROC name here **requires validation**.
- **L8.** The `JCL_PROCLIB_PATH`/current-directory fallback is duplicated (`proc_loader.py:138-140`, `include_loader.py:111-113`). When the variable is unset, both loaders read from the process's working directory.
- **L9.** A minor hot-path cost: `_operand_field` runs about 4 times per record (32,003 calls for 8,001 lines in cProfile). `_find_comment_start` is quadratic on blank-heavy operands (`_statement_parser.py:201`), but records are capped at 71 columns, so it can't bite in practice.
- **L10.** Packaging metadata: the author email is a placeholder (`pyproject.toml:10`), and `Development Status :: 5 - Production/Stable` is optimistic given the mypy debt. `scripts/_closed_source_checks.py:34` matches with `endswith`, so a file like `xprofiling.py` would pass the allow-list.
- **L11.** Dead code: `_registry` at `jclparser/__init__.py:159`.
- **L12.** The `.claude/settings.json` format hook relies on `$CLAUDE_TOOL_INPUT_FILE_PATH`. Whether that variable is populated **requires validation**; if it isn't, the hook does nothing.
- **L13.** There is no deprecation mechanism (`warnings.warn(..., DeprecationWarning)` appears nowhere). Retiring the `parser.py` re-export shim (about 26 names re-exported through two levels) or the dead `ParserConfig` fields will need one. Whether external callers import the private names through `jclparser.parser` **requires validation**.
- **L14.** CLAUDE.md invariant 5 understates the mypy debt. It names profiling, explosion and the parser modules, but `model.py` (17 errors), `cli.py` (7) and about 20 other files also fail.

---

## 6. Areas that are well built

- **Robust main parsing loop.** 30k fuzzed inputs caused no crashes. `Job.warnings` gives dropped content somewhere to be reported. `parse_condition` returns `None` rather than a partial AST when it can't parse the whole condition, which matches invariant 3.
- **Linear performance.** Parsing 40k lines takes 0.8 s, and 40k in-stream records take 0.03 s. `ContinuationContext` tracks its state incrementally instead of rescanning the growing merged line. There are no regexes prone to catastrophic backtracking.
- **Path containment where it is applied.** `is_within_directory` (`utils.py:118-128`) resolves symlinks and treats any error as "outside", and correctly blocks `../` in member names. C1 is a gap in where it is applied, not a flaw in the helper. PROC cycles and depth are handled properly with dedicated `CircularProcedureError` and `ExplosionDepthError`.
- **Closed-source release pipeline.** The leak check runs against every installed wheel, `--import-mode=importlib` stops the source tree from shadowing the wheel, publishing uses PyPI Trusted Publishing, and manual runs default to testpypi. The reasoning is documented in unusual detail (CLAUDE.md and `pyproject.toml` comments).
- **Test discipline.** There are 2.3k tests, `filterwarnings = error`, `--strict-markers`, and a 90 % branch-coverage floor. `TestStatementDispatchCompleteness` fails if a statement type is added without a handler, which prevents a whole class of silent drops. There are zero runtime dependencies, `ruff` is clean, and the `&&TEMP` handling (`collapse_double_amp` / `keep_undefined`) is carefully designed.

---

## 7. Risk matrix

Scores: **Likelihood** (1 = rare, 5 = near certain on realistic input) × **Impact** (1 = cosmetic, 5 = data loss, security or outage). **Risk** = L × I.

| ID | Risk | Likelihood | Impact | Score | Priority |
|---|---|:-:|:-:|:-:|---|
| C5 | Indented `/*` truncates in-stream data | 4 | 4 | **16** | Critical |
| C1 | JCLLIB path traversal (file read) | 3 | 5 | **15** | Critical |
| C2 | INCLUDE exponential blow-up | 3 | 5 | **15** | Critical |
| C3 | Symbol self-reference blow-up | 3 | 5 | **15** | Critical |
| C4 | Quoted DLM drops rest of job silently | 2 | 5 | **10** | Critical |
| H7 | Divergent scanners and in-stream state machines | 4 | 3 | **12** | High |
| H2 | Contract import `JCLParseError` fails | 3 | 4 | **12** | High |
| H6 | `max_steps` doesn't bound fan-out | 2 | 5 | **10** | High |
| H1 | Wrong `__version__` shipped | 5 | 2 | **10** | High |
| H3 | Pre-commit hook always fails | 5 | 2 | **10** | High |
| C6 | `RecursionError` escapes public API | 2 | 4 | **8** | Critical (cheap fix) |
| H5 | `strict_symbols` ignored for plain steps | 3 | 3 | **9** | High |
| H4 | No mypy in CI; weak build check | 4 | 2 | **8** | High |
| H8 | Complex hot-churn functions | 4 | 2 | **8** | High |
| M1 | `\'` treated as escape | 2 | 4 | **8** | Medium |
| M5 | `ParserConfig` fields ignored | 3 | 2 | **6** | Medium |
| M6 | One-line path string read from disk | 2 | 3 | **6** | Medium |
| M2 | Column-71 blank lost in quoted continuation | 2 | 3 | **6** | Medium |
| M4 | Warnings reported as errors | 3 | 2 | **6** | Medium |
| M10 | Unpinned CI actions and loose permissions | 2 | 3 | **6** | Medium |
| M8/M9 | Coverage-driven tests; no benchmarks in CI | 3 | 2 | **6** | Medium |
| M7 | Stale duplicate docs | 4 | 1 | **4** | Medium |
| M11 | CLI edge-case crashes | 2 | 2 | **4** | Medium |
| L* | Low items | 1–2 | 1–2 | ≤4 | Low |

C6 scores lower than some High items but is listed as Critical because it is a raw non-library exception escaping the Tier 1 API, and the fix takes 15 minutes.

---

## 8. Proposed sequencing

1. **Patch release (about 1 day):** C1–C6, H1, H2, H5 and M3. All are small, local fixes, each with a regression test.
2. **Tooling (about 1 day):** H3, H4, M7, M9 and M10, which make future drift visible.
3. **Structural (1–2 weeks, incremental):** H7 (one tokenizer, one in-stream detector), then H6, H8 and M5. Replace coverage-driven tests with property-based tests (M8) as each area is touched.

*Step 1 of the sequencing (patch release) is implemented in this PR. Steps 2 and 3 await review before any further code changes.*
