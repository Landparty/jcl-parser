"""
Comprehensive tests for JCL parsing coverage.

Tests based on reference parser (grossvater/jcl-parser) to ensure
we cover most JCL syntax and statement types.
"""

import pytest
from pathlib import Path
from jclparser import parse_jcl, validate_jcl
from jclparser.errors import (
    JCLSyntaxError,
    JCLValidationError,
    CircularProcedureError,
    ProcedureNotFoundError,
)
from jclparser.explosion import explode_job
from jclparser.jcl_file_type import detect_file_type, FileType


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_jcl"
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


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
        invalid_jcl = """
//BADJOB JOB (ACCT)
//STEP1 EXEC
//DD1 DD
        """
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
        jcl = """
//STEP1 EXEC PGM=IEFBR14
        """
        with pytest.raises((JCLSyntaxError, JCLValidationError)):
            parse_jcl(jcl)

    def test_dd_before_exec_allowed(self):
        """Test DD statement before EXEC is allowed"""
        jcl = """
//TESTJOB JOB (ACCT)
//DD1 DD SYSOUT=*
//STEP1 EXEC PGM=IEFBR14
        """
        errors = validate_jcl(jcl, level="structure")
        assert not any("before EXEC" in err.message for err in errors)

    def test_unclosed_quote(self):
        """Test detection of unclosed quotes"""
        jcl = "//TESTJOB JOB (ACCT)\n//STEP1 EXEC PGM=TEST,PARM='UNCLOSED"
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)

    def test_unmatched_parentheses(self):
        """Test detection of unmatched parentheses"""
        jcl = """
//TESTJOB JOB (ACCT)
//STEP1 EXEC PGM=TEST
//DD1 DD SPACE=(TRK,(10,5)
        """
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl)


class TestCircularProcedure:
    """error_circular_proc.jcl — PROCA → PROCB → PROCA cycle."""

    def test_circular_proc_parses_ok(self):
        """Parser accepts the JCL; the cycle is only detected on explosion."""
        job = parse_jcl(FIXTURES_DIR / "error_circular_proc.jcl")
        assert job.name == "BADJOB"
        assert len(job.procedures) == 2

    def test_circular_proc_explode_raises(self):
        """explode_job must raise CircularProcedureError."""
        job = parse_jcl(FIXTURES_DIR / "error_circular_proc.jcl")
        with pytest.raises(CircularProcedureError, match="PROCA"):
            explode_job(job)


class TestDDWithoutExec:
    """error_dd_without_exec.jcl — DD statement with no preceding EXEC."""

    def test_dd_without_exec_parses_no_steps(self):
        """Parser ignores orphaned DD; job has no steps."""
        job = parse_jcl(FIXTURES_DIR / "error_dd_without_exec.jcl")
        assert job.name == "BADJOB"
        assert len(job.steps) == 0


class TestInvalidDisp:
    """error_invalid_disp.jcl — DISP with syntactically invalid values."""

    def test_invalid_disp_parses_leniently(self):
        """Parser captures whatever DISP values appear without crashing."""
        job = parse_jcl(FIXTURES_DIR / "error_invalid_disp.jcl")
        assert job.name == "BADJOB"
        dd = job.steps[0].dd_statements[0]
        disp = dd.disposition
        assert disp is not None
        assert "INVALID" in disp


class TestInvalidProcOverride:
    """error_invalid_proc_override.jcl — override targets a step that doesn't exist."""

    def test_invalid_override_parses_ok(self):
        """Parser accepts the override syntax; structural issue surfaces later."""
        job = parse_jcl(FIXTURES_DIR / "error_invalid_proc_override.jcl")
        assert job.name == "BADJOB"
        assert len(job.procedures) == 1
        assert job.procedures[0].name == "MYPROC"
        # The EXEC PROC=MYPROC step is captured
        assert any(s.name == "EXEC1" for s in job.steps)


class TestMismatchedBrackets:
    """error_mismatched_brackets.jcl — unclosed parenthesis in PARM."""

    def test_mismatched_brackets_parses_leniently(self):
        """Parser captures the malformed PARM string without raising."""
        job = parse_jcl(FIXTURES_DIR / "error_mismatched_brackets.jcl")
        assert job.name == "BADJOB"
        step = job.steps[0]
        assert step.program == "TESTPGM"
        parm = step.parameters.get("PARM", "")
        assert "VALUE1" in parm


class TestMissingDelimiter:
    """error_missing_delimiter.jcl — DD * with no closing /* delimiter."""

    def test_missing_delimiter_validate_reports_error(self):
        """validate_jcl must surface at least one ERROR for this file."""
        errors = validate_jcl(FIXTURES_DIR / "error_missing_delimiter.jcl")
        error_msgs = [e for e in errors if str(e.severity).endswith("ERROR")]
        assert len(error_msgs) > 0


class TestNameTooLong:
    """error_name_too_long.jcl — step name exceeds 8 characters."""

    def test_name_too_long_parses_leniently(self):
        """Parser captures the oversized name; structural validation elsewhere."""
        job = parse_jcl(FIXTURES_DIR / "error_name_too_long.jcl")
        assert job.name == "BADJOB"
        assert len(job.steps) == 1
        # The oversized name is preserved as-is by the lenient parser
        assert len(job.steps[0].name) > 8


class TestUndefinedProc:
    """error_undefined_proc.jcl — EXEC PROC=NONEXIST with no definition."""

    def test_undefined_proc_parses_ok(self):
        """Parser does not resolve PROCs at parse time; job parses without error."""
        job = parse_jcl(FIXTURES_DIR / "error_undefined_proc.jcl")
        assert job.name == "BADJOB"

    def test_undefined_proc_validate_reports_error(self):
        """validate_jcl must surface at least one error for the missing EXEC target."""
        errors = validate_jcl(FIXTURES_DIR / "error_undefined_proc.jcl")
        assert len(errors) > 0

    def test_undefined_proc_explode_raises(self):
        """explode_job must raise ProcedureNotFoundError."""
        job = parse_jcl(FIXTURES_DIR / "error_undefined_proc.jcl")
        with pytest.raises(ProcedureNotFoundError, match="NONEXIST"):
            explode_job(job)


class TestStandaloneProc:
    """standalone_proc.jcl — a PROC file with no JOB card."""

    def test_standalone_proc_detected_as_proc(self):
        """detect_file_type must classify the file as FileType.PROC."""
        ft = detect_file_type(FIXTURES_DIR / "standalone_proc.jcl")
        assert ft == FileType.PROC

    def test_standalone_proc_parse_raises(self):
        """parse_jcl must raise JCLSyntaxError since there is no JOB statement."""
        with pytest.raises(JCLSyntaxError):
            parse_jcl(FIXTURES_DIR / "standalone_proc.jcl")


class TestDivideExample:
    """examples/DIVIDE.jcl — a realistic IEBGENER job with continuation lines."""

    def test_divide_parses_successfully(self):
        """The DIVIDE example must parse cleanly."""
        job = parse_jcl(EXAMPLES_DIR / "DIVIDE.jcl")
        assert job.name == "DIVIDE"
        assert len(job.steps) == 1

    def test_divide_step_structure(self):
        """STEP1 must be IEBGENER with SYSUT1 and SYSUT2 DDs."""
        job = parse_jcl(EXAMPLES_DIR / "DIVIDE.jcl")
        step = job.steps[0]
        assert step.name == "STEP1"
        assert step.program == "IEBGENER"
        dd_names = [dd.name for dd in step.dd_statements]
        assert "SYSUT1" in dd_names
        assert "SYSUT2" in dd_names

    def test_divide_sysut2_continuation_params(self):
        """SYSUT2 parameters split across continuation lines must be fully parsed."""
        job = parse_jcl(EXAMPLES_DIR / "DIVIDE.jcl")
        sysut2 = job.steps[0].get_dd("SYSUT2")
        assert sysut2.dataset_name == "OUTPUT.DATA"
        assert sysut2.disposition == ["NEW", "CATLG", "DELETE"]
        assert sysut2.parameters.get("UNIT") == "SYSDA"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
