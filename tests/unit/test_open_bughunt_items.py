"""Regression tests for the findings still open in the 2026-11 bug-hunt reports.

Pass 26 (a missing INCLUDE member passed validation), pass 27 (temporary
datasets through a PROC call: overrides, symbols, deletes, double calls),
AUDIT L1 (a quoted positional holding ``=``), the pass-2 validation gaps
(program and symbol names, SPACE unit, unknown keywords, PGM with PROC),
PROC parameters lost after a ``<===`` comment, and JCL-LINT-001 on system
or placeholder high-level qualifiers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jclparser import lint_job, parse_jcl, validate_jcl
from jclparser.errors import ErrorSeverity
from jclparser.lint.config import LintConfigError, lint_config_from_mapping

pytestmark = pytest.mark.unit


def _findings(source: str, **kwargs: object) -> list[tuple[str, str]]:
    return [
        (e.severity.value, e.message)
        for e in validate_jcl(source, level="semantic", **kwargs)  # type: ignore[arg-type]
    ]


def _messages(source: str, **kwargs: object) -> list[str]:
    return [m for _, m in _findings(source, **kwargs)]


# ---------------------------------------------------------------------------
# Pass 26: missing INCLUDE member
# ---------------------------------------------------------------------------


class TestMissingInclude:
    SOURCE = "//J  JOB 1\n// INCLUDE MEMBER=NONE\n//S  EXEC PGM=X\n"

    def test_reported_as_warning(self, tmp_path: Path) -> None:
        (tmp_path / "SYS1.PROCLIB").mkdir()
        errors = validate_jcl(self.SOURCE, level="structure", proc_base_path=tmp_path)
        assert [(e.severity, e.line_number) for e in errors] == [
            (ErrorSeverity.WARNING, 2)
        ]
        assert "INCLUDE member NONE not found" in errors[0].message

    def test_basic_level_reports_only_errors(self) -> None:
        assert validate_jcl(self.SOURCE, level="basic") == []

    def test_still_on_job_warnings(self) -> None:
        job = parse_jcl(self.SOURCE)
        assert any("INCLUDE member NONE" in w for w in job.warnings)

    def test_unresolved_symbol_member_reported(self) -> None:
        messages = _messages("//J  JOB 1\n// INCLUDE MEMBER=&M\n//S  EXEC PGM=X\n")
        assert any("uses a symbol with no SET value" in m for m in messages)


# ---------------------------------------------------------------------------
# Pass 27: temporaries through a PROC call (checked on the exploded job)
# ---------------------------------------------------------------------------

_PROC = (
    "//J    JOB 1\n"
    "//P    PROC{parms}\n"
    "//PS   EXEC PGM=X\n"
    "//O    DD DSN={dsn},DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
    "{more}"
    "//     PEND\n"
)


class TestProcTemporaries:
    def test_override_renaming_dataset_is_not_deleted(self) -> None:
        source = _PROC.format(parms="", dsn="&&A", more="") + (
            "//R    EXEC P\n"
            "//PS.O DD DSN=&&B\n"
            "//S2   EXEC PGM=Y\n"
            "//I    DD DSN=&&B,DISP=(OLD,DELETE)\n"
        )
        assert _messages(source) == []

    def test_symbolic_temporary_name_substituted(self) -> None:
        source = _PROC.format(parms=" T=LOAD", dsn="&&&T", more="") + (
            "//R    EXEC P,T=GOSET\n"
            "//S2   EXEC PGM=Y\n"
            "//I    DD DSN=&&GOSET,DISP=(OLD,DELETE)\n"
        )
        assert _messages(source) == []

    def test_temporary_deleted_inside_proc_then_read(self) -> None:
        more = "//PS2  EXEC PGM=X\n//O    DD DSN=&&A,DISP=(OLD,DELETE)\n"
        source = _PROC.format(parms="", dsn="&&A", more=more) + (
            "//R    EXEC P\n//S2   EXEC PGM=Y\n//I    DD DSN=&&A,DISP=(OLD,DELETE)\n"
        )
        messages = _messages(source)
        assert any(
            "&&A is read in step S2 after step R.PS2 deleted it" in m for m in messages
        )

    def test_same_proc_called_twice_creates_temporary_twice(self) -> None:
        source = _PROC.format(parms="", dsn="&&A", more="") + (
            "//R1   EXEC P\n//R2   EXEC P\n"
        )
        assert (
            "Temporary dataset &&A created in multiple steps: R1.PS and R2.PS"
            in _messages(source)
        )

    def test_unavailable_proc_falls_back_without_false_findings(self) -> None:
        source = (
            "//J    JOB 1\n"
            "//R    EXEC NOSUCH\n"
            "//S2   EXEC PGM=Y\n"
            "//I    DD DSN=&&GOSET,DISP=(OLD,DELETE)\n"
        )
        assert not any("never created" in m for m in _messages(source))

    def test_external_proc_findings_use_the_call_line(self, tmp_path: Path) -> None:
        lib = tmp_path / "SYS1.PROCLIB"
        lib.mkdir()
        (lib / "EXTP.jcl").write_text(
            "//EXTP PROC\n"
            "//PS   EXEC PGM=X\n"
            "//O    DD DSN=&&A,DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
        )
        source = "//J    JOB 1\n//R1   EXEC EXTP\n//R2   EXEC EXTP\n"
        errors = validate_jcl(source, level="structure", proc_base_path=tmp_path)
        duplicate = [e for e in errors if "created in multiple steps" in e.message]
        assert [e.line_number for e in duplicate] == [3]

    def test_gdg_created_in_proc_via_override(self) -> None:
        source = (
            "//J    JOB 1\n"
            "//P    PROC\n"
            "//PS   EXEC PGM=X\n"
            "//O    DD DSN=A.G(+1),DISP=(NEW,CATLG),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//     PEND\n"
            "//R    EXEC P\n"
            "//PS.O DD DSN=B.G(+1)\n"
            "//S2   EXEC PGM=Y\n"
            "//I    DD DSN=B.G(+1),DISP=SHR\n"
        )
        assert not any("no earlier step" in m for m in _messages(source))


# ---------------------------------------------------------------------------
# AUDIT L1: quoted positional holding "="
# ---------------------------------------------------------------------------


class TestQuotedEquals:
    def test_job_programmer_name_with_equals(self) -> None:
        job = parse_jcl("//J JOB (ACCT),'X=Y',CLASS=A\n//S EXEC PGM=X\n")
        assert job.parameters["_pos_1"] == "X=Y"
        assert job.parameters["CLASS"] == "A"
        assert "'X" not in job.parameters

    def test_parenthesised_positional_with_equals(self) -> None:
        job = parse_jcl("//J JOB (A=B),'N'\n//S EXEC PGM=X\n")
        assert not any("=" in key for key in job.parameters)

    def test_keyword_values_unchanged(self) -> None:
        job = parse_jcl("//J JOB 1\n//S EXEC PGM=X,PARM='A=B',COND=(4,LT)\n")
        assert job.steps[0].parameters["PARM"] == "A=B"


# ---------------------------------------------------------------------------
# Pass 2 validation gaps
# ---------------------------------------------------------------------------


class TestOperandChecks:
    def test_program_name_too_long(self) -> None:
        findings = _findings("//J JOB 1\n//S EXEC PGM=ABCDEFGHI\n")
        assert findings and findings[0][0] == "error"
        assert "not a valid program name" in findings[0][1]

    @pytest.mark.parametrize("pgm", ["IEFBR14", "*.S1.SYSLMOD", "&PGM", "$PGM#1"])
    def test_valid_program_names(self, pgm: str) -> None:
        source = f"//J JOB 1\n//S1 EXEC PGM=IEFBR14\n//S EXEC PGM={pgm}\n"
        assert not any("program name" in m for m in _messages(source))

    def test_set_symbol_name_too_long(self) -> None:
        findings = _findings("//J JOB 1\n// SET ABCDEFGHI=1\n//S EXEC PGM=A\n")
        assert ("error", findings[0][1]) == findings[0]
        assert "SET symbol name 'ABCDEFGHI'" in findings[0][1]

    def test_proc_symbol_name_too_long(self) -> None:
        source = (
            "//J JOB 1\n//P PROC ABCDEFGHI=1\n//PS EXEC PGM=A\n// PEND\n//S EXEC P\n"
        )
        assert any("PROC symbol name 'ABCDEFGHI'" in m for m in _messages(source))

    def test_bad_space_unit(self) -> None:
        source = (
            "//J JOB 1\n//S EXEC PGM=A\n"
            "//D DD DSN=A.B,DISP=(NEW,CATLG),SPACE=(FOO,(1,1)),UNIT=SYSDA\n"
        )
        assert (
            "error",
            "SPACE unit 'FOO' on DD D must be TRK, CYL or a block / record length",
        ) in _findings(source)

    @pytest.mark.parametrize(
        "space",
        ["(TRK,1)", "(CYL,(1,1))", "(800,(10,5))", "(ABSTR,(5,1))", "(&U,1)", "TRK"],
    )
    def test_valid_space_units(self, space: str) -> None:
        source = (
            "//J JOB 1\n//S EXEC PGM=A\n"
            f"//D DD DSN=A.B,DISP=(NEW,CATLG),SPACE={space},UNIT=SYSDA\n"
        )
        assert not any("SPACE unit" in m for m in _messages(source))

    def test_unknown_dd_keyword(self) -> None:
        source = "//J JOB 1\n//S EXEC PGM=A\n//D DD DSN=A.B,DISP=SHR,FOOBAR=1\n"
        assert _findings(source) == [
            (
                "warning",
                (
                    "FOOBAR is not a DD statement keyword (DD D); z/OS rejects "
                    "it (IEFC630I)"
                ),
            )
        ]

    def test_unknown_keyword_on_override(self) -> None:
        source = (
            "//J JOB 1\n//P PROC\n//PS EXEC PGM=A\n//O DD DUMMY\n// PEND\n"
            "//S EXEC P\n//PS.O DD DSN=A.B,DISP=SHR,FOOBAR=1\n"
        )
        assert any(
            "FOOBAR is not a DD statement keyword" in m for m in _messages(source)
        )

    def test_unknown_exec_keyword(self) -> None:
        assert _findings("//J JOB 1\n//S EXEC PGM=A,FOOBAR=1\n") == [
            (
                "warning",
                (
                    "FOOBAR is not an EXEC statement keyword (step S); z/OS "
                    "rejects it (IEFC630I)"
                ),
            )
        ]

    def test_proc_call_symbols_are_not_unknown_keywords(self) -> None:
        source = (
            "//J JOB 1\n//P PROC FOOBAR=1\n//PS EXEC PGM=A,PARM=&FOOBAR\n// PEND\n"
            "//S EXEC P,FOOBAR=2\n"
        )
        assert not any("statement keyword" in m for m in _messages(source))

    def test_positional_operands_are_not_keywords(self) -> None:
        source = (
            "//J JOB 1\n//S EXEC PGM=A\n//D DD *\nDATA\n/*\n//E DD DUMMY\n"
            "//F DD DSN=A.B,DISP=SHR,DCB=(RECFM=FB,LRECL=80)\n"
        )
        assert not any("statement keyword" in m for m in _messages(source))

    def test_pgm_and_proc(self) -> None:
        assert _findings("//J JOB 1\n//S EXEC PGM=A,PROC=B\n") == [
            (
                "error",
                (
                    "Step S codes both PGM= and PROC=; an EXEC statement names "
                    "either a program or a procedure"
                ),
            )
        ]


# ---------------------------------------------------------------------------
# PROC parameters after a "<===" comment
# ---------------------------------------------------------------------------


class TestArrowComments:
    def test_proc_parameters_kept(self) -> None:
        job = parse_jcl(
            "//J JOB 1\n"
            "//P PROC A=1,      <=== FIRST\n"
            "//      B=2         <=== SECOND\n"
            "//PS EXEC PGM=X\n// PEND\n"
        )
        assert job.procedures[0].parameters == {"A": "1", "B": "2"}

    def test_exec_proc_call_overrides_kept(self) -> None:
        job = parse_jcl(
            "//J JOB 1\n//P PROC A=1,B=2\n//PS EXEC PGM=X\n// PEND\n"
            "//S EXEC P,A=3,      <=== FIRST\n"
            "//      B=4\n"
        )
        assert job.steps[0].parameters == {"A": "3", "B": "4"}

    def test_blank_inside_operands_still_resumes(self) -> None:
        job = parse_jcl(
            "//J JOB 1\n//P PROC A=1,B=2\n//PS EXEC PGM=X\n// PEND\n"
            "//S EXEC P,A=3,   B=4\n"
        )
        assert job.steps[0].parameters == {"A": "3", "B": "4"}


# ---------------------------------------------------------------------------
# JCL-LINT-001 on system / placeholder HLQs
# ---------------------------------------------------------------------------


def _lint001(source: str, config: object = None) -> list[str]:
    job = parse_jcl(source)
    return [
        e.message
        for e in lint_job(job, config)  # type: ignore[arg-type]
        if e.error_code == "JCL-LINT-001"
    ]


class TestLiteralHlqRule:
    SOURCE = (
        "//J JOB 1\n//S EXEC PGM=A\n"
        "//A DD DSN=SYS1.MACLIB,DISP=SHR\n"
        "//B DD DSN=IGY.V6R4M0.SIGYCOMP,DISP=SHR\n"
        "//C DD DSN=DSNC10.SDSNLOAD,DISP=SHR\n"
        "//D DD DSN=<HLQ>.LOAD,DISP=SHR\n"
        "//E DD DSN=PROD.MASTER,DISP=SHR\n"
    )

    def test_system_and_placeholder_hlqs_skipped(self) -> None:
        messages = _lint001(self.SOURCE)
        assert len(messages) == 1
        assert "PROD.MASTER" in messages[0]

    def test_system_hlqs_configurable(self) -> None:
        config = lint_config_from_mapping({"system-hlqs": ["PROD"]})
        messages = _lint001(self.SOURCE, config)
        assert not any("PROD.MASTER" in m for m in messages)
        assert any("SYS1.MACLIB" in m for m in messages)

    def test_system_hlqs_must_be_strings(self) -> None:
        with pytest.raises(LintConfigError, match="system-hlqs"):
            lint_config_from_mapping({"system-hlqs": "SYS1"})


# ---------------------------------------------------------------------------
# Pass 28: a stray NUL does not make valid JCL "Not a JCL file"
# ---------------------------------------------------------------------------


class TestNulBytes:
    JOB = "//J JOB 1\n//S EXEC PGM=X\n//IN DD *\nA\n/*\n"

    def test_trailing_nul_padding_is_jcl(self) -> None:
        assert validate_jcl(self.JOB + "\x00" * 50) == []

    def test_nul_in_instream_data_is_jcl(self) -> None:
        assert validate_jcl(self.JOB.replace("\nA\n", "\nA\x00B\n")) == []

    def test_nul_in_first_record_is_binary(self) -> None:
        errors = validate_jcl("\x00\x01//J JOB 1\n//S EXEC PGM=X\n")
        assert [e.message for e in errors] == [
            "Not a JCL file: binary content (NUL bytes)"
        ]

    def test_mostly_control_characters_is_binary(self) -> None:
        noise = "".join(chr(i % 32) for i in range(2000))
        errors = validate_jcl(self.JOB + noise)
        assert [e.message for e in errors] == [
            "Not a JCL file: binary content (NUL bytes)"
        ]
