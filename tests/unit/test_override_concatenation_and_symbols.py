"""DD overrides of concatenation members, and symbols in override DDs.

* An unnamed DD coded after a ``PROCSTEP.DDNAME`` override overrides the next
  member of that DD's concatenation (``//  DD`` with no operands leaves the
  member unchanged); it used to be appended after the PROC step's last DD.
* Override DDs are job-level JCL: SET and system symbols in them are resolved,
  and a qualified override coded inside a PROC gets that PROC's symbols.
"""

import pytest

from jclparser import parse_jcl
from jclparser.model import iter_execution_steps

PROC = (
    "//J        JOB (ACCT),'T'\n"
    "//P        PROC\n"
    "//PS       EXEC PGM=IEFBR14\n"
    "//IN       DD DSN=LIB.ONE,DISP=SHR\n"
    "//         DD DSN=LIB.TWO,DISP=SHR\n"
    "//         DD DSN=LIB.THREE,DISP=SHR\n"
    "//OUT      DD SYSOUT=*\n"
    "//         PEND\n"
    "//S1       EXEC P\n"
)


def _dd_list(jcl: str) -> list[tuple[str, str | None]]:
    job = parse_jcl(jcl).explode()
    step = next(iter_execution_steps(job.steps))
    return [(dd.name, dd.dataset_name) for dd in step.dd_statements]


@pytest.mark.unit
class TestConcatenationMemberOverride:
    def test_second_member_override_replaces_it_in_place(self):
        jcl = PROC + "//PS.IN    DD\n//         DD DSN=MY.TWO\n"
        assert _dd_list(jcl) == [
            ("IN", "LIB.ONE"),
            ("", "MY.TWO"),
            ("", "LIB.THREE"),
            ("OUT", None),
        ]

    def test_override_keeps_uncoded_member_parameters(self):
        jcl = PROC + "//PS.IN    DD\n//         DD DSN=MY.TWO\n"
        job = parse_jcl(jcl).explode()
        member = next(iter_execution_steps(job.steps)).dd_statements[1]
        assert member.disposition == "SHR"

    def test_extra_members_are_added_to_the_concatenation(self):
        jcl = (
            PROC + "//PS.IN    DD\n//         DD\n//         DD\n"
            "//         DD DSN=MY.FOUR,DISP=SHR\n"
        )
        assert _dd_list(jcl) == [
            ("IN", "LIB.ONE"),
            ("", "LIB.TWO"),
            ("", "LIB.THREE"),
            ("", "MY.FOUR"),
            ("OUT", None),
        ]

    def test_members_follow_an_added_dd(self):
        jcl = PROC + "//PS.NEW   DD DSN=A.ONE,DISP=SHR\n//         DD DSN=A.TWO\n"
        assert _dd_list(jcl)[-2:] == [("NEW", "A.ONE"), ("", "A.TWO")]

    def test_parse_records_members_under_the_override(self):
        job = parse_jcl(PROC + "//PS.IN    DD\n//         DD DSN=MY.TWO\n")
        step = job.steps[0]
        assert step.dd_statements == []
        members = step.dd_override_concatenations["PS.IN"]
        assert [dd.dataset_name for dd in members] == ["MY.TWO"]

    def test_named_dd_ends_the_concatenation_override(self):
        jcl = PROC + "//PS.IN    DD\n//EXTRA    DD DSN=X.Y\n//         DD DSN=X.Z\n"
        step = parse_jcl(jcl).steps[0]
        assert [dd.dataset_name for dd in step.dd_statements] == ["X.Y", "X.Z"]
        assert "PS.IN" not in step.dd_override_concatenations


@pytest.mark.unit
class TestSymbolsInOverrideDDs:
    def test_set_symbol_resolved_in_qualified_override(self):
        jcl = PROC.replace("//P        PROC\n", "//         SET HLQ=PROD\n//P PROC\n")
        jcl += "//PS.IN    DD DSN=&HLQ..DATA\n//PS.NEW   DD DSN=&HLQ..NEW\n"
        job = parse_jcl(jcl)
        assert job.steps[0].dd_overrides["PS.IN"].dataset_name == "PROD.DATA"
        names = dict(_dd_list(jcl))
        assert names["IN"] == "PROD.DATA"
        assert names["NEW"] == "PROD.NEW"

    def test_system_symbol_resolved_in_override_and_added_dd(self):
        jcl = PROC + "//PS.IN    DD DSN=&SYSUID..OVR\n//ADDED    DD DSN=&SYSUID..ADD\n"
        names = dict(_dd_list(jcl))
        assert names["IN"] == "TESTUSER.OVR"
        assert names["ADDED"] == "TESTUSER.ADD"

    def test_unknown_symbol_in_override_is_left_as_written(self):
        names = dict(_dd_list(PROC + "//PS.IN    DD DSN=&NOPE..X\n"))
        assert names["IN"] == "&NOPE..X"

    def test_nested_proc_override_uses_the_outer_procs_symbols(self):
        jcl = (
            "//J        JOB (ACCT),'T'\n"
            "//INNER    PROC\n"
            "//IS       EXEC PGM=IEFBR14\n"
            "//DD1      DD DSN=INNER.DATA,DISP=SHR\n"
            "//         PEND\n"
            "//OUTER    PROC HLQ=OUTER\n"
            "//OS       EXEC INNER\n"
            "//IS.DD1   DD DSN=&HLQ..OVR\n"
            "//         PEND\n"
            "//S1       EXEC OUTER\n"
        )
        assert _dd_list(jcl) == [("DD1", "OUTER.OVR")]
