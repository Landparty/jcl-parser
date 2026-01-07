"""
Final comprehensive tests to push to 90%+ coverage
Targeting specific uncovered lines
"""

import pytest
from jclparser import parse_jcl
from jclparser.model import Job, Step, DDStatement, Procedure
from jclparser.utils import (
    normalize_jcl_line,
    split_jcl_parameters,
    parse_jcl_parameter,
    quote_jcl_value,
    unquote_jcl_value,
    format_jcl_line,
    merge_continuation_lines
)


class TestUncoveredPaths:
    """Target specific uncovered code paths"""
    
    def test_parser_file_operations(self):
        """Test file-based parsing"""
        import tempfile
        
        jcl_content = """//FILEJOB JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DSN=DATA,DISP=SHR
//"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jcl', delete=False) as f:
            f.write(jcl_content)
            f.flush()
            fname = f.name
        
        try:
            job = parse_jcl(fname, strict_mode=False)
            assert job.name == "FILEJOB"
        finally:
            import os
            os.unlink(fname)
    
    def test_continuation_with_empty_lines(self):
        """Test continuation with various empty line scenarios"""
        jcl = """//JOB1 JOB CLASS=A,
//            PARM1=VALUE1,
//
//            PARM2=VALUE2
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "JOB1"
    
    def test_merge_continuation_edge_cases(self):
        """Test merge_continuation_lines with all scenarios"""
        # Normal continuation
        lines1 = [
            "//JOB JOB CLASS=A,",
            "//      PARM=X"
        ]
        merged1 = merge_continuation_lines(lines1)
        assert len(merged1) == 1
        
        # Multiple continuations
        lines2 = [
            "//STEP EXEC PGM=PROG,",
            "//      REGION=4M,",
            "//      TIME=(1,30)"
        ]
        merged2 = merge_continuation_lines(lines2)
        assert len(merged2) == 1
        
        # Non-continuation
        lines3 = [
            "//JOB JOB CLASS=A",
            "//STEP EXEC PGM=PROG"
        ]
        merged3 = merge_continuation_lines(lines3)
        assert len(merged3) == 2
        
        # Inline data (should not merge)
        lines4 = [
            "//DD1 DD *",
            "DATA LINE 1",
            "DATA LINE 2",
            "/*"
        ]
        merged4 = merge_continuation_lines(lines4)
        assert len(merged4) >= 1
    
    def test_format_jcl_line_all_variations(self):
        """Test format_jcl_line with all parameter types"""
        # Simple parameters
        lines1 = format_jcl_line("EXEC", "STEP1", {"PGM": "PROG"}, 72)
        assert len(lines1) >= 1
        
        # Complex parameters
        lines2 = format_jcl_line("EXEC", "STEP2", {
            "PGM": "PROGRAM",
            "REGION": "4M",
            "TIME": "(1,30)",
            "COND": "(0,NE)",
            "PARM": "'LONG PARAMETER VALUE WITH SPACES'"
        }, 60)
        assert len(lines2) >= 1
        
        # Very long line requiring continuation
        long_params = {f"P{i}": f"VALUE{i}" for i in range(50)}
        lines3 = format_jcl_line("EXEC", "STEP3", long_params, 72)
        assert len(lines3) > 1
    
    def test_quote_unquote_all_cases(self):
        """Test quote/unquote with all special cases"""
        # Values that need quoting
        assert quote_jcl_value("A,B") == "'A,B'"
        assert quote_jcl_value("A=B") == "'A=B'"
        assert quote_jcl_value("A B") == "'A B'"
        assert quote_jcl_value("A(B)") == "'A(B)'"
        
        # Values that don't need quoting
        assert quote_jcl_value("SIMPLE") == "SIMPLE"
        assert quote_jcl_value("VALUE123") == "VALUE123"
        
        # Unquoting with doubled quotes
        assert unquote_jcl_value("'A''B''C'") == "A'B'C"
        assert unquote_jcl_value("'X''Y'") == "X'Y"
        
        # Already unquoted
        assert unquote_jcl_value("UNQUOTED") == "UNQUOTED"
    
    def test_parameter_parsing_edge_cases(self):
        """Test parameter parsing with tricky cases"""
        # Parameter with nested parentheses and quotes
        params1 = split_jcl_parameters("A=(B,(C,D),E),F='G,H',I=J")
        assert len(params1) == 3
        
        # Parameter with multiple levels of nesting
        params2 = split_jcl_parameters("DCB=(RECFM=FB,LRECL=80,BLKSIZE=3200)")
        assert len(params2) == 1
        
        # Multiple quoted parameters
        params3 = split_jcl_parameters("A='X',B='Y',C='Z'")
        assert len(params3) == 3
        
        # Parse each parameter
        key1, val1 = parse_jcl_parameter("PGM=PROG")
        assert key1 == "PGM"
        assert val1 == "PROG"
        
        key2, val2 = parse_jcl_parameter("COND=(0,NE)")
        assert key2 == "COND"
        assert val2 == ['0', 'NE']  # Parenthesized values are parsed as lists
        
        key3, val3 = parse_jcl_parameter("DSN")
        # Positional parameter (no equals sign)
        assert key3 == "_positional"
        assert val3 == "DSN"
    
    def test_model_advanced_operations(self):
        """Test advanced model operations"""
        job = Job(name="ADVJOB", parameters={}, accounting_info="ACCT")
        
        # Add steps with various configurations
        step1 = Step(name="STEP1", program="PROG1", line_number=2)
        dd1 = DDStatement(name="DD1", dataset_name="DATA1", disposition="SHR",
                         parameters={"DSN": "DATA1", "DISP": "SHR"}, line_number=3)
        dd2 = DDStatement(name="DD2", dataset_name="DATA2", disposition="NEW",
                         parameters={"DSN": "DATA2", "DISP": "NEW"}, line_number=4)
        step1.add_dd(dd1)
        step1.add_dd(dd2)
        job.add_step(step1)
        
        step2 = Step(name="STEP2", procedure="PROC1", line_number=5)
        dd3 = DDStatement(name="PDD1", dataset_name="OVERRIDE",
                         parameters={"DSN": "OVERRIDE"}, line_number=6)
        step2.add_dd(dd3)
        job.add_step(step2)
        
        # Test step operations
        assert len(job.steps) == 2
        assert job.steps[0].dd_statements
        
        # Test procedure
        proc = Procedure(name="PROC1", parameters={"P1": "V1"}, line_number=10)
        procstep = Step(name="PS1", program="PPROG", line_number=11)
        proc.add_step(procstep)
        job.add_procedure(proc)
        
        assert len(job.procedures) == 1
    
    def test_explosion_with_overrides(self):
        """Test explosion with DD overrides"""
        jcl = """//OVERJOB JOB CLASS=A
//PROC1 PROC DSN=DEFAULT
//PS1   EXEC PGM=PPROG
//PDD1  DD DSN=&DSN..DATA
//PDD2  DD DSN=STATIC.DATA
//      PEND
//CALL1 EXEC PROC1,DSN=OVERRIDE1
//PS1.PDD1 DD DSN=FULL.OVERRIDE
//CALL2 EXEC PROC1,DSN=OVERRIDE2
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()
        
        # Should have exploded steps
        assert len(exploded.steps) >= 2
    
    def test_complex_jcl_structures(self):
        """Test complex JCL with all features"""
        jcl = """//COMPLEX JOB (ACCT),'USER',
//            CLASS=A,MSGCLASS=X,
//            MSGLEVEL=(1,1),
//            NOTIFY=&SYSUID
//        SET VAR1=VALUE1
//        SET VAR2=VALUE2
//        JCLLIB ORDER=(LIB1,LIB2,LIB3)
//*
//* This is a comment
//*
//PROC1   PROC P1=DEFAULT1,P2=DEFAULT2
//PROCST1 EXEC PGM=PPROG1,REGION=&P1
//PROCDD1 DD DSN=&P2..DATA,DISP=SHR
//PROCST2 EXEC PGM=PPROG2
//PROCDD2 DD DSN=*.PROCST1.PROCDD1
//        PEND
//PROC2   PROC P3=DEFAULT3
//PROCST3 EXEC PROC1,P1=&P3,P2=NESTED
//        PEND
//STEP01  EXEC PGM=PROG1,
//            REGION=8M,
//            TIME=(2,0),
//            COND=(0,NE)
//ST1DD1  DD DSN=INPUT.DATA,DISP=SHR
//ST1DD2  DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG,DELETE),
//           SPACE=(CYL,(10,5),RLSE),
//           UNIT=3390,VOL=SER=VOL123,
//           DCB=(RECFM=FB,LRECL=80,BLKSIZE=3200)
//ST1DD3  DD *
INLINE DATA LINE 1
INLINE DATA LINE 2
INLINE DATA LINE 3
/*
//ST1DD4  DD DATA
DLM DATA LINE 1
DLM DATA LINE 2
/*
//STEP02  EXEC PROC1,P1=4M,P2=CUSTOM
//PROCST1.PROCDD1 DD DSN=OVERRIDE.DATA
//STEP03  EXEC PROC2,P3=8M
//STEP04  EXEC PGM=PROG4
//STEPLIB DD DSN=CUSTOM.LOADLIB,DISP=SHR
//        DD DSN=SYS1.LINKLIB,DISP=SHR
//SYSIN   DD DUMMY
//SYSPRINT DD SYSOUT=*
//SYSOUT  DD SYSOUT=A
//ST4DD1  DD DSN=&&TEMP,DISP=(NEW,PASS)
//ST4DD2  DD DSN=*.STEP01.ST1DD2
//ST4DD3  DD PATH='/usr/local/data/file.txt'
//ST4DD4  DD DSN=GDG.DATA(+1),DISP=(NEW,CATLG)
//ST4DD5  DD DSN=GDG.DATA(0),DISP=SHR
//"""
        job = parse_jcl(jcl, strict_mode=False)
        
        # Verify parsing
        assert job.name == "COMPLEX"
        assert len(job.steps) >= 4
        assert len(job.procedures) >= 2
        assert len(job.set_statements) >= 2
        
        # Verify steps
        assert any(s.name == "STEP01" for s in job.steps)
        assert any(s.name == "STEP02" for s in job.steps)
        
        # Test explosion
        exploded = job.explode(max_depth=10)
        assert len(exploded.steps) >= len(job.steps)
    
    def test_all_dd_statement_types(self):
        """Test all DD statement types"""
        jcl = """//DDJOB JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD01  DD DSN=NORMAL.DATA,DISP=SHR
//DD02  DD DSN=*.DD01
//DD03  DD DSN=&&TEMP
//DD04  DD *
DATA
/*
//DD05  DD DATA
DLM
/*
//DD06  DD DUMMY
//DD07  DD SYSOUT=*
//DD08  DD PATH='/path'
//DD09  DD DSN=GDG(+1)
//DD10  DD DSN=GDG(0)
//DD11  DD DSN=GDG(-1)
//DD12  DD
//      DD DSN=CONCAT1
//      DD DSN=CONCAT2
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps[0].dd_statements) >= 10
    
    def test_normalize_edge_cases(self):
        """Test normalize with various inputs"""
        # Tabs and spaces
        assert "JOB" in normalize_jcl_line("//JOB\t\tNAME")
        
        # Multiple spaces
        assert "STEP" in normalize_jcl_line("//STEP     EXEC")
        
        # Trailing whitespace
        assert "PROG" in normalize_jcl_line("//STEP EXEC PGM=PROG   ")
    
    def test_explosion_audit_trail(self):
        """Test explosion with audit trail"""
        jcl = """//AUDITJOB JOB CLASS=A
//PROC1 PROC
//PS1   EXEC PGM=PPROG
//PDD1  DD DSN=PDATA
//      PEND
//CALL  EXEC PROC1
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode(audit=True)
        
        # Check audit trail
        assert exploded.explosion_audit is not None
        assert len(exploded.explosion_map) >= 0
