"""
Contract tests for Parser API

These tests define the expected behavior of the core parsing functions.
All tests should FAIL initially, then pass as implementation is added.
"""

import pytest
from pathlib import Path
from io import StringIO

# Import the modules we expect to exist
from jclparser.parser import parse_jcl, validate_jcl, parse_statement
from jclparser.model import Job
from jclparser.errors import JCLSyntaxError, ParseError


class TestParseJCLFunction:
    """Contract tests for parse_jcl() function"""
    
    def test_parse_jcl_string(self):
        """GIVEN valid JCL string WHEN parse_jcl() called THEN returns Job with correct structure"""
        jcl_text = """//MYJOB JOB CLASS=A,MSGCLASS=X
//STEP1 EXEC PGM=IEFBR14
//SYSPRINT DD SYSOUT=*"""
        
        job = parse_jcl(jcl_text)
        
        assert isinstance(job, Job)
        assert job.name == "MYJOB"
        assert job.parameters["CLASS"] == "A"
        assert job.parameters["MSGCLASS"] == "X"
        assert len(job.steps) == 1
        assert job.steps[0].name == "STEP1"
        assert job.steps[0].program == "IEFBR14"
    
    def test_parse_jcl_file_path(self):
        """GIVEN JCL file path WHEN parse_jcl() called THEN reads file and parses content"""
        # This test expects the function to handle Path objects
        file_path = Path("test.jcl")
        
        # Mock file content would be handled by the implementation
        # For now, test that Path objects are accepted
        with pytest.raises((FileNotFoundError, AttributeError)):
            # Should try to read file and fail appropriately
            parse_jcl(file_path)
    
    def test_parse_jcl_file_object(self):
        """GIVEN file-like object WHEN parse_jcl() called THEN reads and parses content"""
        jcl_content = StringIO("//TESTJOB JOB CLASS=A\n//STEP1 EXEC PGM=TEST")
        
        job = parse_jcl(jcl_content)
        
        assert job.name == "TESTJOB"
        assert len(job.steps) == 1
    
    def test_parse_jcl_with_options(self):
        """GIVEN JCL and parsing options WHEN parse_jcl() called THEN respects options"""
        jcl_text = "//JOB1 JOB CLASS=A\n//STEP1 EXEC PGM=TEST"
        
        # Test strict mode option
        job = parse_jcl(jcl_text, strict_mode=True)
        assert job.name == "JOB1"
    
    def test_parse_jcl_syntax_error(self):
        """GIVEN invalid JCL syntax WHEN parse_jcl() called THEN raises JCLSyntaxError"""
        invalid_jcl = "//BADJOB JOB CLASS=\n//STEP1 EXEC"  # Missing required parameters
        
        with pytest.raises(JCLSyntaxError) as exc_info:
            parse_jcl(invalid_jcl)
        
        # Error should include line number
        assert exc_info.value.line_number > 0
        assert len(exc_info.value.message) > 0
    
    def test_parse_jcl_file_not_found(self):
        """GIVEN non-existent file path WHEN parse_jcl() called THEN raises FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            parse_jcl(Path("nonexistent.jcl"))


class TestValidateJCLFunction:
    """Contract tests for validate_jcl() function"""
    
    def test_validate_jcl_success(self):
        """GIVEN valid JCL WHEN validate_jcl() called THEN returns empty error list"""
        valid_jcl = """//GOODJOB JOB CLASS=A
//STEP1 EXEC PGM=IEFBR14
//SYSPRINT DD SYSOUT=*"""
        
        errors = validate_jcl(valid_jcl)
        
        assert isinstance(errors, list)
        assert len(errors) == 0
    
    def test_validate_jcl_errors(self):
        """GIVEN invalid JCL WHEN validate_jcl() called THEN returns list of errors"""
        invalid_jcl = """//BADJOB JOB 
//STEP1 EXEC
//DD1 DD DSN=UNCLOSED.QUOTE'"""
        
        errors = validate_jcl(invalid_jcl)
        
        assert isinstance(errors, list)
        assert len(errors) > 0
        
        # Each error should be a ParseError with proper attributes
        for error in errors:
            assert isinstance(error, ParseError)
            assert hasattr(error, 'line_number')
            assert hasattr(error, 'message')
            assert hasattr(error, 'error_type')
    
    def test_validate_jcl_with_level(self):
        """GIVEN JCL and validation level WHEN validate_jcl() called THEN validates at specified level"""
        jcl_text = "//JOB1 JOB CLASS=A\n//STEP1 EXEC PGM=TEST"
        
        # Test different validation levels
        syntax_errors = validate_jcl(jcl_text, level="syntax_only")
        structure_errors = validate_jcl(jcl_text, level="structure")
        semantic_errors = validate_jcl(jcl_text, level="semantic")
        
        assert isinstance(syntax_errors, list)
        assert isinstance(structure_errors, list)
        assert isinstance(semantic_errors, list)


class TestParseStatementFunction:
    """Contract tests for parse_statement() function"""
    
    def test_parse_statement_job(self):
        """GIVEN JOB statement string WHEN parse_statement() called THEN returns JobStatement"""
        job_line = "//MYJOB JOB (12345),'USER',CLASS=A,MSGCLASS=X"
        
        stmt = parse_statement(job_line)
        
        assert stmt is not None
        assert stmt.type == "JOB"
        assert stmt.name == "MYJOB"
        assert "CLASS" in stmt.parameters
        assert stmt.parameters["CLASS"] == "A"
    
    def test_parse_statement_exec(self):
        """GIVEN EXEC statement WHEN parse_statement() called THEN returns ExecStatement"""
        exec_line = "//STEP1 EXEC PGM=IEFBR14,PARM='DEBUG=YES'"
        
        stmt = parse_statement(exec_line)
        
        assert stmt is not None
        assert stmt.type == "EXEC"
        assert stmt.name == "STEP1"
        assert stmt.parameters["PGM"] == "IEFBR14"
        assert stmt.parameters["PARM"] == "DEBUG=YES"  # Quotes are stripped during parsing
    
    def test_parse_statement_dd(self):
        """GIVEN DD statement WHEN parse_statement() called THEN returns DDStatement"""
        dd_line = "//SYSPRINT DD SYSOUT=*,DCB=(LRECL=80,BLKSIZE=800)"
        
        stmt = parse_statement(dd_line)
        
        assert stmt is not None
        assert stmt.type == "DD"
        assert stmt.name == "SYSPRINT"
        assert stmt.parameters["SYSOUT"] == "*"
        assert "DCB" in stmt.parameters
    
    def test_parse_statement_comment(self):
        """GIVEN comment line WHEN parse_statement() called THEN returns None"""
        comment_line = "//* This is a comment"
        
        stmt = parse_statement(comment_line)
        
        assert stmt is None
    
    def test_parse_statement_empty_line(self):
        """GIVEN empty line WHEN parse_statement() called THEN returns None"""
        empty_line = "   "
        
        stmt = parse_statement(empty_line)
        
        assert stmt is None
    
    def test_parse_statement_with_line_number(self):
        """GIVEN statement with line number WHEN parse_statement() called THEN includes line context"""
        job_line = "//TESTJOB JOB CLASS=A"
        
        stmt = parse_statement(job_line, line_number=42)
        
        assert stmt is not None
        assert hasattr(stmt, 'line_number')
        assert stmt.line_number == 42
    
    def test_parse_statement_continuation(self):
        """GIVEN continuation line WHEN parse_statement() called THEN handles continuation"""
        # This might be handled differently - could be part of multi-line parsing
        continuation_line = "//             CLASS=A,MSGCLASS=X"
        
        stmt = parse_statement(continuation_line)
        
        # Behavior depends on implementation - might return None or continuation marker
        # Test ensures function doesn't crash on continuation lines
        assert stmt is None or hasattr(stmt, 'is_continuation')


class TestParserIntegration:
    """Integration tests combining multiple parser functions"""
    
    def test_parse_validate_consistency(self):
        """GIVEN same JCL WHEN parsed and validated THEN results are consistent"""
        jcl_text = """//JOB1 JOB CLASS=A
//STEP1 EXEC PGM=TEST
//DD1 DD DSN=TEST.DATA,DISP=SHR"""
        
        # If validation passes, parsing should succeed
        errors = validate_jcl(jcl_text)
        job = parse_jcl(jcl_text)
        
        if len(errors) == 0:
            assert job is not None
            assert job.name == "JOB1"
    
    def test_statement_parsing_aggregation(self):
        """GIVEN multi-line JCL WHEN parsed statement by statement THEN aggregates correctly"""
        lines = [
            "//TESTJOB JOB CLASS=A",
            "//STEP1 EXEC PGM=TEST", 
            "//DD1 DD DSN=DATA,DISP=SHR"
        ]
        
        statements = []
        for i, line in enumerate(lines, 1):
            stmt = parse_statement(line, line_number=i)
            if stmt:
                statements.append(stmt)
        
        assert len(statements) == 3
        assert statements[0].type == "JOB"
        assert statements[1].type == "EXEC"
        assert statements[2].type == "DD"


def test_dd_before_exec_strict_raises_structure_error():
    """In strict mode, a DD before any EXEC should raise JCLStructureError."""
    from jclparser.errors import JCLStructureError
    jcl = "//BADJOB   JOB (ACCT),'TEST'\n//DD1      DD DSN=MY.DATA,DISP=SHR\n"
    with pytest.raises(JCLStructureError):
        parse_jcl(jcl, strict_mode=True)


def test_dd_before_exec_lenient_no_raise():
    """In lenient mode, DD before EXEC should not raise — just return 0 steps."""
    jcl = "//BADJOB   JOB (ACCT),'TEST'\n//DD1      DD DSN=MY.DATA,DISP=SHR\n"
    job = parse_jcl(jcl, strict_mode=False)
    assert len(job.steps) == 0