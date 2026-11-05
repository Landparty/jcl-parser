"""Issue #176: a symbolic used only in an overriding/added DD is used."""

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl

pytestmark = pytest.mark.unit

_PROC = """//J1 JOB 1
//MYP  PROC HLQ=A
//PS1  EXEC PGM=IEFBR14
//DD1  DD DSN=&HLQ..X,DISP=SHR
//     PEND
"""


def _messages(src: str) -> list[str]:
    return [e.message for e in validate_jcl(src) if "IEFC657I" in e.message]


@pytest.mark.parametrize(
    "call",
    [
        "//S1   EXEC MYP,HLQ=B,ENV=T\n//PS1.DD2 DD DSN=&ENV..Y,DISP=SHR\n",
        "//S1   EXEC MYP,HLQ=B,ENV=T\n//PS1.DD1 DD DSN=&ENV..Y,DISP=SHR\n",
        "//S1   EXEC MYP,HLQ=B,ENV=T\n//PS1.DD1 DD DSN=A.B,DISP=SHR\n"
        "//     DD DSN=&ENV..Z,DISP=SHR\n",
        "//S1   EXEC MYP,HLQ=B,ENV=T,PARM.PS1='&ENV'\n",
    ],
)
def test_symbol_used_in_call_overrides_is_not_reported(call: str) -> None:
    src = _PROC + call
    assert _messages(src) == []
    assert not any("IEFC657I" in w for w in explode_job(parse_jcl(src)).warnings)


def test_override_dd_symbol_is_substituted() -> None:
    src = _PROC + "//S1   EXEC MYP,HLQ=B,ENV=T\n//PS1.DD2 DD DSN=&ENV..Y,DISP=SHR\n"
    exploded = explode_job(parse_jcl(src))
    dsns = [d.parameters.get("DSN") for s in exploded.steps for d in s.dd_statements]
    assert "T.Y" in dsns


def test_symbol_unused_anywhere_is_still_reported() -> None:
    src = _PROC + "//S2   EXEC MYP,HLQ=B,LIB=Z\n//PS1.DD2 DD DSN=&HLQ..Y,DISP=SHR\n"
    assert _messages(src) == [
        "Step 'S2': symbol LIB is not used by procedure 'MYP' (IEFC657I); "
        "the procedure's defaults apply"
    ]
