"""
Tests for EXEC statement parameters.

Tests DYNAMNBR, MEMLIMIT, ACCT, ADDRSPC, DPRTY, PERFORM, RD parameters.
Following TDD - these tests will fail until we add the properties.
"""

from jclparser import parse_jcl


class TestEXECParameters:
    """Test EXEC statement parameters."""
    
    def test_dynamnbr(self):
        """Test DYNAMNBR (dynamic allocation count)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=IKJEFT01,DYNAMNBR=50"""
        
        job = parse_jcl(jcl)
        assert job.steps[0].dynamnbr == 50
    
    def test_memlimit(self):
        """Test MEMLIMIT (memory limit above the bar)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG,MEMLIMIT=2G"""
        
        job = parse_jcl(jcl)
        assert job.steps[0].memlimit == '2G'
    
    def test_acct(self):
        """Test ACCT (step-level accounting)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG,ACCT=(1234,DEPT)"""
        
        job = parse_jcl(jcl)
        assert job.steps[0].acct is not None
        # ACCT is parsed as a list
        assert isinstance(job.steps[0].acct, list)
    
    def test_addrspc(self):
        """Test ADDRSPC (address space type)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG,ADDRSPC=REAL"""
        
        job = parse_jcl(jcl)
        assert job.steps[0].addrspc == 'REAL'
    
    def test_dprty(self):
        """Test DPRTY (dispatching priority)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG,DPRTY=(10,5)"""
        
        job = parse_jcl(jcl)
        assert job.steps[0].dprty is not None
    
    def test_perform(self):
        """Test PERFORM (performance group)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG,PERFORM=5"""
        
        job = parse_jcl(jcl)
        assert job.steps[0].perform == 5
    
    def test_rd(self):
        """Test RD (restart definition)."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG,RD=R"""
        
        job = parse_jcl(jcl)
        assert job.steps[0].rd == 'R'
    
    def test_multiple_exec_parameters(self):
        """Test multiple EXEC parameters together."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG,
//       DYNAMNBR=50,
//       MEMLIMIT=2G,
//       ADDRSPC=REAL,
//       PERFORM=5"""
        
        job = parse_jcl(jcl)
        step = job.steps[0]
        assert step.dynamnbr == 50
        assert step.memlimit == '2G'
        assert step.addrspc == 'REAL'
        assert step.perform == 5


class TestEXECRealWorldScenarios:
    """Test real-world scenarios from audit."""
    
    def test_db2_batch_job(self):
        """Test DB2 batch job from audit (Example 3)."""
        jcl = """//DB2JOB JOB (ACCT),'DB2 BATCH'
//STEP1 EXEC PGM=IKJEFT01,DYNAMNBR=50
//SYSTSPRT DD SYSOUT=*
//SYSTSIN DD *
  DSN SYSTEM(DB2P)
  RUN PROGRAM(MYPROG) PLAN(MYPLAN)
  END
/*
//SYSPRINT DD SYSOUT=*"""
        
        job = parse_jcl(jcl)
        assert job.name == 'DB2JOB'
        assert len(job.steps) == 1
        assert job.steps[0].program == 'IKJEFT01'
        assert job.steps[0].dynamnbr == 50
    
    def test_exec_with_region_and_time(self):
        """Test EXEC with existing parameters plus new ones."""
        jcl = """//TEST JOB (ACCT),'TEST'
//STEP1 EXEC PGM=MYPROG,
//       REGION=4096K,
//       TIME=1440,
//       DYNAMNBR=50,
//       MEMLIMIT=2G"""
        
        job = parse_jcl(jcl)
        step = job.steps[0]
        # Existing parameters still work
        assert 'REGION' in step.parameters
        assert 'TIME' in step.parameters
        # New parameters accessible via properties
        assert step.dynamnbr == 50
        assert step.memlimit == '2G'
