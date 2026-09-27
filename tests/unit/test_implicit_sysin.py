"""In-stream data with no DD statement is read as ``//SYSIN DD *``.

JES treats data records that follow a step without a ``DD *`` / ``DD DATA``
statement as an implicit ``//SYSIN DD *``. The parser used to raise
``JCLSyntaxError`` on the first such record, even with ``strict_mode=False``,
so the whole job failed to parse.
"""

import pytest

from jclparser import JCLSyntaxError, parse_jcl


def _dds(job):
    return {
        s.name: [(d.name, d.inline_data) for d in s.dd_statements] for s in job.steps
    }


@pytest.mark.unit
class TestImplicitSysin:
    def test_data_after_exec_becomes_sysin(self):
        job = parse_jcl("//J JOB\n//S1 EXEC PGM=X\nDATA LINE\nMORE\n//S2 EXEC PGM=Y\n")
        assert _dds(job) == {"S1": [("SYSIN", "DATA LINE\nMORE")], "S2": []}
        sysin = job.steps[0].dd_statements[0]
        assert sysin.parameters == {"*": True}
        assert sysin.line_number == 3
        assert any("treated as //SYSIN DD *" in w for w in job.warnings)

    def test_ended_by_delimiter(self):
        job = parse_jcl("//J JOB\n//S1 EXEC PGM=X\nA\n/*\n//OUT DD SYSOUT=*\n")
        assert _dds(job) == {"S1": [("SYSIN", "A"), ("OUT", None)]}

    def test_runs_to_end_of_file(self):
        job = parse_jcl("//J JOB\n//S1 EXEC PGM=X\nA\nB\n")
        assert _dds(job) == {"S1": [("SYSIN", "A\nB")]}

    def test_after_dd_statements_of_the_step(self):
        job = parse_jcl("//J JOB\n//S1 EXEC PGM=X\n//OUT DD SYSOUT=*\nA\n")
        assert _dds(job) == {"S1": [("OUT", None), ("SYSIN", "A")]}

    def test_explicit_dd_star_unchanged(self):
        job = parse_jcl("//J JOB\n//S1 EXEC PGM=X\n//IN DD *\nA\n/*\n")
        assert _dds(job) == {"S1": [("IN", "A")]}
        assert not job.warnings

    def test_missing_continuation_slashes_still_an_error(self):
        jcl = "//J JOB\n//S1 EXEC PGM=X,\nPARM='NO SLASHES'\n//DD1 DD DUMMY\n"
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)

    def test_comment_after_trailing_comma_still_an_error(self):
        jcl = "//J JOB\n//S1 EXEC PGM=X,   MORE TO COME\nPARM=A\n"
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)

    def test_data_after_completed_continuation(self):
        jcl = "//J JOB\n//S1 EXEC PGM=X,   COMMENT\n//   PARM=A\nDATA\n"
        job = parse_jcl(jcl)
        assert job.steps[0].parameters == {"PARM": "A"}
        assert _dds(job) == {"S1": [("SYSIN", "DATA")]}

    def test_data_before_any_exec_still_an_error(self):
        with pytest.raises(JCLSyntaxError):
            parse_jcl("//J JOB\nDATA\n//S1 EXEC PGM=X\n")
