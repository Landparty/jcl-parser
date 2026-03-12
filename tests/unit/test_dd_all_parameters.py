"""
Tests for all remaining DD parameters (AMP, SUBSYS, DSNTYPE, AVGREC, 
Unix parameters, LIKE, REFDD, KEYOFF, KEYLEN, RECORG).
"""

import pytest
from jclparser import parse_jcl


class TestAMPParameter:
    """Test AMP (Access Method Parameters) for VSAM."""
    
    def test_amp_simple(self):
        """Test simple AMP parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG
//VSAMDD DD DSN=MY.VSAM.CLUSTER,AMP=AMORG,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('VSAMDD')
        
        assert dd is not None
        assert dd.amp == 'AMORG'
    
    def test_amp_with_quotes(self):
        """Test AMP=('BUFND=10','BUFNI=5')."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG
//VSAMDD DD DSN=MY.VSAM.CLUSTER,
//       AMP=('BUFND=20','BUFNI=10','STRNO=3'),
//       DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('VSAMDD')
        
        assert dd is not None
        assert dd.amp is not None
        # AMP should be parsed as a list
        assert isinstance(dd.amp, list)
        assert len(dd.amp) == 3


class TestSUBSYSParameter:
    """Test SUBSYS (Subsystem) parameter."""
    
    def test_subsys_db2(self):
        """Test SUBSYS for DB2."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IKJEFT01
//SYSTSIN DD SUBSYS=(DB2,PLAN=MYPLAN),DSN=MY.FILE"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('SYSTSIN')
        
        assert dd is not None
        assert dd.subsys is not None


class TestDSNTYPEParameter:
    """Test DSNTYPE (Dataset Type) parameter."""
    
    def test_dsntype_library(self):
        """Test DSNTYPE=LIBRARY."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.PDSE,DSNTYPE=LIBRARY,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.dsntype == 'LIBRARY'
    
    def test_dsntype_pds(self):
        """Test DSNTYPE=PDS."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.PDS,DSNTYPE=PDS,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd.dsntype == 'PDS'
    
    def test_dsntype_pdse(self):
        """Test DSNTYPE=PDSE."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.PDSE,DSNTYPE=PDSE,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd.dsntype == 'PDSE'


class TestAVGRECParameter:
    """Test AVGREC (Average Record) parameter."""
    
    def test_avgrec_k(self):
        """Test AVGREC=K."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,SPACE=(CYL,(100,10),,,AVGREC=K),DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        # AVGREC might be inside SPACE parameter or standalone
        # Check if it's accessible
        assert 'SPACE' in dd.parameters
    
    def test_avgrec_m(self):
        """Test AVGREC=M."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,AVGREC=M,SPACE=(CYL,100),DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.avgrec == 'M'


class TestUnixParameters:
    """Test Unix/HFS DD parameters."""
    
    def test_path_parameter(self):
        """Test PATH parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=BPXBATCH
//STDOUT DD PATH='/u/user/output.txt'"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('STDOUT')
        
        assert dd is not None
        assert dd.path == '/u/user/output.txt'
    
    def test_pathdisp_parameter(self):
        """Test PATHDISP parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=BPXBATCH
//STDOUT DD PATH='/u/user/output.txt',PATHDISP=(KEEP,DELETE)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('STDOUT')
        
        assert dd is not None
        assert dd.pathdisp is not None
    
    def test_pathopts_parameter(self):
        """Test PATHOPTS parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=BPXBATCH
//STDOUT DD PATH='/u/user/output.txt',
//       PATHOPTS=(OWRONLY,OCREAT,OTRUNC)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('STDOUT')
        
        assert dd is not None
        assert dd.pathopts is not None
    
    def test_pathmode_parameter(self):
        """Test PATHMODE parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=BPXBATCH
//STDOUT DD PATH='/u/user/output.txt',PATHMODE=SIRWXU"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('STDOUT')
        
        assert dd is not None
        assert dd.pathmode == 'SIRWXU'
    
    def test_unix_file_complete(self):
        """Test complete Unix file DD statement (from audit example)."""
        jcl = """//UNIX JOB (ACCT),'UNIX FILE ACCESS'
//STEP1 EXEC PGM=BPXBATCH
//STDOUT DD PATH='/u/user/output.txt',
//       PATHOPTS=(OWRONLY,OCREAT,OTRUNC),
//       PATHMODE=SIRWXU,
//       PATHDISP=(KEEP,DELETE)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('STDOUT')
        
        assert dd is not None
        assert dd.path == '/u/user/output.txt'
        assert dd.pathmode == 'SIRWXU'
        assert dd.pathdisp is not None
        assert dd.pathopts is not None


class TestRemainingParameters:
    """Test LIKE, REFDD, KEYOFF, KEYLEN, RECORG parameters."""
    
    def test_like_parameter(self):
        """Test LIKE parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=NEW.FILE,LIKE=MODEL.FILE,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.like == 'MODEL.FILE'
    
    def test_refdd_parameter(self):
        """Test REFDD parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=FIRST.FILE,DISP=(NEW,CATLG),SPACE=(CYL,(10,5))
//DD2 DD DSN=SECOND.FILE,REFDD=DD1,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd2 = job.steps[0].get_dd('DD2')
        
        assert dd2 is not None
        assert dd2.refdd == 'DD1'
    
    def test_keyoff_keylen_parameters(self):
        """Test KEYOFF and KEYLEN for KSDS."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IDCAMS
//DD1 DD DSN=MY.KSDS,KEYOFF=0,KEYLEN=10,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.keyoff == 0
        assert dd.keylen == 10
    
    def test_recorg_parameter(self):
        """Test RECORG parameter."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IDCAMS
//DD1 DD DSN=MY.VSAM,RECORG=KS,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.recorg == 'KS'


class TestRealWorldScenarios:
    """Test real-world scenarios from audit."""
    
    def test_vsam_file_processing(self):
        """Test VSAM file processing (from audit example)."""
        jcl = """//VSAM JOB (ACCT),'VSAM PROCESSING'
//STEP1 EXEC PGM=IDCAMS
//SYSPRINT DD SYSOUT=*
//VSAMDD DD DSN=MY.VSAM.CLUSTER,
//       DISP=SHR,
//       AMP=('BUFND=20','BUFNI=10','STRNO=3')"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('VSAMDD')
        
        assert dd is not None
        assert dd.dataset_name == 'MY.VSAM.CLUSTER'
        assert dd.amp is not None
    
    def test_sms_with_dsntype(self):
        """Test SMS parameters with DSNTYPE."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//NEWFILE DD DSN=PROD.SMS.FILE,
//       DISP=(NEW,CATLG,DELETE),
//       DATACLAS=DCPROD,
//       MGMTCLAS=MCPROD,
//       STORCLAS=SCPROD,
//       DSNTYPE=LIBRARY,
//       RECFM=FB,LRECL=80,BLKSIZE=27920"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('NEWFILE')
        
        assert dd is not None
        assert dd.dataclas == 'DCPROD'
        assert dd.dsntype == 'LIBRARY'
        assert dd.parameters['RECFM'] == 'FB'
