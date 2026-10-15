"""Regression tests for issue #107.

Lint rules JCL-LINT-001/002/003 and ``compute_metrics`` iterated
``step.dd_statements`` only, so on an unexploded job the ``//PROCSTEP.DD``
overrides of a PROC call were invisible to them.
"""

from __future__ import annotations

import pytest

from jclparser import explode_job, parse_jcl
from jclparser.lint import LintConfig, lint_job
from jclparser.metrics import compute_metrics

pytestmark = pytest.mark.unit

_LINT_JOB = """//J JOB
//MYPROC PROC
//S1 EXEC PGM=X
//OUT DD DUMMY
// PEND
//STEP1 EXEC MYPROC
//S1.OUT DD DSN=PROD.MASTER.Y,DISP=(NEW,CATLG,DELETE),UNIT=SYSDA
"""

_METRICS_JOB = """//J JOB
//MYPROC PROC
//PS1 EXEC PGM=X
//IN DD DUMMY
//OUT DD DUMMY
// PEND
//STEP1 EXEC MYPROC
//PS1.IN DD DSN=PROD.X,DISP=SHR
//PS1.OUT DD DSN=PROD.Y,DISP=(NEW,CATLG)
"""

_CFG = LintConfig(
    critical_dataset_patterns=["PROD.MASTER"],
    enabled={"JCL-LINT-001", "JCL-LINT-002", "JCL-LINT-003"},
)


def _codes(job) -> set[str]:
    return {f.error_code for f in lint_job(job, _CFG) if f.line_number == 7}


def test_lint_sees_override_dds_on_unexploded_job():
    assert _codes(parse_jcl(_LINT_JOB)) == {
        "JCL-LINT-001",
        "JCL-LINT-002",
        "JCL-LINT-003",
    }


def test_lint_unexploded_matches_exploded():
    assert _codes(parse_jcl(_LINT_JOB)) == _codes(explode_job(parse_jcl(_LINT_JOB)))


def test_metrics_count_override_dds_on_unexploded_job():
    m = compute_metrics(parse_jcl(_METRICS_JOB))
    assert (m.unique_datasets, m.dataset_fanin, m.dataset_fanout, m.dd_count) == (
        2,
        1,
        1,
        2,
    )


def test_metrics_unexploded_matches_exploded():
    def key(m):
        return (m.unique_datasets, m.dataset_fanin, m.dataset_fanout, m.dd_count)

    exploded = compute_metrics(explode_job(parse_jcl(_METRICS_JOB)))
    assert key(compute_metrics(parse_jcl(_METRICS_JOB))) == key(exploded)
