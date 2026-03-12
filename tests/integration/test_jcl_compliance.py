"""
Comprehensive JCL compliance tests to ensure parser handles all valid JCL constructs.

This test suite validates that the parser correctly handles:
- All EXEC statement variations (PGM=, PROC=, procedure name without keyword)
- DD statements with various parameters and special forms
- Statements without name fields (nameless EXEC, concatenated DD)
- Edge cases and complex real-world JCL patterns
"""

import pytest
from jclparser import parse_jcl
from jclparser.errors import JCLSyntaxError, JCLValidationError


class TestEXECStatementVariations:
    """Test all valid EXEC statement forms."""
    
    def test_exec_with_pgm_keyword(self):
        """EXEC with PGM= keyword"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14"""
        job = parse_jcl(jcl)
        assert job.steps[0].program == "IEFBR14"
        assert job.steps[0].procedure is None
    
    def test_exec_with_proc_keyword(self):
        """EXEC with PROC= keyword"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PROC=MYPROC"""
        job = parse_jcl(jcl)
        assert job.steps[0].procedure == "MYPROC"
        assert job.steps[0].program is None
    
    def test_exec_with_procedure_name_positional(self):
        """EXEC with procedure name as positional parameter (no keyword)"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC MYPROC"""
        job = parse_jcl(jcl)
        assert job.steps[0].procedure == "MYPROC"
        assert job.steps[0].program is None
    
    def test_exec_with_procedure_and_parameters(self):
        """EXEC procedure with additional parameters"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC MYPROC,PARM='TEST',COND=(0,NE)"""
        job = parse_jcl(jcl)
        assert job.steps[0].procedure == "MYPROC"
        assert "PARM" in job.steps[0].parameters
    
    def test_exec_without_step_name(self):
        """EXEC statement without step name field"""
        jcl = """//TEST JOB (ACCT),'TEST'
// EXEC PGM=IEFBR14"""
        job = parse_jcl(jcl)
        assert len(job.steps) == 1
        assert job.steps[0].program == "IEFBR14"
        assert job.steps[0].name == ""
    
    def test_exec_with_pds_member_syntax(self):
        """EXEC referencing procedure in PDS (treated as program name)"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC SYS1.PROCLIB(MYPROC)"""
        job = parse_jcl(jcl)
        # Parser treats this as a program/procedure name - both are valid interpretations
        assert job.steps[0].program == "SYS1.PROCLIB(MYPROC)" or job.steps[0].procedure == "SYS1.PROCLIB(MYPROC)"
    
    def test_exec_with_complex_parameters(self):
        """EXEC with multiple complex parameters"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14,COND=((0,NE,STEP1),(4,LT)),TIME=(1,30),REGION=4M"""
        job = parse_jcl(jcl)
        assert job.steps[0].program == "IEFBR14"
        assert "COND" in job.steps[0].parameters
        assert "TIME" in job.steps[0].parameters
        assert "REGION" in job.steps[0].parameters
    
    def test_exec_with_step_override_syntax(self):
        """EXEC with step.ddname override syntax"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1.DD1 EXEC PGM=IEFBR14"""
        job = parse_jcl(jcl)
        assert len(job.steps) == 1


class TestDDStatementVariations:
    """Test all valid DD statement forms."""
    
    def test_dd_with_dsn_and_disp(self):
        """DD with dataset name and disposition"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.DATA.SET,DISP=(NEW,CATLG,DELETE)"""
        job = parse_jcl(jcl)
        assert len(job.steps[0].dd_statements) == 1
        assert job.steps[0].dd_statements[0].dataset_name == "MY.DATA.SET"
    
    def test_dd_with_sysout(self):
        """DD with SYSOUT parameter"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//SYSPRINT DD SYSOUT=*"""
        job = parse_jcl(jcl)
        assert len(job.steps[0].dd_statements) == 1
        assert "SYSOUT" in job.steps[0].dd_statements[0].parameters
    
    def test_dd_with_dummy(self):
        """DD with DUMMY parameter"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DUMMY"""
        job = parse_jcl(jcl)
        assert len(job.steps[0].dd_statements) == 1
        # DUMMY is parsed as a positional parameter
        params = job.steps[0].dd_statements[0].parameters
        assert "DUMMY" in params or "_pos_0" in params and params["_pos_0"] == "DUMMY"
    
    def test_dd_concatenation(self):
        """DD concatenation without ddname"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEBGENER
//SYSUT1 DD DSN=FILE1,DISP=SHR
//       DD DSN=FILE2,DISP=SHR
//       DD DSN=FILE3,DISP=SHR"""
        job = parse_jcl(jcl)
        assert len(job.steps[0].dd_statements) == 3  # 1 named + 2 concatenated
        # First DD has a name
        assert job.steps[0].dd_statements[0].name == "SYSUT1"
        # Concatenated DDs have empty names
        assert job.steps[0].dd_statements[1].name == ""
        assert job.steps[0].dd_statements[2].name == ""
    
    def test_dd_without_name_field(self):
        """DD statement without ddname field"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
// DD SYSOUT=*"""
        job = parse_jcl(jcl)
        assert len(job.steps[0].dd_statements) == 1
        assert job.steps[0].dd_statements[0].name == ""
    
    def test_dd_with_dcb_parameters(self):
        """DD with DCB sub-parameters"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.DATA,DISP=SHR,DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)"""
        job = parse_jcl(jcl)
        assert "DCB" in job.steps[0].dd_statements[0].parameters
    
    def test_dd_with_temporary_dataset(self):
        """DD with temporary dataset (&&)"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=&&TEMP,DISP=(NEW,PASS)"""
        job = parse_jcl(jcl)
        assert job.steps[0].dd_statements[0].dataset_name == "&&TEMP"
    
    def test_dd_with_gdg_notation(self):
        """DD with GDG (Generation Data Group) notation"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.GDG(+1),DISP=(NEW,CATLG)
//DD2 DD DSN=MY.GDG(0),DISP=SHR
//DD3 DD DSN=MY.GDG(-1),DISP=SHR"""
        job = parse_jcl(jcl)
        assert len(job.steps[0].dd_statements) == 3
        dsn = job.steps[0].dd_statements[0].dataset_name
        assert dsn is not None and "GDG(+1)" in dsn
    
    def test_dd_with_referback(self):
        """DD with backward reference to previous DD"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.DATA,DISP=SHR
//STEP2 EXEC PGM=SORT
//DD2 DD DSN=*.STEP1.DD1,DISP=SHR"""
        job = parse_jcl(jcl)
        assert len(job.steps) == 2
        dsn = job.steps[1].dd_statements[0].dataset_name
        assert dsn is not None and "*.STEP1.DD1" in dsn
    
    def test_dd_with_inline_data(self):
        """DD with inline data (DD *)"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//SYSIN DD *
This is inline data
Line 2 of data
/*"""
        job = parse_jcl(jcl)
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin is not None
        assert sysin.has_inline_data
        assert sysin.inline_data is not None and "inline data" in sysin.inline_data


class TestConditionalAndControlStatements:
    """Test conditional execution and control statements."""
    
    def test_if_then_endif_block(self):
        """IF/THEN/ENDIF conditional execution"""
        jcl = """//TEST JOB (ACCT),'TEST'
// IF (RC = 0) THEN
//STEP1 EXEC PGM=IEFBR14
// ENDIF"""
        job = parse_jcl(jcl)
        assert len(job.steps) == 1
        assert len(job.steps[0].then_steps) == 1
    
    def test_if_then_else_endif_block(self):
        """IF/THEN/ELSE/ENDIF conditional execution"""
        jcl = """//TEST JOB (ACCT),'TEST'
// IF (RC > 4) THEN
//STEP1 EXEC PGM=PROG1
// ELSE
//STEP2 EXEC PGM=PROG2
// ENDIF"""
        job = parse_jcl(jcl)
        assert len(job.steps) == 1
        assert len(job.steps[0].then_steps) == 1
        assert len(job.steps[0].else_steps) == 1
    
    def test_set_statement(self):
        """SET statement for symbol substitution"""
        jcl = """//TEST JOB (ACCT),'TEST'
// SET MYDSN=USER.DATA.FILE
// SET MYPGM=IEFBR14
//STEP1 EXEC PGM=&MYPGM"""
        job = parse_jcl(jcl)
        # SET statements are tracked - verify parsing succeeds
        assert len(job.steps) == 1


class TestProcedureHandling:
    """Test procedure definition and invocation."""
    
    def test_inline_procedure_definition(self):
        """Inline procedure with PROC/PEND"""
        jcl = """//TEST JOB (ACCT),'TEST'
//MYPROC PROC DSN=DEFAULT.DATA
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=&DSN,DISP=SHR
//       PEND
//CALLPROC EXEC MYPROC,DSN=MY.DATA.SET"""
        job = parse_jcl(jcl)
        assert len(job.procedures) >= 1
        # The EXEC MYPROC should be parsed as a step calling the procedure
        call_step = next((s for s in job.steps if s.name == "CALLPROC"), None)
        assert call_step is not None
        assert call_step.procedure == "MYPROC"


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and proper error handling."""
    
    def test_exec_without_program_or_procedure_fails(self):
        """EXEC without PGM or procedure should fail"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PARM='TEST'"""
        with pytest.raises((JCLSyntaxError, JCLValidationError)):
            parse_jcl(jcl)
    
    def test_exec_with_empty_parameters_fails(self):
        """EXEC with no parameters should fail"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC"""
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)
    
    def test_exec_with_only_condition_fails(self):
        """EXEC with only COND parameter should fail"""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC COND=(0,NE)"""
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)
    
    def test_dd_before_exec_allowed(self):
        """DD before first EXEC should be allowed and attached to first step"""
        jcl = """//TEST JOB (ACCT),'TEST'
//DD1 DD DSN=MY.DATA,DISP=SHR
//STEP1 EXEC PGM=IEFBR14"""
        job = parse_jcl(jcl)
        
        # Should be valid and DD should be attached to STEP1
        assert len(job.steps) == 1
        assert job.steps[0].get_dd("DD1") is not None
    
    def test_multiple_job_statements_fail(self):
        """Multiple JOB statements should fail"""
        jcl = """//TEST1 JOB (ACCT),'TEST'
//TEST2 JOB (ACCT),'TEST'"""
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)


class TestComplexRealWorldScenarios:
    """Test complex real-world JCL patterns."""
    
    def test_multi_step_job_with_dependencies(self):
        """Multi-step job with backward references and conditions"""
        jcl = """//COMPLEXJOB JOB (ACCT),'COMPLEX TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.INPUT.DATA,DISP=SHR
//DD2 DD DSN=&&TEMP1,DISP=(NEW,PASS)
//STEP2 EXEC PGM=SORT,COND=(0,NE,STEP1)
//SORTIN DD DSN=&&TEMP1,DISP=(OLD,DELETE)
//SORTOUT DD DSN=MY.OUTPUT.DATA,DISP=(NEW,CATLG)
//SYSOUT DD SYSOUT=*
//STEP3 EXEC PGM=IEBGENER,COND=((0,NE,STEP1),(4,LT,STEP2))
//SYSUT1 DD DSN=MY.OUTPUT.DATA,DISP=SHR
//SYSUT2 DD SYSOUT=*"""
        job = parse_jcl(jcl)
        assert job.name == "COMPLEXJOB"
        assert len(job.steps) == 3
        assert all(step.program is not None for step in job.steps)
    
    def test_job_with_procedure_and_overrides(self):
        """Job calling procedure with DD overrides"""
        jcl = """//TEST JOB (ACCT),'TEST'
//PROC1 PROC
//STEP1 EXEC PGM=IEFBR14
//DD1 DD SYSOUT=*
//      PEND
//RUN1 EXEC PROC1
//STEP1.DD1 DD SYSOUT=A"""
        job = parse_jcl(jcl)
        assert len(job.procedures) >= 1
        # Should have at least one step from the procedure call
        assert len(job.steps) >= 1
    
    def test_job_with_jcllib_and_include(self):
        """Job with JCLLIB and INCLUDE statements"""
        jcl = """//TEST JOB (ACCT),'TEST'
// JCLLIB ORDER=(MY.PROCLIB,SYS1.PROCLIB)
// INCLUDE MEMBER=COMMON
//STEP1 EXEC PGM=IEFBR14"""
        job = parse_jcl(jcl)
        assert len(job.jcllib_order) >= 1
        assert len(job.includes) >= 1
    
    def test_job_with_continuation_lines(self):
        """Job with continuation lines in various statements"""
        jcl = """//TEST JOB (ACCT),'TEST',
//         CLASS=A,
//         MSGCLASS=X,
//         NOTIFY=&SYSUID
//STEP1 EXEC PGM=IEFBR14,
//         PARM='OPTION1,OPTION2,OPTION3',
//         COND=(0,NE)
//DD1 DD DSN=MY.VERY.LONG.DATASET.NAME,
//       DISP=(NEW,CATLG,DELETE),
//       SPACE=(CYL,(10,5),RLSE),
//       DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)"""
        job = parse_jcl(jcl)
        assert job.name == "TEST"
        assert "CLASS" in job.parameters
        assert "MSGCLASS" in job.parameters
        assert len(job.steps) == 1
        assert "PARM" in job.steps[0].parameters
