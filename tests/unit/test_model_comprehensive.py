"""
Additional comprehensive tests for jclparser.model module.
"""

from jclparser.model import DDStatement, Job, Procedure, Step


class TestJobModel:
    """Additional tests for Job model"""

    def test_job_creation(self):
        """Test job creation"""
        job = Job(name="TESTJOB", parameters={"CLASS": "A"}, accounting_info="ACCT")
        assert job.name == "TESTJOB"
        assert job.parameters["CLASS"] == "A"
        assert job.accounting_info == "ACCT"

    def test_add_step(self):
        """Test adding steps to job"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")
        step = Step(name="STEP1", program="PROG", line_number=2)
        job.add_step(step)
        assert len(job.steps) == 1
        assert job.steps[0] == step

    def test_add_procedure(self):
        """Test adding procedure to job"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")
        proc = Procedure(name="MYPROC", parameters={}, line_number=2)
        job.add_procedure(proc)
        assert len(job.procedures) == 1
        assert job.procedures[0] == proc

    def test_add_set(self):
        """Test adding SET statement"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")
        job.add_set("MYVAR", "VALUE")
        assert "MYVAR" in job.set_statements
        assert job.set_statements["MYVAR"] == "VALUE"

    def test_add_comment(self):
        """Test adding comment"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")
        # Comments are stored as strings in the job's comments list
        job.comments.append("//* Test comment")
        assert len(job.comments) == 1

    def test_validate_empty_job(self):
        """Test validating empty job"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")
        errors = job.validate()
        assert len(errors) > 0


class TestStepModel:
    """Additional tests for Step model"""

    def test_step_with_program(self):
        """Test step with program"""
        step = Step(name="STEP1", program="MYPROG", line_number=2)
        assert step.name == "STEP1"
        assert step.program == "MYPROG"
        assert step.procedure is None

    def test_step_with_procedure(self):
        """Test step with procedure"""
        step = Step(name="STEP1", procedure="MYPROC", line_number=2)
        assert step.name == "STEP1"
        assert step.procedure == "MYPROC"
        assert step.program is None

    def test_step_parameters(self):
        """Test step parameters"""
        step = Step(
            name="STEP1", program="PROG", parameters={"PARM": "VALUE"}, line_number=2
        )
        assert step.parameters["PARM"] == "VALUE"

    def test_add_dd(self):
        """Test adding DD statement"""
        step = Step(name="STEP1", program="PROG", line_number=2)
        dd = DDStatement(name="DD1", dataset_name="USER.DATA", line_number=3)
        step.add_dd(dd)
        assert len(step.dd_statements) == 1
        assert step.dd_statements[0] == dd

    def test_add_comment(self):
        """Test adding comment to step"""
        step = Step(name="STEP1", program="PROG", line_number=2)
        # Comments are stored as strings
        step.comments.append("//* Step comment")
        assert len(step.comments) == 1

    def test_exploded_step(self):
        """Test exploded step properties"""
        step = Step(name="STEP1", program="PROG", line_number=2)
        assert not step.is_exploded
        assert step.original_proc_call is None
        assert step.dd_overrides == {}

    def test_step_with_dd_overrides(self):
        """Test step with DD overrides"""
        step = Step(
            name="STEP1",
            procedure="MYPROC",
            line_number=2,
            dd_overrides={"DD1": {"DSN": "NEW.DATA"}},
        )
        assert "DD1" in step.dd_overrides


class TestDDStatementModel:
    """Additional tests for DDStatement model"""

    def test_dd_creation(self):
        """Test DD statement creation"""
        dd = DDStatement(name="DD1", dataset_name="USER.DATA", line_number=3)
        assert dd.name == "DD1"
        assert dd.dataset_name == "USER.DATA"

    def test_dd_disposition(self):
        """Test DD disposition"""
        dd = DDStatement(
            name="DD1",
            dataset_name="USER.DATA",
            disposition="(NEW,CATLG,DELETE)",
            line_number=3,
        )
        assert dd.disposition == "(NEW,CATLG,DELETE)"

    def test_dd_parameters(self):
        """Test DD parameters"""
        dd = DDStatement(
            name="DD1", parameters={"SPACE": "(CYL,10)", "UNIT": "SYSDA"}, line_number=3
        )
        assert dd.parameters["SPACE"] == "(CYL,10)"
        assert dd.parameters["UNIT"] == "SYSDA"

    def test_dd_inline_data(self):
        """Test DD with inline data"""
        dd = DDStatement(name="SYSIN", inline_data="INPUT DATA", line_number=3)
        assert dd.inline_data == "INPUT DATA"

    def test_dd_add_comment(self):
        """Test adding comment to DD"""
        dd = DDStatement(name="DD1", dataset_name="USER.DATA", line_number=3)
        # Comments are stored as strings
        dd.comments.append("//* DD comment")
        assert len(dd.comments) == 1


class TestProcedureModel:
    """Additional tests for Procedure model"""

    def test_procedure_creation(self):
        """Test procedure creation"""
        proc = Procedure(name="MYPROC", parameters={}, line_number=2)
        assert proc.name == "MYPROC"
        assert len(proc.steps) == 0

    def test_procedure_parameters(self):
        """Test procedure with parameters"""
        proc = Procedure(
            name="MYPROC", parameters={"DSN": "DEFAULT.DATA"}, line_number=2
        )
        assert proc.parameters["DSN"] == "DEFAULT.DATA"

    def test_add_step_to_procedure(self):
        """Test adding step to procedure"""
        proc = Procedure(name="MYPROC", parameters={}, line_number=2)
        step = Step(name="STEP1", program="PROG", line_number=3)
        proc.steps.append(step)
        assert len(proc.steps) == 1
