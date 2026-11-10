"""Regression tests for the severity:medium validation fixes.

* #119 -- step / DD / job validation findings carry their source line.
* #100 -- a standalone PROC wrapped in the contract's synthetic JOB statement
  validates clean.
* #129 -- validate_jcl / CLI --validate honour the PROC base path.
* #118 -- line numbers after an INCLUDE are reported against the main source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jclparser import parse_jcl, validate_jcl
from jclparser._include_origins import IncludeLineMap
from jclparser.errors import ErrorSeverity, JCLSyntaxError
from jclparser.include_loader import (
    DictMemberLoader,
    LineOrigin,
    resolve_includes,
    resolve_includes_with_origins,
)
from jclparser.model import DDStatement, Step, iter_execution_steps
from jclparser.utils import split_source_lines
from jclparser.validators import validate_step_structure

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# #119 -- validation findings report the line of the step / DD they are about
# ---------------------------------------------------------------------------

_ISSUE_119_JCL = (
    "//J1 JOB (A),'X'\n"
    "//S1 EXEC PGM=IEFBR14\n"
    "//OK DD DSN=A.B,DISP=SHR\n"
    "//TOOLONGDDNAME DD DSN=A..B,DISP=(SHR,BOGUS)\n"
    "//S1 EXEC PGM=X\n"
)


class TestIssue119FindingLines:
    def test_validate_jcl_reports_step_and_dd_lines(self) -> None:
        findings = validate_jcl(_ISSUE_119_JCL, level="structure")
        assert [(f.line_number, f.message.split(":")[0]) for f in findings] == [
            (5, "Duplicate step name"),
            (4, "Invalid DD name 'TOOLONGDDNAME'"),
            (4, "Invalid dataset name 'A..B'"),
            (4, "Invalid DISP parameter '['SHR', 'BOGUS']' on DD TOOLONGDDNAME"),
        ]

    def test_job_validate_str_includes_line(self) -> None:
        messages = [str(e) for e in parse_jcl(_ISSUE_119_JCL).validate()]
        assert messages[0] == "Line 5: [WARNING] Duplicate step name: S1"
        assert all(m.startswith(("Line 4:", "Line 5:")) for m in messages)

    def test_step_rules_use_step_line(self) -> None:
        step = Step(name="BAD.NAME!", line_number=7)
        findings = validate_step_structure(step)
        assert findings
        assert {f.line_number for f in findings} == {7}

    def test_both_program_and_procedure_uses_step_line(self) -> None:
        step = Step(name="S1", program="P", procedure="Q", line_number=9)
        [finding] = validate_step_structure(step)
        assert "both program and procedure" in finding.message
        assert finding.line_number == 9

    def test_duplicate_dd_and_dd_source_rules_use_dd_line(self) -> None:
        step = Step(
            name="S1",
            program="P",
            line_number=2,
            dd_statements=[
                DDStatement(name="A", dataset_name="X.Y", line_number=3),
                DDStatement(name="A", dataset_name="X.Z", line_number=4),
                DDStatement(name="B", line_number=5),
                DDStatement(
                    name="C",
                    dataset_name="X.Y",
                    parameters={"SYSOUT": "A"},
                    line_number=6,
                ),
            ],
        )
        by_message = {f.message: f.line_number for f in validate_step_structure(step)}
        assert by_message["Duplicate DD name in step S1: A"] == 4
        assert (
            by_message[
                "DD B must specify a data source (DSN, SYSOUT, DUMMY, or inline data)"
            ]
            == 5
        )
        assert by_message["DD C has conflicting data source specifications"] == 6

    def test_invalid_job_name_uses_job_line(self) -> None:
        job = parse_jcl("//* lead comment\n//TOOLONGJOB JOB (A)\n//S1 EXEC PGM=X\n")
        [finding] = [f for f in job.validate() if "job name" in f.message]
        assert finding.line_number == 2

    def test_temporary_dataset_findings_use_dd_lines(self) -> None:
        jcl = (
            "//J1 JOB (A)\n"
            "//S1 EXEC PGM=A\n"
            "//O1 DD DSN=&&T,DISP=(NEW,PASS)\n"
            "//S2 EXEC PGM=B\n"
            "//O2 DD DSN=&&T,DISP=(NEW,PASS)\n"
            "//I1 DD DSN=&&NEVER,DISP=(OLD,DELETE)\n"
        )
        by_message = {f.message: f for f in parse_jcl(jcl).validate()}
        dup = by_message["Temporary dataset &&T created in multiple steps: S1 and S2"]
        assert dup.line_number == 5
        unused = by_message["Temporary dataset &&NEVER used but never created"]
        assert unused.line_number == 6
        assert unused.severity == ErrorSeverity.WARNING


# ---------------------------------------------------------------------------
# #100 -- the backend's synthetic JOB wrapper around a standalone PROC
# ---------------------------------------------------------------------------

#: The synthetic JOB statement interface-contract.md documents for wrapping a
#: standalone PROC file ("File Extensions Handled").
_WRAPPER = "//LEGACYLN JOB\n"

_STANDALONE_PROC = (
    "//MYPROC  PROC HLQ=PROD\n"
    "//STEP1   EXEC PGM=IEFBR14\n"
    "//DD1     DD DSN=&HLQ..DATA,DISP=SHR\n"
    "//STEP2   EXEC PGM=SORT\n"
    "//SORTIN  DD DSN=&HLQ..IN,DISP=SHR\n"
    "//SORTOUT DD SYSOUT=*\n"
    "//        PEND\n"
)


class TestIssue100WrappedProcMember:
    def test_contract_wrapper_name_is_a_valid_job_name(self) -> None:
        contract = (
            Path(__file__).resolve().parents[2] / "interface-contract.md"
        ).read_text(encoding="utf-8")
        assert f"wrapped in a synthetic `{_WRAPPER.strip()}` statement" in contract
        assert len(_WRAPPER.split()[0].removeprefix("//")) <= 8

    def test_wrapped_proc_validates_clean(self) -> None:
        job = parse_jcl(_WRAPPER + _STANDALONE_PROC)
        assert [p.name for p in job.procedures] == ["MYPROC"]
        assert job.steps == []
        assert job.validate() == []

    def test_wrapped_proc_has_no_validate_jcl_errors(self) -> None:
        source = _WRAPPER + _STANDALONE_PROC
        for level in ("basic", "structure"):
            findings = validate_jcl(source, level=level)
            assert not [f for f in findings if f.severity == ErrorSeverity.ERROR]

    def test_wrapped_proc_parses_strict(self) -> None:
        parse_jcl(_WRAPPER + _STANDALONE_PROC, strict_mode=True)

    def test_job_without_steps_or_procs_still_errors(self) -> None:
        messages = [e.message for e in parse_jcl(_WRAPPER).validate()]
        assert messages == ["Job must contain at least one execution step"]

    def test_old_ten_character_wrapper_name_is_invalid(self) -> None:
        job = parse_jcl("//LEGACYLENS JOB\n" + _STANDALONE_PROC)
        assert [e.message for e in job.validate()] == [
            "Invalid job name 'LEGACYLENS': must be 1-8 characters, alphanumeric + @#$"
        ]


# ---------------------------------------------------------------------------
# #129 -- validate_jcl / CLI --validate honour the PROC base path
# ---------------------------------------------------------------------------

_JCLLIB_JOB = "//J1 JOB (A),'X'\n//JL JCLLIB ORDER=SYS1.PROCLIB\n//S1 EXEC EXTP\n"


@pytest.fixture
def proc_lib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A PROC library with SYS1.PROCLIB(EXTP); JCL_PROCLIB_PATH unset."""
    monkeypatch.delenv("JCL_PROCLIB_PATH", raising=False)
    lib = tmp_path / "lib"
    (lib / "SYS1.PROCLIB").mkdir(parents=True)
    (lib / "SYS1.PROCLIB" / "EXTP.jcl").write_text(
        "//EXTP PROC\n//PS1 EXEC PGM=IEFBR14\n", encoding="utf-8"
    )
    (tmp_path / "d.jcl").write_text(_JCLLIB_JOB, encoding="utf-8")
    return lib


class TestIssue129ValidateProcPath:
    def test_without_base_path_the_proc_is_not_found(self, proc_lib: Path) -> None:
        findings = validate_jcl(_JCLLIB_JOB, level="structure")
        assert [(f.line_number, f.severity) for f in findings] == [
            (3, ErrorSeverity.ERROR)
        ]
        assert "Procedure 'EXTP' not found" in findings[0].message

    def test_proc_base_path_finds_the_proc(self, proc_lib: Path) -> None:
        assert validate_jcl(_JCLLIB_JOB, "structure", proc_base_path=proc_lib) == []
        assert validate_jcl(_JCLLIB_JOB, proc_base_path=str(proc_lib)) == []

    def test_env_var_still_applies(
        self, proc_lib: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JCL_PROCLIB_PATH", str(proc_lib))
        assert validate_jcl(_JCLLIB_JOB, level="structure") == []

    def test_enable_external_procs_false(self, proc_lib: Path) -> None:
        findings = validate_jcl(
            _JCLLIB_JOB, proc_base_path=proc_lib, enable_external_procs=False
        )
        assert len(findings) == 1
        assert "external PROC loading is disabled" in findings[0].message

    def test_parameters_are_keyword_only(self, proc_lib: Path) -> None:
        with pytest.raises(TypeError):
            validate_jcl(_JCLLIB_JOB, "structure", None, proc_lib)  # type: ignore[misc]

    def test_cli_validate_forwards_proc_path(
        self, proc_lib: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from jclparser.cli import main

        job_file = proc_lib.parent / "d.jcl"
        assert main([str(job_file), "--proc-path", str(proc_lib), "--validate"]) == 0
        assert "OK - no errors found." in capsys.readouterr().out

        assert main([str(job_file), "--validate"]) == 1
        assert "line 3 Procedure 'EXTP' not found" in capsys.readouterr().out

    def test_cli_validate_json_forwards_proc_path(
        self, proc_lib: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from jclparser.cli import main

        argv = [str(proc_lib.parent / "d.jcl"), "--validate", "--json"]
        assert main([*argv, "--proc-path", str(proc_lib)]) == 0
        assert '"valid": true' in capsys.readouterr().out

    def test_procs_note_names_procs_not_found(
        self, proc_lib: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from jclparser.cli import main

        job_file = proc_lib.parent / "f.jcl"
        job_file.write_text("//J1 JOB (A)\n//S1 EXEC NOPE\n", encoding="utf-8")
        assert main([str(job_file), "--proc-path", str(proc_lib), "procs"]) == 0
        out = capsys.readouterr().out
        assert f"Note: PROC(s) NOPE not found under '{proc_lib}'" in out
        assert "expanded with --explode" not in out

    def test_procs_note_when_job_calls_no_proc(
        self, proc_lib: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from jclparser.cli import main

        job_file = proc_lib.parent / "e.jcl"
        job_file.write_text("//J1 JOB (A)\n//S1 EXEC PGM=X\n", encoding="utf-8")
        assert main([str(job_file), "--proc-path", str(proc_lib), "procs"]) == 0
        assert f"this job calls no PROC from '{proc_lib}'" in capsys.readouterr().out

    def test_procs_lists_external_proc_without_note(
        self, proc_lib: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from jclparser.cli import main

        job_file = proc_lib.parent / "d.jcl"
        assert main([str(job_file), "--proc-path", str(proc_lib), "procs"]) == 0
        out = capsys.readouterr().out
        assert "PROC: EXTP  [external]" in out
        assert "Note:" not in out


# ---------------------------------------------------------------------------
# #118 -- INCLUDE expansion no longer shifts later line numbers
# ---------------------------------------------------------------------------

_COMMON = "//C1 EXEC PGM=A\n//C2 EXEC PGM=B\n//C3 EXEC PGM=C\n//C4 EXEC PGM=D\n"

_MEMBERS = {
    "COMMON": _COMMON,
    "BAD": "//B1 EXEC PGM=A\n//B2 EXEC\n",
    "OUTER": "//O1 EXEC PGM=A\n//O2 EXEC PGM=B\n// INCLUDE MEMBER=BAD\n",
    "WARN": "//W1 EXEC PGM=A\n//D1 DD DSN=X.Y,DISP=SHR,DISP=OLD\n",
    "EMPTY": "",
    "NOEOL": "//N1 EXEC PGM=A",
}

_ISSUE_118_JCL = (
    "//J1 JOB (A),'X'\n// INCLUDE MEMBER=COMMON\n//S5 EXEC PGM=MYPGM\n//S6 EXEC\n"
)


def _loader() -> DictMemberLoader:
    return DictMemberLoader(_MEMBERS)


class TestIssue118IncludeLineNumbers:
    def test_issue_repro_error_line(self) -> None:
        with pytest.raises(JCLSyntaxError) as info:
            parse_jcl(_ISSUE_118_JCL, include_loader=_loader())
        assert info.value.line_number == 4
        assert str(info.value) == "Line 4: EXEC statement missing program or procedure"

    def test_steps_after_include_keep_their_lines(self) -> None:
        source = _ISSUE_118_JCL.replace("//S6 EXEC\n", "")
        job = parse_jcl(source, include_loader=_loader())
        lines = {s.name: s.line_number for s in iter_execution_steps(job.steps)}
        # Member steps are reported at the INCLUDE statement's line.
        assert lines == {"C1": 2, "C2": 2, "C3": 2, "C4": 2, "S5": 3}

    def test_member_error_names_member_and_member_line(self) -> None:
        source = "//J1 JOB (A)\n//S0 EXEC PGM=X\n// INCLUDE MEMBER=BAD\n"
        with pytest.raises(JCLSyntaxError) as info:
            parse_jcl(source, include_loader=_loader())
        assert info.value.line_number == 3
        assert info.value.include_note == "INCLUDE member BAD, line 2"
        assert str(info.value) == (
            "Line 3 (INCLUDE member BAD, line 2): "
            "EXEC statement missing program or procedure"
        )

    def test_nested_include_uses_outermost_line_and_innermost_member(self) -> None:
        source = (
            "//J1 JOB (A)\n//S0 EXEC PGM=X\n//S1 EXEC PGM=Y\n// INCLUDE MEMBER=OUTER\n"
        )
        with pytest.raises(JCLSyntaxError) as info:
            parse_jcl(source, include_loader=_loader())
        assert str(info.value).startswith("Line 4 (INCLUDE member BAD, line 2): ")

    def test_warnings_are_relabelled(self) -> None:
        source = (
            "//J1 JOB (A)\n"
            "// INCLUDE MEMBER=WARN\n"
            "//S9 EXEC PGM=Y\n"
            "//DD9 DD DSN=A.B,DISP=SHR,DISP=OLD\n"
        )
        job = parse_jcl(source, include_loader=_loader())
        dup = [w for w in job.warnings if "duplicate parameter 'DISP'" in w]
        assert [w.split(":")[0] for w in dup] == [
            "Line 2 (INCLUDE member WARN, line 2)",
            "Line 4",
        ]
        step = job.get_step("S9")
        assert step is not None
        assert step.dd_statements[0].line_number == 4
        member_step = job.get_step("W1")
        assert member_step is not None
        assert member_step.dd_statements[0].line_number == 2

    def test_unresolved_output_refs_are_relabelled(self) -> None:
        loader = DictMemberLoader(
            {"OUT": "//O1 EXEC PGM=A\n//D1 DD SYSOUT=A,OUTPUT=*.NOPE\n"}
        )
        source = "//J1 JOB (A)\n// INCLUDE MEMBER=OUT\n//S2 EXEC PGM=B\n"
        job = parse_jcl(source, include_loader=loader)
        assert [line for _, _, line in job.unresolved_output_refs] == [2]

    def test_validation_findings_use_main_source_lines(self) -> None:
        loader = DictMemberLoader({"DUP": "//S1 EXEC PGM=A\n"})
        source = (
            "//J1 JOB (A)\n//S1 EXEC PGM=X\n// INCLUDE MEMBER=DUP\n//S2 EXEC PGM=Y\n"
        )
        job = parse_jcl(source, include_loader=loader)
        [dup] = [e for e in job.validate() if "Duplicate step" in e.message]
        assert dup.line_number == 3
        step = job.get_step("S2")
        assert step is not None and step.line_number == 4

    def test_validate_jcl_reports_member_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JCL_PROCLIB_PATH", raising=False)
        (tmp_path / "BAD.jcl").write_text(_MEMBERS["BAD"], encoding="utf-8")
        source = "//J1 JOB (A)\n//S0 EXEC PGM=X\n// INCLUDE MEMBER=BAD\n//S9 EXEC\n"
        findings = validate_jcl(source, proc_base_path=tmp_path)
        assert [(f.line_number, f.message) for f in findings] == [
            (
                3,
                (
                    "EXEC statement missing program or procedure "
                    "(INCLUDE member BAD, line 2)"
                ),
            ),
            (4, "EXEC statement missing program or procedure"),
        ]

    def test_external_proc_lines_are_not_relabelled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JCL_PROCLIB_PATH", raising=False)
        (tmp_path / "SYS1.PROCLIB").mkdir()
        (tmp_path / "SYS1.PROCLIB" / "EXTP.jcl").write_text(
            "//EXTP PROC\n//PS1 EXEC PGM=A\n//PS2 EXEC PGM=B\n", encoding="utf-8"
        )
        (tmp_path / "COMMON.jcl").write_text(_COMMON, encoding="utf-8")
        source = "//J1 JOB (A)\n// INCLUDE MEMBER=COMMON\n//S1 EXEC EXTP\n"
        job = parse_jcl(source, proc_base_path=tmp_path)
        proc = job.get_procedure("EXTP")
        assert proc is not None and proc.is_external
        # The PROC's lines are its own library member's (as without INCLUDE),
        # never translated through this source's INCLUDE map.
        plain = parse_jcl("//J1 JOB (A)\n//S1 EXEC EXTP\n", proc_base_path=tmp_path)
        plain_proc = plain.get_procedure("EXTP")
        assert plain_proc is not None
        expected = [s.line_number for s in iter_execution_steps(plain_proc.steps)]
        assert [s.line_number for s in iter_execution_steps(proc.steps)] == expected
        assert expected[0] > 2  # would collapse to the INCLUDE line if relabelled
        step = job.get_step("S1")
        assert step is not None and step.line_number == 3

    def test_instream_proc_from_member_is_relabelled(self) -> None:
        loader = DictMemberLoader({"PROCS": "//P PROC\n//PS1 EXEC PGM=A\n// PEND\n"})
        source = "//J1 JOB (A)\n// INCLUDE MEMBER=PROCS\n//S1 EXEC P\n"
        job = parse_jcl(source, include_loader=loader)
        proc = job.get_procedure("P")
        assert proc is not None and proc.line_number == 2
        assert [s.line_number for s in proc.steps] == [2]
        step = job.get_step("S1")
        assert step is not None and step.line_number == 3

    def test_no_include_keeps_line_numbers(self) -> None:
        job = parse_jcl("//J1 JOB (A)\n//S1 EXEC PGM=A\n//S2 EXEC PGM=B\n")
        assert [s.line_number for s in iter_execution_steps(job.steps)] == [2, 3]


class TestResolveIncludesWithOrigins:
    def test_origins_map_every_line(self) -> None:
        source = "//J1 JOB\n// INCLUDE MEMBER=OUTER\n//S9 EXEC PGM=Y\n"
        text, origins = resolve_includes_with_origins(source, _loader())
        assert text == resolve_includes(source, _loader())
        assert len(origins) == len(split_source_lines(text))
        assert origins == [
            LineOrigin(None, 1),
            LineOrigin("OUTER", 2, 1),
            LineOrigin("OUTER", 2, 2),
            LineOrigin("BAD", 2, 1),
            LineOrigin("BAD", 2, 2),
            LineOrigin(None, 3),
        ]

    def test_collected_members(self) -> None:
        collected: list[str] = []
        resolve_includes_with_origins(
            "// INCLUDE MEMBER=OUTER\n", _loader(), collected=collected
        )
        assert collected == ["OUTER", "BAD"]

    def test_empty_member_and_missing_newline(self) -> None:
        source = "// INCLUDE MEMBER=EMPTY\n// INCLUDE MEMBER=NOEOL\n//X EXEC PGM=Z"
        text, origins = resolve_includes_with_origins(source, _loader())
        assert text == "\n//N1 EXEC PGM=A\n//X EXEC PGM=Z"
        assert origins == [
            LineOrigin("EMPTY", 1, 1),
            LineOrigin("NOEOL", 2, 1),
            LineOrigin(None, 3),
        ]

    def test_unresolved_member_left_intact(self) -> None:
        source = "// INCLUDE MEMBER=MISSING\n"
        assert resolve_includes_with_origins(source, _loader()) == (
            source,
            [LineOrigin(None, 1)],
        )

    def test_depth_limit_keeps_include_line(self) -> None:
        text, origins = resolve_includes_with_origins(
            "// INCLUDE MEMBER=OUTER\n", _loader(), max_depth=1
        )
        assert "// INCLUDE MEMBER=BAD" in text
        assert origins[-1] == LineOrigin("OUTER", 1, 3)


class TestIncludeLineMap:
    def test_out_of_range_lines_pass_through(self) -> None:
        line_map = IncludeLineMap([LineOrigin(None, 1), LineOrigin("M", 1, 1)])
        assert line_map.translate(0) == 0
        assert line_map.translate(9) == 9
        assert line_map.label(2) == "Line 1 (INCLUDE member M, line 1)"
        assert line_map.label(1) == "Line 1"
        assert line_map.relabel_text("ended on line 2") == "ended on line 1"

    def test_error_without_line_is_untouched(self) -> None:
        exc = JCLSyntaxError("no line")
        IncludeLineMap([LineOrigin("M", 1, 1)]).relabel_error(exc)
        assert str(exc) == "no line"
        assert exc.include_note == ""

    def test_error_with_column(self) -> None:
        exc = JCLSyntaxError("bad", line_number=2, column_number=5)
        IncludeLineMap([LineOrigin(None, 1), LineOrigin("M", 1, 1)]).relabel_error(exc)
        assert str(exc) == "Line 1 (INCLUDE member M, line 1), column 5: bad"
        assert str(JCLSyntaxError("bad", 3, column_number=4)) == (
            "Line 3, column 4: bad"
        )
