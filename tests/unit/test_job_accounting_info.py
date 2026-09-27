"""JOB accounting information keeps its nested parentheses.

``_create_job_from_statement`` used ``str.strip("()")``, which removes *every*
leading and trailing parenthesis, so ``(1234,(A,B))`` became ``1234,(A,B``.
"""

import pytest

from jclparser import parse_jcl
from jclparser._model_factories import _strip_enclosing_parens


def _acct(operand: str) -> str | None:
    return parse_jcl(f"//MYJOB JOB {operand},'N'\n//S EXEC PGM=X\n").accounting_info


@pytest.mark.unit
class TestJobAccountingInfo:
    @pytest.mark.parametrize(
        ("operand", "expected"),
        [
            ("(1234,(A,B))", "1234,(A,B)"),
            ("((A,B),C)", "(A,B),C"),
            ("(ACCT)", "ACCT"),
            ("1234", "1234"),
            ("(1234,'X(1)')", "1234,'X(1)'"),
            ("(1234,')')", "1234,')'"),
        ],
    )
    def test_only_the_enclosing_pair_is_removed(self, operand, expected):
        assert _acct(operand) == expected

    def test_programmer_name_stays_in_parameters(self):
        job = parse_jcl("//MYJOB JOB (A,(B)),'O''BRIEN'\n//S EXEC PGM=X\n")
        assert job.accounting_info == "A,(B)"
        assert job.parameters["_pos_1"] == "O'BRIEN"

    @pytest.mark.parametrize("value", ["(A),(B)", "(A", "A)", "", "()"])
    def test_non_enclosing_values_unchanged(self, value):
        expected = "" if value == "()" else value
        assert _strip_enclosing_parens(value) == expected
