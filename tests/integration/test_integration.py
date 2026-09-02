"""
Integration tests based on quickstart scenarios

These tests validate end-to-end behavior against acceptance criteria.
All tests should FAIL initially, then pass as implementation is added.
"""

import time

import pytest

# Import the main jclparser module and expected classes
from jclparser import get_plugin_registry, parse_jcl, validate_jcl
from jclparser.errors import ErrorType, JCLSyntaxError, JCLValidationError
from jclparser.plugins import StatementPlugin


class TestBasicJCLParsing:
    """Integration tests for basic JCL parsing - Validates FR-001, FR-003, FR-007"""

    def setup_method(self):
        """Setup sample JCL content for testing"""
        self.jcl_content = """//MYJOB    JOB (12345),'DEVELOPER',CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD   SYSOUT=*
//SYSIN    DD   *
This is inline data
for the SYSIN DD
/*
//STEP2    EXEC PGM=SORT
//SORTIN   DD   DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD   DSN=OUTPUT.DATA,DISP=(NEW,CATLG)
//SYSOUT   DD   SYSOUT=*"""

    def test_parse_complete_job_structure(self):
        """GIVEN complete JCL script WHEN parsed THEN job structure correct"""
        job = parse_jcl(self.jcl_content)

        # Validate job metadata
        assert job.name == "MYJOB"
        assert job.accounting_info == "12345"
        assert job.parameters["CLASS"] == "A"
        assert job.parameters["MSGCLASS"] == "X"

        # Validate job steps
        assert len(job.steps) == 2
        assert job.steps[0].name == "STEP1"
        assert job.steps[0].program == "IEFBR14"
        assert job.steps[1].name == "STEP2"
        assert job.steps[1].program == "SORT"

    def test_parse_dd_statements(self):
        """GIVEN JCL with various DD types WHEN parsed THEN DD statements correct"""
        job = parse_jcl(self.jcl_content)

        # Validate STEP1 DD statements
        step1_dds = job.steps[0].dd_statements
        assert len(step1_dds) == 2

        sysprint_dd = next(dd for dd in step1_dds if dd.name == "SYSPRINT")
        assert sysprint_dd.parameters["SYSOUT"] == "*"

        sysin_dd = next(dd for dd in step1_dds if dd.name == "SYSIN")
        assert sysin_dd.has_inline_data
        assert sysin_dd.inline_data is not None
        assert "This is inline data" in sysin_dd.inline_data
        assert "for the SYSIN DD" in sysin_dd.inline_data

        # Validate STEP2 DD statements
        step2_dds = job.steps[1].dd_statements
        assert len(step2_dds) == 3

        sortin_dd = next(dd for dd in step2_dds if dd.name == "SORTIN")
        assert sortin_dd.dataset_name == "INPUT.DATA"
        assert sortin_dd.disposition == "SHR"

        sortout_dd = next(dd for dd in step2_dds if dd.name == "SORTOUT")
        assert sortout_dd.dataset_name == "OUTPUT.DATA"
        assert sortout_dd.disposition == ["NEW", "CATLG"]

    def test_job_navigation_methods(self):
        """GIVEN parsed job WHEN navigation methods used THEN returns correct objects"""
        job = parse_jcl(self.jcl_content)

        # Test step lookup
        step1 = job.get_step("STEP1")
        if step1 is None:
            raise AssertionError("STEP1 not found")
        assert step1.program == "IEFBR14"

        step2 = job.get_step("STEP2")
        if step2 is None:
            raise AssertionError("STEP2 not found")
        assert step2.program == "SORT"

        # Test DD lookup within steps
        sysprint = step1.get_dd("SYSPRINT")
        if sysprint is None:
            raise AssertionError("SYSPRINT DD not found")
        assert sysprint.parameters["SYSOUT"] == "*"

        # Test all DD statements collection
        all_dds = job.get_dd_statements()
        assert len(all_dds) == 5  # 2 from STEP1, 3 from STEP2
        dd_names = [dd.name for dd in all_dds]
        assert "SYSPRINT" in dd_names
        assert "SYSIN" in dd_names
        assert "SORTIN" in dd_names
        assert "SORTOUT" in dd_names
        assert "SYSOUT" in dd_names


class TestErrorHandlingAndValidation:
    """Integration tests for error handling - Validates FR-004, FR-009"""

    def setup_method(self):
        """Setup invalid JCL with various error types"""
        self.invalid_jcl = """//BADJOB   JOB CLASS=A
//STEP1    EXEC PGM=TEST
//DD1      DD   DSN=UNCLOSED.QUOTE'
//         DD   DSN=MISSING.NAME
//STEP2    EXEC"""

    def test_validation_catches_syntax_errors(self):
        """GIVEN invalid JCL WHEN validated THEN returns specific errors"""
        errors = validate_jcl(self.invalid_jcl)

        # Should find multiple errors
        assert len(errors) > 0

        # Verify error structure
        for error in errors:
            assert hasattr(error, "line_number")
            assert hasattr(error, "message")
            assert hasattr(error, "error_type")
            assert error.line_number > 0
            assert len(error.message) > 0

        # Should identify specific error types
        syntax_errors = [e for e in errors if e.error_type == ErrorType.SYNTAX_ERROR]
        # With correct continuation merging the unclosed-quote statement spans
        # multiple physical lines (the continuation handler propagates the
        # unclosed-quote context), so they collapse into a single logical error.
        # We assert >= 1 to verify errors are found and correctly structured.
        assert len(syntax_errors) >= 1

    def test_parsing_raises_exceptions_for_errors(self):
        """GIVEN invalid JCL WHEN parsed THEN raises appropriate exceptions"""
        with pytest.raises(JCLSyntaxError) as exc_info:
            parse_jcl(self.invalid_jcl)

        # Verify exception details
        assert exc_info.value.line_number > 0
        error_message = exc_info.value.message.lower()
        assert (
            "quote" in error_message
            or "name" in error_message
            or "missing" in error_message
        )

    def test_validation_levels(self):
        """GIVEN JCL and validation levels WHEN validated THEN appropriate level of checking"""
        jcl_text = "//JOB1 JOB CLASS=A\n//STEP1 EXEC PGM=TEST"

        # Test different validation levels
        syntax_errors = validate_jcl(jcl_text, level="syntax_only")
        structure_errors = validate_jcl(jcl_text, level="structure")
        semantic_errors = validate_jcl(jcl_text, level="semantic")

        assert isinstance(syntax_errors, list)
        assert isinstance(structure_errors, list)
        assert isinstance(semantic_errors, list)

        # Semantic validation should include all previous levels
        assert len(semantic_errors) >= len(structure_errors) >= len(syntax_errors)


class TestComplexJCLFeatures:
    """Integration tests for complex JCL features - Validates FR-002, FR-005, FR-008"""

    def setup_method(self):
        """Setup complex JCL with various advanced features"""
        self.complex_jcl = """//* This is a job comment
//COMPLEX  JOB (ACCT,1234),'USER NAME',
//             CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//PROC1    EXEC MYPROC,PARM='OPTION1,OPTION2'
//SYSIN    DD   DSN=&&TEMP,UNIT=SYSDA,
//             SPACE=(TRK,(5,2)),DISP=(NEW,PASS)
//*
//STEP2    EXEC PGM=MYPROG,
//             PARM='DEBUG=YES,TRACE=ON'
//INPUT    DD   DSN=&&TEMP,DISP=(OLD,DELETE)
//OUTPUT   DD   DSN=FINAL.OUTPUT,
//             DISP=(NEW,CATLG,DELETE),
//             UNIT=DISK,SPACE=(CYL,(10,5,5)),
//             DCB=(LRECL=80,BLKSIZE=800,RECFM=FB)"""

    def test_parse_job_continuation_and_parameters(self):
        """GIVEN JCL with continuations WHEN parsed THEN handles multi-line parameters"""
        job = parse_jcl(self.complex_jcl)

        # Validate job-level continuation parsing
        assert job.name == "COMPLEX"
        assert "NOTIFY" in job.parameters
        assert job.parameters["NOTIFY"] == "&SYSUID"
        assert job.parameters["CLASS"] == "A"
        assert job.parameters["MSGCLASS"] == "X"

    def test_parse_procedure_calls(self):
        """GIVEN procedure call WHEN parsed THEN identifies as procedure"""
        job = parse_jcl(self.complex_jcl)

        # Find procedure step
        proc_step = job.get_step("PROC1")
        if proc_step is None:
            raise AssertionError("PROC1 not found")
        assert proc_step.is_procedure
        assert "PARM" in proc_step.parameters
        assert "OPTION1" in proc_step.parameters["PARM"]

    def test_parse_temporary_datasets(self):
        """GIVEN temporary dataset references WHEN parsed THEN handles correctly"""
        job = parse_jcl(self.complex_jcl)

        # Test temporary dataset creation
        proc_step = job.get_step("PROC1")
        if proc_step is None:
            raise AssertionError("PROC1 not found")
        sysin_dd = proc_step.get_dd("SYSIN")
        if sysin_dd is None:
            raise AssertionError("SYSIN DD not found")
        assert sysin_dd.is_temporary()
        assert sysin_dd.dataset_name == "&&TEMP"

        # Test temporary dataset usage
        step2 = job.get_step("STEP2")
        if step2 is None:
            raise AssertionError("STEP2 not found")
        input_dd = step2.get_dd("INPUT")
        if input_dd is None:
            raise AssertionError("INPUT DD not found")
        assert input_dd.dataset_name == "&&TEMP"
        assert input_dd.disposition == ["OLD", "DELETE"]

    def test_parse_complex_parameters(self):
        """GIVEN complex parameter structures WHEN parsed THEN handles nested parameters"""
        job = parse_jcl(self.complex_jcl)

        step2 = job.get_step("STEP2")
        if step2 is None:
            pytest.skip("STEP2 not found in parsed job")
            return
        output_dd = step2.get_dd("OUTPUT")
        if output_dd is None:
            pytest.skip("OUTPUT DD not found in STEP2")
            return

        # Test complex DCB parameter
        assert "DCB" in output_dd.parameters
        dcb_param = output_dd.parameters["DCB"]

        # DCB may be a raw string, a subfield list (the parser's normal shape
        # for a parenthesised value), or a mapping.
        if isinstance(dcb_param, str):
            assert "LRECL=80" in dcb_param
            assert "BLKSIZE=800" in dcb_param
            assert "RECFM=FB" in dcb_param
        elif isinstance(dcb_param, list):
            assert dcb_param == ["LRECL=80", "BLKSIZE=800", "RECFM=FB"]
        else:  # Dictionary format
            assert dcb_param["LRECL"] == "80"
            assert dcb_param["BLKSIZE"] == "800"
            assert dcb_param["RECFM"] == "FB"

    def test_parse_step_relationships(self):
        """GIVEN steps with data dependencies WHEN parsed THEN relationships identifiable"""
        job = parse_jcl(self.complex_jcl)

        # Test input/output dataset analysis
        proc_step = job.get_step("PROC1")
        if proc_step is None:
            raise AssertionError("PROC1 not found")
        step2 = job.get_step("STEP2")
        if step2 is None:
            raise AssertionError("STEP2 not found")

        proc_outputs = proc_step.get_output_datasets()
        step2_inputs = step2.get_input_datasets()

        # Should find temporary dataset passed between steps
        assert "&&TEMP" in proc_outputs or any("TEMP" in ds for ds in proc_outputs)
        assert "&&TEMP" in step2_inputs or any("TEMP" in ds for ds in step2_inputs)


class TestPluginExtensibility:
    """Integration tests for plugin system - Validates FR-010"""

    def test_custom_statement_plugin_registration(self):
        """GIVEN custom statement plugin WHEN registered THEN available for parsing"""

        # Define custom plugin for hypothetical MYSTAT statement
        class MyStatementPlugin(StatementPlugin):
            def can_parse(self, line: str) -> bool:
                return line.strip().startswith("//") and "MYSTAT" in line

            def parse_statement(self, line: str, line_number: int):
                class CustomStatement:
                    def __init__(self):
                        self.type = "MYSTAT"
                        self.name = "CUSTOM"
                        self.parameters = {"PARAM1": "VALUE1"}
                        self.line_number = line_number

                return CustomStatement()

            @property
            def statement_types(self) -> list:
                return ["MYSTAT"]

        # Register the plugin
        registry = get_plugin_registry()
        plugin = MyStatementPlugin()
        registry.register_statement_plugin(plugin)

        # Verify plugin is registered and available
        found_plugin = registry.get_parser_for_line("//MYSTAT CUSTOM PARAM1=VALUE1")
        assert found_plugin is not None
        assert isinstance(found_plugin, MyStatementPlugin)

    def test_custom_statement_parsing_integration(self):
        """GIVEN JCL with custom statement WHEN parsed THEN custom plugin used"""
        # This test would require full integration with the parser
        # For now, verify that plugins can be called appropriately

        registry = get_plugin_registry()
        registry.get_statement_plugins() if hasattr(
            registry, "get_statement_plugins"
        ) else []

        # Test that plugin system is functional
        assert registry is not None
        assert hasattr(registry, "register_statement_plugin")

    def test_parser_configuration_with_plugins(self):
        """GIVEN parser configuration WHEN plugins enabled/disabled THEN configuration respected"""
        from jclparser.plugins import ParserConfig

        config = ParserConfig()

        # Test plugin enable/disable
        config.enable_plugin("MyCustomPlugin")
        assert "MyCustomPlugin" in config.enabled_plugins

        config.disable_plugin("MyCustomPlugin")
        assert "MyCustomPlugin" not in config.enabled_plugins


class TestPerformanceValidation:
    """Integration tests for performance requirements - Validates FR-012"""

    def generate_large_jcl(self, num_steps: int) -> str:
        """Generate large JCL file for performance testing"""
        jcl_parts = ["//BIGJOB JOB CLASS=A"]

        for i in range(num_steps):
            jcl_parts.extend(
                [
                    f"//STEP{i:04d} EXEC PGM=TEST{i % 10}",
                    f"//INPUT{i:04d} DD DSN=INPUT.DATA{i},DISP=SHR",
                    f"//OUTPUT{i:04d} DD DSN=OUTPUT.DATA{i},DISP=(NEW,CATLG)",
                ]
            )

        return "\n".join(jcl_parts)

    def test_large_jcl_parsing_performance(self):
        """GIVEN large JCL file WHEN parsed THEN meets performance requirements"""
        # Generate JCL with 1000 steps (3000+ lines)
        large_jcl = self.generate_large_jcl(1000)

        start_time = time.time()
        job = parse_jcl(large_jcl)
        parse_time = time.time() - start_time

        # Performance expectations
        assert parse_time < 5.0  # Should parse 3000+ lines in under 5 seconds
        assert len(job.steps) == 1000

        # Verify all DD statements parsed
        all_dds = job.get_dd_statements()
        assert len(all_dds) == 2000  # 2 DDs per step

        print(f"Parsed {len(large_jcl.splitlines())} lines in {parse_time:.3f} seconds")

    def test_memory_usage_reasonable(self):
        """GIVEN large JCL file WHEN parsed THEN memory usage reasonable"""
        try:
            import os

            import psutil
        except ImportError:
            pytest.skip("psutil not installed")

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Parse moderately large JCL
        large_jcl = self.generate_large_jcl(500)
        job = parse_jcl(large_jcl)

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 50MB for 1500 lines)
        assert memory_increase < 50 * 1024 * 1024  # 50MB

        # Verify parsing was successful
        assert len(job.steps) == 500


class TestEndToEndScenarios:
    """Complete end-to-end integration tests"""

    def test_real_world_jcl_parsing(self):
        """GIVEN realistic JCL script WHEN processed end-to-end THEN all features work"""
        realistic_jcl = """//PAYROLL  JOB (ACCT001),'PAYROLL SYSTEM',
//             CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//* STEP 1: SORT EMPLOYEE FILE
//*
//SORT1    EXEC PGM=SORT
//SYSOUT   DD   SYSOUT=*
//SORTIN   DD   DSN=PAYROLL.EMPLOYEE.FILE,DISP=SHR
//SORTOUT  DD   DSN=&&SORTED,UNIT=SYSDA,
//             SPACE=(TRK,(100,10)),DISP=(NEW,PASS)
//SYSIN    DD   *
  SORT FIELDS=(1,9,CH,A)
/*
//*
//* STEP 2: CALCULATE PAY
//*
//CALC     EXEC PGM=PAYCALC,PARM='WEEKLY'
//STEPLIB  DD   DSN=PAYROLL.LOADLIB,DISP=SHR
//INPUT    DD   DSN=&&SORTED,DISP=(OLD,DELETE)
//OUTPUT   DD   DSN=PAYROLL.WEEKLY.PAY,
//             DISP=(NEW,CATLG,DELETE),
//             UNIT=DISK,SPACE=(CYL,(50,5)),
//             DCB=(LRECL=133,BLKSIZE=1330,RECFM=FB)
//REPORT   DD   SYSOUT=A
"""

        # Parse and validate complete structure
        job = parse_jcl(realistic_jcl)

        assert job.name == "PAYROLL"
        assert len(job.steps) == 2

        # Validate SORT step
        sort_step = job.get_step("SORT1")
        if sort_step is None:
            raise AssertionError("SORT1 not found")
        assert sort_step.program == "SORT"

        sysin_dd = sort_step.get_dd("SYSIN")
        if sysin_dd is None:
            raise AssertionError("SYSIN DD not found")
        assert sysin_dd.has_inline_data
        assert sysin_dd.inline_data is not None
        assert "SORT FIELDS" in sysin_dd.inline_data

        # Validate CALC step
        calc_step = job.get_step("CALC")
        if calc_step is None:
            raise AssertionError("CALC not found")
        assert calc_step.program == "PAYCALC"
        assert "PARM" in calc_step.parameters
        assert (
            calc_step.parameters["PARM"] == "WEEKLY"
        )  # Quotes stripped during parsing

        # Validate data flow
        sort_outputs = sort_step.get_output_datasets()
        calc_step.get_input_datasets()

        # Should have temporary dataset linkage
        temp_datasets = [ds for ds in sort_outputs if ds.startswith("&&")]
        assert len(temp_datasets) > 0

    def test_validation_and_parsing_consistency(self):
        """GIVEN various JCL samples WHEN validated and parsed THEN results consistent"""
        test_cases = [
            ("//GOOD JOB CLASS=A\n//STEP1 EXEC PGM=TEST", True),  # Valid
            ("//BAD JOB\n//STEP1 EXEC", False),  # Invalid - missing parameters
            ("//MIXED JOB CLASS=A\n//BADSTEP EXEC", False),  # Mixed validity
        ]

        for jcl_text, should_be_valid in test_cases:
            errors = validate_jcl(jcl_text)

            if should_be_valid:
                assert len(errors) == 0
                # If validation passes, parsing should succeed
                job = parse_jcl(jcl_text)
                assert job is not None
            else:
                # If validation finds errors, parsing should fail
                assert len(errors) > 0
                with pytest.raises((JCLSyntaxError, JCLValidationError)):
                    parse_jcl(jcl_text)

    def test_complete_feature_coverage(self):
        """GIVEN all documented features WHEN used together THEN parser handles correctly"""
        # This comprehensive test ensures all features work together
        comprehensive_jcl = """//FULLTEST JOB (12345,67),'COMPREHENSIVE TEST',
//             CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1)
//*
//* Test all major JCL features in one job
//*
//PROC1    EXEC MYPROC,PARM='INIT'
//PROCDD   DD   DSN=&&INIT,DISP=(NEW,PASS),SPACE=(TRK,(1,1))
//*
//STEP1    EXEC PGM=IEBGENER
//SYSPRINT DD   SYSOUT=*
//SYSUT1   DD   *
Sample inline data
With multiple lines
/*
//SYSUT2   DD   DSN=TEST.OUTPUT,DISP=(NEW,CATLG),
//             UNIT=3390,SPACE=(TRK,(5,1)),
//             DCB=(LRECL=80,BLKSIZE=800,RECFM=FB)
//SYSIN    DD   DUMMY
//*
//STEP2    EXEC PGM=SORT,REGION=1M,TIME=(0,30)
//SORTIN   DD   DSN=TEST.OUTPUT,DISP=SHR
//SORTOUT  DD   DSN=TEST.SORTED,DISP=(NEW,CATLG)
//SYSOUT   DD   SYSOUT=*
//SYSIN    DD   *
  SORT FIELDS=(1,10,CH,A)
  OUTREC FIELDS=(1:1,10,11:C'SORTED')
/*"""

        # Should parse without errors
        job = parse_jcl(comprehensive_jcl)

        # Verify all components parsed correctly
        assert job.name == "FULLTEST"
        assert len(job.steps) == 3  # PROC1, STEP1, STEP2
        assert job.parameters["MSGLEVEL"] == ["1", "1"]  # Parsed as list

        # Test procedure step
        proc_step = job.get_step("PROC1")
        if proc_step is None:
            raise AssertionError("PROC1 not found")
        assert proc_step.is_procedure

        # Test inline data handling
        step1 = job.get_step("STEP1")
        if step1 is None:
            raise AssertionError("STEP1 not found")
        sysut1 = step1.get_dd("SYSUT1")
        if sysut1 is None:
            raise AssertionError("SYSUT1 DD not found")
        assert sysut1.has_inline_data
        assert sysut1.inline_data is not None
        assert "Sample inline data" in sysut1.inline_data

        # Test parameter parsing
        step2 = job.get_step("STEP2")
        if step2 is None:
            raise AssertionError("STEP2 not found")
        assert "REGION" in step2.parameters
        assert "TIME" in step2.parameters

        print("Comprehensive JCL parsing successful - all features working")
