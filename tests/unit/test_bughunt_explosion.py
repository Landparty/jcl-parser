"""Regression tests for PROC explosion / SET / INCLUDE symbol bugs."""

from __future__ import annotations

from pathlib import Path

import pytest

from jclparser import DictMemberLoader, explode_job, parse_jcl
from jclparser.model import Step, iter_execution_steps
from jclparser.proc_loader import DictProcedureLoader

pytestmark = pytest.mark.unit


def _steps(job) -> dict[str, Step]:
    return {s.name: s for s in iter_execution_steps(job.steps)}


def _dd(job, step: str, dd: str):
    return next(d for d in _steps(job)[step].dd_statements if d.name == dd)


@pytest.fixture
def proclib(tmp_path: Path) -> Path:
    lib = tmp_path / "MY.PROCLIB"
    lib.mkdir()
    (lib / "OUTER.jcl").write_text(
        "//OUTER PROC\n//PS1 EXEC INNER\n//PS2 EXEC PGM=OPGM\n// PEND\n"
    )
    (lib / "INNER.jcl").write_text("//INNER PROC\n//IS1 EXEC PGM=IPGM\n// PEND\n")
    return tmp_path


class TestExplodeUsesJobProcLoader:
    def test_external_proc_nested_in_external_proc(self, proclib: Path) -> None:
        job = parse_jcl(
            "//J JOB\n//LIBS JCLLIB ORDER=MY.PROCLIB\n//S1 EXEC OUTER\n",
            proc_base_path=proclib,
        )
        steps = _steps(explode_job(job))
        assert steps["S1.PS1.IS1"].program == "IPGM"
        assert steps["S1.PS2"].program == "OPGM"

    def test_external_proc_called_inside_if_is_preloaded(self, proclib: Path) -> None:
        job = parse_jcl(
            "//J JOB\n//LIBS JCLLIB ORDER=MY.PROCLIB\n//S0 EXEC PGM=IEFBR14\n"
            "// IF S0.RC = 0 THEN\n//S1 EXEC INNER\n// ENDIF\n",
            proc_base_path=proclib,
        )
        assert job.get_procedure("INNER") is not None
        assert _steps(explode_job(job))["S1.IS1"].program == "IPGM"


class TestSetInsideProc:
    def test_set_in_cataloged_proc_applies_on_expansion(self) -> None:
        loader = DictProcedureLoader(
            {
                "EXT": (
                    "//EXT PROC\n// SET Q=INPROC\n//E1 EXEC PGM=Z\n"
                    "//D1 DD DSN=&Q..X,DISP=SHR\n// PEND\n"
                )
            }
        )
        job = explode_job(parse_jcl("//J JOB\n//S1 EXEC EXT\n"), proc_loader=loader)
        assert _dd(job, "S1.E1", "D1").dataset_name == "INPROC.X"

    def test_set_in_uncalled_instream_proc_does_not_leak(self) -> None:
        jcl = (
            "//J JOB\n// SET LIB=JOB.LIB\n//P PROC\n// SET LIB=PROC.LIB\n"
            "//PS1 EXEC PGM=X\n//D1 DD DSN=&LIB,DISP=SHR\n// PEND\n"
            "//S0 EXEC PGM=Y\n//D1 DD DSN=&LIB,DISP=SHR\n//S1 EXEC P\n"
        )
        job = parse_jcl(jcl)
        assert job.set_statements == {"LIB": "JOB.LIB"}
        assert job.get_procedure("P").set_statements == {"LIB": "PROC.LIB"}
        assert _dd(job, "S0", "D1").dataset_name == "JOB.LIB"
        exploded = explode_job(job)
        assert _dd(exploded, "S0", "D1").dataset_name == "JOB.LIB"
        # Inside the procedure its own SET is in effect.
        assert _dd(exploded, "S1.PS1", "D1").dataset_name == "PROC.LIB"

    # A SET inside a PROC takes effect from where it is coded, as at job
    # level: a step coded before a later SET redefined a symbol still sees
    # the earlier value. Every PROC step used to see the last value.
    PROC_BODY = (
        "// SET A=ONE\n"
        "//PS1 EXEC PGM=X,PARM='&A'\n//D1 DD DSN=&A..DATA,DISP=SHR\n"
        "// SET A=TWO\n"
        "//PS2 EXEC PGM=Y,PARM='&A'\n//D1 DD DSN=&A..DATA,DISP=SHR\n"
    )
    PROC_SET_REDEFINED = "//J JOB\n//P PROC\n" + PROC_BODY + "// PEND\n//S1 EXEC P\n"

    def test_set_redefined_inside_proc_applies_from_that_point(self) -> None:
        exploded = explode_job(parse_jcl(self.PROC_SET_REDEFINED))
        steps = _steps(exploded)
        assert steps["S1.PS1"].parameters["PARM"] == "ONE"
        assert _dd(exploded, "S1.PS1", "D1").dataset_name == "ONE.DATA"
        assert steps["S1.PS2"].parameters["PARM"] == "TWO"
        assert _dd(exploded, "S1.PS2", "D1").dataset_name == "TWO.DATA"

    def test_set_redefined_inside_cataloged_proc(self) -> None:
        loader = DictProcedureLoader(
            {"EXT": "//EXT PROC\n" + self.PROC_BODY + "// PEND\n"}
        )
        job = explode_job(parse_jcl("//J JOB\n//S1 EXEC EXT\n"), proc_loader=loader)
        assert _dd(job, "S1.PS1", "D1").dataset_name == "ONE.DATA"
        assert _dd(job, "S1.PS2", "D1").dataset_name == "TWO.DATA"
        assert _steps(job)["S1.PS1"].parameters["PARM"] == "ONE"


def test_symbols_in_exec_overrides_of_proc_call_are_substituted() -> None:
    jcl = (
        "//J JOB\n// SET RC=4\n//P PROC\n//PS1 EXEC PGM=X\n//PS2 EXEC PGM=Z\n"
        "// PEND\n//S1 EXEC P,PARM.PS1='&SYSUID',COND.PS2=(&RC,LT)\n"
    )
    steps = _steps(explode_job(parse_jcl(jcl)))
    assert "&" not in steps["S1.PS1"].parameters["PARM"]
    assert steps["S1.PS1"].parameters["PARM"]
    assert "&RC" not in str(steps["S1.PS2"].parameters["COND"])
    assert "4" in str(steps["S1.PS2"].parameters["COND"])


def test_undefined_bare_symbol_dsn_is_kept_as_temp_dataset() -> None:
    jcl = (
        "//J JOB\n//P PROC\n//PS1 EXEC PGM=X\n"
        "//D1 DD DSN=&TEMP,DISP=(NEW,PASS),UNIT=SYSDA\n// PEND\n"
        "//S0 EXEC PGM=Y\n//D1 DD DSN=&TEMP,DISP=(NEW,PASS)\n//S1 EXEC P\n"
    )
    job = parse_jcl(jcl)
    assert _dd(job, "S0", "D1").dataset_name == "&TEMP"
    exploded = explode_job(job)
    for step in ("S0", "S1.PS1"):
        dd = _dd(exploded, step, "D1")
        assert dd.dataset_name == "&TEMP"
        assert dd.parameters["DSN"] == "&TEMP"
    assert not any("TEMP" in w for w in exploded.warnings)


def test_include_member_name_resolves_set_symbol() -> None:
    loader = DictMemberLoader({"MEMA": "//INC1 EXEC PGM=INCPGM\n"})
    job = parse_jcl(
        "//J JOB\n// SET M=MEMA\n// INCLUDE MEMBER=&M\n//S2 EXEC PGM=Y\n",
        include_loader=loader,
    )
    assert [s.program for s in job.steps] == ["INCPGM", "Y"]
    assert job.includes == ["MEMA"]


class TestUndefinedDdParameterAndRlstmout:
    def test_undefined_symbol_in_dd_parameter_warns(self) -> None:
        jcl = (
            "//J JOB\n//P PROC\n//PS1 EXEC PGM=X\n"
            "//D1 DD DSN=A.B,DISP=SHR,UNIT=&NOPE2\n// PEND\n//S1 EXEC P\n"
        )
        job = explode_job(parse_jcl(jcl))
        assert any("&NOPE2" in w and "DD D1" in w for w in job.warnings)

    def test_rlstmout_override_is_applied(self) -> None:
        jcl = "//J JOB\n//P PROC\n//PS1 EXEC PGM=X\n// PEND\n//S1 EXEC P,RLSTMOUT.PS1=10\n"
        step = _steps(explode_job(parse_jcl(jcl)))["S1.PS1"]
        assert step.parameters["RLSTMOUT"] == "10"
