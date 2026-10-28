"""
Tests for missing/unsupported JCL statement types.

Tests NULL, COMMAND, CNTL/ENDCNTL statements and unknown statement handling
to ensure parser doesn't crash when encountering them.
"""

import pytest

from jclparser import parse_jcl
from jclparser.errors import JCLSyntaxError


class TestNULLStatement:
    """Test NULL statement (//) handling."""

    # The null statement ends the job on z/OS: records after it, up to the
    # next JOB statement, are not part of the job and are reported (#124).

    def test_null_statement_basic(self):
        """Test basic NULL statement (//)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//
//DD1 DD DUMMY"""

        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert len(job.steps) == 1
        assert job.steps[0].get_dd("DD1") is None
        assert any("null statement (//) ends job TEST" in w for w in job.warnings)

    def test_null_statement_right_after_job(self):
        """A null statement straight after the JOB statement ends it there."""
        jcl = """//TEST JOB (ACCT),'TEST'
//
//STEP1 EXEC PGM=IEFBR14
//
//DD1 DD DUMMY
//"""

        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert job.steps == []
        assert any("Line 2: null statement" in w for w in job.warnings)
        assert any("(lines 3-6)" in w for w in job.warnings)

    def test_null_statement_between_steps(self):
        """Test NULL statement between job steps."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DUMMY
//
//STEP2 EXEC PGM=SORT
//DD2 DD DUMMY"""

        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert [s.name for s in job.steps] == ["STEP1"]

    def test_trailing_null_statement_is_silent(self):
        """A null statement as the last record ends the job with no warning."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//
//* trailing comment
"""

        job = parse_jcl(jcl)
        assert [s.name for s in job.steps] == ["STEP1"]
        assert job.warnings == []

    def test_null_before_job_statement_is_ignored(self):
        jcl = """//
//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14"""

        job = parse_jcl(jcl)
        assert [s.name for s in job.steps] == ["STEP1"]
        assert job.warnings == []

    def test_data_after_null_is_ignored(self):
        """In-stream data after the null statement is not attached to a step."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//
//IN DD *
DATA
/*"""

        job = parse_jcl(jcl)
        assert job.steps[0].dd_statements == []
        assert any("3 record(s)" in w for w in job.warnings)

    def test_second_job_after_null_is_still_an_error(self):
        jcl = """//J1 JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//
//J2 JOB (ACCT),'TEST'
//STEP2 EXEC PGM=IEFBR14"""

        with pytest.raises(JCLSyntaxError, match="Multiple JOB"):
            parse_jcl(jcl)


class TestCOMMANDStatement:
    """Test COMMAND statement handling."""

    def test_command_statement_basic(self):
        """Test basic COMMAND statement."""
        jcl = """//TEST JOB (ACCT),'TEST'
//CMD1 COMMAND 'START MYPROC'
//STEP1 EXEC PGM=IEFBR14"""

        job = parse_jcl(jcl)
        # Should parse without crashing
        assert job.name == "TEST"
        assert len(job.steps) == 1

    def test_command_with_parameters(self):
        """Test COMMAND with complex parameters."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//CMD1 COMMAND 'DISPLAY A,L'
//DD1 DD DUMMY"""

        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert len(job.steps) == 1

    def test_multiple_command_statements(self):
        """Test multiple COMMAND statements."""
        jcl = """//TEST JOB (ACCT),'TEST'
//CMD1 COMMAND 'START PROC1'
//CMD2 COMMAND 'DISPLAY JOBS'
//STEP1 EXEC PGM=IEFBR14"""

        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert len(job.steps) == 1


class TestCNTLStatements:
    """Test CNTL/ENDCNTL statement handling."""

    def test_cntl_endcntl_in_inline_data(self):
        """Test CNTL/ENDCNTL in inline data."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEBCOPY
//SYSIN DD *
  CNTL
  COPY INDD=IN,OUTDD=OUT
  ENDCNTL
/*
//DD1 DD DUMMY"""

        job = parse_jcl(jcl)
        # Should parse without crashing
        assert job.name == "TEST"
        # CNTL/ENDCNTL should be in inline data
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin is not None
        assert sysin.has_inline_data
        assert "CNTL" in sysin.inline_data
        assert "ENDCNTL" in sysin.inline_data

    def test_cntl_as_statement(self):
        """Test CNTL as a statement (edge case)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//CNTL1 CNTL
//STEP1 EXEC PGM=IEFBR14
//ENDCTL ENDCNTL"""

        job = parse_jcl(jcl)
        # Should parse without crashing
        assert job.name == "TEST"
        assert len(job.steps) == 1


class TestUnknownStatements:
    """Test handling of unknown/unsupported statement types."""

    def test_unknown_statement_doesnt_crash(self):
        """Test that unknown statements don't crash parser."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//UNKNOWN FAKETYPE PARAM=VALUE
//DD1 DD DUMMY"""

        job = parse_jcl(jcl)
        # Should parse without crashing
        assert job.name == "TEST"
        assert len(job.steps) == 1
        assert job.steps[0].get_dd("DD1") is not None

    def test_multiple_unknown_statements(self):
        """Test multiple unknown statements."""
        jcl = """//TEST JOB (ACCT),'TEST'
//WEIRD1 CUSTOM1 X=Y
//WEIRD2 CUSTOM2 A=B
//STEP1 EXEC PGM=IEFBR14"""

        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert len(job.steps) == 1

    def test_unknown_statement_between_valid_statements(self):
        """Test unknown statement between valid statements."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DUMMY
//MYSTERY UNKNOWN PARAM=X
//DD2 DD DUMMY"""

        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert len(job.steps) == 1
        # Both DDs should be parsed
        assert job.steps[0].get_dd("DD1") is not None
        assert job.steps[0].get_dd("DD2") is not None

    def test_unknown_statement_with_continuation(self):
        """Test unknown statement with continuation lines."""
        jcl = """//TEST JOB (ACCT),'TEST'
//WEIRD CUSTOM PARAM1=VALUE1,
//       PARAM2=VALUE2
//STEP1 EXEC PGM=IEFBR14"""

        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert len(job.steps) == 1


class TestRealWorldScenarios:
    """Test real-world scenarios with missing statement types."""

    def test_complete_job_with_all_missing_types(self):
        """Test job with NULL, COMMAND, CNTL, and unknown statements."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
//CMD1 COMMAND 'START PROC1'
//STEP1 EXEC PGM=IEBCOPY
//SYSIN DD *
  CNTL
  COPY INDD=IN,OUTDD=OUT
  ENDCNTL
/*
//UNKNOWN CUSTOM PARAM=VALUE
//STEP2 EXEC PGM=IEFBR14
//DD1 DD DUMMY
//"""

        job = parse_jcl(jcl)
        assert job.name == "TESTJOB"
        assert len(job.steps) == 2
        # Verify inline data was captured
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data

    def test_operator_commands_in_production_jcl(self):
        """Test production JCL with operator commands."""
        jcl = """//PRODJOB JOB (ACCT),'PRODUCTION'
//CMD1 COMMAND 'DISPLAY ACTIVE'
//CMD2 COMMAND 'START BACKUP'
//BACKUP EXEC PGM=IEBGENER
//SYSUT1 DD DSN=PROD.DATA,DISP=SHR
//SYSUT2 DD DSN=BACKUP.DATA,DISP=(NEW,CATLG)
//SYSIN DD DUMMY
//SYSPRINT DD SYSOUT=*
//CMD3 COMMAND 'DISPLAY JOBS'"""

        job = parse_jcl(jcl)
        assert job.name == "PRODJOB"
        assert len(job.steps) == 1
        assert job.steps[0].name == "BACKUP"
