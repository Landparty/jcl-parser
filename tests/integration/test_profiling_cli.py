"""Integration tests: jcl-parser CLI --profile flags."""
import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

_HELLO = """\
//HELLO    JOB (ACCT),'Test',CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD   SYSOUT=*
"""


@pytest.fixture
def jcl_file(tmp_path):
    p = tmp_path / "hello.jcl"
    p.write_text(_HELLO, encoding="utf-8")
    return str(p)


def _run_cli(argv: list[str]) -> tuple[int, str]:
    """Run jcl-parser CLI and capture stdout. Returns (exit_code, stdout)."""
    from jclparser.cli import main
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


def test_json_no_profile_no_profiling_key(jcl_file):
    rc, out = _run_cli([jcl_file, "--json"])
    assert rc == 0
    data = json.loads(out)
    assert "profiling" not in data


def test_json_with_profile_has_profiling_key(jcl_file):
    rc, out = _run_cli([jcl_file, "--json", "--profile"])
    assert rc == 0
    data = json.loads(out)
    assert "profiling" in data
    assert data["profiling"]["wall_clock_s"] > 0.0
    assert data["profiling"]["peak_memory_mb"] >= 0.0


def test_json_profile_top_n_respected(jcl_file):
    rc, out = _run_cli([jcl_file, "--json", "--profile", "--profile-top-n", "3"])
    assert rc == 0
    data = json.loads(out)
    assert 0 < len(data["profiling"]["top_functions"]) <= 3


def test_json_profile_writes_prof_file(jcl_file, tmp_path):
    prof_path = str(tmp_path / "out.prof")
    rc, _ = _run_cli([jcl_file, "--json", "--profile", "--profile-output", prof_path])
    assert rc == 0
    assert Path(prof_path).exists()


def test_profile_without_json_does_not_error(jcl_file):
    """--profile without --json should still parse without crashing."""
    rc, _ = _run_cli([jcl_file, "--profile"])
    assert rc == 0
