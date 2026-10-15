"""Regression test for issue #99.

``job.steps`` is ``list[Step | ConditionalBlock]``; the flat view the backend
contract now points at, ``iter_execution_steps``, is exported from
``jclparser`` together with ``ConditionalBlock``.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl

pytestmark = pytest.mark.unit


def test_iter_execution_steps_reexported_for_contract():
    import jclparser
    from jclparser import ConditionalBlock, iter_execution_steps

    job = parse_jcl(
        "//J JOB\n//S1 EXEC PGM=EXTRACT\n// IF (S1.RC = 0) THEN\n"
        "//S2 EXEC PGM=LOAD\n// ENDIF\n"
    )
    assert any(isinstance(s, ConditionalBlock) for s in job.steps)
    assert [s.name for s in iter_execution_steps(job.steps)] == ["S1", "S2"]
    assert [s.name for s in iter_execution_steps(job.explode().steps)] == [
        "S1",
        "S2",
    ]
    assert {"ConditionalBlock", "iter_execution_steps"} <= set(jclparser.__all__)
