"""Lint in CI: TOML config, inline suppressions, rules 006/009/010,
multi-file SARIF, ``jcl-lint`` and ``jcl-parser DIR lint / --validate``."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from jclparser import parse_jcl
from jclparser.checks import (
    FileReport,
    as_finding,
    exit_code,
    format_reports,
    iter_source_files,
    lint_main,
    lint_paths,
    reports_to_dict,
    reports_to_sarif,
    resolve_lint_config,
    validate_paths,
)
from jclparser.cli import main
from jclparser.errors import ErrorSeverity, ErrorType, ParseError, ValidationError
from jclparser.lint import (
    PARSE_ERROR_CODE,
    LintConfig,
    LintConfigError,
    find_lint_config,
    lint_config_from_mapping,
    lint_job,
    load_lint_config,
    parse_suppressions,
    to_sarif_files,
)

CLEAN_JOB = """\
//CLEAN    JOB (ACCT),'X',TIME=5,REGION=0M
//S1       EXEC PGM=IEFBR14
//DD1      DD DSN=&&TEMP,DISP=(NEW,PASS),SPACE=(TRK,1)
"""

BAD_JOB = """\
//MYJOB    JOB (ACCT),'X'
//S1       EXEC PGM=IEFBR14
//DD1      DD DSN=PROD.DATA.ONE,DISP=(NEW,CATLG),SPACE=(CYL,(1,1))
"""


def _codes(findings: list[ValidationError]) -> list[str]:
    return [f.error_code or "" for f in findings]


def _lint(text: str, config: LintConfig | None = None, **kw: object) -> list[str]:
    return _codes(lint_job(parse_jcl(text), config, **kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestLintConfig:
    def test_every_key(self) -> None:
        cfg = lint_config_from_mapping(
            {
                "select": ["jcl-lint-001", "JCL-LINT-004"],
                "ignore": ["JCL-LINT-004"],
                "severity": {"jcl-lint-001": "Warning"},
                "critical-datasets": ["PROD."],
                "fail-on": "error",
            }
        )
        assert cfg.enabled == {"JCL-LINT-001", "JCL-LINT-004"}
        assert cfg.disabled == {"JCL-LINT-004"}
        assert cfg.severities == {"JCL-LINT-001": ErrorSeverity.WARNING}
        assert cfg.critical_dataset_patterns == ["PROD."]
        assert cfg.fail_on is ErrorSeverity.ERROR
        assert not cfg.should_run("JCL-LINT-004")

    def test_defaults(self) -> None:
        cfg = lint_config_from_mapping({})
        assert cfg == LintConfig()
        assert cfg.fails(ErrorSeverity.INFO)

    def test_fails_threshold(self) -> None:
        cfg = LintConfig(fail_on=ErrorSeverity.WARNING)
        assert not cfg.fails(ErrorSeverity.INFO)
        assert cfg.fails(ErrorSeverity.WARNING)
        assert cfg.fails(ErrorSeverity.ERROR)

    @pytest.mark.parametrize(
        "data, message",
        [
            ({"bogus": 1}, "unknown lint setting"),
            ({"select": "JCL-LINT-001"}, "select"),
            ({"ignore": [1]}, "ignore"),
            ({"severity": ["x"]}, "severity"),
            ({"severity": {"JCL-LINT-001": "loud"}}, "severity.JCL-LINT-001"),
            ({"critical-datasets": "PROD."}, "critical-datasets"),
            ({"fail-on": 3}, "fail-on"),
        ],
    )
    def test_invalid(self, data: dict, message: str) -> None:
        with pytest.raises(LintConfigError, match=message):
            lint_config_from_mapping(data)

    def test_pyproject_table(self, tmp_path: Path) -> None:
        path = tmp_path / "pyproject.toml"
        path.write_text('[tool.jcl-parser.lint]\nignore = ["JCL-LINT-005"]\n')
        assert load_lint_config(path).disabled == {"JCL-LINT-005"}

    def test_pyproject_without_table_is_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "pyproject.toml"
        path.write_text('[project]\nname = "x"\n')
        assert load_lint_config(path) == LintConfig()

    def test_other_toml_is_the_table(self, tmp_path: Path) -> None:
        path = tmp_path / "lint.toml"
        path.write_text('fail-on = "warning"\n')
        assert load_lint_config(path).fail_on is ErrorSeverity.WARNING

    def test_bad_toml(self, tmp_path: Path) -> None:
        path = tmp_path / "lint.toml"
        path.write_text("fail-on = \n")
        with pytest.raises(LintConfigError, match="lint.toml"):
            load_lint_config(path)

    def test_find_walks_up_to_a_pyproject_with_the_table(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.jcl-parser.lint]\n")
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        # A pyproject without the table, or a broken one, is passed over.
        (tmp_path / "a" / "pyproject.toml").write_text("[project]\n")
        (nested / "pyproject.toml").write_text("not toml [\n")
        job = nested / "J.jcl"
        job.write_text(CLEAN_JOB)
        assert find_lint_config(job) == (tmp_path / "pyproject.toml").resolve()
        assert find_lint_config(nested) == (tmp_path / "pyproject.toml").resolve()

    def test_find_none(self, tmp_path: Path) -> None:
        assert find_lint_config(tmp_path) is None

    def test_resolve(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        explicit = tmp_path / "x.toml"
        explicit.write_text('ignore = ["JCL-LINT-001"]\n')
        assert resolve_lint_config(str(explicit)).disabled == {"JCL-LINT-001"}
        monkeypatch.chdir(tmp_path)
        assert resolve_lint_config(None) == LintConfig()
        (tmp_path / "pyproject.toml").write_text(
            '[tool.jcl-parser.lint]\nfail-on = "error"\n'
        )
        assert resolve_lint_config(None).fail_on is ErrorSeverity.ERROR


# ---------------------------------------------------------------------------
# Suppressions
# ---------------------------------------------------------------------------


class TestSuppressions:
    def test_next_statement(self) -> None:
        text = BAD_JOB.replace(
            "//DD1 ", "//* jcl-lint: disable=JCL-LINT-001,jcl-lint-006\n//DD1 "
        )
        assert _lint(text) == _lint(BAD_JOB, source=BAD_JOB)
        codes = _lint(text, source=text)
        assert "JCL-LINT-001" not in codes
        assert "JCL-LINT-006" not in codes
        assert "JCL-LINT-004" in codes

    def test_skips_comment_records_before_the_statement(self) -> None:
        sup = parse_suppressions(
            "//J JOB\n//* jcl-lint: disable=X\n//* note\n//S EXEC PGM=A\n"
        )
        assert sup.line_codes == {4: {"X"}}

    def test_whole_file_and_all(self) -> None:
        text = "//* jcl-lint: disable-file=all\n" + BAD_JOB
        assert _lint(text, source=text) == []
        text = "//* JCL-LINT: DISABLE-FILE=JCL-LINT-004\n" + BAD_JOB
        assert "JCL-LINT-004" not in _lint(text, source=text)

    def test_lines_and_findings_without_code(self) -> None:
        sup = parse_suppressions(["//* jcl-lint: disable=all", "//J JOB"])
        assert sup.suppresses(ValidationError("m", line_number=2))
        assert not sup.suppresses(ValidationError("m", line_number=1))
        assert not parse_suppressions("//J JOB\n").suppresses(ValidationError("m"))

    def test_directive_at_end_applies_to_nothing(self) -> None:
        sup = parse_suppressions("//J JOB\n//* jcl-lint: disable=X\n")
        assert sup.line_codes == {}


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class TestNewDatasetWithoutRlse:
    @pytest.mark.parametrize(
        "dd",
        [
            "DSN=A.B,DISP=(NEW,CATLG),SPACE=(CYL,(1,1))",
            "DSN=A.B,DISP=(,CATLG),SPACE=(TRK,5)",
            "DSN=A.B,SPACE=(TRK,5)",
        ],
    )
    def test_reported(self, dd: str) -> None:
        assert "JCL-LINT-006" in _lint(f"//J JOB\n//S EXEC PGM=A\n//D DD {dd}\n")

    @pytest.mark.parametrize(
        "dd",
        [
            "DSN=A.B,DISP=(NEW,CATLG),SPACE=(CYL,(1,1),RLSE)",
            "DSN=A.B,DISP=OLD,SPACE=(CYL,(1,1))",
            "DSN=&&T,DISP=(NEW,PASS),SPACE=(CYL,(1,1))",
            "DSN=A.B,DISP=(NEW,CATLG)",
            "SYSOUT=*",
        ],
    )
    def test_not_reported(self, dd: str) -> None:
        assert "JCL-LINT-006" not in _lint(f"//J JOB\n//S EXEC PGM=A\n//D DD {dd}\n")


class TestCondMixedWithIf:
    def test_reported_once_per_cond_step(self) -> None:
        text = (
            "//J JOB\n//S1 EXEC PGM=A,COND=(4,LT)\n//S2 EXEC PGM=B\n"
            "// IF (S1.RC = 0) THEN\n//S3 EXEC PGM=C,COND=EVEN\n// ENDIF\n"
        )
        findings = [
            f for f in lint_job(parse_jcl(text)) if f.error_code == "JCL-LINT-009"
        ]
        assert [f.line_number for f in findings] == [2, 5]

    def test_cond_alone_is_fine(self) -> None:
        text = "//J JOB\n//S1 EXEC PGM=A,COND=(4,LT)\n"
        assert "JCL-LINT-009" not in _lint(text)


class TestLiteralSetValueHlq:
    TEXT = (
        "//J JOB\n// SET HLQ=PROD\n//S EXEC PGM=A\n"
        "//D1 DD DSN=PROD.X,DISP=SHR\n//D2 DD DSN=&HLQ..Y,DISP=SHR\n"
        "//D3 DD DSN=TEST.Z,DISP=SHR\n"
    )

    def test_reported_instead_of_001(self) -> None:
        findings = lint_job(parse_jcl(self.TEXT))
        by_line = {(f.error_code, f.line_number) for f in findings}
        assert ("JCL-LINT-010", 4) in by_line
        assert ("JCL-LINT-001", 4) not in by_line
        assert ("JCL-LINT-001", 6) in by_line
        assert not any(line == 5 for _, line in by_line)
        msg = next(f.message for f in findings if f.error_code == "JCL-LINT-010")
        assert "&HLQ" in msg

    def test_001_reports_it_when_010_is_off(self) -> None:
        cfg = LintConfig(disabled={"JCL-LINT-010"})
        findings = lint_job(parse_jcl(self.TEXT), cfg)
        assert ("JCL-LINT-001", 4) in {(f.error_code, f.line_number) for f in findings}

    def test_no_set_symbols(self) -> None:
        assert "JCL-LINT-010" not in _lint("//J JOB\n//S EXEC PGM=A\n//D DD DSN=A.B\n")

    def test_value_that_is_no_qualifier(self) -> None:
        text = "//J JOB\n// SET X='A.B'\n//S EXEC PGM=A\n//D DD DSN=A.B.C\n"
        assert "JCL-LINT-010" not in _lint(text)


# ---------------------------------------------------------------------------
# SARIF
# ---------------------------------------------------------------------------


class TestSarifFiles:
    def test_results_carry_their_file(self) -> None:
        a = ValidationError("a", line_number=3, error_code="JCL-LINT-001")
        b = ValidationError("b", error_code=PARSE_ERROR_CODE)
        c = ValidationError("c")
        sarif = to_sarif_files([("x/A.jcl", [a]), ("x/B.jcl", [b]), (None, [c])])
        run = sarif["runs"][0]
        first, second, third = run["results"]
        loc = first["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"] == {"uri": "x/A.jcl"}
        assert loc["region"] == {"startLine": 3}
        assert second["locations"][0]["physicalLocation"] == {
            "artifactLocation": {"uri": "x/B.jcl"}
        }
        assert third["locations"] == []
        assert third["ruleId"] == "JCL-GEN-000"
        rules = {r["id"]: r for r in run["tool"]["driver"]["rules"]}
        assert rules[PARSE_ERROR_CODE]["fullDescription"]["text"]


# ---------------------------------------------------------------------------
# checks: lint_paths / validate_paths / rendering
# ---------------------------------------------------------------------------


@pytest.fixture
def jobs(tmp_path: Path) -> Path:
    root = tmp_path / "jobs"
    root.mkdir()
    (root / "BAD.jcl").write_text(BAD_JOB)
    (root / "CLEAN.jcl").write_text(CLEAN_JOB)
    (root / "JUNK.jcl").write_text("not jcl\n")
    (root / "PROCA.jcl").write_text("//PROCA PROC\n//P1 EXEC PGM=IEFBR14\n")
    (root / ".hidden.jcl").write_text("junk\n")
    return root


class TestChecks:
    def test_iter_source_files_skips_hidden(self, jobs: Path) -> None:
        names = [p.name for p in iter_source_files(jobs)]
        assert names == ["BAD.jcl", "CLEAN.jcl", "JUNK.jcl", "PROCA.jcl"]

    def test_lint_directory(self, jobs: Path) -> None:
        reports = lint_paths([jobs])
        by_uri = {Path(r.uri).name: r for r in reports}
        # PROC members are not jobs; a junk file is a parse finding.
        assert sorted(by_uri) == ["BAD.jcl", "CLEAN.jcl", "JUNK.jcl"]
        assert by_uri["CLEAN.jcl"].findings == []
        assert _codes(by_uri["JUNK.jcl"].findings) == [PARSE_ERROR_CODE]
        assert "JCL-LINT-006" in _codes(by_uri["BAD.jcl"].findings)

    def test_lint_files_and_explode(self, jobs: Path) -> None:
        reports = lint_paths([jobs / "BAD.jcl", jobs / "JUNK.jcl"], explode=True)
        assert [Path(r.uri).name for r in reports] == ["BAD.jcl", "JUNK.jcl"]
        junk = reports[1].findings[0]
        assert junk.severity is ErrorSeverity.ERROR
        assert junk.line_number == 1

    def test_lint_honours_suppressions(self, tmp_path: Path) -> None:
        path = tmp_path / "J.jcl"
        path.write_text("//* jcl-lint: disable-file=all\n" + BAD_JOB)
        assert lint_paths([path])[0].findings == []

    def test_validate(self, jobs: Path) -> None:
        reports = validate_paths([jobs])
        assert len(reports) == 4
        by_name = {Path(r.uri).name: r for r in reports}
        assert by_name["JUNK.jcl"].findings
        assert by_name["CLEAN.jcl"].findings == []
        assert validate_paths([jobs / "CLEAN.jcl"])[0].findings == []

    def test_validate_unreadable(self, tmp_path: Path) -> None:
        reports = validate_paths([tmp_path / "missing.jcl"])
        assert _codes(reports[0].findings) == [PARSE_ERROR_CODE]

    def test_as_finding(self) -> None:
        err = ParseError(ErrorType.SYNTAX_ERROR, "m", 0, severity=ErrorSeverity.INFO)
        finding = as_finding(err)
        assert (finding.message, finding.line_number, finding.severity) == (
            "m",
            None,
            ErrorSeverity.INFO,
        )
        same = ValidationError("x")
        assert as_finding(same) is same

    def test_rendering_and_exit_code(self) -> None:
        reports = [
            FileReport(
                "a.jcl",
                [
                    ValidationError("late", line_number=9, severity=ErrorSeverity.INFO),
                    ValidationError("early", line_number=2, error_code="C"),
                ],
            ),
            FileReport("b.jcl"),
        ]
        text = format_reports(reports, "OK")
        assert text.splitlines() == [
            "a.jcl:2: ERROR [C] early",
            "a.jcl:9: INFO late",
            "2 finding(s) in 1 of 2 file(s)",
        ]
        assert format_reports([FileReport("b.jcl")], "OK") == "OK\n"
        data = reports_to_dict(reports)
        assert data["count"] == 2 and data["files"]["b.jcl"] == []
        assert reports_to_sarif(reports)["runs"][0]["results"]
        assert exit_code(reports, ErrorSeverity.ERROR) == 1
        info_only = [FileReport("a.jcl", [reports[0].findings[0]])]
        assert exit_code(info_only, ErrorSeverity.WARNING) == 0
        assert exit_code(info_only, ErrorSeverity.INFO) == 1


# ---------------------------------------------------------------------------
# jcl-lint
# ---------------------------------------------------------------------------


class TestJclLint:
    def test_text(self, jobs: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert lint_main([str(jobs)]) == 1
        out = capsys.readouterr().out
        assert "BAD.jcl:3: INFO [JCL-LINT-006]" in out
        assert "JUNK.jcl: ERROR [JCL-PARSE-000]" in out

    def test_clean_file(self, jobs: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert lint_main([str(jobs / "CLEAN.jcl")]) == 0
        assert capsys.readouterr().out == "OK - no lint findings.\n"

    def test_fail_on_select_ignore(self, jobs: Path) -> None:
        bad = str(jobs / "BAD.jcl")
        assert lint_main([bad, "--fail-on", "warning"]) == 0
        assert lint_main([bad, "--select", "JCL-LINT-007"]) == 0
        assert lint_main([bad, "--ignore", "jcl-lint-001, JCL-LINT-004"]) == 1
        everything = "JCL-LINT-001,JCL-LINT-004,JCL-LINT-005,JCL-LINT-006"
        assert lint_main([bad, "--ignore", everything]) == 0

    def test_sarif_to_file(self, jobs: Path, tmp_path: Path) -> None:
        out = tmp_path / "r.sarif"
        assert lint_main([str(jobs), "--format", "sarif", "-o", str(out)]) == 1
        sarif = json.loads(out.read_text())
        uris = {
            loc["physicalLocation"]["artifactLocation"]["uri"]
            for result in sarif["runs"][0]["results"]
            for loc in result["locations"]
        }
        assert {Path(u).name for u in uris} == {"BAD.jcl", "JUNK.jcl"}

    def test_json(self, jobs: Path, capsys: pytest.CaptureFixture[str]) -> None:
        lint_main([str(jobs), "--format", "json", "--glob", "C*"])
        data = json.loads(capsys.readouterr().out)
        assert data["count"] == 0 and len(data["files"]) == 1

    def test_config_file(self, jobs: Path, tmp_path: Path) -> None:
        cfg = tmp_path / "lint.toml"
        cfg.write_text('fail-on = "error"\n')
        assert lint_main([str(jobs / "BAD.jcl"), "--config", str(cfg)]) == 0

    def test_errors(
        self, jobs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad_cfg = tmp_path / "bad.toml"
        bad_cfg.write_text("nope = 1\n")
        assert lint_main([str(jobs), "--config", str(bad_cfg)]) == 2
        assert lint_main([str(jobs), "--config", str(tmp_path / "none.toml")]) == 2
        assert lint_main([str(tmp_path / "missing")]) == 2
        assert lint_main([str(jobs), "--glob", "*.none"]) == 2
        err = capsys.readouterr().err
        assert "unknown lint setting" in err and "not found" in err
        assert "no JCL files" in err


# ---------------------------------------------------------------------------
# jcl-parser CLI
# ---------------------------------------------------------------------------


class _Stdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


class TestCli:
    def test_file_lint_sarif(
        self, jobs: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = jobs / "BAD.jcl"
        assert main([str(path), "lint", "--sarif"]) == 1
        sarif = json.loads(capsys.readouterr().out)
        loc = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == path.as_posix()

    def test_file_lint_fail_on_and_config(
        self, jobs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = str(jobs / "BAD.jcl")
        assert main([path, "lint", "--fail-on", "warning"]) == 0
        capsys.readouterr()
        (jobs / "pyproject.toml").write_text(
            '[tool.jcl-parser.lint]\nignore = ["JCL-LINT-006"]\n'
        )
        main([path, "lint", "--json"])
        codes = {f["code"] for f in json.loads(capsys.readouterr().out)["findings"]}
        assert "JCL-LINT-006" not in codes and "JCL-LINT-004" in codes
        bad = tmp_path / "bad.toml"
        bad.write_text("fail-on = 'loud'\n")
        assert main([path, "lint", "--config", str(bad)]) == 2
        assert "fail-on" in capsys.readouterr().err

    def test_stdin_lint_honours_suppressions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        text = "//* jcl-lint: disable-file=all\n" + BAD_JOB
        monkeypatch.setattr(sys, "stdin", _Stdin(text.encode()))
        assert main(["-", "lint", "--sarif"]) == 0
        sarif = json.loads(capsys.readouterr().out)
        assert sarif["runs"][0]["results"] == []

    def test_directory_lint(
        self, jobs: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([str(jobs), "lint"]) == 1
        assert "BAD.jcl:3:" in capsys.readouterr().out
        assert main([str(jobs), "lint", "--glob", "C*"]) == 0
        assert main([str(jobs), "lint", "--json", "--glob", "C*"]) == 0
        assert json.loads(capsys.readouterr().out.split("\n", 1)[1])["count"] == 0
        assert main([str(jobs), "lint", "--sarif"]) == 1
        assert json.loads(capsys.readouterr().out)["version"] == "2.1.0"

    def test_directory_lint_errors(
        self, jobs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([str(jobs), "lint", "--glob", "*.none"]) == 1
        bad = tmp_path / "bad.toml"
        bad.write_text("x = 1\n")
        assert main([str(jobs), "lint", "--config", str(bad)]) == 2
        assert main([str(jobs), "lint", "--validate"]) == 1
        err = capsys.readouterr().err
        assert "no JCL jobs found" in err and "--validate apply" in err

    def test_directory_validate(
        self, jobs: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([str(jobs), "--validate"]) == 1
        assert "JUNK.jcl:1: ERROR" in capsys.readouterr().out
        assert main([str(jobs), "--validate", "--glob", "C*"]) == 0
        assert capsys.readouterr().out == "OK - no errors found.\n"
        assert main([str(jobs), "--validate", "--json", "--glob", "C*"]) == 0
        assert json.loads(capsys.readouterr().out)["count"] == 0
        assert main([str(jobs), "--validate", "--sarif"]) == 1
        assert json.loads(capsys.readouterr().out)["runs"][0]["results"]

    def test_file_validate_sarif(
        self, jobs: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([str(jobs / "JUNK.jcl"), "--validate", "--sarif"]) == 1
        result = json.loads(capsys.readouterr().out)["runs"][0]["results"][0]
        assert result["ruleId"] == "JCL-GEN-000"
        assert main([str(jobs / "CLEAN.jcl"), "--validate", "--sarif"]) == 0
