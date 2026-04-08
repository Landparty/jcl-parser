"""Tests for the jclparser CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jclparser.cli import main

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SORT_JCL = str(FIXTURES / "real_world" / "sort_job.jcl")
COMPLEX_JCL = str(FIXTURES / "real_world" / "complex_proc.jcl")


@pytest.mark.unit
class TestCLISummary:
    """Test default summary output."""

    def test_summary_prints_job_name(self, capsys):
        rc = main([SORT_JCL])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SORTJOB" in out

    def test_summary_lists_steps(self, capsys):
        rc = main([SORT_JCL])
        assert rc == 0
        out = capsys.readouterr().out
        assert "STEP1" in out
        assert "STEP2" in out

    def test_summary_shows_step_count(self, capsys):
        rc = main([SORT_JCL])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Steps:  2" in out

    def test_summary_shows_procs(self, capsys):
        rc = main([COMPLEX_JCL])
        assert rc == 0
        out = capsys.readouterr().out
        assert "MYPROC" in out


@pytest.mark.unit
class TestCLISteps:
    """Test 'steps' query."""

    def test_steps_lists_all(self, capsys):
        rc = main([SORT_JCL, "steps"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "STEP1" in out
        assert "PGM=SORT" in out
        assert "PGM=ICEMAN" in out


@pytest.mark.unit
class TestCLIStepDetail:
    """Test querying a specific step."""

    def test_step_detail(self, capsys):
        rc = main([SORT_JCL, "STEP1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PGM=SORT" in out
        assert "SORTIN" in out
        assert "SYSIN" in out

    def test_step_case_insensitive(self, capsys):
        rc = main([SORT_JCL, "step1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "STEP1" in out


@pytest.mark.unit
class TestCLIStepDD:
    """Test STEP.DDNAME queries."""

    def test_step_dd(self, capsys):
        rc = main([SORT_JCL, "STEP1.SYSIN"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SYSIN" in out
        assert "inline data" in out
        assert "SORT FIELDS" in out

    def test_step_dd_case_insensitive(self, capsys):
        rc = main([SORT_JCL, "step1.sysin"])
        assert rc == 0
        assert capsys.readouterr().out.strip()

    def test_step_dd_not_found(self, capsys):
        rc = main([SORT_JCL, "STEP1.NOPE"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err

    def test_step_not_found_for_dd(self, capsys):
        rc = main([SORT_JCL, "NOPE.SYSIN"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err.lower()


@pytest.mark.unit
class TestCLIDDAcrossSteps:
    """Test DD name query across all steps."""

    def test_dd_across_steps(self, capsys):
        rc = main([SORT_JCL, "SYSIN"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[STEP1]" in out
        assert "[STEP2]" in out

    def test_dd_not_found(self, capsys):
        rc = main([SORT_JCL, "NONEXISTENT"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "NONEXISTENT" in err


@pytest.mark.unit
class TestCLIJSON:
    """Test --json output."""

    def test_json_output_is_valid(self, capsys):
        rc = main([SORT_JCL, "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["name"] == "SORTJOB"
        assert len(data["steps"]) == 2

    def test_json_contains_dd_statements(self, capsys):
        rc = main([SORT_JCL, "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        step1 = data["steps"][0]
        dd_names = [dd["name"] for dd in step1["dd_statements"]]
        assert "SORTIN" in dd_names
        assert "SYSIN" in dd_names

    def test_json_includes_inline_data(self, capsys):
        rc = main([SORT_JCL, "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        sysin = [
            dd for dd in data["steps"][0]["dd_statements"] if dd["name"] == "SYSIN"
        ][0]
        assert "SORT FIELDS" in sysin["inline_data"]


@pytest.mark.unit
class TestCLIValidate:
    """Test --validate flag."""

    def test_validate_ok(self, capsys):
        rc = main([SORT_JCL, "--validate"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "OK" in out


@pytest.mark.unit
class TestCLIErrors:
    """Test error handling."""

    def test_file_not_found(self, capsys):
        rc = main(["nonexistent.jcl"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err

    def test_invalid_jcl(self, capsys, tmp_path):
        bad = tmp_path / "bad.jcl"
        bad.write_text("this is not JCL at all")
        rc = main([str(bad)])
        # Should either parse (empty job) or error gracefully
        assert rc in (0, 1)


@pytest.mark.unit
class TestCLIVersion:
    """Test --version flag."""

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "1.0.0" in out
