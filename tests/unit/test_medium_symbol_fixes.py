"""Regression tests for symbol-handling fixes (#127, #121, #128)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl
from jclparser._statement_parser import _extract_jcllib_order
from jclparser.errors import ProcedureNotFoundError
from jclparser.explosion import (
    SymbolScope,
    _dsn_keep_undefined,
    substitute_dd_statement,
)
from jclparser.model import DDStatement

pytestmark = pytest.mark.unit


def _parms(job) -> dict[str, str | None]:
    return {s.name: s.parameters.get("PARM") for s in job.steps}


class TestDoubleAmpersandInSymbolValues:
    """#127: ``&&`` inside a symbol value collapses like a literal ``&&``."""

    @staticmethod
    def _job(value: str):
        src = (
            "//J JOB\n"
            f"// SET X='{value}'\n"
            f"//P PROC Y='{value}'\n"
            "//PS1 EXEC PGM=A,PARM='&X'\n"
            "//PS2 EXEC PGM=A,PARM='&Y'\n"
            f"//PS3 EXEC PGM=A,PARM='{value}'\n"
            "//PS4 EXEC PGM=A,PARM='&X.C'\n"
            "// PEND\n"
            "//PLAIN EXEC PGM=A,PARM='&X'\n"
            "//R EXEC P\n"
        )
        return explode_job(parse_jcl(src))

    def test_collapses_in_proc_and_plain_steps(self) -> None:
        parms = _parms(self._job("A&&B"))
        assert parms["PLAIN"] == "A&B"
        assert parms["R.PS1"] == "A&B"
        assert parms["R.PS2"] == "A&B"
        assert parms["R.PS3"] == "A&B"
        assert parms["R.PS4"] == "A&BC"

    def test_collapses_exactly_once(self) -> None:
        parms = _parms(self._job("A&&&&B"))
        assert parms["PLAIN"] == "A&&B"
        assert parms["R.PS1"] == "A&&B"
        assert parms["R.PS2"] == "A&&B"
        assert parms["R.PS3"] == "A&&B"
        assert parms["R.PS4"] == "A&&BC"

    def test_exec_override_and_nested_symbolic_value(self) -> None:
        src = (
            "//J JOB\n"
            "// SET X='A&&B'\n"
            "//P PROC\n//PS1 EXEC PGM=A\n//PS2 EXEC PGM=A\n// PEND\n"
            "//I PROC TT='&&TMP2'\n//IS1 EXEC PGM=A\n"
            "//D DD DSN=&TT,DISP=(NEW,PASS)\n// PEND\n"
            "//O PROC\n//OS1 EXEC I,TT='&&TMP2'\n// PEND\n"
            "//R EXEC P,PARM.PS1='&X',PARM.PS2='A&&B'\n"
            "//R2 EXEC O\n"
        )
        job = explode_job(parse_jcl(src))
        parms = _parms(job)
        # A keyword override collapses && whether coded or from a symbol...
        assert parms["R.PS1"] == parms["R.PS2"] == "A&B"
        # ...while a nested EXEC procname's symbolic value keeps it.
        inner = next(s for s in job.steps if s.name == "R2.OS1.IS1")
        assert inner.dd_statements[0].dataset_name == "&&TMP2"
        assert not job.warnings

    def test_dsn_double_ampersand_untouched(self) -> None:
        src = (
            "//J JOB\n"
            "// SET X='A&&B'\n"
            "//P PROC T='&&TMP',U='A&&B'\n"
            "//PS1 EXEC PGM=A\n"
            "//D1 DD DSN=&&TEMP,DISP=(NEW,PASS)\n"
            "//D2 DD DSN=&T,DISP=(NEW,PASS)\n"
            "//D3 DD DSN=&U..X,DISP=SHR\n"
            "//D4 DD DSN=&X..Y,DISP=SHR\n"
            "// PEND\n"
            "//R EXEC P\n"
        )
        step = explode_job(parse_jcl(src)).steps[0]
        dsns = {d.name: d.dataset_name for d in step.dd_statements}
        assert dsns == {
            "D1": "&&TEMP",
            "D2": "&&TMP",
            "D3": "A&&B.X",
            "D4": "A&&B.Y",
        }
        assert step.get_dd("D1").is_temporary()
        assert step.get_dd("D2").is_temporary()


class TestParenthesisedDsn:
    """#121: ``DSN=(A.B)`` with a SET in the job no longer crashes."""

    @pytest.mark.parametrize("keyword", ["DSN", "DSNAME"])
    @pytest.mark.parametrize("set_line", ["// SET HLQ=PROD\n", ""])
    def test_dataset_name_is_text(self, keyword: str, set_line: str) -> None:
        src = (
            "//J1 JOB (A),'X'\n"
            f"{set_line}"
            "//S1 EXEC PGM=X\n"
            f"//DD1 DD {keyword}=(A.B),DISP=SHR\n"
        )
        job = parse_jcl(src)
        dd = job.steps[0].dd_statements[0]
        assert dd.dataset_name == "(A.B)"
        assert dd.parameters[keyword] == ["A.B"]
        assert explode_job(job).steps[0].dd_statements[0].dataset_name == "(A.B)"
        errors = validate_jcl(src)
        assert any("Invalid dataset name '(A.B)'" in e.message for e in errors)

    def test_symbol_inside_parenthesised_dsn_resolves(self) -> None:
        src = (
            "//J1 JOB (A),'X'\n"
            "// SET HLQ=PROD\n"
            "//S1 EXEC PGM=X\n"
            "//DD1 DD DSN=(&HLQ..X),DISP=SHR\n"
        )
        dd = parse_jcl(src).steps[0].dd_statements[0]
        assert dd.dataset_name == "(PROD.X)"

    def test_list_dataset_name_left_alone_by_substitution(self) -> None:
        dd = DDStatement(name="DD1", dataset_name=["&HLQ"])  # type: ignore[arg-type]
        scope = SymbolScope(set_symbols={"HLQ": "PROD"})
        substitute_dd_statement(dd, scope)
        assert dd.dataset_name == ["&HLQ"]

    def test_dsn_keep_undefined_ignores_non_text(self) -> None:
        def keep(name: str) -> bool:
            return False

        assert _dsn_keep_undefined(["&T"], keep, strict=False) is keep  # type: ignore[arg-type]
        kept = _dsn_keep_undefined("&T", None, strict=False)
        assert kept is not None and kept("T")


_OUTER = "//OUTER PROC\n//S1 EXEC PGM=IEFBR14\n// PEND\n"


@pytest.fixture
def proc_base(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    (base / "MY.PROCLIB").mkdir(parents=True)
    (base / "MY.PROCLIB" / "OUTER.jcl").write_text(_OUTER)
    # A library outside the base directory that must never be reached.
    (tmp_path / "OUT").mkdir()
    (tmp_path / "OUT" / "OUTER.jcl").write_text(_OUTER)
    return base


class TestJcllibOrderSymbols:
    """#128: SET symbols in effect at JCLLIB are resolved in ORDER."""

    def test_set_symbol_resolved_and_proc_found(self, proc_base: Path) -> None:
        src = (
            "//J JOB\n// SET LIB=MY.PROCLIB\n//L JCLLIB ORDER=(&LIB)\n//R EXEC OUTER\n"
        )
        job = parse_jcl(src, proc_base_path=proc_base)
        assert job.jcllib_order == ["MY.PROCLIB"]
        assert not job.warnings
        assert [s.name for s in explode_job(job).steps] == ["R.S1"]

    def test_period_delimiter(self, proc_base: Path) -> None:
        src = "//J JOB\n// SET HLQ=MY\n//L JCLLIB ORDER=&HLQ..PROCLIB\n//R EXEC OUTER\n"
        job = parse_jcl(src, proc_base_path=proc_base)
        assert job.jcllib_order == ["MY.PROCLIB"]
        assert [s.name for s in explode_job(job).steps] == ["R.S1"]

    def test_system_symbol_left_with_warning(self, proc_base: Path) -> None:
        src = (
            "//J JOB\n// SET HLQ=MY\n"
            "//L JCLLIB ORDER=(&HLQ..PROCLIB,&SYSUID..PROCLIB)\n//R EXEC OUTER\n"
        )
        job = parse_jcl(src, proc_base_path=proc_base)
        assert job.jcllib_order == ["MY.PROCLIB", "&SYSUID..PROCLIB"]
        assert any("&SYSUID..PROCLIB" in w and "unresolved" in w for w in job.warnings)

    def test_set_after_jcllib_not_applied(self, proc_base: Path) -> None:
        src = "//J JOB\n//L JCLLIB ORDER=&LIB\n// SET LIB=MY.PROCLIB\n//R EXEC OUTER\n"
        job = parse_jcl(src, proc_base_path=proc_base)
        assert job.jcllib_order == ["&LIB"]
        assert any("JCLLIB ORDER library &LIB" in w for w in job.warnings)
        with pytest.raises(ProcedureNotFoundError):
            explode_job(job)

    def test_set_before_job_statement_applies(self, proc_base: Path) -> None:
        src = (
            "// SET LIB=MY.PROCLIB\n//L JCLLIB ORDER=(&LIB)\n//J JOB\n//R EXEC OUTER\n"
        )
        job = parse_jcl(src, proc_base_path=proc_base)
        assert job.jcllib_order == ["MY.PROCLIB"]

    def test_traversal_from_set_value_rejected(self, proc_base: Path) -> None:
        src = "//J JOB\n// SET LIB='../OUT'\n//L JCLLIB ORDER=(&LIB)\n//R EXEC OUTER\n"
        job = parse_jcl(src, proc_base_path=proc_base)
        assert job.jcllib_order == ["../OUT"]
        assert job.get_procedure("OUTER") is None
        with pytest.raises(ProcedureNotFoundError):
            explode_job(job)

    def test_prescan_substitutes_earlier_sets(self) -> None:
        src = (
            "//J JOB\n// SET LIB=MY.PROCLIB\n"
            "//L JCLLIB ORDER=(&LIB,'&LIB..Q',&SYSUID..X,&LATER)\n"
            "// SET LATER=NO\n"
        )
        assert _extract_jcllib_order(src) == [
            "MY.PROCLIB",
            "MY.PROCLIB.Q",
            "&SYSUID..X",
            "&LATER",
        ]

    def test_include_found_through_symbolic_jcllib(self, tmp_path: Path) -> None:
        lib = tmp_path / "MY.INCLIB"
        lib.mkdir()
        (lib / "COMMON.jcl").write_text("//S1 EXEC PGM=FROMINC\n")
        src = (
            "//J JOB\n// SET LIB=MY.INCLIB\n//L JCLLIB ORDER=(&LIB)\n"
            "// INCLUDE MEMBER=COMMON\n"
        )
        job = parse_jcl(src, proc_base_path=tmp_path)
        assert [s.program for s in job.steps] == ["FROMINC"]
