"""Step references inside a PROC are qualified when the PROC is exploded.

Inside a procedure, ``IF (PS1.RC = 0)`` and ``COND=(4,LT,PS1)`` name the
procedure's own step. After explosion that step is ``CALLER.PS1``; the
unqualified reference matched no step, so RC analysis could not evaluate it
and two expansions of the same PROC were indistinguishable.
"""

import pytest

from jclparser import parse_jcl
from jclparser.condition_parser import AndCondition, ReturnCodeCondition
from jclparser.explosion import _qualify_cond_parameter
from jclparser.model import ConditionalBlock

JCL = (
    "//J        JOB (A),'B'\n"
    "//P        PROC\n"
    "//PS1      EXEC PGM=A\n"
    "//         IF (PS1.RC = 0 & S0.RC = 0) THEN\n"
    "//PS2      EXEC PGM=B\n"
    "//         ENDIF\n"
    "//PS3      EXEC PGM=C,COND=(4,LT,PS1)\n"
    "//PS4      EXEC PGM=C,COND=((4,LT,PS1),(8,EQ),EVEN)\n"
    "//         PEND\n"
    "//S0       EXEC PGM=Z\n"
    "//S1       EXEC P\n"
    "//S2       EXEC P\n"
)


def _items(job):
    return [
        (i.condition_ast if isinstance(i, ConditionalBlock) else i) for i in job.steps
    ]


@pytest.mark.unit
class TestProcStepRefQualification:
    def test_if_condition_refs_are_qualified_per_expansion(self):
        job = parse_jcl(JCL).explode()
        asts = [i for i in _items(job) if isinstance(i, AndCondition)]
        assert [a.left.step_name for a in asts] == ["S1.PS1", "S2.PS1"]
        # A reference to a job step is left alone.
        assert [a.right.step_name for a in asts] == ["S0", "S0"]

    def test_proc_definition_ast_is_not_mutated(self):
        job = parse_jcl(JCL)
        job.explode()
        block = job.procedures[0].steps[1]
        assert block.condition_ast.left == ReturnCodeCondition("PS1", "EQ", 0)

    def test_cond_parameter_refs_are_qualified(self):
        steps = {
            s.name: s for s in parse_jcl(JCL).explode().steps if hasattr(s, "name")
        }
        assert steps["S1.PS3"].parameters["COND"] == ["4", "LT", "S1.PS1"]
        assert steps["S2.PS4"].parameters["COND"] == [
            "(4,LT,S2.PS1)",
            "(8,EQ)",
            "EVEN",
        ]

    def test_rc_evaluation_uses_qualified_step(self):
        job = parse_jcl(JCL).explode()
        ast = next(i for i in _items(job) if isinstance(i, AndCondition))
        results = {"S0": (0, False), "S1.PS1": (8, False)}
        assert ast.evaluate(results) is False

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("EVEN", "EVEN"),
            (["4", "LT"], ["4", "LT"]),
            (["4", "LT", "OTHER"], ["4", "LT", "OTHER"]),
            (["4", "LT", "PS1.INNER"], ["4", "LT", "X.PS1.INNER"]),
            (["(4,LT)", "(8,EQ)", "(12,GT)"], ["(4,LT)", "(8,EQ)", "(12,GT)"]),
        ],
    )
    def test_cond_parameter_forms(self, value, expected):
        assert _qualify_cond_parameter(value, frozenset({"PS1"}), "X") == expected
