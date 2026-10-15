"""Regression tests for issue #126.

The keyword overrides and DDs coded under an ``EXEC procname`` statement
(``PARM.S1='&HLQ'``, ``//S1.IN DD DSN=&HLQ..OVR``) are merged into the
procedure, so their symbols now resolve in the called PROC's scope.  Before,
they were never substituted at explode time; and when the job had any
``// SET``, parse_jcl() blanked them first, so ``PARM.S1=`` nullified the
PROC's PARM and the DSN became ``.OVR``.
"""

from __future__ import annotations

import pytest

from jclparser import explode_job, parse_jcl
from jclparser.errors import UndefinedSymbolError

pytestmark = pytest.mark.unit

_PROC = """//P PROC HLQ=PROD
//S1 EXEC PGM=A,PARM=X
//IN DD DSN=&HLQ..IN,DISP=SHR
// PEND
"""


def _job(call: str, override: str, set_stmt: str = "") -> str:
    return "//J JOB\n" + set_stmt + _PROC + call + override


def _exploded_s1(src: str, **kwargs):
    job = explode_job(parse_jcl(src), **kwargs)
    (step,) = job.steps
    return step, job


@pytest.mark.parametrize("set_stmt", ["", "// SET ENV=PROD\n"])
def test_override_symbols_resolve_in_called_proc(set_stmt):
    src = _job(
        "//R EXEC P,HLQ=TEST,PARM.S1='&HLQ'\n",
        "//S1.IN DD DSN=&HLQ..OVR,DISP=SHR\n",
        set_stmt,
    )
    step, job = _exploded_s1(src)
    assert step.parameters["PARM"] == "TEST"
    assert step.get_dd("IN").dataset_name == "TEST.OVR"
    assert job.warnings == []


def test_proc_default_used_when_call_does_not_set_symbol():
    src = _job("//R EXEC P,PARM.S1='&HLQ'\n", "//S1.IN DD DSN=&HLQ..OVR,DISP=SHR\n")
    step, _ = _exploded_s1(src)
    assert step.parameters["PARM"] == "PROD"
    assert step.get_dd("IN").dataset_name == "PROD.OVR"


def test_proc_symbol_shadows_job_set_in_overrides():
    src = _job(
        "//R EXEC P,HLQ=TEST,PARM.S1='&HLQ'\n",
        "//S1.IN DD DSN=&HLQ..OVR,DISP=SHR\n",
        "// SET HLQ=JOBVAL\n",
    )
    step, _ = _exploded_s1(src)
    assert step.parameters["PARM"] == "TEST"
    assert step.get_dd("IN").dataset_name == "TEST.OVR"


def test_job_set_still_resolves_in_overrides_and_symbolic_values():
    src = _job(
        "//R EXEC P,HLQ=&ENV,PARM.S1='&ENV'\n",
        "//S1.IN DD DSN=&ENV..OVR,DISP=SHR\n",
        "// SET ENV=QA\n",
    )
    job = parse_jcl(src)
    call = job.steps[0]
    assert call.parameters == {"HLQ": "QA", "PARM.S1": "QA"}
    assert call.dd_overrides["S1.IN"].dataset_name == "QA.OVR"
    step, _ = _exploded_s1(src)
    assert step.parameters["PARM"] == "QA"
    assert step.get_dd("IN").dataset_name == "QA.OVR"


def test_parse_keeps_proc_symbols_in_overrides_unresolved():
    src = _job(
        "//R EXEC P,HLQ=TEST,PARM.S1='&HLQ'\n",
        "//S1.IN DD DSN=&HLQ..OVR,DISP=SHR\n",
        "// SET HLQ=JOBVAL\n",
    )
    job = parse_jcl(src)
    call = job.steps[0]
    assert call.parameters["PARM.S1"] == "&HLQ"
    assert call.dd_overrides["S1.IN"].dataset_name == "&HLQ..OVR"
    assert job.warnings == []


def test_undefined_symbol_is_kept_not_blanked_and_does_not_nullify():
    src = _job(
        "//R EXEC P,PARM.S1='&NOPE'\n",
        "//S1.IN DD DSN=&NOPE..OVR,DISP=SHR\n",
        "// SET ENV=PROD\n",
    )
    step, job = _exploded_s1(src)
    assert step.parameters["PARM"] == "&NOPE"
    assert step.get_dd("IN").dataset_name == "&NOPE..OVR"
    assert any("&NOPE" in w and "left as written" in w for w in job.warnings)


def test_undefined_symbol_in_override_raises_with_strict_symbols():
    src = _job("//R EXEC P,PARM.S1='&NOPE'\n", "")
    with pytest.raises(UndefinedSymbolError):
        explode_job(parse_jcl(src), strict_symbols=True)


def test_coded_empty_override_still_nullifies():
    step, _ = _exploded_s1(_job("//R EXEC P,PARM.S1=\n", ""))
    assert "PARM" not in step.parameters


def test_added_dd_resolves_in_called_proc():
    src = _job("//R EXEC P,HLQ=TEST\n", "//S1.NEW DD DSN=&HLQ..NEW,DISP=SHR\n")
    step, _ = _exploded_s1(src)
    assert step.get_dd("NEW").dataset_name == "TEST.NEW"


def test_temporary_dataset_in_override_kept():
    src = _job("//R EXEC P\n", "//S1.IN DD DSN=&&TEMP,DISP=(OLD,DELETE)\n")
    step, _ = _exploded_s1(src)
    assert step.get_dd("IN").dataset_name == "&&TEMP"
