"""Tests for the jclparser CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jclparser.cli import main, _print_step_detail, _print_dd_detail
from jclparser.model import Step, DDStatement

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SORT_JCL = str(FIXTURES / "real_world" / "sort_job.jcl")
COMPLEX_JCL = str(FIXTURES / "real_world" / "complex_proc.jcl")
ADVANCED_DD_JCL = str(FIXTURES / "sample_jcl" / "advanced_dd_statements.jcl")
CONDITIONAL_JCL = str(FIXTURES / "sample_jcl" / "conditional_if.jcl")
COND_CODES_JCL = str(FIXTURES / "real_world" / "cond_codes.jcl")


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


@pytest.mark.unit
class TestCLIExplode:
    """Test --explode flag."""

    def test_explode_expands_procs(self, capsys):
        rc = main([COMPLEX_JCL, "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        # After explosion, PROC steps are expanded into real PGM steps
        assert "PGM=" in out

    def test_explode_with_json(self, capsys):
        rc = main([COMPLEX_JCL, "--explode", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["name"] == "COMPLEX"

    def test_explode_error(self, capsys, tmp_path):
        """A job referencing an undefined external proc should error on explode."""
        jcl = tmp_path / "bad_proc.jcl"
        jcl.write_text("//BADJOB  JOB (ACCT),'TEST'\n//STEP1   EXEC NOPROC\n")
        rc = main([str(jcl), "--explode", "--proc-path", str(tmp_path)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "error" in err.lower()


@pytest.mark.unit
class TestCLIValidateErrors:
    """Test --validate when errors are present."""

    def test_validate_reports_syntax_errors(self, capsys, tmp_path):
        """Malformed JCL triggers error reporting loop (lines 133-139)."""
        jcl = tmp_path / "bad.jcl"
        jcl.write_text("//BAD JOB\nGARBAGE LINE\n//MISSING\n")
        rc = main([str(jcl), "--validate"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "[" in out  # severity tag like [ERROR]
        assert "GARBAGE" in out or "Invalid" in out


@pytest.mark.unit
class TestCLIEmptySteps:
    """Test output for a job with no execution steps."""

    def test_no_steps_message(self, capsys, tmp_path):
        jcl = tmp_path / "empty.jcl"
        jcl.write_text("//EMPTYJOB JOB (ACCT),'EMPTY'\n")
        rc = main([str(jcl)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "(no steps)" in out


@pytest.mark.unit
class TestCLIStepWithProcedure:
    """Test step detail for a procedure-calling step."""

    def test_proc_step_shows_proc_name(self, capsys):
        rc = main([COMPLEX_JCL, "RUN1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PROC=MYPROC" in out

    def test_proc_step_no_dds(self, capsys):
        """PROC-calling steps without DD overrides show (no DD statements)."""
        rc = main([COMPLEX_JCL, "RUN2"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "(no DD statements)" in out


@pytest.mark.unit
class TestCLIStepParameters:
    """Test step detail with EXEC parameters."""

    def test_step_shows_cond_parameter(self, capsys):
        rc = main([COND_CODES_JCL, "STEP2"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "COND=" in out


@pytest.mark.unit
class TestCLIDDDetail:
    """Test detailed DD display paths (DSN, DISP, SYSOUT, DCB, SPACE, extra params)."""

    def test_dd_detail_shows_dsn_and_disp(self, capsys):
        rc = main([SORT_JCL, "STEP1.SORTIN"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "DSN=INPUT.DATA" in out
        assert "DISP=" in out

    def test_dd_detail_shows_sysout(self, capsys):
        rc = main([SORT_JCL, "STEP1.SYSSOUT"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SYSOUT=*" in out

    def test_dd_detail_shows_dcb(self, capsys):
        rc = main([ADVANCED_DD_JCL, "STEP1.DD1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "RECFM=" in out
        assert "LRECL=" in out

    def test_dd_detail_shows_space(self, capsys):
        rc = main([ADVANCED_DD_JCL, "STEP1.DD1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SPACE=" in out

    def test_dd_detail_shows_extra_params(self, capsys):
        rc = main([ADVANCED_DD_JCL, "STEP1.DD6"])
        assert rc == 0
        out = capsys.readouterr().out
        # DD6 has DEST, OUTLIM, HOLD, FREE params beyond the standard ones
        assert "DEST=" in out or "HOLD=" in out or "OUTLIM=" in out


@pytest.mark.unit
class TestCLIJSONConditional:
    """Test JSON output with IF/THEN/ELSE conditional blocks."""

    def test_json_includes_conditionals(self, capsys):
        rc = main([CONDITIONAL_JCL, "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        # The conditional JCL has IF/THEN/ELSE blocks which become conditionals
        types = [s["type"] for s in data["steps"]]
        assert "conditional" in types

    def test_json_conditional_has_then_else(self, capsys):
        rc = main([CONDITIONAL_JCL, "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        conds = [s for s in data["steps"] if s["type"] == "conditional"]
        assert len(conds) > 0
        cond = conds[0]
        assert "condition" in cond
        assert "then_steps" in cond
        assert "else_steps" in cond


@pytest.mark.unit
class TestCLIStepComments:
    """Test step detail displays comments."""

    def test_step_with_comments(self, capsys):
        step = Step(
            name="MYSTEP",
            program="IEFBR14",
            comments=["This step does nothing", "Just a placeholder"],
            line_number=5,
        )
        _print_step_detail(step)
        out = capsys.readouterr().out
        assert "* This step does nothing" in out
        assert "* Just a placeholder" in out


@pytest.mark.unit
class TestCLISummaryMinimal:
    """Test summary for a job without accounting info or parameters."""

    def test_summary_no_accounting(self, capsys, tmp_path):
        jcl = tmp_path / "noacct.jcl"
        jcl.write_text("//MYJOB   JOB\n//S1 EXEC PGM=IEFBR14\n")
        rc = main([str(jcl)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "MYJOB" in out
        # Should NOT show Acct: line
        assert "Acct:" not in out


@pytest.mark.unit
class TestCLIProcPath:
    """Test --proc-path flag."""

    def test_proc_path_passed(self, capsys):
        proclibs = str(FIXTURES / "proclibs")
        rc = main([SORT_JCL, "--proc-path", proclibs])
        assert rc == 0


@pytest.mark.unit
class TestCLIDDPartialParams:
    """Test DD detail with partial DCB/SPACE (cover False branches)."""

    def test_dcb_only_dsorg_no_recfm_lrecl_blksize(self, capsys):
        """DCB with no RECFM, LRECL, or BLKSIZE prints nothing for those fields."""
        dd = DDStatement(name="DD1", parameters={"DCB": "DSORG=PS"}, line_number=1)
        _print_dd_detail(dd)
        out = capsys.readouterr().out
        assert "RECFM=" not in out
        assert "LRECL=" not in out
        assert "BLKSIZE=" not in out
        # DCB section should not appear since no displayable sub-fields
        assert "DCB=" not in out

    def test_dcb_recfm_only(self, capsys):
        """DCB with only RECFM — LRECL and BLKSIZE branches are False."""
        dd = DDStatement(name="DD1", parameters={"DCB": "RECFM=FB"}, line_number=1)
        _print_dd_detail(dd)
        out = capsys.readouterr().out
        assert "RECFM=FB" in out
        assert "LRECL=" not in out
        assert "BLKSIZE=" not in out

    def test_space_unit_only_no_primary_secondary(self, capsys):
        """SPACE with only unit — primary/secondary branches are False."""
        dd = DDStatement(name="DD1", parameters={"SPACE": "CYL"}, line_number=1)
        _print_dd_detail(dd)
        out = capsys.readouterr().out
        # Space should show the unit
        assert "SPACE=" in out
        assert "CYL" in out

    def test_space_unit_and_primary_no_secondary(self, capsys):
        """SPACE with unit+primary but no secondary."""
        dd = DDStatement(name="DD1", parameters={"SPACE": "TRK,10"}, line_number=1)
        _print_dd_detail(dd)
        out = capsys.readouterr().out
        assert "TRK" in out
        assert "10" in out

    def test_space_empty_no_output(self, capsys):
        """Empty SPACE value — all sub-fields None, no SPACE line printed."""
        dd = DDStatement(name="DD1", parameters={"SPACE": ""}, line_number=1)
        _print_dd_detail(dd)
        out = capsys.readouterr().out
        assert "SPACE=" not in out


@pytest.mark.unit
class TestCLIJSONWithQuery:
    """Test --json combined with query arguments."""

    def test_json_summary(self, capsys):
        """--json without a query outputs the full job."""
        rc = main([SORT_JCL, "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["name"] == "SORTJOB"

    def test_json_steps(self, capsys):
        """--json steps outputs a JSON list of steps."""
        rc = main([SORT_JCL, "steps", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "STEP1"

    def test_json_step_detail(self, capsys):
        """--json STEP outputs JSON for that single step."""
        rc = main([SORT_JCL, "STEP1", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["name"] == "STEP1"
        assert data["program"] == "SORT"
        assert data["type"] == "step"

    def test_json_step_dd(self, capsys):
        """--json STEP.DD outputs JSON for that single DD."""
        rc = main([SORT_JCL, "STEP1.SORTIN", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["name"] == "SORTIN"
        assert data["dataset_name"] == "INPUT.DATA"

    def test_json_dd_across_steps(self, capsys):
        """--json DDNAME outputs JSON list of matching DDs with step labels."""
        rc = main([SORT_JCL, "SYSIN", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["step"] == "STEP1"
        assert data[1]["step"] == "STEP2"


@pytest.mark.unit
class TestCLIValidateJSON:
    """Test --validate --json outputs structured JSON errors."""

    def test_validate_json_ok(self, capsys):
        rc = main([SORT_JCL, "--validate", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_json_with_errors(self, capsys, tmp_path):
        jcl = tmp_path / "bad.jcl"
        jcl.write_text("//BAD JOB\nGARBAGE LINE\n//MISSING\n")
        rc = main([str(jcl), "--validate", "--json"])
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["valid"] is False
        assert len(data["errors"]) > 0
        assert "message" in data["errors"][0]
        assert "severity" in data["errors"][0]


@pytest.mark.unit
class TestCLIProcs:
    """Test 'procs' query — inline PROC definitions and explosion audit."""

    def test_procs_lists_inline_proc(self, capsys):
        rc = main([COMPLEX_JCL, "procs"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "MYPROC" in out

    def test_procs_shows_inline_tag(self, capsys):
        rc = main([COMPLEX_JCL, "procs"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[inline]" in out

    def test_procs_shows_proc_parameters(self, capsys):
        rc = main([COMPLEX_JCL, "procs"])
        assert rc == 0
        out = capsys.readouterr().out
        # MYPROC defines DSN, UNIT, SPACE, VOL parameters
        assert "DSN=" in out or "UNIT=" in out

    def test_procs_shows_step_count(self, capsys):
        rc = main([COMPLEX_JCL, "procs"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Steps:" in out

    def test_procs_no_inline_procs(self, capsys):
        rc = main([SORT_JCL, "procs"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "(no inline procedures)" in out

    def test_procs_proc_path_hint(self, capsys):
        """When --proc-path is given without --explode, a hint is shown."""
        proclibs = str(FIXTURES / "proclibs")
        rc = main([SORT_JCL, "procs", "--proc-path", proclibs])
        assert rc == 0
        out = capsys.readouterr().out
        assert "external" in out.lower()
        assert "--explode" in out

    def test_procs_json(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["name"] == "MYPROC"
        assert "parameters" in data[0]
        assert "steps" in data[0]

    def test_procs_json_no_inline_procs(self, capsys):
        rc = main([SORT_JCL, "procs", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_procs_explode_shows_audit(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        # Should show expansion records for RUN1 and RUN2 calling MYPROC
        assert "MYPROC" in out
        assert "Expansion:" in out

    def test_procs_explode_shows_inline_tag(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[inline]" in out

    def test_procs_explode_shows_depth(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "depth" in out

    def test_procs_explode_shows_expanded_steps(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Expanded steps:" in out

    def test_procs_explode_json(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--explode", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) > 0
        record = data[0]
        assert "step_name" in record
        assert "proc_name" in record
        assert "parameters" in record
        assert "depth" in record
        assert "expanded_steps" in record
        assert "source" in record

    def test_procs_explode_json_inline_source(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--explode", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        proc_names = [r["proc_name"] for r in data]
        assert "MYPROC" in proc_names
        sources = {r["proc_name"]: r["source"] for r in data}
        assert sources["MYPROC"] == "inline"

    def test_procs_explode_no_procs_empty_audit(self, capsys):
        """A job with no PROC calls has no audit records after explosion."""
        rc = main([SORT_JCL, "procs", "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "(no procedure expansions recorded)" in out

    def test_procs_explode_external_proc_tag(self, capsys, tmp_path):
        """External PROCs loaded via --proc-path are tagged [external] in audit."""
        proclibs = str(FIXTURES / "proclibs")
        jcl = tmp_path / "ext.jcl"
        jcl.write_text(
            "//EXTJOB  JOB (ACCT),'EXT TEST'\n"
            "//         JCLLIB ORDER=(SYS1.PROCLIB)\n"
            "//STEP1   EXEC SORTPROC\n"
        )
        rc = main([str(jcl), "procs", "--explode", "--proc-path", proclibs])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[external]" in out
        assert "SORTPROC" in out

    def test_procs_explode_external_proc_json_source(self, capsys, tmp_path):
        """External PROCs have source='external' in JSON audit output."""
        proclibs = str(FIXTURES / "proclibs")
        jcl = tmp_path / "ext.jcl"
        jcl.write_text(
            "//EXTJOB  JOB (ACCT),'EXT TEST'\n"
            "//         JCLLIB ORDER=(SYS1.PROCLIB)\n"
            "//STEP1   EXEC SORTPROC\n"
        )
        rc = main([str(jcl), "procs", "--explode", "--proc-path", proclibs, "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert any(r["source"] == "external" for r in data)

    # ------------------------------------------------------------------
    # DD names visible in PROC text output (improvement 3)
    # ------------------------------------------------------------------

    def test_procs_text_shows_dd_names(self, capsys):
        """Text output of procs shows individual DD names, not just a count."""
        rc = main([COMPLEX_JCL, "procs"])
        assert rc == 0
        out = capsys.readouterr().out
        # MYPROC STEP1 has DD1 with DSN=&DSN
        assert "DD1" in out

    # ------------------------------------------------------------------
    # Single PROC detail query (improvement 4)
    # ------------------------------------------------------------------

    def test_procs_single_by_name(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "MYPROC"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "MYPROC" in out
        assert "[inline]" in out

    def test_procs_single_case_insensitive(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "myproc"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "MYPROC" in out

    def test_procs_single_shows_parameters(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "MYPROC"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "DSN=" in out or "UNIT=" in out

    def test_procs_single_shows_steps(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "MYPROC"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Steps:" in out
        assert "STEP1" in out

    def test_procs_single_shows_dd_names(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "MYPROC"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "DD1" in out

    def test_procs_single_not_found(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "NOPROC"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err.lower()

    def test_procs_single_json(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "MYPROC", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["name"] == "MYPROC"
        assert data["source"] == "inline"
        assert "parameters" in data
        assert "steps" in data

    def test_procs_single_json_has_line_number(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "MYPROC", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "line_number" in data
        assert data["line_number"] > 0

    # ------------------------------------------------------------------
    # explosion_map resolved parameters in audit (improvement 2)
    # ------------------------------------------------------------------

    def test_procs_explode_shows_resolved(self, capsys):
        """Audit shows Resolved: line with merged param values."""
        rc = main([COMPLEX_JCL, "procs", "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Resolved:" in out

    def test_procs_explode_resolved_shows_defaults(self, capsys):
        """Resolved params include PROC defaults not overridden by EXEC."""
        # RUN1 calls MYPROC with no overrides → resolved should show all defaults
        rc = main([COMPLEX_JCL, "procs", "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        # MYPROC has DSN='DEFAULT.DATA' as default; RUN1 has no overrides so
        # resolved value must contain the default
        assert "DEFAULT.DATA" in out

    def test_procs_explode_json_has_resolved_parameters(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--explode", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert any("resolved_parameters" in r for r in data)

    def test_procs_explode_json_has_source_line_numbers(self, capsys):
        rc = main([COMPLEX_JCL, "procs", "--explode", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert any("source_line_numbers" in r for r in data)

    def test_procs_explode_shows_overrides_separately(self, capsys):
        """RUN2 uses overrides; audit shows both Overrides: and Resolved: lines."""
        rc = main([COMPLEX_JCL, "procs", "--explode"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Overrides:" in out

    # ------------------------------------------------------------------
    # Step explosion metadata in JSON (improvement 1)
    # ------------------------------------------------------------------

    def test_json_exploded_step_has_is_exploded(self, capsys):
        rc = main([COMPLEX_JCL, "--explode", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        steps = [s for s in data["steps"] if s.get("type") == "step"]
        assert any(s.get("is_exploded") is True for s in steps)

    def test_json_exploded_step_has_original_proc_call(self, capsys):
        rc = main([COMPLEX_JCL, "--explode", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        steps = [s for s in data["steps"] if s.get("type") == "step"]
        exploded = [s for s in steps if s.get("is_exploded")]
        assert all("original_proc_call" in s for s in exploded)

    def test_json_non_exploded_step_is_exploded_false(self, capsys):
        """Non-exploded steps have is_exploded=False in JSON."""
        rc = main([SORT_JCL, "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        steps = [s for s in data["steps"] if s.get("type") == "step"]
        assert all(s.get("is_exploded") is False for s in steps)

    # ------------------------------------------------------------------
    # --list-available flag (improvement 5)
    # ------------------------------------------------------------------

    def test_list_available_shows_proc_names(self, capsys):
        proclibs = str(FIXTURES / "proclibs")
        rc = main([SORT_JCL, "procs", "--proc-path", proclibs, "--list-available"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SORTPROC" in out

    def test_list_available_organises_by_library(self, capsys):
        proclibs = str(FIXTURES / "proclibs")
        rc = main([SORT_JCL, "procs", "--proc-path", proclibs, "--list-available"])
        assert rc == 0
        out = capsys.readouterr().out
        # fixture has SYS1.PROCLIB and USER.PROCLIB
        assert "SYS1.PROCLIB" in out or "USER.PROCLIB" in out

    def test_list_available_marks_referenced_procs(self, capsys, tmp_path):
        """PROCs referenced by the job are marked with * in the listing."""
        proclibs = str(FIXTURES / "proclibs")
        jcl = tmp_path / "ref.jcl"
        jcl.write_text(
            "//REFJOB  JOB (ACCT),'REF'\n"
            "//         JCLLIB ORDER=(SYS1.PROCLIB)\n"
            "//STEP1   EXEC SORTPROC\n"
        )
        rc = main([str(jcl), "procs", "--proc-path", proclibs, "--list-available"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SORTPROC *" in out

    def test_list_available_json(self, capsys):
        proclibs = str(FIXTURES / "proclibs")
        rc = main([SORT_JCL, "procs", "--proc-path", proclibs, "--list-available", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, dict)
        # keys are library names, values are lists of PROC names
        all_procs = [p for procs in data.values() for p in procs]
        assert "SORTPROC" in all_procs

    def test_list_available_no_proc_path(self, capsys):
        rc = main([SORT_JCL, "procs", "--list-available"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "--proc-path" in err
