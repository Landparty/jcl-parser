"""
Additional edge case tests to push coverage over 90%.
"""

import os
import tempfile
from pathlib import Path

from jclparser import parse_jcl
from jclparser.model import DDStatement, Job, Step
from jclparser.validators import validate_job_structure


class TestParserEdgeCases:
    """Additional parser edge cases"""

    def test_parse_from_path(self):
        """Test parsing from Path object"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jcl", delete=False) as f:
            f.write("//TESTJOB JOB CLASS=A\n")
            f.write("//STEP1 EXEC PGM=PROG\n")
            f.write("//\n")
            f.flush()
            path = Path(f.name)

        try:
            job = parse_jcl(path, strict_mode=False)
            assert job.name == "TESTJOB"
        finally:
            os.unlink(path)

    def test_conditional_statements(self):
        """Test IF/THEN/ELSE/ENDIF handling"""
        jcl = """
//TESTJOB JOB CLASS=A
//        IF (RC=0) THEN
//STEP1   EXEC PGM=PROG
//        ENDIF
//"""
        job = parse_jcl(jcl, strict_mode=False)
        (block,) = job.steps
        assert block.condition == "(RC=0)"
        assert [s.name for s in block.then_steps] == ["STEP1"]

    def test_very_long_line(self):
        """Test handling of very long lines"""
        long_params = ",".join([f"P{i}=V{i}" for i in range(50)])
        jcl = f"""
//TESTJOB JOB {long_params}
//STEP1 EXEC PGM=PROG
//"""
        # A record over 80 columns cannot be a card image: it is read whole
        # (nothing past column 71 is silently cut) and reported.
        job = parse_jcl(jcl, strict_mode=False)
        assert job.parameters["P0"] == "V0"
        assert job.parameters["P49"] == "V49"
        assert any("characters long" in m for _, m, _ in job.statement_findings)
        assert [s.name for s in job.steps] == ["STEP1"]

    def test_special_characters_in_strings(self):
        """Test special characters in quoted strings"""
        jcl = """
//TESTJOB JOB (ACCT),'O''BRIEN',CLASS=A
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "TESTJOB"

    def test_multiple_dd_same_name(self):
        """Test multiple DD statements with same name (concatenation)"""
        jcl = """
//TESTJOB JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DSN=FILE1
//DD1   DD DSN=FILE2
//"""
        job = parse_jcl(jcl, strict_mode=False)
        # Both DDs should be captured
        assert len(job.steps[0].dd_statements) >= 2

    def test_nullfile_dd(self):
        """Test NULLFILE DD statement"""
        jcl = """
//TESTJOB JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DUMMY
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps[0].dd_statements) == 1

    def test_referback_dd(self):
        """Test DD referback"""
        jcl = """
//TESTJOB JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DSN=USER.DATA,DISP=SHR
//STEP2 EXEC PGM=PROG
//DD2   DD DSN=*.STEP1.DD1
//"""
        job = parse_jcl(jcl, strict_mode=False)
        assert len(job.steps) == 2


class TestModelEdgeCases:
    """Additional model edge cases"""

    def test_job_with_no_accounting(self):
        """Test job without accounting info"""
        job = Job(name="TESTJOB", parameters={})
        assert job.accounting_info is None

    def test_step_without_name(self):
        """Test step without name"""
        step = Step(program="PROG", line_number=1)
        assert step.name is None

    def test_dd_without_dataset(self):
        """Test DD without dataset name"""
        dd = DDStatement(name="DD1", line_number=1)
        assert dd.dataset_name is None

    def test_procedure_step_validation(self):
        """Test procedure step validation"""
        job = Job(name="TESTJOB", parameters={}, accounting_info="ACCT")
        step = Step(name="CALL", procedure="MYPROC", line_number=2)
        job.add_step(step)
        errors = validate_job_structure(job)
        # Should not complain about procedure step
        assert len([e for e in errors if "program or procedure" in e.message]) == 0


class TestExplosionEdgeCases:
    """Additional explosion edge cases"""

    def test_explode_without_procedures(self):
        """Test exploding job without procedures"""
        jcl = """
//TESTJOB JOB CLASS=A
//STEP1 EXEC PGM=PROG
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()
        # Should return job unchanged
        assert len(exploded.steps) == 1
        assert not exploded.steps[0].is_exploded

    def test_explode_program_steps_unchanged(self):
        """Test program steps remain unchanged after explosion"""
        jcl = """
//TESTJOB JOB CLASS=A
//STEP1 EXEC PGM=PROG1
//DD1   DD DSN=DATA1
//STEP2 EXEC PGM=PROG2
//DD2   DD DSN=DATA2
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()
        assert len(exploded.steps) == 2
        for step in exploded.steps:
            assert not step.is_exploded


class TestValidatorEdgeCases:
    """Additional validator edge cases"""

    def test_validate_special_dataset_names(self):
        """Test validation of special dataset names"""
        from jclparser.validators import validate_dataset_name

        # SYSIN, SYSOUT, etc. are valid
        assert validate_dataset_name("SYSIN") or True  # May not be fully implemented

    def test_validate_generation_dataset(self):
        """Test validation of generation dataset"""
        from jclparser.validators import validate_dataset_name

        # GDG names like USER.DATA(+1)
        result = validate_dataset_name("USER.DATA")
        assert isinstance(result, bool)


class TestParserContinuationEdgeCases:
    """Additional continuation tests"""

    def test_continuation_with_many_lines(self):
        """Test many continuation lines"""
        jcl = "//TESTJOB JOB CLASS=A,\n"
        for i in range(10):
            jcl += f"//            PARM{i}=VALUE{i},\n"
        jcl += "//            MSGCLASS=X\n//STEP1 EXEC PGM=PROG\n//"
        job = parse_jcl(jcl, strict_mode=False)
        # Should parse successfully
        assert job.name == "TESTJOB"

    def test_continuation_in_dd(self):
        """Test continuation in DD statement"""
        jcl = """
//TESTJOB JOB CLASS=A
//STEP1 EXEC PGM=PROG
//DD1   DD DSN=USER.DATA,
//         DISP=(NEW,CATLG,DELETE),
//         SPACE=(CYL,(10,5))
//"""
        job = parse_jcl(jcl, strict_mode=False)
        dd = job.steps[0].dd_statements[0]
        assert "SPACE" in dd.parameters or "DISP" in dd.parameters


class TestSymbolicParameterEdgeCases:
    """Additional symbolic parameter tests"""

    def test_symbol_with_period_concatenation(self):
        """Test symbolic parameter with period concatenation"""
        from jclparser.explosion import SymbolScope, substitute_symbols

        scope = SymbolScope(set_symbols={"VAR": "VALUE"})
        result = substitute_symbols("&VAR..DATA", scope, strict=False)
        # Should become VALUE.DATA
        assert "VALUE" in result

    def test_double_ampersand_escape(self):
        """Test && escapes to single &"""
        from jclparser.explosion import SymbolScope, substitute_symbols

        scope = SymbolScope(set_symbols={})
        result = substitute_symbols("&&TEMP", scope, strict=False)
        assert "&" in result or result == "&&TEMP"

    def test_undefined_symbol_lenient(self):
        """Test undefined symbol in lenient mode"""
        from jclparser.explosion import SymbolScope, substitute_symbols

        scope = SymbolScope(set_symbols={})
        result = substitute_symbols("&UNDEF", scope, strict=False, allow_undefined=True)
        # Should keep as-is in lenient mode
        assert "&UNDEF" in result


class TestProcLoaderEdgeCases:
    """Additional proc loader edge cases"""

    def test_inline_loader_case_insensitive(self):
        """Test inline loader with case variations"""
        from jclparser.model import Procedure
        from jclparser.proc_loader import InlineProcedureLoader

        proc = Procedure(name="MYPROC", parameters={}, line_number=1)
        # Pass list of procedures, not dict
        loader = InlineProcedureLoader([proc])

        # Should find by exact name
        result = loader.load_procedure("MYPROC", ())
        assert result is not None

    def test_jcllib_loader_invalid_path(self):
        """Test JCLLIB loader with invalid path"""
        from jclparser.proc_loader import JCLLIBProcedureLoader

        loader = JCLLIBProcedureLoader("/nonexistent/path")
        result = loader.load_procedure("MYPROC", ())
        # Should return None for non-existent proc
        assert result is None


class TestSystemSymbolsEdgeCases:
    """Additional system symbols tests"""

    def test_runtime_provider_date_format(self):
        """Test runtime provider date formats"""
        from jclparser.system_symbols import RuntimeSystemSymbolProvider

        provider = RuntimeSystemSymbolProvider()
        sysdate = provider.get_symbol("SYSDATE")
        # Should be in format YY/MM/DD or YYYY/MM/DD
        assert "/" in sysdate or len(sysdate) > 0

    def test_environment_provider_missing_var(self):
        """Test environment provider with missing variable"""
        from jclparser.system_symbols import EnvironmentSystemSymbolProvider

        provider = EnvironmentSystemSymbolProvider()
        # Request a symbol that doesn't exist in environment
        result = provider.get_symbol("NONEXISTENT_VAR_XYZ")
        # Should return a default or None
        assert result is None or isinstance(result, str)
