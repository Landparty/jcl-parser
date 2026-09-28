"""compute_metrics counts datasets, not backward references or NULLFILE."""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.metrics import compute_metrics

pytestmark = pytest.mark.unit


def test_backward_reference_counts_as_the_referenced_dataset():
    job = parse_jcl(
        "//J        JOB 1\n"
        "//S1       EXEC PGM=A\n"
        "//OUT      DD DSN=A.B.C,DISP=(NEW,CATLG),SPACE=(TRK,1)\n"
        "//S2       EXEC PGM=B\n"
        "//IN       DD DSN=*.S1.OUT,DISP=SHR\n"
        "//NUL      DD DSN=NULLFILE\n"
    )
    m = compute_metrics(job)
    assert m.unique_datasets == 1
    assert m.dataset_fanin == 1
    assert m.dataset_fanout == 1
    assert m.dd_count == 3


def test_same_step_and_unresolved_backward_references():
    job = parse_jcl(
        "//J        JOB 1\n"
        "//S1       EXEC PGM=A\n"
        "//A        DD DSN=X.Y,DISP=SHR\n"
        "//B        DD DSN=*.A,DISP=SHR\n"
        "//C        DD DSN=*.NOSTEP.NODD,DISP=SHR\n"
    )
    m = compute_metrics(job)
    assert m.unique_datasets == 1
    assert m.dataset_fanin == 1


def test_proc_step_backward_reference_in_exploded_job():
    job = parse_jcl(
        "//J        JOB 1\n"
        "//P        PROC\n"
        "//A        EXEC PGM=A\n"
        "//O        DD DSN=X.Y,DISP=(NEW,CATLG),SPACE=(TRK,1)\n"
        "//B        EXEC PGM=B\n"
        "//I        DD DSN=*.A.O,DISP=SHR\n"
        "//         PEND\n"
        "//S1       EXEC P\n"
        "//S2       EXEC PGM=C\n"
        "//I        DD DSN=*.S1.A.O,DISP=SHR\n"
    ).explode()
    m = compute_metrics(job)
    assert m.unique_datasets == 1
    assert m.dataset_fanin == 1
