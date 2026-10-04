#!/usr/bin/env python3
"""OKF staleness checker -- keeps the ``.okf/`` bundle in sync with source changes.

Each source path maps to the ``.okf/`` pages that describe it; a change is
covered when ANY of those pages, or the bundle's change log ``.okf/log.md``,
changes with it. (This used to point every path at ``docs/OKF.md``, which
does not exist, so every commit touching the package failed the hook.)

Modes
-----
  (no args)      Claude Code PostToolUse hook: read tool JSON from stdin,
                 print a one-line reminder if no covering OKF page was touched.
  --mode=git     Git pre-commit hook: check staged files and exit 1 if any
                 OKF-covered source changed without a covering OKF update.
"""

import json
import subprocess
import sys
from pathlib import Path

OKF_LOG = ".okf/log.md"

_PIPELINE = ".okf/core/parsing-pipeline.md"
_PROCS = ".okf/advanced/proc-expansion.md"
_VALIDATION = ".okf/advanced/validation.md"

# First matching prefix wins, so specific paths come before their directory.
OKF_MAP: list[tuple[str, list[str]]] = [
    ("jclparser/model.py", [".okf/core/data-model.md"]),
    ("jclparser/explosion.py", [_PROCS]),
    ("jclparser/proc_loader.py", [_PROCS]),
    ("jclparser/include_loader.py", [_PROCS]),
    ("jclparser/builtin_procs.py", [_PROCS]),
    ("jclparser/validators.py", [_VALIDATION]),
    ("jclparser/parameter_validators.py", [_VALIDATION]),
    ("jclparser/lint/", [_VALIDATION]),
    ("jclparser/cli.py", [".okf/api/cli-reference.md"]),
    ("jclparser/__init__.py", [".okf/api/public-api.md"]),
    ("jclparser/errors.py", [".okf/api/public-api.md"]),
    ("jclparser/", [_PIPELINE, ".okf/development/workflow.md"]),
    ("tests/", [".okf/development/workflow.md"]),
]


def _get_okf_files(rel_path: str) -> list[str]:
    """Pages that cover *rel_path* (empty when it is not OKF-covered)."""
    for prefix, okf_files in OKF_MAP:
        if rel_path.startswith(prefix) or rel_path == prefix.rstrip("/"):
            return [*okf_files, OKF_LOG]
    return []


def _git(args, cwd):
    r = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return r.stdout.strip()


def _is_okf_modified(okf_file: str, repo_root: Path) -> bool:
    return bool(_git(["status", "--porcelain", okf_file], repo_root))


def _is_okf_path(rel_path: str) -> bool:
    return rel_path.startswith(".okf/")


def _git_mode(repo_root: Path) -> int:
    staged_raw = _git(["diff", "--cached", "--name-only"], repo_root)
    staged = {f.strip() for f in staged_raw.splitlines() if f.strip()}

    needs_update: dict[str, set[str]] = {}
    for src in staged:
        if _is_okf_path(src):
            continue
        okf_files = _get_okf_files(src)
        if okf_files and not any(f in staged for f in okf_files):
            needs_update.setdefault(okf_files[0], set()).add(src)

    if not needs_update:
        return 0

    print("OKF staleness warning -- update the .okf/ bundle before committing:")
    for okf_file in sorted(needs_update):
        triggers = ", ".join(sorted(needs_update[okf_file]))
        print(f"  {okf_file} (or {OKF_LOG})  (changed by: {triggers})")
    print()
    print("To bypass: git commit --no-verify")
    return 1


def _claude_mode(repo_root: Path) -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    file_path = (data.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0

    try:
        rel = Path(file_path).relative_to(repo_root).as_posix()
    except ValueError:
        rel = file_path.replace("\\", "/")
        for marker in ("jclparser/", "tests/", ".okf/"):
            idx = rel.find(marker)
            if idx != -1:
                rel = rel[idx:]
                break

    if _is_okf_path(rel):
        return 0

    okf_files = _get_okf_files(rel)
    if okf_files and not any(_is_okf_modified(f, repo_root) for f in okf_files):
        print(f"[OKF] {rel} -- consider updating {okf_files[0]} or {OKF_LOG}")

    return 0


def main():
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return 0
    repo_root = Path(result.stdout.strip())

    if "--mode=git" in sys.argv:
        return _git_mode(repo_root)
    return _claude_mode(repo_root)


if __name__ == "__main__":
    sys.exit(main())
