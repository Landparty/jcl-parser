"""Round-5 regressions: SET redefinition scope, unnamed DDs after an
unqualified PROC DD override, and DFSRRC00 with a parenthesised PARM."""

import pytest

from jclparser import parse_jcl
from jclparser.explosion import explode_job
from jclparser.program_profiles import analyze_step


def _dsns(step):
    return [(dd.name, dd.dataset_name) for dd in step.dd_statements]


@pytest.mark.unit
class TestSetRedefinition:
    JCL = (
        "//J        JOB 1\n"
        "// SET A=ONE\n"
        "//P        PROC\n"
        "//PS       EXEC PGM=Y\n"
        "//D        DD DSN=P.&A,DISP=SHR\n"
        "// PEND\n"
        "//S1       EXEC PGM=X,PARM='&A'\n"
        "//D        DD DSN=HLQ.&A,DISP=SHR\n"
        "//S2       EXEC P\n"
        "// IF RC = 0 THEN\n"
        "//S3       EXEC PGM=&A\n"
        "// ENDIF\n"
        "// SET A=TWO\n"
        "//S4       EXEC PGM=X\n"
        "//D        DD DSN=HLQ.&A,DISP=SHR\n"
        "//S5       EXEC P\n"
    )

    def test_parse_uses_value_in_effect_at_each_step(self):
        job = parse_jcl(self.JCL)
        s1, _s2, cond, s4, _s5 = job.steps
        assert _dsns(s1) == [("D", "HLQ.ONE")]
        assert s1.parameters["PARM"] == "ONE"
        assert cond.then_steps[0].program == "ONE"
        assert _dsns(s4) == [("D", "HLQ.TWO")]
        assert job.set_statements == {"A": "TWO"}

    def test_explosion_uses_value_in_effect_at_each_proc_call(self):
        exploded = explode_job(parse_jcl(self.JCL))
        by_name = {s.name: s for s in exploded.steps if hasattr(s, "name")}
        assert _dsns(by_name["S2.PS"]) == [("D", "P.ONE")]
        assert _dsns(by_name["S5.PS"]) == [("D", "P.TWO")]
        assert _dsns(by_name["S1"]) == [("D", "HLQ.ONE")]

    def test_no_snapshot_without_redefinition(self):
        job = parse_jcl(
            "//J        JOB 1\n"
            "// SET A=ONE\n"
            "//S1       EXEC PGM=X\n"
            "//D        DD DSN=HLQ.&A..&B,DISP=SHR\n"
            "// SET B=LATE\n"
            "//S2       EXEC PGM=X\n"
        )
        assert all(s.set_symbols is None for s in job.steps)
        # A forward reference still falls back to the final table.
        assert _dsns(job.steps[0]) == [("D", "HLQ.ONE.LATE")]

    def test_forward_reference_still_resolves_after_redefinition(self):
        job = parse_jcl(
            "//J        JOB 1\n"
            "// SET A=ONE\n"
            "//S1       EXEC PGM=X\n"
            "//D        DD DSN=HLQ.&A..&B,DISP=SHR\n"
            "// SET A=TWO,B=LATE\n"
        )
        assert _dsns(job.steps[0]) == [("D", "HLQ.ONE.LATE")]


@pytest.mark.unit
class TestUnqualifiedOverrideConcatenation:
    PROC = (
        "//J        JOB 1\n"
        "//P        PROC\n"
        "//S1       EXEC PGM=X\n"
        "//LIB      DD DSN=A1,DISP=SHR\n"
        "//         DD DSN=A2,DISP=SHR\n"
        "//OUT      DD SYSOUT=*\n"
        "// PEND\n"
        "//R1       EXEC P\n"
    )

    def _exploded_first_step(self, overrides):
        return explode_job(parse_jcl(self.PROC + overrides)).steps[0]

    def test_unnamed_dd_overrides_second_member(self):
        step = self._exploded_first_step("//LIB      DD DSN=B1\n//         DD DSN=B2\n")
        assert _dsns(step) == [("LIB", "B1"), ("", "B2"), ("OUT", None)]
        # Merge semantics: the member keeps the PROC member's DISP.
        assert step.dd_statements[1].parameters["DISP"] == "SHR"

    def test_empty_member_override_keeps_member_and_extra_is_added(self):
        step = self._exploded_first_step(
            "//LIB      DD DSN=B1\n//         DD\n//         DD DSN=B3,DISP=SHR\n"
        )
        assert _dsns(step) == [
            ("LIB", "B1"),
            ("", "A2"),
            ("", "B3"),
            ("OUT", None),
        ]

    def test_added_dd_keeps_its_own_concatenation(self):
        step = self._exploded_first_step(
            "//NEW      DD DSN=N1,DISP=SHR\n//         DD DSN=N2,DISP=SHR\n"
        )
        assert _dsns(step) == [
            ("LIB", "A1"),
            ("", "A2"),
            ("OUT", None),
            ("NEW", "N1"),
            ("", "N2"),
        ]


@pytest.mark.unit
class TestDfsrrc00ParenthesisedParm:
    @pytest.mark.parametrize(
        "parm",
        ["(BMP,MYPROG,MYPSB)", "'BMP,MYPROG,MYPSB'", "(BMP,'MYPROG',MYPSB,,,N)"],
    )
    def test_program_and_psb_extracted(self, parm):
        job = parse_jcl(f"//J        JOB 1\n//S1       EXEC PGM=DFSRRC00,PARM={parm}\n")
        analysis = analyze_step(job.steps[0])
        assert analysis.summary == "IMS BMP step running MYPROG"
        assert "PSB: MYPSB" in analysis.notes

    def test_exploded_symbolic_parm_list(self):
        job = parse_jcl(
            "//J        JOB 1\n"
            "//IMSB     PROC MBR=,PSB=\n"
            "//G        EXEC PGM=DFSRRC00,PARM=(DLI,&MBR,&PSB)\n"
            "// PEND\n"
            "//S1       EXEC IMSB,MBR=APP1,PSB=PSB1\n"
        )
        analysis = analyze_step(explode_job(job).steps[0])
        assert analysis.summary == "IMS DLI step running APP1"
        assert "PSB: PSB1" in analysis.notes
