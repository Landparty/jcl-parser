"""The CLI prints parameters in JCL syntax, not as Python reprs.

``DISP=(,CATLG,DELETE)`` used to print as ``DISP=['', 'CATLG', 'DELETE']`` and
the JOB programmer-name operand as ``_pos_1=TEST``.
"""

import pytest

from jclparser.cli import _fmt_param, _fmt_value, main

JCL = (
    "//MYJOB    JOB (1234),'TEST',CLASS=A\n"
    "//S1       EXEC PGM=X,COND=((4,LT),(8,EQ))\n"
    "//OUT      DD DSN=A.B,DISP=(,CATLG,DELETE),SPACE=(TRK,(1,1))\n"
)


@pytest.mark.unit
class TestCliParamFormat:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (["", "CATLG", "DELETE"], "(,CATLG,DELETE)"),
            (["TRK", ["1", "1"]], "(TRK,(1,1))"),
            ("SHR", "SHR"),
        ],
    )
    def test_fmt_value(self, value, expected):
        assert _fmt_value(value) == expected

    @pytest.mark.parametrize(
        ("key", "value", "expected"),
        [
            ("_pos_1", "TEST", "TEST"),
            ("DISP", ["NEW", "PASS"], "DISP=(NEW,PASS)"),
            ("*", True, "*"),
            ("CLASS", "A", "CLASS=A"),
        ],
    )
    def test_fmt_param(self, key, value, expected):
        assert _fmt_param(key, value) == expected

    def test_cli_output_uses_jcl_syntax(self, tmp_path, capsys):
        path = tmp_path / "j.jcl"
        path.write_text(JCL)
        assert main([str(path)]) == 0
        assert main([str(path), "S1"]) == 0
        out = capsys.readouterr().out
        assert "Params: TEST, CLASS=A" in out
        assert "DISP=(,CATLG,DELETE)" in out
        assert "COND=((4,LT),(8,EQ))" in out
        assert "['" not in out
        assert "_pos_" not in out
