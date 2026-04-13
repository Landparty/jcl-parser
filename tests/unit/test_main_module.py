"""
Tests for jclparser/__main__.py.

Verifies that ``python -m jclparser`` works and produces sensible output.

Two layers of testing:
1. In-process via ``runpy.run_module`` so that lines in ``__main__.py``
   are traced by coverage (subprocess calls are invisible to coverage).
2. Subprocess tests for behavioural verification (exit codes, output text).
"""

import runpy
import subprocess
import sys

import pytest


class TestMainModuleInProcess:
    """In-process execution of __main__.py so coverage counts the lines."""

    def test_help_flag_raises_system_exit_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jclparser", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("jclparser.__main__", run_name="__main__", alter_sys=True)
        assert exc_info.value.code == 0

    def test_version_flag_raises_system_exit(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jclparser", "--version"])
        with pytest.raises(SystemExit):
            runpy.run_module("jclparser.__main__", run_name="__main__", alter_sys=True)


class TestMainModuleSubprocess:
    """Subprocess-level behavioural tests (verifies real CLI output)."""

    def test_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "-m", "jclparser", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "usage" in result.stdout.lower() or "jclparser" in result.stdout.lower()

    def test_no_args_exits_without_crash(self):
        result = subprocess.run(
            [sys.executable, "-m", "jclparser"],
            capture_output=True,
            text=True,
        )
        assert isinstance(result.returncode, int)
        assert "Traceback" not in result.stderr
