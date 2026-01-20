"""
Tests for SMS (Storage Management Subsystem) DD parameters.

SMS parameters: DATACLAS, MGMTCLAS, STORCLAS
These are used in modern z/OS environments for automated storage management.
"""

import pytest
from jclparser import parse_jcl


class TestSMSParameters:
    """Test SMS parameter parsing."""
    
    def test_dataclas_parameter(self):
        """Test DATACLAS parameter parsing."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,DATACLAS=DCPROD,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert 'DATACLAS' in dd.parameters
        assert dd.parameters['DATACLAS'] == 'DCPROD'
        # Test convenience property
        assert dd.dataclas == 'DCPROD'
    
    def test_mgmtclas_parameter(self):
        """Test MGMTCLAS parameter parsing."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,MGMTCLAS=MCPROD,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert 'MGMTCLAS' in dd.parameters
        assert dd.parameters['MGMTCLAS'] == 'MCPROD'
        # Test convenience property
        assert dd.mgmtclas == 'MCPROD'
    
    def test_storclas_parameter(self):
        """Test STORCLAS parameter parsing."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,STORCLAS=SCPROD,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert 'STORCLAS' in dd.parameters
        assert dd.parameters['STORCLAS'] == 'SCPROD'
        # Test convenience property
        assert dd.storclas == 'SCPROD'
    
    def test_all_sms_classes_together(self):
        """Test all three SMS classes in one DD statement."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,
//       DATACLAS=DCPROD,
//       MGMTCLAS=MCPROD,
//       STORCLAS=SCPROD,
//       DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.dataclas == 'DCPROD'
        assert dd.mgmtclas == 'MCPROD'
        assert dd.storclas == 'SCPROD'
    
    def test_sms_with_space_and_disp(self):
        """Test SMS parameters with SPACE and DISP."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,
//       DISP=(NEW,CATLG,DELETE),
//       DATACLAS=DCPROD,
//       MGMTCLAS=MCPROD,
//       STORCLAS=SCPROD,
//       SPACE=(CYL,(100,10),RLSE)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.dataclas == 'DCPROD'
        assert dd.mgmtclas == 'MCPROD'
        assert dd.storclas == 'SCPROD'
        assert 'SPACE' in dd.parameters
        assert 'DISP' in dd.parameters
    
    def test_sms_none_when_not_specified(self):
        """Test that SMS properties return None when not specified."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,DISP=SHR"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.dataclas is None
        assert dd.mgmtclas is None
        assert dd.storclas is None


class TestSMSRealWorldScenarios:
    """Test real-world SMS usage scenarios."""
    
    def test_sms_managed_dataset_creation(self):
        """Test creating an SMS-managed dataset (from audit example)."""
        jcl = """//CREATE JOB (ACCT),'CREATE SMS FILE'
//STEP1 EXEC PGM=IEFBR14
//NEWFILE DD DSN=PROD.SMS.FILE,
//       DISP=(NEW,CATLG,DELETE),
//       DATACLAS=DCPROD,
//       MGMTCLAS=MCPROD,
//       STORCLAS=SCPROD,
//       SPACE=(CYL,(100,10),RLSE)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('NEWFILE')
        
        assert dd is not None
        assert dd.dataset_name == 'PROD.SMS.FILE'
        assert dd.dataclas == 'DCPROD'
        assert dd.mgmtclas == 'MCPROD'
        assert dd.storclas == 'SCPROD'
    
    def test_sms_with_recfm_lrecl(self):
        """Test SMS parameters with RECFM and LRECL."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,
//       DATACLAS=DCPROD,
//       RECFM=FB,
//       LRECL=80,
//       DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.dataclas == 'DCPROD'
        assert dd.parameters['RECFM'] == 'FB'
        assert dd.parameters['LRECL'] == '80'
    
    def test_partial_sms_specification(self):
        """Test specifying only some SMS classes."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1 DD DSN=MY.FILE,DATACLAS=DCPROD,DISP=(NEW,CATLG)"""
        
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd('DD1')
        
        assert dd is not None
        assert dd.dataclas == 'DCPROD'
        assert dd.mgmtclas is None  # Not specified
        assert dd.storclas is None  # Not specified
