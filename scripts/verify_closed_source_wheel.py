#!/usr/bin/env python3
"""Build a closed-source wheel and verify no .py source leaks into it.

Usage: python scripts/verify_closed_source_wheel.py

Mirrors the cobol-parser sibling repo's
scripts/verify_closed_source_wheel.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

from _closed_source_checks import assert_no_leaked_source

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_wheel(dist_dir: Path) -> Path:
    env = dict(os.environ)
    env["JCLPARSER_CLOSED_SOURCE"] = "1"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )
    # The PyPI distribution name is "jcl-parser" ([project].name in
    # pyproject.toml), which wheel filenames normalize to "jcl_parser-*" --
    # not the "jclparser" import package name. dist_dir is a fresh tempdir
    # from this one build, so a bare "*.whl" glob is unambiguous and doesn't
    # need to track that normalization if the project name ever changes again.
    wheels = list(dist_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one wheel, found {wheels}")
    return wheels[0]


def check_no_leaked_source(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        names = [n for n in zf.namelist() if n.startswith("jclparser/")]

    py_count, ext_count = assert_no_leaked_source(names)
    print(
        f"OK: {py_count} allowed .py shim(s), {ext_count} compiled "
        "extension(s), no .c/.pyx/.h/.pyi source"
    )


def smoke_test_install(wheel_path: Path, venv_dir: Path) -> None:
    venv.create(venv_dir, with_pip=True)
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    exe = "python.exe" if sys.platform == "win32" else "python"
    python = venv_dir / bin_dir / exe
    subprocess.run([str(python), "-m", "pip", "install", str(wheel_path)], check=True)
    check = (
        "import jclparser.parser, jclparser.model\n"
        "assert not jclparser.parser.__file__.endswith('.py'), jclparser.parser.__file__\n"
        "assert not jclparser.model.__file__.endswith('.py'), jclparser.model.__file__\n"
        "from jclparser import parse_jcl\n"
        "job = parse_jcl('//MYJOB JOB (ACCT),CLASS=A\\n//STEP1 EXEC PGM=IEFBR14\\n')\n"
        "assert job.name == 'MYJOB', job.name\n"
        "print('smoke test OK')\n"
    )
    # cwd matters here: `python -c` prepends the current directory to
    # sys.path, and REPO_ROOT contains a "jclparser/" source tree that
    # would otherwise shadow the just-installed wheel in the venv's
    # site-packages, making this check pass even for a broken wheel. Run
    # from venv_dir (which has no such subpackage) so the import is
    # resolved from site-packages only.
    subprocess.run([str(python), "-c", check], cwd=venv_dir, check=True)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        wheel_path = build_wheel(dist_dir)
        check_no_leaked_source(wheel_path)
        smoke_test_install(wheel_path, tmp_path / "venv")
    print("All checks passed.")


if __name__ == "__main__":
    main()
