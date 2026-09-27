"""Parenthesised symbol values substitute as JCL, not as Python reprs.

The tokenizer stores ``DP=(NEW,CATLG)`` as ``["NEW", "CATLG"]``; symbol
resolution used ``str()`` on it, so ``DISP=&DP`` exploded to
``"['NEW', 'CATLG']"``. ``// SET A=(1,2)`` and ``// SET *`` crashed the parse
with ``TypeError``.
"""

import pytest

from jclparser import parse_jcl
from jclparser.model import iter_execution_steps
from jclparser.utils import jcl_value_text

JCL = (
    "//J        JOB (A),'B'\n"
    "//P        PROC SP=(CYL,(1,1)),DP=(NEW,CATLG),S=NEW\n"
    "//S        EXEC PGM=X\n"
    "//D        DD DSN=A.B,SPACE=&SP,DISP=&DP\n"
    "//E        DD DSN=A.&S,DISP=(&S,PASS)\n"
    "//F        DD DSN=A.C,UNIT=SYSDA,VOL=SER=V&DP\n"
    "//         PEND\n"
    "//R        EXEC P\n"
    "//R2       EXEC P,DP=(OLD,KEEP)\n"
)


def _dds(job):
    return {
        (s.name, d.name): d
        for s in iter_execution_steps(job.steps)
        for d in s.dd_statements
    }


@pytest.mark.unit
class TestListSymbolValues:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (["NEW", "CATLG"], "(NEW,CATLG)"),
            (["TRK", "(1,1)"], "(TRK,(1,1))"),
            (["A", ["B", "C"]], "(A,(B,C))"),
            ("SHR", "SHR"),
            (True, ""),
        ],
    )
    def test_jcl_value_text(self, value, expected):
        assert jcl_value_text(value) == expected

    def test_whole_value_symbol_keeps_list_form(self):
        dds = _dds(parse_jcl(JCL).explode())
        dd = dds[("R.S", "D")]
        assert dd.disposition == ["NEW", "CATLG"]
        assert dd.parameters["DISP"] == ["NEW", "CATLG"]
        assert dd.parameters["SPACE"] == ["CYL", "(1,1)"]
        assert dd.space.subparameters["_unit"] == "CYL"
        assert dd.is_output()

    def test_exec_override_list_value(self):
        dd = _dds(parse_jcl(JCL).explode())[("R2.S", "D")]
        assert dd.disposition == ["OLD", "KEEP"]
        assert dd.is_input()

    def test_symbol_inside_list_still_substituted(self):
        dd = _dds(parse_jcl(JCL).explode())[("R.S", "E")]
        assert dd.disposition == ["NEW", "PASS"]
        assert dd.dataset_name == "A.NEW"

    def test_embedded_list_symbol_is_jcl_text(self):
        dd = _dds(parse_jcl(JCL).explode())[("R.S", "F")]
        assert "['" not in str(dd.parameters)
        assert "(NEW,CATLG)" in str(dd.parameters["VOL"])

    @pytest.mark.parametrize(
        ("stmt", "sets", "warned"),
        [
            ("// SET A=(1,2)", {"A": "(1,2)"}, False),
            ("// SET *", {}, True),
            ("// SET A", {}, True),
            ("// SET A=1,B", {"A": "1"}, True),
        ],
    )
    def test_set_statement_forms(self, stmt, sets, warned):
        job = parse_jcl(f"//J JOB\n{stmt}\n//S EXEC PGM=X\n")
        assert job.set_statements == sets
        assert any("is not SYMBOL=value" in w for w in job.warnings) is warned
