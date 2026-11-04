"""Issues #172 (unused PROC symbolics, IEFC657I) and #173 (IMS MSG regions)."""

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl
from jclparser.program_profiles import analyze_step

pytestmark = pytest.mark.unit

_PROC = """//J1       JOB (A),'X',CLASS=A
//MYP      PROC PROG=,LIB='A.SRC'
//         SET Q=1
//C1       EXEC PGM=IGYCRCTL,PARM='&Q'
//SYSIN    DD DSN=&LIB(&PROG),DISP=SHR
//         PEND
"""


def _messages(src: str) -> list[str]:
    return [e.message for e in validate_jcl(src) if "IEFC657I" in e.message]


class TestUnusedProcSymbols:
    def test_unused_symbolics_are_reported(self):
        src = _PROC + "//S1       EXEC MYP,MEMBER=PAYROLL,PLIB='X.Y'\n"
        tail = (
            " is not used by procedure 'MYP' (IEFC657I); the procedure's defaults apply"
        )
        assert _messages(src) == [
            f"Step 'S1': symbol MEMBER{tail}",
            f"Step 'S1': symbol PLIB{tail}",
        ]
        exploded = explode_job(parse_jcl(src))
        assert exploded.warnings == [
            "EXEC S1: symbol(s) MEMBER, PLIB not used by PROC MYP (IEFC657I); its "
            + "defaults apply"
        ]

    def test_declared_referenced_and_keyword_overrides_pass(self):
        src = (
            _PROC
            + "//S1       EXEC MYP,PROG=PAY,LIB='B.SRC',Q=2,PARM.C1=X,"
            + "COND=(4,LT)\n"
            + "//S2       EXEC PROC=MYP,PROG=X,REGION.C1=4M\n"
        )
        assert _messages(src) == []
        assert not [w for w in explode_job(parse_jcl(src)).warnings if "IEFC657I" in w]

    def test_symbol_used_only_in_a_dd_or_condition_counts(self):
        src = """//J1       JOB (A),'X',CLASS=A
//MYP      PROC
//C1       EXEC PGM=IEFBR14
//         IF (C1.RC = &RCX) THEN
//C2       EXEC PGM=IEFBR14
//OUT      DD DSN=&&TMP,UNIT=&U
//         ENDIF
//         PEND
//S1       EXEC MYP,U=SYSDA,RCX=0
"""
        assert _messages(src) == []

    def test_escaped_ampersand_is_not_a_reference(self):
        src = """//J1       JOB (A),'X',CLASS=A
//MYP      PROC
//C1       EXEC PGM=IEFBR14
//OUT      DD DSN=&&TMP,DISP=(NEW,PASS)
//         PEND
//S1       EXEC MYP,TMP=X
"""
        assert len(_messages(src)) == 1


class TestImsMessageRegion:
    def _analysis(self, parm: str):
        job = parse_jcl(f"//J JOB 1\n//S EXEC PGM=DFSRRC00,PARM='{parm}'\n")
        return analyze_step(job.steps[0])

    def test_msg_region_names_no_program(self):
        a = self._analysis("MSG,001002003004,0000,,,,,,,IMS1")
        assert a.summary == "IMS MSG region (DFSRRC00), classes 001 002 003 004"
        assert not any("application program:" in n for n in a.notes)
        assert not any(n.startswith("PSB") for n in a.notes)
        assert "transaction classes: 001 002 003 004" in a.notes

    def test_ifp_region_names_no_program(self):
        a = self._analysis("IFP,ABC,0")
        assert a.summary == "IMS IFP region (DFSRRC00)"
        assert not any("application program:" in n for n in a.notes)

    @pytest.mark.parametrize("region", ["BMP", "DLI", "DBB"])
    def test_batch_regions_keep_program_and_psb(self, region):
        a = self._analysis(f"{region},MYPROG,MYPSB")
        assert a.summary == f"IMS {region} step running MYPROG"
        assert "PSB: MYPSB" in a.notes

    def test_bundled_dfsmpr(self):
        job = explode_job(parse_jcl("//J JOB 1\n//S EXEC DFSMPR\n"))
        a = analyze_step(job.steps[0])
        assert a.summary == "IMS MSG region (DFSRRC00), classes 001 000 000 000"
