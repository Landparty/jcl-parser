"""Regression tests for symbol-handling fixes (#127, #121, #128)."""

from __future__ import annotations

import pytest

from jclparser import explode_job, parse_jcl

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
