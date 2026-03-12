"""
Tests for JOB statement parameters.

Tests BYTES, LINES, PAGES, SYSAFF, SCHENV parameters.
Following TDD - these tests will fail until we add the properties.
"""

import pytest
from jclparser import parse_jcl


class TestJOBParameters:
    """Test JOB statement parameters."""
    
    def test_bytes_limit(self):
        """Test BYTES (output byte limit)."""
        jcl = "//MYJOB JOB (ACCT),'USER',BYTES=(1000,CANCEL)"
        
        job = parse_jcl(jcl)
        assert job.bytes_limit is not None
        # BYTES is parsed as a list
        assert isinstance(job.bytes_limit, list)
    
    def test_lines_limit(self):
        """Test LINES (output line limit)."""
        jcl = "//MYJOB JOB (ACCT),'USER',LINES=(5000,WARNING)"
        
        job = parse_jcl(jcl)
        assert job.lines_limit is not None
    
    def test_pages_limit(self):
        """Test PAGES (output page limit)."""
        jcl = "//MYJOB JOB (ACCT),'USER',PAGES=(100,CANCEL)"
        
        job = parse_jcl(jcl)
        assert job.pages_limit is not None
    
    def test_sysaff(self):
        """Test SYSAFF (system affinity)."""
        jcl = "//MYJOB JOB (ACCT),'USER',SYSAFF=SYS1"
        
        job = parse_jcl(jcl)
        assert job.sysaff == 'SYS1'
    
    def test_schenv(self):
        """Test SCHENV (scheduling environment)."""
        jcl = "//MYJOB JOB (ACCT),'USER',SCHENV=PROD"
        
        job = parse_jcl(jcl)
        assert job.schenv == 'PROD'
    
    def test_multiple_job_parameters(self):
        """Test multiple JOB parameters together."""
        jcl = """//MYJOB JOB (ACCT),'USER',
//       BYTES=(1000,CANCEL),
//       LINES=(5000,WARNING),
//       SYSAFF=SYS1"""
        
        job = parse_jcl(jcl)
        assert job.bytes_limit is not None
        assert job.lines_limit is not None
        assert job.sysaff == 'SYS1'


class TestJOBRealWorldScenarios:
    """Test real-world scenarios."""
    
    def test_job_with_resource_limits(self):
        """Test JOB with resource limits."""
        jcl = """//PRODJOB JOB (ACCT),'PRODUCTION',
//       CLASS=A,
//       MSGCLASS=X,
//       BYTES=(10000,CANCEL),
//       LINES=(50000,WARNING),
//       SYSAFF=SYS1
//STEP1 EXEC PGM=MYPROG"""
        
        job = parse_jcl(jcl)
        assert job.name == 'PRODJOB'
        assert job.bytes_limit is not None
        assert job.lines_limit is not None
        assert job.sysaff == 'SYS1'
        # Existing parameters still work
        assert 'CLASS' in job.parameters
        assert 'MSGCLASS' in job.parameters
    
    def test_job_parameters_none_when_not_specified(self):
        """Test that JOB properties return None when not specified."""
        jcl = "//SIMPLEJOB JOB (ACCT),'USER'"
        
        job = parse_jcl(jcl)
        assert job.bytes_limit is None
        assert job.lines_limit is None
        assert job.pages_limit is None
        assert job.sysaff is None
        assert job.schenv is None
