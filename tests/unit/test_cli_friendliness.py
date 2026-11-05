"""First-run friendliness of the jcl-parser CLI: help, typos, --format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jclparser.cli import _QUERY_WORDS, main

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ADVANCED_DD_JCL = str(FIXTURES / "sample_jcl" / "advanced_dd_statements.jcl")


@pytest.mark.unit
class TestHelp:
    def test_bare_invocation_prints_queries_and_exits_2(self, capsys):
        assert main([]) == 2
        out = capsys.readouterr().out
        assert "usage: jcl-parser FILE [QUERY ...] [options]" in out
        assert "queries (the words after FILE):" in out
        assert "exit codes:" in out

    def test_help_documents_every_query_word(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        for word in _QUERY_WORDS:
            assert word in out


@pytest.mark.unit
class TestTypoHints:
    def test_misspelt_query_word(self, capsys):
        assert main([ADVANCED_DD_JCL, "stpes"]) == 1
        err = capsys.readouterr().err
        assert "No step or DD named 'STPES' found." in err
        assert "Did you mean the query 'steps'?" in err

    def test_misspelt_step_name(self, capsys):
        assert main([ADVANCED_DD_JCL, "STP1"]) == 1
        assert "Did you mean: STEP1?" in capsys.readouterr().err

    def test_unrelated_name_gets_no_hint(self, capsys):
        assert main([ADVANCED_DD_JCL, "QQQQQQQQ"]) == 1
        assert "Did you mean" not in capsys.readouterr().err


@pytest.mark.unit
class TestFormatFlag:
    def test_format_json_is_json(self, capsys):
        assert main([ADVANCED_DD_JCL, "--format", "json"]) == 0
        assert json.loads(capsys.readouterr().out)["name"] == "DDTEST"

    def test_format_sarif_on_lint(self, capsys):
        main([ADVANCED_DD_JCL, "lint", "--format", "sarif"])
        assert json.loads(capsys.readouterr().out)["version"] == "2.1.0"

    def test_old_flags_still_work(self, capsys):
        assert main([ADVANCED_DD_JCL, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["name"] == "DDTEST"
