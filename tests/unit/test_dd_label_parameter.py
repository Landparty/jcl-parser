"""
Tests for LABEL DD parameter.

Following KISS - LABEL is just a simple property accessor, not structured parsing.
"""

from jclparser import parse_jcl


class TestLABELParameter:
    """Test LABEL parameter (KISS - simple accessor)."""
    
    def test_label_basic(self):
        """Test basic LABEL parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=TAPE.FILE,LABEL=(3,SL),UNIT=TAPE"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        label = dd.parameters.get('LABEL')
        assert label is not None
        # LABEL is stored as a list: [3, 'SL']
        assert isinstance(label, list)
    
    def test_label_with_retpd(self):
        """Test LABEL with RETPD."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=TAPE.FILE,LABEL=(1,SL,RETPD=30)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        assert dd.parameters.get('LABEL') is not None
    
    def test_label_with_expdt(self):
        """Test LABEL with EXPDT."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=TAPE.FILE,LABEL=(1,SL,EXPDT=2025/365)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        assert dd.parameters.get('LABEL') is not None
    
    def test_label_none_when_not_specified(self):
        """Test LABEL is None when not specified."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        assert dd.parameters.get('LABEL') is None


class TestLABELRealWorld:
    """Test real-world LABEL scenarios from audit."""
    
    def test_tape_processing_from_audit(self):
        """Test tape processing example from audit (Example 4)."""
        jcl = """//TAPE JOB (ACCT),'TAPE PROCESSING'
//STEP1 EXEC PGM=IEBGENER
//SYSUT1 DD DSN=TAPE.INPUT.FILE,
//       DISP=(OLD,KEEP),
//       UNIT=TAPE,
//       VOL=SER=TAPE01,
//       LABEL=(3,SL,RETPD=30,EXPDT=2025/12/31)
//SYSUT2 DD DSN=DISK.OUTPUT.FILE,DISP=(NEW,CATLG)
//SYSPRINT DD SYSOUT=*
//SYSIN DD DUMMY"""
        
        job = parse_jcl(jcl)
        assert job.name == 'TAPE'
        assert len(job.steps) == 1
        
        # LABEL parameter is accessible
        sysut1 = job.steps[0].get_dd('SYSUT1')
        assert sysut1.parameters.get('LABEL') is not None
        # Can access via parameters dict too
        assert 'LABEL' in sysut1.parameters
    
    def test_multiple_tape_files(self):
        """Test multiple tape files with different labels."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG
//TAPE1 DD DSN=TAPE.FILE1,LABEL=(1,SL),UNIT=TAPE
//TAPE2 DD DSN=TAPE.FILE2,LABEL=(2,SL),UNIT=TAPE
//TAPE3 DD DSN=TAPE.FILE3,LABEL=(3,NL),UNIT=TAPE"""
        
        job = parse_jcl(jcl)
        assert job.steps[0].get_dd('TAPE1').parameters.get('LABEL') is not None
        assert job.steps[0].get_dd('TAPE2').parameters.get('LABEL') is not None
        assert job.steps[0].get_dd('TAPE3').parameters.get('LABEL') is not None
