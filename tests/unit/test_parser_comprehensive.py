"""
Additional comprehensive tests for jclparser.parser module.
"""

import pytest
from io import StringIO
from jclparser.parser import parse_jcl, parse_statement
from jclparser.errors import JCLSyntaxError, JCLValidationError


class TestParseStatement:
    """Tests for parse_statement function"""

    def test_parse_job_statement(self):
        """Test parsing JOB statement"""
        stmt = parse_statement("//MYJOB JOB (ACCT),'USER',CLASS=A", 1)
        assert stmt.type == "JOB"
        assert stmt.name == "MYJOB"
        assert "CLASS" in stmt.parameters

    def test_parse_exec_statement(self):
        """Test parsing EXEC statement"""
        stmt = parse_statement("//STEP1 EXEC PGM=IEFBR14", 1)
        assert stmt.type == "EXEC"
        assert stmt.name == "STEP1"
        assert stmt.parameters["PGM"] == "IEFBR14"

    def test_parse_dd_statement(self):
        """Test parsing DD statement"""
        stmt = parse_statement("//DD1 DD DSN=USER.DATA,DISP=SHR", 1)
        assert stmt.type == "DD"
        assert stmt.name == "DD1"
        assert stmt.parameters["DSN"] == "USER.DATA"

    def test_parse_proc_statement(self):
        """Test parsing PROC statement"""
        stmt = parse_statement("//MYPROC PROC DSN=DEFAULT", 1)
        assert stmt.type == "PROC"
        assert stmt.name == "MYPROC"

    def test_parse_pend_statement(self):
        """Test parsing PEND statement"""
        stmt = parse_statement("//       PEND", 1)
        assert stmt.type == "PEND"

    def test_parse_set_statement(self):
        """Test parsing SET statement"""
        stmt = parse_statement("//      SET MYVAR=VALUE", 1)
        assert stmt.type == "SET"

    def test_parse_jcllib_statement(self):
        """Test parsing JCLLIB statement"""
        stmt = parse_statement("//      JCLLIB ORDER=MY.PROCLIB", 1)
        assert stmt.type == "JCLLIB"

    def test_parse_include_statement(self):
        """Test parsing INCLUDE statement"""
        stmt = parse_statement("//      INCLUDE MEMBER=MYMEM", 1)
        assert stmt.type == "INCLUDE"


class TestParseJCLBasic:
    """Basic parse_jcl tests"""

    def test_parse_simple_job(self):
        """Test parsing simple job"""
        jcl = """
//TESTJOB JOB (ACCT),'TEST',CLASS=A
//STEP1   EXEC PGM=IEFBR14
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "TESTJOB"
        assert len(job.steps) == 1
        assert job.steps[0].name == "STEP1"

    def test_parse_from_string(self):
        """Test parsing from string"""
        jcl = "//TESTJOB JOB CLASS=A\n//STEP1 EXEC PGM=PROG\n//"
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "TESTJOB"

    def test_parse_from_stringio(self):
        """Test parsing from StringIO"""
        jcl = "//TESTJOB JOB CLASS=A\n//STEP1 EXEC PGM=PROG\n//"
        job = parse_jcl(StringIO(jcl), strict_mode=False)
        assert job.name == "TESTJOB"

    def test_parse_with_dd_statements(self):
        """Test parsing with DD statements"""
        jcl = """
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=PROG
//DD1     DD DSN=USER.DATA,DISP=SHR
//DD2     DD DSN=USER.OUT,DISP=(NEW,CATLG)
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps[0].dd_statements) == 2


class TestParseJCLProcedures:
    """Tests for parsing procedures"""

    def test_parse_inline_procedure(self):
        """Test parsing inline procedure"""
        jcl = """
//TESTJOB JOB CLASS=A
//MYPROC  PROC
//STEP1   EXEC PGM=PROG
//        PEND
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.procedures) == 1
        assert job.procedures[0].name == "MYPROC"
        assert len(job.procedures[0].steps) == 1

    def test_parse_procedure_with_parameters(self):
        """Test parsing procedure with parameters"""
        jcl = """
//TESTJOB JOB CLASS=A
//MYPROC  PROC DSN=DEFAULT.DATA
//STEP1   EXEC PGM=PROG
//DD1     DD DSN=&DSN
//        PEND
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert "DSN" in job.procedures[0].parameters

    def test_parse_procedure_call(self):
        """Test parsing procedure call"""
        jcl = """
//TESTJOB JOB CLASS=A
//MYPROC  PROC
//STEP1   EXEC PGM=PROG
//        PEND
//CALL    EXEC MYPROC
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps) == 1
        assert job.steps[0].procedure == "MYPROC"


class TestParseJCLAdvanced:
    """Advanced parsing tests"""

    def test_parse_set_statements(self):
        """Test parsing SET statements"""
        jcl = """
//TESTJOB JOB CLASS=A
//        SET MYVAR=VALUE1
//        SET OTHER=VALUE2
//STEP1   EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert "MYVAR" in job.set_statements
        assert job.set_statements["MYVAR"] == "VALUE1"

    def test_parse_jcllib(self):
        """Test parsing JCLLIB"""
        jcl = """
//TESTJOB JOB CLASS=A
//        JCLLIB ORDER=MY.PROCLIB
//STEP1   EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert "MY.PROCLIB" in job.jcllib_order

    def test_parse_include(self):
        """Test parsing INCLUDE"""
        jcl = """
//TESTJOB JOB CLASS=A
//        INCLUDE MEMBER=MYMEM
//STEP1   EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert "MYMEM" in job.includes

    def test_parse_inline_data(self):
        """Test parsing inline data"""
        jcl = """
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=PROG
//SYSIN   DD *
INPUT LINE 1
INPUT LINE 2
/*
//"""
        job = parse_jcl(jcl, strict_mode=False)
        dd = job.steps[0].dd_statements[0]
        assert dd.inline_data is not None
        assert "INPUT LINE 1" in dd.inline_data

    def test_parse_dd_overrides(self):
        """Test parsing DD overrides"""
        jcl = """
//TESTJOB JOB CLASS=A
//MYPROC  PROC
//STEP1   EXEC PGM=PROG
//DD1     DD DSN=PROC.DATA
//        PEND
//CALL    EXEC MYPROC
//STEP1.DD1 DD DSN=OVERRIDE.DATA
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps) == 1
        # DD override should be stored
        step = job.steps[0]
        assert len(step.dd_overrides) > 0


class TestParseJCLErrors:
    """Tests for parsing errors"""

    def test_no_job_statement(self):
        """Test missing JOB statement"""
        jcl = "//STEP1 EXEC PGM=PROG\n//"
        # The error might be about unknown statement type or missing JOB
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl, strict_mode=False)

    def test_exec_before_job(self):
        """Test EXEC before JOB"""
        jcl = "//STEP1 EXEC PGM=PROG\n//TESTJOB JOB CLASS=A\n//"
        with pytest.raises(JCLSyntaxError, match="before JOB"):
            parse_jcl(jcl, strict_mode=False)

    def test_multiple_job_statements(self):
        """Test multiple JOB statements"""
        jcl = "//JOB1 JOB CLASS=A\n//JOB2 JOB CLASS=B\n//"
        with pytest.raises(JCLSyntaxError, match="Multiple JOB"):
            parse_jcl(jcl, strict_mode=False)

    def test_validation_in_strict_mode(self):
        """Test validation errors in strict mode"""
        jcl = "//TOOLONGNAME JOB CLASS=A\n//STEP1 EXEC PGM=PROG\n//"
        with pytest.raises(JCLValidationError):
            parse_jcl(jcl, strict_mode=True)


class TestParseJCLContinuation:
    """Tests for continuation line handling"""

    def test_simple_continuation(self):
        """Test simple continuation"""
        jcl = """
//TESTJOB JOB CLASS=A,
//            MSGCLASS=X
//STEP1   EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert "MSGCLASS" in job.parameters

    def test_multiple_continuations(self):
        """Test multiple continuation lines"""
        jcl = """
//TESTJOB JOB CLASS=A,
//            MSGCLASS=X,
//            NOTIFY=USER
//STEP1   EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert "NOTIFY" in job.parameters


class TestParseJCLEdgeCases:
    """Edge case tests"""

    def test_empty_jcl(self):
        """Test empty JCL"""
        with pytest.raises(JCLSyntaxError):
            parse_jcl("", strict_mode=False)

    def test_only_comments(self):
        """Test JCL with only comments"""
        jcl = "//* Comment 1\n//* Comment 2\n"
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl, strict_mode=False)

    def test_whitespace_handling(self):
        """Test whitespace handling"""
        jcl = "//TESTJOB   JOB   CLASS=A  \n//STEP1   EXEC   PGM=PROG  \n//"
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "TESTJOB"

    def test_case_sensitivity(self):
        """Test case handling"""
        jcl = "//TestJob JOB class=a\n//Step1 EXEC pgm=Prog\n//"
        job = parse_jcl(jcl, strict_mode=False)
        # Names are case-sensitive, keywords are not
        assert job.name == "TestJob"
