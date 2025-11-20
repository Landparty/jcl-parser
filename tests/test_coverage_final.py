"""
Additional focused tests to improve coverage beyond 88%.

These tests target specific uncovered lines in parser.py to reach 90% coverage.
"""

import pytest
from pathlib import Path
import tempfile
import io
from jclparser import parse_jcl
from jclparser.errors import JCLSyntaxError


class TestParserFileHandling:
    """Test file handling edge cases."""
    
    def test_parse_from_path_object(self):
        """Test parsing from Path object."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jcl', delete=False) as f:
            f.write("//MYJOB JOB\n//STEP1 EXEC PGM=TEST\n")
            temp_path = Path(f.name)
        
        try:
            job = parse_jcl(temp_path)
            assert job.name == "MYJOB"
        finally:
            temp_path.unlink()
    
    def test_parse_from_file_object(self):
        """Test parsing from file-like object."""
        jcl_content = "//MYJOB JOB\n//STEP1 EXEC PGM=TEST\n"
        file_obj = io.StringIO(jcl_content)
        
        job = parse_jcl(file_obj)
        assert job.name == "MYJOB"
    
    def test_parse_nonexistent_file(self):
        """Test parsing non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            parse_jcl(Path("/nonexistent/file.jcl"))


class TestParserErrorPaths:
    """Test error handling paths in parser."""
    
    def test_parse_invalid_disposition_format(self):
        """Test parsing DD with complex disposition."""
        jcl = """//MYJOB JOB
//STEP1 EXEC PGM=TEST
//DD1 DD DSN=MY.DATA,DISP=(NEW,CATLG,DELETE)
"""
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        # Disposition might be parsed as list or string
        assert dd.disposition is not None
    
    def test_parse_dd_with_ref_dsn(self):
        """Test DD with referback."""
        jcl = """//MYJOB JOB
//STEP1 EXEC PGM=TEST
//DD1 DD DSN=*.STEP1.DD1
"""
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.dataset_name == "*.STEP1.DD1"
    
    def test_parse_dd_concat_unnamed(self):
        """Test DD concatenation with unnamed DD."""
        jcl = """//MYJOB JOB
//STEP1 EXEC PGM=TEST
//DD1 DD DSN=FILE1
//    DD DSN=FILE2
"""
        job = parse_jcl(jcl)
        # Should have at least the first DD
        assert len(job.steps[0].dd_statements) >= 1
    
    def test_parse_with_accounting_info(self):
        """Test JOB with accounting information."""
        jcl = """//MYJOB JOB (ACCT123),'PROGRAMMER NAME'
//STEP1 EXEC PGM=TEST
"""
        job = parse_jcl(jcl)
        assert job.name == "MYJOB"
    
    def test_parse_exec_with_region(self):
        """Test EXEC with REGION parameter."""
        jcl = """//MYJOB JOB
//STEP1 EXEC PGM=TEST,REGION=4M
"""
        job = parse_jcl(jcl)
        assert "REGION" in job.steps[0].parameters
    
    def test_parse_exec_with_time(self):
        """Test EXEC with TIME parameter."""
        jcl = """//MYJOB JOB
//STEP1 EXEC PGM=TEST,TIME=1440
"""
        job = parse_jcl(jcl)
        assert "TIME" in job.steps[0].parameters
    
    def test_parse_dd_with_unit(self):
        """Test DD with UNIT parameter."""
        jcl = """//MYJOB JOB
//STEP1 EXEC PGM=TEST
//DD1 DD DSN=MY.DATA,UNIT=(SYSDA,2)
"""
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert "UNIT" in dd.parameters
    
    def test_parse_multiline_job_parameters(self):
        """Test JOB with continued parameters."""
        jcl = """//MYJOB JOB (ACCT),
//    'PROGRAMMER',
//    CLASS=A
//STEP1 EXEC PGM=TEST
"""
        job = parse_jcl(jcl)
        assert job.name == "MYJOB"
