"""EXEC keyword overrides on an ``EXEC procname`` statement reach the PROC steps.

``PARM.procstep=``, ``COND.procstep=`` etc. override one step; an unqualified
``PARM=`` goes to the first step and nullifies PARM on the rest; any other
unqualified keyword overrides every step; an empty value nullifies.
"""

import pytest

from jclparser import parse_jcl
from jclparser.explosion import apply_exec_parameter_overrides
from jclparser.model import Step, iter_execution_steps

PROC = (
    "//J        JOB (ACCT),'T'\n"
    "//P        PROC\n"
    "//A        EXEC PGM=PA,PARM='ORIGA',REGION=4M\n"
    "//B        EXEC PGM=PB,PARMDD=PARMS,COND=(4,LT)\n"
    "//         PEND\n"
)


def _steps(call: str):
    job = parse_jcl(PROC + call).explode()
    return {s.name: s for s in iter_execution_steps(job.steps)}, job


@pytest.mark.unit
class TestExecParameterOverrides:
    def test_qualified_overrides_target_one_step(self):
        steps, _ = _steps("//S1       EXEC P,PARM.B='NEWB',REGION.A=8M,COND.B=(8,LT)\n")
        assert steps["S1.A"].parameters == {"PARM": "ORIGA", "REGION": "8M"}
        assert steps["S1.B"].parameters["PARM"] == "NEWB"
        assert "PARMDD" not in steps["S1.B"].parameters
        assert steps["S1.B"].parameters["COND"] == ["8", "LT"]

    def test_unqualified_parm_goes_to_first_step_only(self):
        steps, _ = _steps("//S1       EXEC P,PARM='ALL'\n")
        assert steps["S1.A"].parameters["PARM"] == "ALL"
        assert "PARM" not in steps["S1.B"].parameters
        assert "PARMDD" not in steps["S1.B"].parameters

    def test_unqualified_keyword_overrides_every_step(self):
        steps, _ = _steps("//S1       EXEC P,COND=EVEN,TIME=5\n")
        for name in ("S1.A", "S1.B"):
            assert steps[name].parameters["COND"] == "EVEN"
            assert steps[name].parameters["TIME"] == "5"

    def test_empty_value_nullifies(self):
        steps, _ = _steps("//S1       EXEC P,PARM.A=,COND.B=\n")
        assert "PARM" not in steps["S1.A"].parameters
        assert "COND" not in steps["S1.B"].parameters

    def test_unknown_procstep_warns(self):
        steps, job = _steps("//S1       EXEC P,PARM.ZZ=X\n")
        assert steps["S1.A"].parameters["PARM"] == "ORIGA"
        assert any("PARM.ZZ" in w for w in job.warnings)

    def test_symbolic_parameters_are_not_exec_keywords(self):
        jcl = (
            "//J        JOB (ACCT),'T'\n"
            "//P        PROC MBR=X\n"
            "//A        EXEC PGM=&MBR\n"
            "//         PEND\n"
            "//S1       EXEC P,MBR=REAL\n"
        )
        job = parse_jcl(jcl).explode()
        step = next(iter_execution_steps(job.steps))
        assert step.program == "REAL"
        assert "MBR" not in step.parameters

    def test_no_steps_is_a_noop(self):
        apply_exec_parameter_overrides([], {"PARM": "X"}, "S1")

    def test_applies_inside_conditional_block(self):
        jcl = (
            "//J        JOB (ACCT),'T'\n"
            "//P        PROC\n"
            "//         IF RC = 0 THEN\n"
            "//A        EXEC PGM=PA,PARM=OLD\n"
            "//         ENDIF\n"
            "//         PEND\n"
            "//S1       EXEC P,PARM.A=NEW\n"
        )
        job = parse_jcl(jcl).explode()
        step = next(iter_execution_steps(job.steps))
        assert isinstance(step, Step)
        assert step.parameters["PARM"] == "NEW"
