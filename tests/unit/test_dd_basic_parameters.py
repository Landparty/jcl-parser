"""
Tests for basic DD statement parameters (RECFM, LRECL, BLKSIZE).

These parameters can appear either inside DCB=(...) or as standalone DD parameters.
This test file verifies they are parsed correctly in both cases.
"""

from jclparser import parse_jcl


class TestBasicDDParametersOutsideDCB:
    """Test RECFM, LRECL, BLKSIZE as standalone parameters (outside DCB)."""
    
    def test_recfm_outside_dcb(self):
        """Test RECFM as standalone parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,RECFM=FB,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert 'RECFM' in dd.parameters
        assert dd.parameters['RECFM'] == 'FB'
    
    def test_lrecl_outside_dcb(self):
        """Test LRECL as standalone parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,LRECL=80,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert 'LRECL' in dd.parameters
        assert dd.parameters['LRECL'] == '80'
    
    def test_blksize_outside_dcb(self):
        """Test BLKSIZE as standalone parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,BLKSIZE=8000,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert 'BLKSIZE' in dd.parameters
        assert dd.parameters['BLKSIZE'] == '8000'
    
    def test_all_three_combined(self):
        """Test RECFM, LRECL, BLKSIZE together as standalone parameters."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,RECFM=FB,LRECL=80,BLKSIZE=27920,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.parameters['RECFM'] == 'FB'
        assert dd.parameters['LRECL'] == '80'
        assert dd.parameters['BLKSIZE'] == '27920'
    
    def test_recfm_vb(self):
        """Test RECFM=VB (Variable Blocked)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,RECFM=VB,LRECL=255,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd.parameters['RECFM'] == 'VB'
        assert dd.parameters['LRECL'] == '255'
    
    def test_recfm_fba(self):
        """Test RECFM=FBA (Fixed Blocked with ASA control characters)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,RECFM=FBA,LRECL=133,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd.parameters['RECFM'] == 'FBA'


class TestBasicDDParametersWithContinuation:
    """Test basic parameters with continuation lines."""
    
    def test_parameters_on_continuation_line(self):
        """Test RECFM, LRECL, BLKSIZE on continuation lines."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.VERY.LONG.DATASET.NAME,
//       RECFM=FB,
//       LRECL=80,
//       BLKSIZE=27920,
//       DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.parameters['RECFM'] == 'FB'
        assert dd.parameters['LRECL'] == '80'
        assert dd.parameters['BLKSIZE'] == '27920'


class TestBasicDDParametersWithDCB:
    """Test that parameters inside DCB are still parsed correctly."""
    
    def test_parameters_inside_dcb(self):
        """Test RECFM, LRECL, BLKSIZE inside DCB parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000),DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert 'DCB' in dd.parameters
        # DCB should be parsed into structured object
        assert dd.dcb is not None
        assert dd.dcb.recfm == 'FB'
        assert dd.dcb.lrecl == 80
        assert dd.dcb.blksize == 8000
    
    def test_mixed_inside_and_outside_dcb(self):
        """Test some parameters inside DCB and some outside (edge case)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,DCB=(RECFM=FB,LRECL=80),BLKSIZE=8000,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        # DCB parameters should be in DCB object
        assert dd.dcb is not None
        assert dd.dcb.recfm == 'FB'
        assert dd.dcb.lrecl == 80
        # BLKSIZE outside DCB should be in parameters
        assert dd.parameters['BLKSIZE'] == '8000'


class TestBasicDDParametersRealWorld:
    """Test real-world scenarios with basic DD parameters."""
    
    def test_new_dataset_creation(self):
        """Test creating a new dataset with all attributes."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//NEWFILE DD DSN=MY.NEW.FILE,
//       DISP=(NEW,CATLG,DELETE),
//       RECFM=FB,
//       LRECL=80,
//       BLKSIZE=27920,
//       SPACE=(CYL,(10,5),RLSE)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('NEWFILE')
        
        assert dd is not None
        assert dd.dataset_name == 'MY.NEW.FILE'
        assert dd.parameters['RECFM'] == 'FB'
        assert dd.parameters['LRECL'] == '80'
        assert dd.parameters['BLKSIZE'] == '27920'
        assert 'SPACE' in dd.parameters
    
    def test_print_file_with_fba(self):
        """Test print file with FBA (ASA control characters)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG
//REPORT DD DSN=MY.REPORT.FILE,
//       DISP=(NEW,CATLG),
//       RECFM=FBA,
//       LRECL=133,
//       BLKSIZE=13300"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('REPORT')
        
        assert dd is not None
        assert dd.parameters['RECFM'] == 'FBA'
        assert dd.parameters['LRECL'] == '133'
        assert dd.parameters['BLKSIZE'] == '13300'
    
    def test_variable_length_file(self):
        """Test variable length file with VB."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG
//VARFILE DD DSN=MY.VAR.FILE,
//       DISP=SHR,
//       RECFM=VB,
//       LRECL=255"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('VARFILE')
        
        assert dd is not None
        assert dd.parameters['RECFM'] == 'VB'
        assert dd.parameters['LRECL'] == '255'
