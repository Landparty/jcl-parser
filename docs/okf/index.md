# jcl-parser — OKF Index

> **AI quick-start:** Load this file first for fast orientation. For the full reference (module inventory, API tiers, PROC chain, 14 invariants, task → file map), load [`../OKF.md`](../OKF.md).

**Last Updated:** 2026-06-27

---

## What Is This Repo?

`jclparser` is a pure-Python library (Python 3.10+) for parsing IBM z/OS JCL. It builds a structured model of Jobs, Steps, and DD statements; validates JCL syntax; expands PROCs; and provides analysis tools for datasets, SQL, metrics, linting, and return-code feasibility.

| Attribute | Value |
|-----------|-------|
| Package | `jclparser` |
| Version | 1.1.0 |
| Python | ≥3.10 |
| Runtime deps | **None** |
| Integration | Vendored into `backend/_vendor/jcl-parser/` — manual copy required |
| Vendor sync | `cp -r jclparser/ ../backend/_vendor/jcl-parser/jclparser/` |
| Interface contract | [`interface-contract.md`](../../interface-contract.md) |

---

## Pipeline at a Glance

```
Input → ContinuationLineHandler → parse_jcl() → validate_jcl() → explode_job() → Job
```

Key invariant: **`parse_jcl()` does NOT expand PROCs**. Call `explode_job()` separately.

---

## Quick Navigation → OKF.md Sections

| Section | What you need |
|---------|---------------|
| [§1 Identity](../OKF.md#1-identity) | Package facts, version, install |
| [§2 Repository Layout](../OKF.md#2-repository-layout) | Module inventory with line counts |
| [§3 Parsing Pipeline](../OKF.md#3-parsing-pipeline-data-flow) | Step-by-step data flow |
| [§4 Public API Tiers](../OKF.md#4-public-api-tiers) | Tier 1/2/3 API tables |
| [§5 Data Model](../OKF.md#5-data-model-hierarchy) | Job, Step, DDStatement, Parameter |
| [§6 PROC Chain](../OKF.md#6-proc-loading-chain) | Loader resolution order |
| [§7 Test Structure](../OKF.md#7-test-structure) | Unit / integration / benchmark layout |
| [§8 CLI Reference](../OKF.md#8-cli-reference) | All `jcl-parser` subcommands |
| [§9 Configuration](../OKF.md#9-configuration-reference) | Env vars, path config |
| [§10 Logging](../OKF.md#10-logging) | Logger names, structured fields |
| [§11 Invariants](../OKF.md#11-key-invariants-and-non-obvious-behaviors) | 14 non-obvious rules |
| [§12 Task → File](../OKF.md#12-common-task--file-mapping) | Where to edit for common tasks |
| [§13 Dev Workflow](../OKF.md#13-development-workflow) | Coverage floor, vendor sync, mypy |

---

## Most Common Task → File

| Task | File |
|------|------|
| Fix a parsing bug | `jclparser/parser.py` |
| Add a data model field | `jclparser/model.py` |
| Fix PROC expansion | `jclparser/explosion.py` |
| Add a lint rule | `jclparser/lint/rules.py` |
| Add a CLI subcommand | `jclparser/cli.py` |
| Add a program profile | `jclparser/program_profiles/` |

---

## Maintenance

Update `docs/OKF.md` in the same commit as the source change. Bump `Last Updated` in both files on every OKF edit.
