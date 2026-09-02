"""
Comprehensive tests for jclparser.validators module.
"""

from jclparser.model import DDStatement, Job, Step
from jclparser.validators import (
    ErrorType,
    ValidationError,
    validate_data_dependencies,
    validate_dataset_name,
    validate_dd_statement,
    validate_jcl_identifier,
    validate_job_structure,
    validate_step_structure,
)


class TestValidateJCLIdentifier:
    """Tests for validate_jcl_identifier function"""

    def test_valid_simple(self):
        """Test valid simple identifier"""
        assert validate_jcl_identifier("JOBNAME")

    def test_valid_with_numbers(self):
        """Test valid identifier with numbers"""
        assert validate_jcl_identifier("JOB123")

    def test_valid_with_at(self):
        """Test valid identifier with @"""
        assert validate_jcl_identifier("@JOBNAME")

    def test_valid_with_hash(self):
        """Test valid identifier with #"""
        assert validate_jcl_identifier("#JOBNAME")

    def test_valid_with_dollar(self):
        """Test valid identifier with $"""
        assert validate_jcl_identifier("$JOBNAME")

    def test_valid_max_length(self):
        """Test valid 8-character identifier"""
        assert validate_jcl_identifier("ABCD1234")

    def test_too_long(self):
        """Test identifier too long"""
        assert not validate_jcl_identifier("TOOLONGNAME")

    def test_empty(self):
        """Test empty identifier"""
        assert not validate_jcl_identifier("")

    def test_start_with_number(self):
        """Test invalid start with number"""
        assert not validate_jcl_identifier("1JOBNAME")

    def test_invalid_characters(self):
        """Test invalid characters"""
        assert not validate_jcl_identifier("JOB-NAME")
        assert not validate_jcl_identifier("JOB.NAME")


class TestValidateDatasetName:
    """Tests for validate_dataset_name function"""

    def test_valid_simple(self):
        """Test valid simple dataset name"""
        assert validate_dataset_name("USER")

    def test_valid_qualified(self):
        """Test valid qualified dataset name"""
        assert validate_dataset_name("USER.DATA.SET")

    def test_valid_temporary(self):
        """Test valid temporary dataset"""
        assert validate_dataset_name("&&TEMP")

    def test_empty(self):
        """Test empty dataset name"""
        assert not validate_dataset_name("")

    def test_invalid_qualifier(self):
        """Test invalid qualifier"""
        assert not validate_dataset_name("USER.123INVALID.DATA")


class TestValidateJobStructure:
    """Tests for validate_job_structure function"""

    def test_valid_job(self):
        """Test valid job structure"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")
        step = Step(name="STEP1", program="PROG", line_number=2)
        job.add_step(step)

        errors = validate_job_structure(job)
        assert len(errors) == 0

    def test_invalid_job_name(self):
        """Test invalid job name"""
        job = Job(name="TOOLONGNAME", parameters={}, accounting_info="ACCT")
        step = Step(name="STEP1", program="PROG", line_number=2)
        job.add_step(step)

        errors = validate_job_structure(job)
        assert len(errors) > 0
        assert any("Invalid job name" in err.message for err in errors)

    def test_no_steps(self):
        """Test job with no steps"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")

        errors = validate_job_structure(job)
        assert len(errors) > 0
        assert any("at least one execution step" in err.message for err in errors)

    def test_duplicate_step_names(self):
        """Test duplicate step names"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")
        step1 = Step(name="STEP1", program="PROG1", line_number=2)
        step2 = Step(name="STEP1", program="PROG2", line_number=3)
        job.add_step(step1)
        job.add_step(step2)

        errors = validate_job_structure(job)
        assert len(errors) > 0
        assert any("Duplicate step name" in err.message for err in errors)


class TestValidateStepStructure:
    """Tests for validate_step_structure function"""

    def test_valid_program_step(self):
        """Test valid program step"""
        step = Step(name="STEP1", program="PROG", line_number=2)
        errors = validate_step_structure(step)
        assert len(errors) == 0

    def test_valid_procedure_step(self):
        """Test valid procedure step"""
        step = Step(name="STEP1", procedure="MYPROC", line_number=2)
        errors = validate_step_structure(step)
        assert len(errors) == 0

    def test_no_program_or_procedure(self):
        """Test step with no program or procedure"""
        step = Step(name="STEP1", line_number=2)
        errors = validate_step_structure(step)
        assert len(errors) > 0
        assert any("program (PGM=) or procedure" in err.message for err in errors)

    def test_both_program_and_procedure(self):
        """Test step with both program and procedure"""
        step = Step(name="STEP1", program="PROG", procedure="PROC", line_number=2)
        errors = validate_step_structure(step)
        assert len(errors) > 0
        assert any(
            "cannot specify both program and procedure" in err.message for err in errors
        )

    def test_invalid_step_name(self):
        """Test invalid step name"""
        step = Step(name="TOOLONGNAME", program="PROG", line_number=2)
        errors = validate_step_structure(step)
        assert len(errors) > 0
        assert any("Invalid step name" in err.message for err in errors)


class TestValidateDDStatement:
    """Tests for validate_dd_statement function"""

    def test_valid_dd(self):
        """Test valid DD statement"""
        dd = DDStatement(name="DD1", dataset_name="USER.DATA", line_number=3)
        errors = validate_dd_statement(dd)
        assert len(errors) == 0

    def test_valid_temporary_dataset(self):
        """Test valid temporary dataset"""
        dd = DDStatement(name="DD1", dataset_name="&&TEMP", line_number=3)
        errors = validate_dd_statement(dd)
        assert len(errors) == 0

    def test_invalid_dd_name(self):
        """Test invalid DD name"""
        dd = DDStatement(name="123INVALID", dataset_name="USER.DATA", line_number=3)
        errors = validate_dd_statement(dd)
        assert len(errors) > 0
        assert any("Invalid DD name" in err.message for err in errors)

    def test_invalid_dataset_name(self):
        """Test invalid dataset name"""
        dd = DDStatement(name="DD1", dataset_name="USER.123BAD.DATA", line_number=3)
        errors = validate_dd_statement(dd)
        assert len(errors) > 0
        assert any("Invalid dataset name" in err.message for err in errors)

    def test_special_dd_names(self):
        """Test special DD names are valid"""
        dd = DDStatement(name="SYSIN", parameters={"DUMMY": True}, line_number=3)
        errors = validate_dd_statement(dd)
        assert len(errors) == 0


class TestValidateDataDependencies:
    """Tests for validate_data_dependencies function"""

    def test_valid_dependencies(self):
        """Test valid data dependencies"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")

        step1 = Step(name="STEP1", program="PROG1", line_number=2)
        dd1 = DDStatement(
            name="OUT1", dataset_name="&&TEMP", disposition="(NEW,PASS)", line_number=3
        )
        step1.add_dd(dd1)
        job.add_step(step1)

        step2 = Step(name="STEP2", program="PROG2", line_number=4)
        dd2 = DDStatement(
            name="IN1", dataset_name="&&TEMP", disposition="(OLD,DELETE)", line_number=5
        )
        step2.add_dd(dd2)
        job.add_step(step2)

        errors = validate_data_dependencies(job)
        assert len(errors) == 0

    def test_undefined_temp_dataset(self):
        """Test reference to undefined temporary dataset"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")

        step = Step(name="STEP1", program="PROG1", line_number=2)
        dd = DDStatement(
            name="IN1", dataset_name="&&UNDEF", disposition="OLD", line_number=3
        )
        step.add_dd(dd)
        job.add_step(step)

        errors = validate_data_dependencies(job)
        assert len(errors) > 0
        assert any("&&UNDEF" in err.message for err in errors)

    def test_multiple_creators(self):
        """Test multiple steps creating same temp dataset"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")

        step1 = Step(name="STEP1", program="PROG1", line_number=2)
        dd1 = DDStatement(
            name="OUT1", dataset_name="&&TEMP", disposition="NEW", line_number=3
        )
        step1.add_dd(dd1)
        job.add_step(step1)

        step2 = Step(name="STEP2", program="PROG2", line_number=4)
        dd2 = DDStatement(
            name="OUT2", dataset_name="&&TEMP", disposition="NEW", line_number=5
        )
        step2.add_dd(dd2)
        job.add_step(step2)

        errors = validate_data_dependencies(job)
        assert len(errors) > 0
        assert any("created in multiple steps" in err.message for err in errors)


class TestValidationError:
    """Tests for ValidationError class"""

    def test_create_error(self):
        """Test creating validation error"""
        error = ValidationError("Test message", ErrorType.VALIDATION_ERROR)
        assert error.message == "Test message"
        assert error.error_type == ErrorType.VALIDATION_ERROR

    def test_with_line_number(self):
        """Test error with line number"""
        error = ValidationError("Test message", ErrorType.SYNTAX_ERROR, line_number=42)
        assert error.line_number == 42

    def test_string_representation(self):
        """Test string representation"""
        error = ValidationError("Test message", ErrorType.VALIDATION_ERROR)
        assert "Test message" in str(error)
