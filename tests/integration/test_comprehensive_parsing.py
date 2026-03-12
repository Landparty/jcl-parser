"""
Comprehensive tests for JCL parsing coverage.

Tests based on reference parser (grossvater/jcl-parser) to ensure
we cover most JCL syntax and statement types.
"""

import pytest
from pathlib import Path
from jclparser import parse_jcl, validate_jcl
from jclparser.model import Job, Step, DDStatement, ConditionalBlock, Procedure
from jclparser.errors import JCLSyntaxError, JCLValidationError


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_jcl"


class TestBasicParsing:
    """Test basic JCL statement parsing"""
    
    def test_basic_job(self):
        """Test parsing simple job with one step"""
        jcl_file = FIXTURES_DIR / "basic_job.jcl"
        job = parse_jcl(jcl_file)
        
        assert job.name == "TESTJOB1"
        assert len(job.steps) == 1
        assert job.steps[0].name == "STEP1"
        assert job.steps[0].program == "IEFBR14"
    
    def test_job_with_accounting(self):
        """Test job accounting information extraction"""
        jcl_file = FIXTURES_DIR / "basic_job.jcl"
        job = parse_jcl(jcl_file)
        
        assert job.accounting_info == "ACCT123"
        assert "CLASS" in job.parameters
        assert job.parameters["CLASS"] == "A"
    
    def test_dd_statements(self):
        """Test DD statement parsing"""
        jcl_file = FIXTURES_DIR / "basic_job.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.steps[0]
        assert len(step.dd_statements) == 1
        
        dd = step.dd_statements[0]
        assert dd.name == "SYSPRINT"


class TestContinuationLines:
    """Test continuation line handling"""
    
    def test_continued_parameters(self):
        """Test parameters spanning multiple lines"""
        jcl_file = FIXTURES_DIR / "continuation_lines.jcl"
        job = parse_jcl(jcl_file)
        
        assert job.name == "CONTTEST"
        assert "CLASS" in job.parameters
        assert "MSGCLASS" in job.parameters
    
    def test_continued_dd_parameters(self):
        """Test DD statement with continued parameters"""
        jcl_file = FIXTURES_DIR / "continuation_lines.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.steps[0]
        dd = step.get_dd("DD1")
        assert dd is not None
        assert dd.dataset_name == "MY.DATA.SET"
        assert "SPACE" in dd.parameters
        assert "DCB" in dd.parameters


class TestInstreamData:
    """Test inline/instream data handling"""
    
    def test_dd_star_inline_data(self):
        """Test DD * inline data"""
        jcl_file = FIXTURES_DIR / "instream_data.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.get_step("STEP1")
        sysin = step.get_dd("SYSIN")
        
        assert sysin.has_inline_data
        assert "This is inline data" in sysin.inline_data
    
    def test_dd_data_with_delimiter(self):
        """Test DD DATA with custom delimiter"""
        jcl_file = FIXTURES_DIR / "instream_data.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.get_step("STEP2")
        sortin = step.get_dd("SORTIN")
        
        assert "DATA" in sortin.parameters or sortin.has_inline_data


class TestConditionalStatements:
    """Test IF/THEN/ELSE/ENDIF conditional logic"""
    
    def test_simple_if_statement(self):
        """Test basic IF condition"""
        jcl_file = FIXTURES_DIR / "conditional_if.jcl"
        job = parse_jcl(jcl_file)
        
        assert len(job.conditionals) >= 1
        # First conditional should check RC
        cond = job.conditionals[0]
        assert "RC" in cond.condition or "0" in cond.condition
    
    def test_if_else_statement(self):
        """Test IF/ELSE branching"""
        jcl_file = FIXTURES_DIR / "conditional_if.jcl"
        job = parse_jcl(jcl_file)
        
        # Should have at least 2 conditionals
        assert len(job.conditionals) >= 2


class TestProcedures:
    """Test PROC and PEND statement handling"""
    
    def test_inline_procedure(self):
        """Test inline PROC definition"""
        jcl_file = FIXTURES_DIR / "procedure.jcl"
        job = parse_jcl(jcl_file)
        
        assert len(job.procedures) >= 1
        proc = job.get_procedure("MYPROC")
        assert proc is not None
        assert "DSN" in proc.parameters
    
    def test_procedure_invocation(self):
        """Test calling a procedure"""
        jcl_file = FIXTURES_DIR / "procedure.jcl"
        job = parse_jcl(jcl_file)
        
        callproc = job.get_step("CALLPROC")
        assert callproc is not None


class TestSetStatements:
    """Test SET symbol definitions"""
    
    def test_set_symbols(self):
        """Test SET statement parsing"""
        jcl_file = FIXTURES_DIR / "set_symbols.jcl"
        job = parse_jcl(jcl_file)
        
        assert len(job.set_statements) >= 2
        assert "MYDSN" in job.set_statements
        assert "MYPGM" in job.set_statements


class TestComplexParameters:
    """Test complex parameter syntax"""
    
    def test_parameter_lists(self):
        """Test parameters with lists"""
        jcl_file = FIXTURES_DIR / "complex_params.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.steps[0]
        assert step.program == "IDCAMS"
    
    def test_nested_parentheses(self):
        """Test nested parameter structures"""
        jcl_file = FIXTURES_DIR / "complex_params.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.steps[0]
        dd1 = step.get_dd("DD2")
        
        if dd1:
            assert "DISP" in dd1.parameters
            assert "SPACE" in dd1.parameters


class TestJclLibAndInclude:
    """Test JCLLIB and INCLUDE statements"""
    
    def test_jcllib_order(self):
        """Test JCLLIB ORDER parsing"""
        jcl_file = FIXTURES_DIR / "jcllib_include.jcl"
        job = parse_jcl(jcl_file)
        
        assert len(job.jcllib_order) >= 2
        libs = [lib.upper() for lib in job.jcllib_order]
        assert any("PROCLIB" in lib for lib in libs)
    
    def test_include_member(self):
        """Test INCLUDE statement"""
        jcl_file = FIXTURES_DIR / "jcllib_include.jcl"
        job = parse_jcl(jcl_file)
        
        assert len(job.includes) >= 1
        assert any("COMMON" in incl for incl in job.includes)


class TestMultilineStrings:
    """Test string continuation across lines"""
    
    def test_continued_string_parameter(self):
        """Test string that continues on next line"""
        jcl_file = FIXTURES_DIR / "multiline_strings.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.steps[0]
        assert "PARM" in step.parameters
    
    def test_quoted_strings(self):
        """Test quoted dataset names"""
        jcl_file = FIXTURES_DIR / "multiline_strings.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.steps[0]
        dd1 = step.get_dd("DD1")
        if dd1:
            assert dd1.dataset_name or "DSN" in dd1.parameters
    
    def test_escaped_quotes(self):
        """Test doubled quotes in strings"""
        jcl_file = FIXTURES_DIR / "multiline_strings.jcl"
        job = parse_jcl(jcl_file)
        
        step = job.steps[0]
        dd2 = step.get_dd("DD2")
        assert dd2 is not None


class TestValidation:
    """Test validation functionality"""
    
    def test_validate_valid_jcl(self):
        """Test validation of valid JCL"""
        jcl_file = FIXTURES_DIR / "basic_job.jcl"
        errors = validate_jcl(jcl_file, level="structure")
        
        assert len(errors) == 0
    
    def test_validate_syntax_errors(self):
        """Test detection of syntax errors"""
        invalid_jcl = '''
//BADJOB JOB (ACCT)
//STEP1 EXEC
//DD1 DD
        '''
        errors = validate_jcl(invalid_jcl, level="structure")
        
        # Should catch missing program
        assert len(errors) > 0


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_empty_jcl(self):
        """Test parsing empty JCL"""
        with pytest.raises((JCLSyntaxError, JCLValidationError)):
            parse_jcl("")
    
    def test_no_job_statement(self):
        """Test JCL without JOB statement"""
        jcl = '''
//STEP1 EXEC PGM=IEFBR14
        '''
        with pytest.raises((JCLSyntaxError, JCLValidationError)):
            parse_jcl(jcl)
    
    def test_dd_before_exec_allowed(self):
        """Test DD statement before EXEC is allowed"""
        jcl = '''
//TESTJOB JOB (ACCT)
//DD1 DD SYSOUT=*
//STEP1 EXEC PGM=IEFBR14
        '''
        errors = validate_jcl(jcl, level="structure")
        assert not any("before EXEC" in err.message for err in errors)
    
    def test_unclosed_quote(self):
        """Test detection of unclosed quotes"""
        jcl = "//TESTJOB JOB (ACCT)\n//STEP1 EXEC PGM=TEST,PARM='UNCLOSED"
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)
    
    def test_unmatched_parentheses(self):
        """Test detection of unmatched parentheses"""
        jcl = '''
//TESTJOB JOB (ACCT)
//STEP1 EXEC PGM=TEST
//DD1 DD SPACE=(TRK,(10,5)
        '''
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
