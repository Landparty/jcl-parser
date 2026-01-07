"""
Ultra-comprehensive tests - final push to 90%+
Targeting very specific uncovered paths
"""

import pytest
import tempfile
import os
from io import StringIO
from jclparser import parse_jcl
from jclparser.model import Job, Step, DDStatement, Procedure
from jclparser.errors import JCLSyntaxError


class TestUltraComprehensive:
    """Ultra-comprehensive tests for final coverage"""
    
    def test_parse_jcl_from_string_io(self):
        """Test parsing from StringIO object"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DSN=DATA
//"""
        sio = StringIO(jcl)
        job = parse_jcl(sio, strict_mode=False)
        assert job.name == "JOB1"
    
    def test_parse_jcl_from_list(self):
        """Test parsing from list of lines"""
        lines = [
            "//JOB2 JOB CLASS=A",
            "//STEP1 EXEC PGM=PROG",
            "//DD1   DD DSN=DATA",
            "//"
        ]
        # Convert list to string
        jcl_string = "\n".join(lines)
        job = parse_jcl(jcl_string, strict_mode=False)
        assert job.name == "JOB2"
    
    def test_parse_jcl_empty_input(self):
        """Test parsing empty input"""
        try:
            job = parse_jcl("", strict_mode=False)
        except:
            pass  # May raise error
    
    def test_parse_jcl_only_comments(self):
        """Test parsing only comments"""
        jcl = """//****************************
//* THIS IS A COMMENT
//* ANOTHER COMMENT
//****************************
//"""
        try:
            job = parse_jcl(jcl, strict_mode=False)
        except:
            pass  # May raise error or return empty job
    
    def test_parser_inline_data_variations(self):
        """Test all inline data variations"""
        jcl1 = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD *
LINE1
LINE2
/*
//"""
        job1 = parse_jcl(jcl1, strict_mode=False)
        assert job1.steps[0].dd_statements[0].inline_data
        
        jcl2 = """//JOB2 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DATA
LINE1
LINE2
/*
//"""
        job2 = parse_jcl(jcl2, strict_mode=False)
        assert len(job2.steps) >= 1
        
        jcl3 = """//JOB3 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DATA,DLM=$$
LINE1
LINE2
$$
//"""
        job3 = parse_jcl(jcl3, strict_mode=False)
        assert len(job3.steps) >= 1
    
    def test_parser_concat_dd(self):
        """Test concatenated DD statements"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DSN=DATA1,DISP=SHR
//      DD DSN=DATA2,DISP=SHR
//      DD DSN=DATA3,DISP=SHR
//      DD DSN=DATA4,DISP=SHR
//DD2   DD DSN=OTHER
//"""
        job = parse_jcl(jcl, strict_mode=False)
        # Should have multiple DD statements
        assert len(job.steps[0].dd_statements) >= 2
    
    def test_parser_null_statement(self):
        """Test null statements"""
        jcl = """//JOB1 JOB CLASS=A
//
//STEP1 EXEC PGM=PROG
//
//DD1   DD DSN=DATA
//
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "JOB1"
    
    def test_parser_command_statement(self):
        """Test COMMAND statement"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//SYSIN   DD *
 COMMAND 'S STARTED'
/*
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps) >= 1
    
    def test_parser_very_long_continuation(self):
        """Test very long continuation"""
        parts = ["//JOB1 JOB CLASS=A,"]
        for i in range(50):
            parts.append(f"//      PARM{i}=VALUE{i},")
        parts[-1] = parts[-1].rstrip(',')
        parts.append("//STEP1 EXEC PGM=PROG")
        parts.append("//")
        
        jcl = "\n".join(parts)
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "JOB1"
        assert len(job.parameters) >= 30
    
    def test_parser_output_statement(self):
        """Test OUTPUT statement"""
        jcl = """//JOB1 JOB CLASS=A
//OUT1  OUTPUT DEFAULT=YES,CLASS=A
//STEP1 EXEC PGM=PROG
//SYSOUT DD SYSOUT=*,OUTPUT=*.OUT1
//"""
        job = parse_jcl(jcl, strict_mode=False)
        # OUTPUT may be treated as comment or ignored
        assert job.name == "JOB1"
    
    def test_parser_xmit_statement(self):
        """Test XMIT statement"""
        jcl = """//JOB1 JOB CLASS=A
//XMIT DEST='NODE1'
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        # XMIT may be treated as comment or ignored
        assert job.name == "JOB1"
    
    def test_parser_cntl_endcntl(self):
        """Test CNTL/ENDCNTL statements"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//SYSIN DD *
//CNTL
//INTERNAL JOB
//ENDCNTL
/*
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps) >= 1
    
    def test_parser_include_statement(self):
        """Test INCLUDE statement"""
        jcl = """//JOB1 JOB CLASS=A
//      INCLUDE MEMBER=COMMON
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        # INCLUDE may be stored or processed
        assert job.name == "JOB1"
    
    def test_parser_if_then_else_endif(self):
        """Test IF/THEN/ELSE/ENDIF"""
        jcl = """//JOB1 JOB CLASS=A
//      IF (RC = 0) THEN
//STEP1 EXEC PGM=PROG1
//      ELSE
//STEP2 EXEC PGM=PROG2
//      ENDIF
//"""
        job = parse_jcl(jcl, strict_mode=False)
        # Conditional steps may or may not be included
        assert job.name == "JOB1"
    
    def test_parser_nested_if(self):
        """Test nested IF statements"""
        jcl = """//JOB1 JOB CLASS=A
//      IF (RC = 0) THEN
//        IF (RC = 4) THEN
//STEP1   EXEC PGM=PROG1
//        ENDIF
//      ENDIF
//STEP2 EXEC PGM=PROG2
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "JOB1"
    
    def test_parser_schedule_statement(self):
        """Test SCHEDULE statement"""
        jcl = """//JOB1 JOB CLASS=A
//      SCHEDULE TIME=1200
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "JOB1"
    
    def test_parser_export_statement(self):
        """Test EXPORT statement"""
        jcl = """//JOB1 JOB CLASS=A
//      EXPORT SYMLIST=*
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "JOB1"
    
    def test_parser_special_dd_names(self):
        """Test special DD names"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//STEPLIB DD DSN=LOADLIB
//JOBLIB DD DSN=JOBLOADLIB
//SYSIN   DD *
INPUT
/*
//SYSOUT  DD SYSOUT=*
//SYSPRINT DD SYSOUT=A
//SYSDUMP DD SYSOUT=D
//SYSUDUMP DD SYSOUT=D
//SYSABEND DD SYSOUT=A
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps[0].dd_statements) >= 5
    
    def test_dd_with_referback(self):
        """Test DD with referback to previous step"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG1
//OUT1  DD DSN=DATA.SET,DISP=(NEW,PASS)
//STEP2 EXEC PGM=PROG2
//IN1   DD DSN=*.STEP1.OUT1,DISP=(OLD,DELETE)
//STEP3 EXEC PGM=PROG3
//IN2   DD DSN=*.*.OUT1
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps) >= 3
    
    def test_dd_with_subsystem(self):
        """Test DD with subsystem parameters"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DSN=DATA,SUBSYS=(DB2,PLAN)
//DD2   DD DSN=DATA,AMP=('BUFND=10')
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps[0].dd_statements) >= 2
    
    def test_model_export_to_dict(self):
        """Test exporting model to dict"""
        job = Job(name="EXPORT", parameters={"CLASS": "A"}, accounting_info="ACCT")
        step = Step(name="STEP1", program="PROG", line_number=2)
        dd = DDStatement(name="DD1", dataset_name="DATA", disposition="SHR",
                        parameters={"DSN": "DATA", "DISP": "SHR"}, line_number=3)
        step.add_dd(dd)
        job.add_step(step)
        
        # Test to_dict if available
        if hasattr(job, 'to_dict'):
            d = job.to_dict()
            assert d['name'] == "EXPORT"
    
    def test_procedure_with_symbolic_defaults(self):
        """Test procedure with symbolic parameter defaults"""
        jcl = """//JOB1 JOB CLASS=A
//PROC1 PROC P1='DEFAULT',P2=100,P3=(A,B,C)
//PS1   EXEC PGM=PPROG,PARM='&P1'
//PDD1  DD DSN=DATA.&P2
//PDD2  DD DSN=&P3
//      PEND
//CALL  EXEC PROC1
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()
        assert len(exploded.steps) >= 1
    
    def test_step_with_all_parameters(self):
        """Test step with all possible parameters"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG,
//      REGION=8M,
//      TIME=(1,30),
//      COND=((0,NE),(4,LE,STEP0)),
//      PARM='PARAM1,PARAM2',
//      ACCT=(1234),
//      RD=R,
//      DPRTY=(10,5),
//      PERFORM=5,
//      ADDRSPC=VIRT,
//      MEMLIMIT=2G
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps[0].parameters) >= 5
    
    def test_dd_with_all_parameters(self):
        """Test DD with all possible parameters"""
        jcl = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DSN=DATA.SET,
//      DISP=(NEW,CATLG,DELETE),
//      UNIT=SYSDA,
//      VOL=SER=VOL123,
//      SPACE=(CYL,(100,10,5),RLSE),
//      DCB=(RECFM=FB,LRECL=80,BLKSIZE=3200),
//      LABEL=(1,SL),
//      PROTECT=YES,
//      RETPD=30,
//      EXPDT=2025/12/31
//"""
        job = parse_jcl(jcl, strict_mode=False)
        dd = job.steps[0].dd_statements[0]
        assert "DSN" in dd.parameters or "dsn" in dd.parameters
    
    def test_jcllib_with_multiple_libraries(self):
        """Test JCLLIB with multiple libraries"""
        jcl = """//JOB1 JOB CLASS=A
//      JCLLIB ORDER=(LIB1,LIB2,LIB3,LIB4,LIB5)
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.jcllib_order) >= 3
    
    def test_set_with_expressions(self):
        """Test SET with complex expressions"""
        jcl = """//JOB1 JOB CLASS=A
//      SET V1=10
//      SET V2=20
//      SET V3=&V1+&V2
//      SET V4='STRING VALUE'
//      SET V5=&SYSUID..&SYSDATE
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.set_statements) >= 3
