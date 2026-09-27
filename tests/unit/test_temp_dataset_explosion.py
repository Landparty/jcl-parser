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
