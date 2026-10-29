# jcl-parser Development Guidelines

`CLAUDE.md` at the repository root is the maintained contributor guide: commands, architecture, key
invariants, code style and release process. The full reference is the OKF bundle, starting at
`.okf/index.md`. Read both before changing parsing code.

Quick facts:

- Pure-Python package `jclparser/` (no `src/` layout), Python 3.10+, no runtime dependencies.
- `pip install -e .[dev]`, then `pytest` (90% coverage floor), `ruff check .`, `ruff format .`,
  `python scripts/mypy_ratchet.py`.
- Document behaviour changes in the matching `.okf/` page and add an entry to `.okf/log.md`.
