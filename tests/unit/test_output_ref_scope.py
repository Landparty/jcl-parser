"""#85: ``DD OUTPUT=*.name`` resolves by step scope, not by name alone."""

import pytest

from jclparser import OutputStatement, parse_jcl
from jclparser._post_parse import _extract_output_refs
from jclparser.validators import validate_output_references

ISSUE_JCL = """\
//J1   JOB (A),'X'
//OUT1 OUTPUT DEST=JOBLVL
//S1   EXEC PGM=A
//OUT1 OUTPUT DEST=RMT1
//D1   DD SYSOUT=A,OUTPUT=*.OUT1
//S2   EXEC PGM=B
//OUT1 OUTPUT DEST=RMT2
//D2   DD SYSOUT=A,OUTPUT=*.OUT1
//S3   EXEC PGM=C
//D3   DD SYSOUT=A,OUTPUT=*.OUT1
//D4   DD SYSOUT=A,OUTPUT=*.S1.OUT1
"""


def _dds(job):
    return {dd.name: dd for step in job.steps for dd in step.dd_statements}


@pytest.mark.unit
class TestOutputStatementScope:
    def test_step_name_recorded(self):
        job = parse_jcl(ISSUE_JCL)
        assert [(o.step_name, o.dest) for o in job.output_statements] == [
            (None, "JOBLVL"),
            ("S1", "RMT1"),
            ("S2", "RMT2"),
        ]
        assert all(o.procedure_name is None for o in job.output_statements)

    def test_backward_compatible_construction(self):
        out = OutputStatement("X", {"DEST": "A"}, 3)
        assert out.step_name is None
        assert out.procedure_name is None
        assert out.type == "OUTPUT"

    def test_instream_proc_output_scoped_to_proc_step(self):
        jcl = """\
//J    JOB 1
//P    PROC
//PS1  EXEC PGM=X
//POUT OUTPUT DEST=INPROC
//     PEND
//RUN  EXEC P
"""
        (out,) = parse_jcl(jcl).output_statements
        assert (out.procedure_name, out.step_name) == ("P", "PS1")


@pytest.mark.unit
class TestOutputRefResolution:
    @pytest.mark.parametrize(
        ("dd_name", "dest"),
        [("D1", "RMT1"), ("D2", "RMT2"), ("D3", "JOBLVL"), ("D4", "RMT1")],
    )
    def test_issue_table(self, dd_name, dest):
        job = parse_jcl(ISSUE_JCL)
        refs = _dds(job)[dd_name].output_refs
        assert [o.dest for o in refs] == [dest]
        assert job.unresolved_output_refs == []

    def test_other_steps_output_does_not_satisfy_star_name(self):
        jcl = """\
//J    JOB 1
//S1   EXEC PGM=A
//OUT2 OUTPUT DEST=RMT1
//S2   EXEC PGM=B
//D2   DD SYSOUT=A,OUTPUT=*.OUT2
"""
        job = parse_jcl(jcl)
        assert _dds(job)["D2"].output_refs == []
        assert job.unresolved_output_refs == [("S2", "OUT2", 5)]
        (warning,) = validate_output_references(job)
        assert "OUTPUT=*.OUT2 in step 'S2'" in warning.message
        assert warning.line_number == 5

    def test_qualified_ref_needs_that_steps_output(self):
        jcl = """\
//J    JOB 1
//OUT1 OUTPUT DEST=JOBLVL
//S1   EXEC PGM=A
//S2   EXEC PGM=B
//D2   DD SYSOUT=A,OUTPUT=(*.S1.OUT1,*.S9.OUT1)
"""
        job = parse_jcl(jcl)
        assert _dds(job)["D2"].output_refs == []
        assert job.unresolved_output_refs == [
            ("S2", "S1.OUT1", 5),
            ("S2", "S9.OUT1", 5),
        ]
        messages = [e.message for e in validate_output_references(job)]
        assert any("OUTPUT=*.S9.OUT1" in m for m in messages)

    def test_proc_body_output_not_seen_by_job_step(self):
        jcl = """\
//J    JOB 1
//P    PROC
//PS1  EXEC PGM=X
//OUT1 OUTPUT DEST=INPROC
//     PEND
//PS1  EXEC PGM=Y
//D1   DD SYSOUT=A,OUTPUT=*.OUT1
//D2   DD SYSOUT=A,OUTPUT=*.PS1.OUT1
"""
        job = parse_jcl(jcl)
        assert _dds(job)["D1"].output_refs == []
        assert _dds(job)["D2"].output_refs == []
        assert [r[1] for r in job.unresolved_output_refs] == ["OUT1", "PS1.OUT1"]

    def test_step_procstep_name_into_instream_proc(self):
        jcl = """\
//J    JOB 1
//P    PROC
//PS1  EXEC PGM=X
//POUT OUTPUT DEST=INPROC
//     PEND
//RUN  EXEC P
//S2   EXEC PGM=Y
//D1   DD SYSOUT=A,OUTPUT=*.RUN.PS1.POUT
//D2   DD SYSOUT=A,OUTPUT=*.RUN.PS9.POUT
"""
        job = parse_jcl(jcl)
        assert [o.dest for o in _dds(job)["D1"].output_refs] == ["INPROC"]
        assert job.unresolved_output_refs == [("S2", "RUN.PS9.POUT", 9)]

    def test_step_procstep_name_into_external_proc_not_checked(self):
        jcl = """\
//J    JOB 1
//RUN  EXEC EXTPROC
//S2   EXEC PGM=Y
//D1   DD SYSOUT=A,OUTPUT=*.RUN.PS1.POUT
"""
        job = parse_jcl(jcl)
        assert _dds(job)["D1"].output_refs == []
        assert job.unresolved_output_refs == []

    def test_too_many_qualifiers_unresolved(self):
        jcl = """\
//J    JOB 1
//S1   EXEC PGM=A
//D1   DD SYSOUT=A,OUTPUT=*.A.B.C.D
"""
        job = parse_jcl(jcl)
        assert job.unresolved_output_refs == [("S1", "A.B.C.D", 3)]


@pytest.mark.unit
class TestExtractOutputRefs:
    def test_forms(self):
        assert _extract_output_refs("*.n") == [("N",)]
        assert _extract_output_refs(["*.S.N", "*.S.P.N"]) == [
            ("S", "N"),
            ("S", "P", "N"),
        ]
        assert _extract_output_refs("S.P.N") == []
        assert _extract_output_refs("*.") == []
        assert _extract_output_refs(None) == []
