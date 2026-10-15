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


def test_override_sees_proc_sets_in_effect_at_its_procstep():
    # Review of #137: the PROC's SETs as of the overridden procstep, not
    # the PROC's last SET of each symbol.
    src = """//J JOB
//MYPROC PROC
// SET X=FIRST
//S1 EXEC PGM=A,PARM='&X'
//IN DD DSN=&X..A,DISP=SHR
// SET X=SECOND
//S2 EXEC PGM=B
//OUT DD DSN=&X..B,DISP=SHR
// PEND
//C EXEC MYPROC,PARM.S1='&X',PARM.S2='&X'
//S1.IN DD DSN=&X..OVR,DISP=SHR
//S2.OUT DD DSN=&X..OVR,DISP=SHR
"""
    s1, s2 = explode_job(parse_jcl(src)).steps
    assert (s1.parameters["PARM"], s1.get_dd("IN").dataset_name) == (
        "FIRST",
        "FIRST.OVR",
    )
    assert (s2.parameters["PARM"], s2.get_dd("OUT").dataset_name) == (
        "SECOND",
        "SECOND.OVR",
    )


def test_proc_unknown_at_parse_time_keeps_symbols_for_explode():
    # Review of #137: with the PROC only known to explode_job's loader, a
    # job SET must not pre-empt the PROC's default at parse time.
    from jclparser import DictProcedureLoader

    src = "//J JOB\n// SET HLQ=JOBSET\n//C EXEC MYPROC\n//S1.IN DD DSN=&HLQ..OVR\n"
    loader = DictProcedureLoader(
        {"MYPROC": "//MYPROC PROC HLQ=PROD\n//S1 EXEC PGM=A\n//IN DD DSN=X\n// PEND\n"}
    )
    job = parse_jcl(src, enable_external_procs=False)
    assert job.steps[0].dd_overrides["S1.IN"].dataset_name == "&HLQ..OVR"
    (step,) = explode_job(job, proc_loader=loader).steps
    assert step.get_dd("IN").dataset_name == "PROD.OVR"


def test_nested_call_override_resolves_in_inner_proc_then_outer():
    # Review of #137: a call nested in a PROC resolves its overrides like a
    # job-level one, with the calling PROC's symbols as the fallback.
    src = """//J JOB
//INNER PROC Y=INNERVAL
//IS1 EXEC PGM=A,PARM=X
//DD1 DD DSN=INNER.DATA,DISP=SHR
// PEND
//OUTER PROC HLQ=OUTER
//OS EXEC INNER,PARM.IS1='&Y'
//IS1.DD1 DD DSN=&HLQ..&Y,DISP=SHR
// PEND
//S1 EXEC OUTER
"""
    exploded = explode_job(parse_jcl(src))
    (step,) = exploded.steps
    assert step.parameters["PARM"] == "INNERVAL"
    assert step.get_dd("DD1").dataset_name == "OUTER.INNERVAL"
    assert exploded.warnings == []


def test_nested_call_symbolic_value_still_from_outer_proc():
    src = """//J JOB
//INNER PROC Y=INNERVAL
//IS1 EXEC PGM=A,PARM='&Y'
// PEND
//OUTER PROC HLQ=OUTER
//OS EXEC INNER,Y=&HLQ
// PEND
//S1 EXEC OUTER
"""
    (step,) = explode_job(parse_jcl(src)).steps
    assert step.parameters["PARM"] == "OUTER"
