"""Regression tests for the CLI sweep over open-source JCL (2026-11-11).

Every ``jcl-parser`` subcommand was run on 491 JCL files from 19 public
GitHub repositories (Zowe, IBM samples, CardDemo, MVS sysgen, ...); these
tests pin the fixes for what it found.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jclparser import (
    ConstantComparison,
    analyze_job,
    detect_sql_in_job,
    parse_condition,
    parse_jcl,
    validate_jcl,
)
from jclparser.checks import lint_paths, validate_paths
from jclparser.cli import main
from jclparser.errors import ErrorSeverity
from jclparser.rc_analysis import compute_feasible_paths

pytestmark = pytest.mark.unit

_JOB = "//J JOB (A),'X'\n"


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    rc = main(argv)
    return rc, capsys.readouterr().out


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


# ---------------------------------------------------------------------------
# 1. IF comparing two constants (a SET symbol substituted into the condition)
# ---------------------------------------------------------------------------

# Zowe SZWESAMP(ZWEKRING) shape: the security product is chosen by SET.
_ZOWE_IF = (
    _JOB + "// SET OPTION=1\n"
    "//IFOPT1 IF (&OPTION EQ 1) THEN\n"
    "//RUNOPT1 EXEC PGM=IKJEFT01\n"
    "//IFOPT1E ENDIF\n"
    "//IFOPT2 IF (&OPTION EQ 2) THEN\n"
    "//RUNOPT2 EXEC PGM=IKJEFT01\n"
    "//IFOPT2E ENDIF\n"
)


class TestConstantComparison:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("(0 EQ 1)", False),
            ("(1 EQ 1)", True),
            ("1 = 1", True),
            ("2 GT 1", True),
            ("2 < 1", False),
            ("3 NE 3", False),
            ("1 LE 1", True),
            ("0 GE 1", False),
        ],
    )
    def test_parses_and_evaluates(self, text: str, expected: bool) -> None:
        ast = parse_condition(text)
        assert isinstance(ast, ConstantComparison)
        assert ast.evaluate({}) is expected

    def test_combines_with_step_tests(self) -> None:
        ast = parse_condition("(1 EQ 1) AND S1.RC = 0")
        assert ast is not None
        assert ast.evaluate({"S1": (0, False)}) is True
        assert ast.evaluate({"S1": (4, False)}) is False

    def test_value_first_rc_comparison_unchanged(self) -> None:
        ast = parse_condition("4 LT RC")
        assert ast is not None and not isinstance(ast, ConstantComparison)

    def test_set_symbol_in_if_validates_clean(self) -> None:
        assert validate_jcl(_ZOWE_IF, level="semantic") == []

    def test_dead_branch_is_unreachable(self) -> None:
        report = compute_feasible_paths(parse_jcl(_ZOWE_IF))
        assert "RUNOPT2" in report.unreachable_steps
        assert "RUNOPT1" not in report.unreachable_steps
        assert not report.unanalysed_conditions


# ---------------------------------------------------------------------------
# 2. A bundled PROC template is not the site's PROC
# ---------------------------------------------------------------------------

_IGYWCLG_CALL = _JOB + "//COBRUN EXEC IGYWCLG,SRC=HELLO\n"


class TestBuiltinProcedureTemplate:
    def test_unused_symbol_is_warning_against_builtin(self) -> None:
        findings = [
            e
            for e in validate_jcl(_IGYWCLG_CALL, level="semantic")
            if "SRC" in e.message
        ]
        assert len(findings) == 1
        assert findings[0].severity == ErrorSeverity.WARNING
        assert "built-in IGYWCLG template" in findings[0].message

    def test_unused_symbol_is_error_against_site_proc(self, tmp_path: Path) -> None:
        lib = tmp_path / "SYS1.PROCLIB"
        lib.mkdir()
        (lib / "IGYWCLG.jcl").write_text(
            "//IGYWCLG PROC LNGPRFX='IGY'\n//COBOL EXEC PGM=IGYCRCTL\n"
        )
        findings = [
            e
            for e in validate_jcl(
                _IGYWCLG_CALL, level="semantic", proc_base_path=str(tmp_path)
            )
            if "SRC" in e.message
        ]
        assert len(findings) == 1
        assert findings[0].severity == ErrorSeverity.ERROR

    def test_site_proc_declaring_symbol_is_clean(self, tmp_path: Path) -> None:
        lib = tmp_path / "SYS1.PROCLIB"
        lib.mkdir()
        (lib / "IGYWCLG.jcl").write_text(
            "//IGYWCLG PROC SRC=X\n//COBOL EXEC PGM=IGYCRCTL\n"
            "//SYSIN DD DSN=A.CBL(&SRC),DISP=SHR\n"
        )
        messages = [
            e.message
            for e in validate_jcl(
                _IGYWCLG_CALL, level="semantic", proc_base_path=str(tmp_path)
            )
        ]
        assert not any("IEFC657I" in m for m in messages)

    def test_procs_labels_builtin(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        empty = tmp_path / "lib"
        empty.mkdir()
        jcl = _write(tmp_path, "c.jcl", _IGYWCLG_CALL)
        rc, out = _run([str(jcl), "procs", "--proc-path", str(empty)], capsys)
        assert rc == 0
        assert "PROC: IGYWCLG  [builtin]" in out

    def test_cli_validate_exits_zero_on_builtin_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        jcl = _write(tmp_path, "c.jcl", _IGYWCLG_CALL)
        rc, out = _run([str(jcl), "--validate"], capsys)
        assert rc == 0
        assert "[WARNING]" in out


# ---------------------------------------------------------------------------
# 3. SQL detection
# ---------------------------------------------------------------------------


def _sql_steps(jcl: str) -> dict[str, list[str]]:
    """``{step: [keyword, ...]}`` for every step detect_sql_in_job reports."""
    return {
        r.step_name or "": [kw for kw, _, _ in r.sql_statements]
        for r in detect_sql_in_job(parse_jcl(jcl))
    }


class TestSqlDetection:
    def test_tso_batch_without_dsn_is_not_db2(self) -> None:
        jcl = (
            _JOB + "//GITCOPY EXEC PGM=IKJEFT01\n//SYSTSPRT DD SYSOUT=*\n"
            "//SYSTSIN DD *\n OGETX '/u/x' 'A.B' LC SUFFIX ASIS\n/*\n"
        )
        assert _sql_steps(jcl) == {}

    def test_tso_batch_with_dsn_command_is_db2(self) -> None:
        jcl = (
            _JOB + "//RUN EXEC PGM=IKJEFT01\n//SYSTSIN DD *\n"
            " DSN SYSTEM(DB2P)\n RUN PROGRAM(DSNTEP2) PLAN(P)\n END\n/*\n"
            "//SYSIN DD *\n SELECT * FROM T;\n/*\n"
        )
        result = detect_sql_in_job(parse_jcl(jcl))
        assert len(result) == 1
        assert result[0].is_db2_program
        assert [kw for kw, _, _ in result[0].sql_statements] == ["SELECT"]

    def test_tso_batch_with_db2_steplib_is_db2(self) -> None:
        # CardDemo: SYSTSIN read from a dataset, so only STEPLIB tells.
        jcl = (
            _JOB + "//FREEPLN EXEC PGM=IKJEFT01\n"
            "//STEPLIB DD DISP=SHR,DSN=DSN.V13.SDSNLOAD\n"
            "//SYSTSIN DD DISP=SHR,DSN=MY.CNTL(DB2FREE)\n"
        )
        (result,) = detect_sql_in_job(parse_jcl(jcl))
        assert result.is_db2_program

    def test_tso_batch_with_db2_joblib_is_db2(self) -> None:
        jcl = (
            _JOB + "//JOBLIB DD DISP=SHR,DSN=DSN.V13.SDSNEXIT\n"
            "//FREEPLN EXEC PGM=IKJEFT1B\n"
            "//SYSTSIN DD DISP=SHR,DSN=MY.CNTL(DB2FREE)\n"
        )
        (result,) = detect_sql_in_job(parse_jcl(jcl))
        assert result.is_db2_program

    def test_racf_commands_through_ddname_are_not_sql(self) -> None:
        # Zowe ZWENOSEC: SYSTSIN DD DDNAME=RACF reads the RACF DD.
        jcl = (
            _JOB + "//RUN EXEC PGM=IKJEFT01\n//SYSTSIN DD DDNAME=RACF\n"
            "//RACF DD DATA,DLM=$$\n DELETE USER1\n SETROPTS REFRESH\n$$\n"
        )
        assert _sql_steps(jcl) == {}

    @pytest.mark.parametrize(
        ("program", "ddname", "card"),
        [
            ("IFOX00", "SYSIN", "         DROP  R12"),
            ("ASMA90", "SYSIN", "         DROP  R12"),
            ("DFHCSDUP", "SYSIN", " DELETE GROUP(GENA)"),
            ("IXCMIAPU", "SYSIN", " DELETE LOGSTREAM NAME(X.Y)"),
            ("GIMSMP", "SMPCNTL", " APPLY SELECT(ZP60011)"),
        ],
    )
    def test_control_languages_reusing_sql_verbs(
        self, program: str, ddname: str, card: str
    ) -> None:
        jcl = _JOB + f"//S EXEC PGM={program}\n//{ddname} DD *\n{card}\n/*\n"
        assert _sql_steps(jcl) == {}

    def test_smpcntl_under_unexploded_proc_call(self) -> None:
        jcl = _JOB + "//RECEIVE EXEC SMPREC\n//SMPCNTL DD *\n RECEIVE SELECT(X)\n/*\n"
        assert _sql_steps(jcl) == {}

    def test_assembler_source_under_ibm_assembler_proc(self) -> None:
        jcl = _JOB + "//ULAM EXEC ASMFCL\n//ASM.SYSIN DD *\n         DROP  R12\n/*\n"
        assert _sql_steps(jcl) == {}

    def test_dsntep2_sql_still_found(self) -> None:
        jcl = _JOB + "//S EXEC PGM=DSNTEP2\n//SYSIN DD *\n DROP TABLE T;\n/*\n"
        assert _sql_steps(jcl) == {"S": ["DROP"]}


# ---------------------------------------------------------------------------
# 4. Validating files that are not JCL
# ---------------------------------------------------------------------------


class TestValidateNonJcl:
    def test_binary_content_is_one_finding(self) -> None:
        errors = validate_jcl("\x00\x01abc\n" * 500)
        assert [e.message for e in errors] == [
            "Not a JCL file: binary content (NUL bytes)"
        ]

    def test_text_without_jcl_records_is_one_finding(self) -> None:
        errors = validate_jcl("FROM image\nRUN make\n" * 300)
        assert [e.message for e in errors] == [
            "Not a JCL file: no record starts with //"
        ]

    def test_empty_input_still_reports_missing_job(self) -> None:
        assert [e.message for e in validate_jcl("")] == ["No JOB statement found"]

    def test_many_bad_records_are_capped(self) -> None:
        junk = "".join(f"junk {i}\n" for i in range(50))
        errors = validate_jcl(junk + _JOB + "//S EXEC PGM=X\n")
        bad = [e for e in errors if e.message.startswith("Invalid JCL statement")]
        assert len(bad) == 20
        assert any(
            e.message.startswith("30 more record(s) do not start with //")
            for e in errors
        )

    def test_few_bad_records_all_reported(self) -> None:
        errors = validate_jcl("junk 1\njunk 2\n" + _JOB + "//S EXEC PGM=X\n")
        bad = [e for e in errors if e.message.startswith("Invalid JCL statement")]
        assert len(bad) == 2
        assert not any("more record(s)" in e.message for e in errors)

    def test_directory_validate_one_finding_per_bad_file(self, tmp_path: Path) -> None:
        (tmp_path / "blob.bin").write_bytes(bytes(range(256)) * 400)
        _write(tmp_path, "Dockerfile", "FROM x\nRUN y\n" * 100)
        _write(tmp_path, "ok.jcl", _JOB + "//S EXEC PGM=X\n")
        reports = {Path(r.uri).name: r for r in validate_paths([tmp_path])}
        assert len(reports["blob.bin"].findings) == 1
        assert len(reports["Dockerfile"].findings) == 1
        assert reports["ok.jcl"].findings == []

    def test_lint_parse_failure_message_is_printable(self, tmp_path: Path) -> None:
        (tmp_path / "blob.bin").write_bytes(b"\x01\x02\x7f" * 200 + b"\n")
        (report,) = lint_paths([tmp_path / "blob.bin"])
        (finding,) = report.findings
        assert finding.message.isprintable()
        assert len(finding.message) <= len("Not parsed: ") + 160


# ---------------------------------------------------------------------------
# 5. analyze: IEBGENER submit idiom, IDCAMS BLDINDEX / DEFINE ALIAS
# ---------------------------------------------------------------------------


class TestAnalyzeProfiles:
    def test_iebgener_instream_to_intrdr(self) -> None:
        jcl = (
            _JOB + "//SUB EXEC PGM=IEBGENER\n//SYSPRINT DD DUMMY\n//SYSIN DD DUMMY\n"
            "//SYSUT1 DD DATA,DLM=$$\n//J2 JOB 1\n$$\n"
            "//SYSUT2 DD SYSOUT=(A,INTRDR)\n"
        )
        (result,) = analyze_job(parse_jcl(jcl))
        assert result.summary == "IEBGENER: copy SYSUT1 -> SYSUT2"
        assert "reads in-stream data" in result.notes
        assert "writes to the internal reader (submits it as a job)" in result.notes

    def test_iebgener_dataset_to_sysout(self) -> None:
        jcl = (
            _JOB + "//P EXEC PGM=IEBGENER\n//SYSUT1 DD DSN=A.B,DISP=SHR\n"
            "//SYSUT2 DD SYSOUT=*\n"
        )
        (result,) = analyze_job(parse_jcl(jcl))
        assert result.notes == ["reads A.B", "writes to SYSOUT class *"]

    def test_iebgener_without_sysut_dds(self) -> None:
        jcl = _JOB + "//P EXEC PGM=IEBGENER\n//SYSPRINT DD SYSOUT=*\n"
        (result,) = analyze_job(parse_jcl(jcl))
        assert result.summary == "IEBGENER (no SYSUT1/SYSUT2)"

    def test_idcams_bldindex(self) -> None:
        jcl = (
            _JOB + "//STEP30 EXEC PGM=IDCAMS\n//SYSPRINT DD SYSOUT=*\n//SYSIN DD *\n"
            "   BLDINDEX                                 -\n"
            "   INDATASET(A.KSDS)                        -\n"
            "   OUTDATASET(A.AIX)\n/*\n"
        )
        (result,) = analyze_job(parse_jcl(jcl))
        assert result.notes == ["IDCAMS BLDINDEX A.KSDS -> A.AIX"]

    def test_idcams_define_alias_is_noted_not_allocated(self) -> None:
        jcl = (
            _JOB + "//ALIAS EXEC PGM=IDCAMS\n//SYSPRINT DD SYSOUT=*\n//SYSIN DD *\n"
            "  DEFINE ALIAS(NAME(BREXX) RELATE(UCPUB001))\n/*\n"
        )
        (result,) = analyze_job(parse_jcl(jcl))
        assert result.notes == ["IDCAMS DEFINE ALIAS BREXX"]
        assert result.dataset_events == []


# ---------------------------------------------------------------------------
# 6. Step / DD display
# ---------------------------------------------------------------------------

_DISPLAY_JCL = (
    _JOB + "//G EXEC PGM=IEBGENER\n//SYSPRINT DD DUMMY\n//SYSUT1 DD *\nX\n/*\n"
    "//SYSUT2 DD SYSOUT=(A,INTRDR)\n"
)


class TestDisplay:
    def test_step_detail_shows_dummy_and_sysout_sublist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        jcl = _write(tmp_path, "g.jcl", _DISPLAY_JCL)
        rc, out = _run([str(jcl), "G"], capsys)
        assert rc == 0
        lines = [line.strip() for line in out.splitlines()]
        assert "SYSPRINT     DUMMY" in lines
        assert "SYSUT2       SYSOUT=(A,INTRDR)" in lines
        assert "['A', 'INTRDR']" not in out

    def test_dd_detail_shows_sysout_sublist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        jcl = _write(tmp_path, "g.jcl", _DISPLAY_JCL)
        rc, out = _run([str(jcl), "G.SYSUT2"], capsys)
        assert rc == 0
        assert "SYSOUT=(A,INTRDR)" in out


# ---------------------------------------------------------------------------
# 7. An empty in-stream DD as the last statement
# ---------------------------------------------------------------------------


class TestEmptyInstreamAtEnd:
    def test_dd_star_at_end_of_file_is_empty_instream_data(self) -> None:
        job = parse_jcl(_JOB + "//S EXEC PGM=X\n//IN DD *\n")
        assert job.steps[0].dd_statements[0].inline_data == ""

    def test_dd_star_at_end_of_file_validates_clean(self) -> None:
        assert validate_jcl(_JOB + "//S EXEC PGM=X\n//IN DD *\n") == []


# ---------------------------------------------------------------------------
# 8. --validate exit code: errors fail, warnings do not (unless --fail-on)
# ---------------------------------------------------------------------------

_WARN_ONLY = _JOB + "//A EXEC PGM=X\n//A EXEC PGM=Y\n"
_WITH_ERROR = _JOB + "//A EXEC PGM=X\n//D DD DSN=X,DISP=BOGUS\n"


class TestValidateExitCode:
    @pytest.mark.parametrize("fmt", [[], ["--json"], ["--sarif"]])
    def test_warning_alone_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], fmt: list[str]
    ) -> None:
        jcl = _write(tmp_path, "w.jcl", _WARN_ONLY)
        rc, _ = _run([str(jcl), "--validate", *fmt], capsys)
        assert rc == 0

    def test_fail_on_warning_fails_on_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        jcl = _write(tmp_path, "w.jcl", _WARN_ONLY)
        rc, _ = _run([str(jcl), "--validate", "--fail-on", "warning"], capsys)
        assert rc == 1

    def test_json_valid_ignores_warnings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        jcl = _write(tmp_path, "w.jcl", _WARN_ONLY)
        _, out = _run([str(jcl), "--validate", "--json"], capsys)
        doc = json.loads(out)
        assert doc["valid"] is True
        assert doc["errors"][0]["severity"] == "WARNING"

    def test_error_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        jcl = _write(tmp_path, "e.jcl", _WITH_ERROR)
        rc, out = _run([str(jcl), "--validate", "--json"], capsys)
        assert rc == 1
        assert json.loads(out)["valid"] is False

    def test_directory_validate_follows_fail_on(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path, "w.jcl", _WARN_ONLY)
        assert _run([str(tmp_path), "--validate"], capsys)[0] == 0
        assert (
            _run([str(tmp_path), "--validate", "--fail-on", "warning"], capsys)[0] == 1
        )
        _write(tmp_path, "e.jcl", _WITH_ERROR)
        assert _run([str(tmp_path), "--validate"], capsys)[0] == 1
