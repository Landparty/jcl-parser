"""``&&NAME`` temporary datasets survive PROC explosion.

``substitute_dd_statement`` collapsed ``&&`` to ``&`` in the dataset name, so
after ``explode()`` every ``DSN=&&TEMP`` read ``&TEMP`` and
``is_temporary()`` was False.
"""

import pytest

from jclparser import parse_jcl
from jclparser.model import iter_execution_steps

JCL = (
    "//J        JOB (ACCT),'T'\n"
    "//P        PROC SFX=A\n"
    "//S        EXEC PGM=X,PARM='A&&B'\n"
    "//D        DD DSN=&&TEMP&SFX,DISP=(NEW,PASS)\n"
    "//E        DD DSNAME=&&T2,DISP=(NEW,PASS)\n"
    "//         PEND\n"
    "//R        EXEC P\n"
    "//S2       EXEC PGM=Y\n"
    "//D        DD DSN=&&TEMP2,DISP=(OLD,DELETE)\n"
)


@pytest.fixture
def steps():
    job = parse_jcl(JCL).explode()
    return {s.name: s for s in iter_execution_steps(job.steps)}


@pytest.mark.unit
class TestTempDatasetExplosion:
    def test_proc_dd_keeps_double_ampersand(self, steps):
        dd = steps["R.S"].dd_statements[0]
        assert dd.dataset_name == "&&TEMPA"
        assert dd.parameters["DSN"] == "&&TEMPA"
        assert dd.is_temporary()

    def test_dsname_parameter_keeps_double_ampersand(self, steps):
        dd = steps["R.S"].dd_statements[1]
        assert dd.dataset_name == "&&T2"
        assert dd.parameters["DSNAME"] == "&&T2"
        assert dd.is_temporary()

    def test_plain_step_dd_keeps_double_ampersand(self, steps):
        dd = steps["S2"].dd_statements[0]
        assert dd.dataset_name == "&&TEMP2"
        assert dd.is_temporary()

    def test_parm_still_collapses_escaped_ampersand(self, steps):
        assert steps["R.S"].parameters["PARM"] == "A&B"


# A temporary dataset name passed as a symbolic value on an ``EXEC procname``
# coded *inside* another procedure: the nested call's values were substituted
# with "&&" collapsed to "&" (a top-level call keeps them), so the inner DD
# read ``&TMP2.`` -- a single ampersand plus a stray trailing period.
NESTED_JCL = (
    "//J        JOB (ACCT),'T'\n"
    "//INNER    PROC TT=\n"
    "//QS1      EXEC PGM=B\n"
    "//T2       DD DSN=&TT,DISP=(NEW,PASS)\n"
    "//T3       DD DSN=&TT..A,DISP=(NEW,PASS)\n"
    "//         PEND\n"
    "//OUTER    PROC\n"
    "//PS1      EXEC INNER,TT='&&TMP2',PARM.QS1='A&&B'\n"
    "//         PEND\n"
    "//S1       EXEC OUTER\n"
    "//S2       EXEC INNER,TT='&&TMP2'\n"
)


@pytest.fixture
def nested_steps():
    job = parse_jcl(NESTED_JCL).explode()
    return {s.name: s for s in iter_execution_steps(job.steps)}


@pytest.mark.unit
class TestNestedProcTempDatasetValue:
    def test_nested_call_value_keeps_double_ampersand(self, nested_steps):
        dd = nested_steps["S1.PS1.QS1"].dd_statements[0]
        assert dd.dataset_name == "&&TMP2"
        assert dd.parameters["DSN"] == "&&TMP2"
        assert dd.is_temporary()

    def test_nested_call_value_with_suffix(self, nested_steps):
        dd = nested_steps["S1.PS1.QS1"].dd_statements[1]
        assert dd.dataset_name == "&&TMP2.A"

    def test_nested_matches_top_level_call(self, nested_steps):
        nested = nested_steps["S1.PS1.QS1"].dd_statements
        top = nested_steps["S2.QS1"].dd_statements
        assert [d.dataset_name for d in nested] == [d.dataset_name for d in top]

    def test_nested_exec_override_still_collapses(self, nested_steps):
        assert nested_steps["S1.PS1.QS1"].parameters["PARM"] == "A&B"

    def test_nested_call_uses_set_value_in_effect_at_each_step(self):
        jcl = NESTED_JCL.replace(
            "//PS1      EXEC INNER,TT='&&TMP2',PARM.QS1='A&&B'\n",
            "//         SET TT='&&TMP2',ARG=A\n"
            "//PS1      EXEC INNER,TT=&TT,PARM.QS1='&ARG&&B'\n"
            "//         SET TT='&&TMP3',ARG=C\n"
            "//PS2      EXEC INNER,TT=&TT,PARM.QS1='&ARG&&D'\n",
        )
        job = parse_jcl(jcl).explode()
        steps = {s.name: s for s in iter_execution_steps(job.steps)}

        for name, dataset, parm in (
            ("S1.PS1.QS1", "&&TMP2", "A&B"),
            ("S1.PS2.QS1", "&&TMP3", "C&D"),
        ):
            step = steps[name]
            assert step.parameters["PARM"] == parm
            assert [dd.dataset_name for dd in step.dd_statements] == [
                dataset,
                f"{dataset}.A",
            ]
            assert all(dd.is_temporary() for dd in step.dd_statements)
