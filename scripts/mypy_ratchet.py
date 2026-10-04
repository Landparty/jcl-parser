#!/usr/bin/env python
"""Fail only on mypy errors that are not in the committed baseline.

``mypy jclparser/`` (strict) still reports known errors (CLAUDE.md invariant
5; audit 2026-09-27 H4), so a plain ``mypy jclparser/`` gate would always be
red. This ratchet runs mypy with the
``[tool.mypy]`` config from ``pyproject.toml``, normalises every error line by
dropping its line/column numbers (so unrelated edits that shift code do not
count as new errors), and compares the result with ``mypy-baseline.txt``:

* an error line that is not in the baseline (or appears more often than the
  baseline records for that file) fails the run;
* errors that disappeared are reported so the baseline can be tightened with
  ``--update``, but they never fail the run.

Usage::

    python scripts/mypy_ratchet.py            # check (CI)
    python scripts/mypy_ratchet.py --update   # rewrite the baseline after fixing errors

Exit codes: 0 no new errors, 1 new errors, 2 mypy could not run.

The baseline must be produced with the mypy version pinned in the CI
``typecheck`` job (``.github/workflows/ci.yml``).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "mypy-baseline.txt"

# path:line[:col]: error: message  [code]
_ERROR_RE = re.compile(r"^(?P<path>[^:\n]+):\d+(?::\d+)?: error: (?P<rest>.*)$")


def normalize(output: str) -> list[str]:
    """Return mypy's error lines without line/column numbers, sorted.

    Args:
        output: Raw mypy stdout.

    Returns:
        One ``path: error: message [code]`` entry per error (duplicates kept).
    """
    errors = []
    for line in output.splitlines():
        match = _ERROR_RE.match(line.strip())
        if match:
            path = match.group("path").replace("\\", "/")
            errors.append(f"{path}: error: {match.group('rest').strip()}")
    return sorted(errors)


def run_mypy(targets: list[str]) -> list[str]:
    """Run mypy on ``targets`` from the repo root and return normalised errors.

    Raises:
        RuntimeError: When mypy crashed or reported a usage/config error.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", *targets, "--no-error-summary", "--no-pretty"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # 0 = clean, 1 = type errors found; anything else is a crash or bad config.
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "mypy failed")
    return normalize(proc.stdout)


def read_baseline(path: Path) -> list[str]:
    """Read the baseline file (missing file = empty baseline)."""
    if not path.exists():
        return []
    return [
        line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def compare(current: list[str], baseline: list[str]) -> tuple[list[str], list[str]]:
    """Return (new, fixed) error lines, counting duplicates.

    Args:
        current: Normalised errors from this run.
        baseline: Normalised errors recorded in the baseline.

    Returns:
        ``new`` holds lines seen more often than in the baseline, ``fixed``
        lines seen less often.
    """
    cur, base = Counter(current), Counter(baseline)
    new = sorted((cur - base).elements())
    fixed = sorted((base - cur).elements())
    return new, fixed


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    parser.add_argument("--baseline", type=Path, default=BASELINE, help="baseline file")
    parser.add_argument(
        "targets", nargs="*", default=["jclparser"], help="paths to check"
    )
    args = parser.parse_args(argv)

    try:
        current = run_mypy(args.targets)
    except RuntimeError as exc:
        print(f"error: mypy did not run: {exc}", file=sys.stderr)
        return 2

    if args.update:
        args.baseline.write_text(
            "".join(f"{line}\n" for line in current), encoding="utf-8"
        )
        print(f"Baseline written: {len(current)} errors -> {args.baseline.name}")
        return 0

    new, fixed = compare(current, read_baseline(args.baseline))
    if fixed:
        print(
            f"{len(fixed)} baseline error(s) no longer reported. Tighten the ratchet with "
            "`python scripts/mypy_ratchet.py --update` and commit mypy-baseline.txt."
        )
    if new:
        print(f"{len(new)} new mypy error(s) not in {args.baseline.name}:")
        for line in new:
            print(f"  {line}")
        print(
            "\nFix them (run `mypy jclparser/` for line numbers). If an error is only a moved or "
            "reworded existing one, regenerate the baseline with --update."
        )
        return 1

    print(
        f"mypy ratchet OK: {len(current)} errors, none new (baseline {args.baseline.name})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
