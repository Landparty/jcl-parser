"""
Contract tests for Job Model API

These tests define the expected behavior of the data model classes.
All tests should FAIL initially, then pass as implementation is added.
"""

# Import the model classes we expect to exist
from jclparser.model import Job, Step, DDStatement
from jclparser.errors import ValidationError


class TestJobClass:
    """Contract tests for Job class interface"""

    def test_job_creation(self):
        """GIVEN job name and parameters WHEN Job() constructed THEN properties accessible"""
        job = Job(
            name="TESTJOB",
            parameters={"CLASS": "A", "MSGCLASS": "X"},
            accounting_info="12345",
        )

        assert job.name == "TESTJOB"
        assert job.parameters["CLASS"] == "A"
        assert job.parameters["MSGCLASS"] == "X"
        assert job.accounting_info == "12345"
        assert isinstance(job.steps, list)
        assert len(job.steps) == 0

    def test_job_add_step(self):
        """GIVEN Job instance and Step WHEN step added THEN appears in steps list"""
        job = Job(name="TESTJOB")
        step = Step(name="STEP1", program="IEFBR14")

        job.add_step(step)

        assert len(job.steps) == 1
        assert job.steps[0] == step
        assert job.steps[0].name == "STEP1"

    def test_job_get_step_found(self):
        """GIVEN Job with named steps WHEN get_step() called with valid name THEN returns Step"""
        job = Job(name="TESTJOB")
        step1 = Step(name="STEP1", program="TEST1")
        step2 = Step(name="STEP2", program="TEST2")

        job.add_step(step1)
        job.add_step(step2)

        found_step = job.get_step("STEP2")

        assert found_step is not None
        assert found_step.name == "STEP2"
        assert found_step.program == "TEST2"

    def test_job_get_step_not_found(self):
        """GIVEN Job with steps WHEN get_step() called with invalid name THEN returns None"""
        job = Job(name="TESTJOB")
        step = Step(name="STEP1", program="TEST")
        job.add_step(step)

        found_step = job.get_step("NONEXISTENT")

        assert found_step is None

    def test_job_get_dd_statements(self):
        """GIVEN Job with multiple steps containing DDs WHEN get_dd_statements() called THEN returns all DDs"""
        job = Job(name="TESTJOB")

        step1 = Step(name="STEP1", program="TEST1")
        dd1 = DDStatement(name="DD1", dataset_name="DATA1.TEST")
        dd2 = DDStatement(name="DD2", dataset_name="DATA2.TEST")
        step1.add_dd(dd1)
        step1.add_dd(dd2)

        step2 = Step(name="STEP2", program="TEST2")
        dd3 = DDStatement(name="DD3", dataset_name="DATA3.TEST")
        step2.add_dd(dd3)

        job.add_step(step1)
        job.add_step(step2)

        all_dds = job.get_dd_statements()

        assert len(all_dds) == 3
        dd_names = [dd.name for dd in all_dds]
        assert "DD1" in dd_names
        assert "DD2" in dd_names
        assert "DD3" in dd_names

    def test_job_validation_success(self):
        """GIVEN valid Job structure WHEN validate() called THEN returns empty error list"""
        job = Job(name="VALIDJOB", parameters={"CLASS": "A"})
        step = Step(name="STEP1", program="IEFBR14")
        job.add_step(step)

        errors = job.validate()

        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_job_validation_errors(self):
        """GIVEN invalid Job structure WHEN validate() called THEN returns validation errors"""
        # Job without any steps should be invalid
        job = Job(name="INVALIDJOB")

        errors = job.validate()

        assert isinstance(errors, list)
        assert len(errors) > 0

        for error in errors:
            assert isinstance(error, ValidationError)
            assert hasattr(error, "message")
            assert len(error.message) > 0


class TestStepClass:
    """Contract tests for Step class interface"""

    def test_step_creation(self):
        """GIVEN step name and program WHEN Step() constructed THEN properties accessible"""
        step = Step(name="TESTSTEP", program="MYPROG", parameters={"PARM": "DEBUG=YES"})

        assert step.name == "TESTSTEP"
        assert step.program == "MYPROG"
        assert step.parameters["PARM"] == "DEBUG=YES"
        assert isinstance(step.dd_statements, list)
        assert len(step.dd_statements) == 0
        assert not step.is_procedure

    def test_step_procedure_detection(self):
        """GIVEN step that executes procedure WHEN created THEN is_procedure is True"""
        # Procedure call doesn't have PGM parameter
        step = Step(name="PROCSTEP", procedure="MYPROC", parameters={"PARM": "VALUE"})

        assert step.is_procedure
        assert step.procedure == "MYPROC"

    def test_step_add_dd(self):
        """GIVEN Step instance and DDStatement WHEN DD added THEN appears in dd_statements"""
        step = Step(name="STEP1", program="TEST")
        dd = DDStatement(name="TESTDD", dataset_name="TEST.DATA")

        step.add_dd(dd)

        assert len(step.dd_statements) == 1
        assert step.dd_statements[0] == dd
        assert step.dd_statements[0].name == "TESTDD"

    def test_step_get_dd_found(self):
        """GIVEN Step with DDs WHEN get_dd() called with valid name THEN returns DD"""
        step = Step(name="STEP1", program="TEST")
        dd1 = DDStatement(name="INPUT", dataset_name="INPUT.DATA")
        dd2 = DDStatement(name="OUTPUT", dataset_name="OUTPUT.DATA")

        step.add_dd(dd1)
        step.add_dd(dd2)

        found_dd = step.get_dd("OUTPUT")

        assert found_dd is not None
        assert found_dd.name == "OUTPUT"
        assert found_dd.dataset_name == "OUTPUT.DATA"

    def test_step_get_dd_not_found(self):
        """GIVEN Step with DDs WHEN get_dd() called with invalid name THEN returns None"""
        step = Step(name="STEP1", program="TEST")
        dd = DDStatement(name="DD1", dataset_name="TEST.DATA")
        step.add_dd(dd)

        found_dd = step.get_dd("NONEXISTENT")

        assert found_dd is None

    def test_step_get_input_datasets(self):
        """GIVEN Step with input DDs WHEN get_input_datasets() called THEN returns input dataset names"""
        step = Step(name="STEP1", program="TEST")

        input_dd = DDStatement(
            name="INPUT", dataset_name="INPUT.DATA", disposition="SHR"
        )
        output_dd = DDStatement(
            name="OUTPUT", dataset_name="OUTPUT.DATA", disposition="(NEW,CATLG)"
        )
        temp_dd = DDStatement(
            name="TEMP", dataset_name="&&TEMP", disposition="(NEW,PASS)"
        )

        step.add_dd(input_dd)
        step.add_dd(output_dd)
        step.add_dd(temp_dd)

        input_datasets = step.get_input_datasets()

        assert isinstance(input_datasets, list)
        assert "INPUT.DATA" in input_datasets
        # Temporary datasets might or might not be included depending on implementation

    def test_step_get_output_datasets(self):
        """GIVEN Step with output DDs WHEN get_output_datasets() called THEN returns output dataset names"""
        step = Step(name="STEP1", program="TEST")

        input_dd = DDStatement(
            name="INPUT", dataset_name="INPUT.DATA", disposition="SHR"
        )
        output_dd = DDStatement(
            name="OUTPUT", dataset_name="OUTPUT.DATA", disposition="(NEW,CATLG)"
        )

        step.add_dd(input_dd)
        step.add_dd(output_dd)

        output_datasets = step.get_output_datasets()

        assert isinstance(output_datasets, list)
        assert "OUTPUT.DATA" in output_datasets
        assert "INPUT.DATA" not in output_datasets


class TestDDStatementClass:
    """Contract tests for DDStatement class interface"""

    def test_dd_statement_creation(self):
        """GIVEN DD name and parameters WHEN DDStatement created THEN properties accessible"""
        dd = DDStatement(
            name="TESTDD",
            dataset_name="TEST.DATA",
            disposition="SHR",
            parameters={"UNIT": "DISK", "VOL": "SER=VOL001"},
        )

        assert dd.name == "TESTDD"
        assert dd.dataset_name == "TEST.DATA"
        assert dd.disposition == "SHR"
        assert dd.parameters["UNIT"] == "DISK"
        assert not dd.has_inline_data
        assert dd.inline_data is None

    def test_dd_statement_inline_data(self):
        """GIVEN DD * with inline data WHEN DDStatement created THEN inline data accessible"""
        inline_content = "This is inline data\nWith multiple lines\n"

        dd = DDStatement(name="SYSIN", inline_data=inline_content)

        assert dd.name == "SYSIN"
        assert dd.has_inline_data
        assert dd.inline_data == inline_content
        assert dd.dataset_name is None

    def test_dd_disposition_parsing(self):
        """GIVEN DD with DISP parameter WHEN DDStatement created THEN disposition parsed correctly"""
        # Test simple disposition
        dd1 = DDStatement(name="DD1", disposition="SHR")
        assert dd1.disposition == "SHR"

        # Test complex disposition
        dd2 = DDStatement(name="DD2", disposition="(NEW,CATLG,DELETE)")
        assert dd2.disposition == "(NEW,CATLG,DELETE)"

    def test_dd_is_input(self):
        """GIVEN DD with input characteristics WHEN is_input() called THEN returns True"""
        input_dd = DDStatement(
            name="INPUT", dataset_name="INPUT.DATA", disposition="SHR"
        )

        assert input_dd.is_input()

    def test_dd_is_output(self):
        """GIVEN DD with output characteristics WHEN is_output() called THEN returns True"""
        output_dd = DDStatement(
            name="OUTPUT", dataset_name="OUTPUT.DATA", disposition="(NEW,CATLG)"
        )

        assert output_dd.is_output()

    def test_dd_is_temporary(self):
        """GIVEN DD with temporary dataset WHEN is_temporary() called THEN returns True"""
        temp_dd = DDStatement(name="TEMP", dataset_name="&&TEMPDATA")

        assert temp_dd.is_temporary()

    def test_dd_is_not_temporary(self):
        """GIVEN DD with permanent dataset WHEN is_temporary() called THEN returns False"""
        perm_dd = DDStatement(name="PERM", dataset_name="PERM.DATA.SET")

        assert not perm_dd.is_temporary()

    def test_dd_sysout_handling(self):
        """GIVEN DD with SYSOUT WHEN created THEN handled correctly"""
        sysout_dd = DDStatement(name="SYSPRINT", parameters={"SYSOUT": "*"})

        assert sysout_dd.name == "SYSPRINT"
        assert sysout_dd.parameters["SYSOUT"] == "*"
        assert sysout_dd.dataset_name is None  # SYSOUT doesn't have DSN

    def test_dd_dcb_parameter_parsing(self):
        """GIVEN DD with complex DCB parameter WHEN created THEN DCB parsed correctly"""
        dd = DDStatement(
            name="FILE",
            dataset_name="DATA.FILE",
            parameters={"DCB": "(LRECL=80,BLKSIZE=800,RECFM=FB)"},
        )

        assert "DCB" in dd.parameters
        # DCB parsing might be handled as string or parsed into sub-parameters
        dcb_value = dd.parameters["DCB"]
        assert "LRECL=80" in dcb_value or isinstance(dcb_value, dict)


class TestModelIntegration:
    """Integration tests for model class interactions"""

    def test_complete_job_structure(self):
        """GIVEN complete job structure WHEN built THEN all relationships work correctly"""
        # Build a complete job
        job = Job(name="FULLJOB", parameters={"CLASS": "A"})

        step1 = Step(name="STEP1", program="SORT")
        input_dd = DDStatement(
            name="SORTIN", dataset_name="INPUT.DATA", disposition="SHR"
        )
        output_dd = DDStatement(
            name="SORTOUT", dataset_name="OUTPUT.DATA", disposition="(NEW,CATLG)"
        )
        step1.add_dd(input_dd)
        step1.add_dd(output_dd)

        step2 = Step(name="STEP2", program="IEFBR14")
        step2.add_dd(DDStatement(name="DUMMY", parameters={"DUMMY": ""}))

        job.add_step(step1)
        job.add_step(step2)

        # Validate complete structure
        assert job.name == "FULLJOB"
        assert len(job.steps) == 2
        assert len(job.get_dd_statements()) == 3

        # Test cross-references
        found_step = job.get_step("STEP1")
        assert found_step is not None

        found_dd = found_step.get_dd("SORTIN")
        assert found_dd is not None
        assert found_dd.dataset_name == "INPUT.DATA"

    def test_model_validation_cascade(self):
        """GIVEN job with validation errors WHEN validated THEN errors from all levels reported"""
        job = Job(name="BADJOB")

        # Add step with validation issues
        bad_step = Step(name="", program="")  # Invalid: empty name and program
        bad_dd = DDStatement(
            name="", dataset_name=""
        )  # Invalid: empty name and dataset
        bad_step.add_dd(bad_dd)
        job.add_step(bad_step)

        errors = job.validate()

        assert len(errors) > 0
        # Should include errors from job, step, and DD levels
        error_messages = [error.message for error in errors]
        assert any("step" in msg.lower() for msg in error_messages)
        assert any(
            "dd" in msg.lower() or "name" in msg.lower() for msg in error_messages
        )
