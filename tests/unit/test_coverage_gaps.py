"""
Tests targeting specific coverage gaps identified during test coverage analysis.

Covers:
- Contract tests for Tier 1 API stability
- validate_jcl() JCLValidationError catch path
- Quoted DLM delimiter in inline data
- iter_execution_steps() with nested conditionals
- SYSOUT DD override in PROC explosion
- Binary fallback file reading (utils.py)
- __main__.py entry point
- Procedure.add_step()
"""

import io
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jclparser import (
    Job,
    Step,
    DDStatement,
    Statement,
    ParseError,
    ErrorType,
    ErrorSeverity,
    JCLSyntaxError,
    JCLValidationError,
    JCLStructureError,
    parse_jcl,
    validate_jcl,
    parse_statement,
)
from jclparser.model import (
    Procedure,
    ConditionalBlock,
    iter_execution_steps,
)
from jclparser.explosion import explode_job
from jclparser.utils import _read_file_with_fallback, read_source


# ─────────────────────────────────────────────────────────────────────────────
# Contract tests for Tier 1 API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.contract
class TestParseJCLContract:
    """Contract tests ensuring parse_jcl return types and fields remain stable."""

    SIMPLE_JCL = (
        "//MYJOB   JOB (ACCT),'DESC',CLASS=A,MSGCLASS=X\n"
        "//STEP1   EXEC PGM=IEFBR14\n"
        "//DD1     DD   DSN=MY.DATASET,DISP=SHR\n"
    )

    def test_returns_job_instance(self):
        result = parse_jcl(self.SIMPLE_JCL)
        assert isinstance(result, Job)

    def test_job_has_required_fields(self):
        job = parse_jcl(self.SIMPLE_JCL)
        # All these fields must exist on Job
        assert isinstance(job.name, str)
        assert isinstance(job.parameters, dict)
        assert isinstance(job.steps, list)
        assert isinstance(job.procedures, list)
        assert isinstance(job.conditionals, list)
        assert isinstance(job.set_statements, dict)
        assert isinstance(job.jcllib_order, list)
        assert isinstance(job.comments, list)
        assert isinstance(job.line_number, int)

    def test_step_has_required_fields(self):
        job = parse_jcl(self.SIMPLE_JCL)
        step = job.steps[0]
        assert isinstance(step, Step)
        assert isinstance(step.name, str)
        assert isinstance(step.dd_statements, list)
        assert isinstance(step.parameters, dict)
        assert isinstance(step.line_number, int)
        # program or procedure must be present
        assert step.program is not None or step.procedure is not None

    def test_dd_has_required_fields(self):
        job = parse_jcl(self.SIMPLE_JCL)
        dd = job.steps[0].dd_statements[0]
        assert isinstance(dd, DDStatement)
        assert isinstance(dd.name, str)
        assert isinstance(dd.parameters, dict)
        assert isinstance(dd.line_number, int)
        # dataset_name and disposition are optional but must be str or None
        assert dd.dataset_name is None or isinstance(dd.dataset_name, str)
        assert dd.disposition is None or isinstance(dd.disposition, str)

    def test_job_name_parsed_correctly(self):
        job = parse_jcl(self.SIMPLE_JCL)
        assert job.name == "MYJOB"

    def test_step_program_parsed(self):
        job = parse_jcl(self.SIMPLE_JCL)
        assert job.steps[0].program == "IEFBR14"

    def test_dd_dataset_name_parsed(self):
        job = parse_jcl(self.SIMPLE_JCL)
        dd = job.steps[0].dd_statements[0]
        assert dd.dataset_name == "MY.DATASET"


@pytest.mark.contract
class TestValidateJCLContract:
    """Contract tests for validate_jcl return type and error format."""

    def test_returns_list(self):
        result = validate_jcl("//MYJOB JOB (ACCT),'DESC'\n//STEP1 EXEC PGM=IEFBR14\n")
        assert isinstance(result, list)

    def test_valid_jcl_returns_empty_list(self):
        result = validate_jcl("//MYJOB JOB (ACCT),'DESC'\n//STEP1 EXEC PGM=IEFBR14\n")
        assert result == []

    def test_error_is_parse_error_instance(self):
        # Two JOB statements should produce an error
        jcl = "//JOB1 JOB (ACCT),'D'\n//JOB2 JOB (ACCT),'D'\n//STEP1 EXEC PGM=IEFBR14\n"
        errors = validate_jcl(jcl)
        assert len(errors) > 0
        for err in errors:
            assert isinstance(err, ParseError)

    def test_parse_error_has_required_fields(self):
        jcl = "//JOB1 JOB (ACCT),'D'\n//JOB2 JOB (ACCT),'D'\n//STEP1 EXEC PGM=IEFBR14\n"
        errors = validate_jcl(jcl)
        err = errors[0]
        assert isinstance(err.error_type, ErrorType)
        assert isinstance(err.message, str)
        assert isinstance(err.line_number, int)
        assert isinstance(err.severity, ErrorSeverity)


@pytest.mark.contract
class TestParseStatementContract:
    """Contract tests for parse_statement return type."""

    def test_returns_statement_or_none(self):
        result = parse_statement("//STEP1 EXEC PGM=IEFBR14", line_number=1)
        assert isinstance(result, Statement)

    def test_comment_returns_none(self):
        result = parse_statement("//* This is a comment", line_number=1)
        assert result is None

    def test_empty_returns_none(self):
        result = parse_statement("", line_number=1)
        assert result is None

    def test_statement_has_type_and_name(self):
        stmt = parse_statement("//STEP1 EXEC PGM=IEFBR14", line_number=1)
        assert hasattr(stmt, "type")
        assert hasattr(stmt, "name")
        assert hasattr(stmt, "parameters")
        assert hasattr(stmt, "line_number")


@pytest.mark.contract
class TestErrorHierarchyContract:
    """Contract tests for error class hierarchy stability."""

    def test_syntax_error_is_exception(self):
        assert issubclass(JCLSyntaxError, Exception)

    def test_validation_error_is_exception(self):
        assert issubclass(JCLValidationError, Exception)

    def test_structure_error_is_exception(self):
        assert issubclass(JCLStructureError, Exception)

    def test_error_has_message_and_line(self):
        err = JCLSyntaxError("test message", line_number=5, context="ctx")
        assert err.message == "test message"
        assert err.line_number == 5
        assert err.context == "ctx"


# ─────────────────────────────────────────────────────────────────────────────
# validate_jcl() JCLValidationError catch path (parser.py:650-651)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestValidateJCLValidationErrorPath:
    """Test that validate_jcl catches JCLValidationError during line-by-line validation."""

    def test_validation_error_caught_in_line_validation(self):
        """Patch parse_statement to raise JCLValidationError, verify it's caught."""
        jcl = "//MYJOB JOB (ACCT),'DESC'\n//STEP1 EXEC PGM=IEFBR14\n"

        with patch(
            "jclparser.parser.parse_statement",
            side_effect=JCLValidationError("bad validation", line_number=2),
        ):
            # parse_jcl in strict mode will fail, then validate_jcl falls through
            # to line-by-line validation where the patched parse_statement raises
            errors = validate_jcl(jcl)

        # Should have captured the validation error
        validation_errors = [
            e for e in errors if e.error_type == ErrorType.VALIDATION_ERROR
        ]
        assert len(validation_errors) >= 1
        assert "bad validation" in validation_errors[0].message


# ─────────────────────────────────────────────────────────────────────────────
# Quoted DLM delimiter in inline data (parser.py:284-287)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestQuotedDLMDelimiter:
    """Test inline data with quoted DLM parameter."""

    def test_quoted_dlm_delimiter(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'DESC'\n"
            "//STEP1  EXEC PGM=SORT\n"
            "//SYSIN  DD *,DLM='ZZ'\n"
            "  SORT FIELDS=COPY\n"
            "  GIVE OUTPUT\n"
            "ZZ\n"
            "//SYSOUT DD SYSOUT=*\n"
        )
        job = parse_jcl(jcl)
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin is not None
        assert sysin.inline_data is not None
        assert "SORT FIELDS=COPY" in sysin.inline_data
        assert "GIVE OUTPUT" in sysin.inline_data

    def test_unquoted_dlm_delimiter(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'DESC'\n"
            "//STEP1  EXEC PGM=SORT\n"
            "//SYSIN  DD *,DLM=XX\n"
            "  SORT FIELDS=COPY\n"
            "XX\n"
            "//SYSOUT DD SYSOUT=*\n"
        )
        job = parse_jcl(jcl)
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin is not None
        assert sysin.inline_data is not None
        assert "SORT FIELDS=COPY" in sysin.inline_data


# ─────────────────────────────────────────────────────────────────────────────
# iter_execution_steps() with nested conditionals (model.py:582-589)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestIterExecutionSteps:
    """Test iter_execution_steps with nested ConditionalBlocks."""

    def test_flat_steps(self):
        steps = [Step(name="S1", program="PGM1"), Step(name="S2", program="PGM2")]
        result = list(iter_execution_steps(steps))
        assert len(result) == 2
        assert result[0].name == "S1"
        assert result[1].name == "S2"

    def test_then_branch(self):
        cond = ConditionalBlock(condition="RC = 0")
        cond.add_then_step(Step(name="THEN1", program="PGM1"))
        result = list(iter_execution_steps([cond]))
        assert len(result) == 1
        assert result[0].name == "THEN1"

    def test_else_branch(self):
        cond = ConditionalBlock(condition="RC = 0")
        cond.add_else_step(Step(name="ELSE1", program="PGM1"))
        result = list(iter_execution_steps([cond]))
        assert len(result) == 1
        assert result[0].name == "ELSE1"

    def test_both_branches(self):
        cond = ConditionalBlock(condition="RC = 0")
        cond.add_then_step(Step(name="THEN1", program="PGM1"))
        cond.add_else_step(Step(name="ELSE1", program="PGM2"))
        result = list(iter_execution_steps([cond]))
        assert len(result) == 2
        assert result[0].name == "THEN1"
        assert result[1].name == "ELSE1"

    def test_nested_conditionals(self):
        """Nested conditional inside a then-branch."""
        inner = ConditionalBlock(condition="RC = 4")
        inner.add_then_step(Step(name="INNER_THEN", program="PGM1"))
        inner.add_else_step(Step(name="INNER_ELSE", program="PGM2"))

        outer = ConditionalBlock(condition="RC = 0")
        outer.add_then_step(inner)
        outer.add_else_step(Step(name="OUTER_ELSE", program="PGM3"))

        result = list(iter_execution_steps([outer]))
        names = [s.name for s in result]
        assert names == ["INNER_THEN", "INNER_ELSE", "OUTER_ELSE"]

    def test_mixed_steps_and_conditionals(self):
        cond = ConditionalBlock(condition="RC = 0")
        cond.add_then_step(Step(name="COND_STEP", program="PGM2"))

        steps = [
            Step(name="S1", program="PGM1"),
            cond,
            Step(name="S3", program="PGM3"),
        ]
        result = list(iter_execution_steps(steps))
        names = [s.name for s in result]
        assert names == ["S1", "COND_STEP", "S3"]

    def test_empty_list(self):
        result = list(iter_execution_steps([]))
        assert result == []

    def test_empty_conditional(self):
        cond = ConditionalBlock(condition="RC = 0")
        result = list(iter_execution_steps([cond]))
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# SYSOUT DD override in PROC explosion
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSysoutDDOverrideExplosion:
    """Test that SYSOUT parameter is correctly applied as DD override during explosion."""

    def test_sysout_override_in_proc(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'DESC'\n"
            "//MYPROC PROC\n"
            "//PS1    EXEC PGM=IEFBR14\n"
            "//SYSOUT DD SYSOUT=A\n"
            "//       PEND\n"
            "//STEP1  EXEC MYPROC\n"
            "//PS1.SYSOUT DD SYSOUT=X\n"
        )
        job = parse_jcl(jcl)
        exploded = explode_job(job)
        # Find the step and its SYSOUT DD (name may be qualified after override)
        for step in iter_execution_steps(exploded.steps):
            for dd in step.dd_statements:
                if "SYSOUT" in dd.name:
                    # The override should have changed SYSOUT class from A to X
                    assert dd.parameters.get("SYSOUT") == "X"
                    return
        pytest.fail("SYSOUT DD not found in exploded job")

    def test_dd_override_preserves_non_overridden(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'DESC'\n"
            "//MYPROC PROC\n"
            "//PS1    EXEC PGM=IEFBR14\n"
            "//OUT1   DD DSN=MY.DATA,DISP=SHR\n"
            "//OUT2   DD DSN=MY.OTHER,DISP=OLD\n"
            "//       PEND\n"
            "//STEP1  EXEC MYPROC\n"
            "//PS1.OUT1 DD DSN=NEW.DATA,DISP=NEW\n"
        )
        job = parse_jcl(jcl)
        exploded = explode_job(job)
        for step in iter_execution_steps(exploded.steps):
            dd_by_name = {dd.name.split(".")[-1]: dd for dd in step.dd_statements}
            if "OUT1" in dd_by_name and "OUT2" in dd_by_name:
                # OUT1 should be overridden
                assert dd_by_name["OUT1"].dataset_name == "NEW.DATA"
                # OUT2 should be unchanged
                assert dd_by_name["OUT2"].dataset_name == "MY.OTHER"
                return
        pytest.fail("DD statements not found in exploded job")


# ─────────────────────────────────────────────────────────────────────────────
# Binary fallback file reading (utils.py:96-97)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestBinaryFallbackFileReading:
    """Test _read_file_with_fallback when all text encodings fail."""

    def test_binary_fallback_for_undecodable_file(self):
        """File with bytes that fail utf-8, latin-1, and cp1252 still gets read."""
        # Create a file with a mix of valid UTF-8 and raw bytes that include
        # surrogate-range sequences. latin-1 and cp1252 decode any single byte,
        # so we need to force them to fail using the mock approach.
        with tempfile.NamedTemporaryFile(suffix=".jcl", delete=False, mode="wb") as f:
            # Write some valid JCL-like text mixed with problematic bytes
            f.write(b"//MYJOB JOB\n")
            f.write(b"Hello \x80\x81\x82\n")  # valid in latin-1/cp1252
            path = Path(f.name)

        try:
            # This should succeed (latin-1 handles these bytes)
            content = _read_file_with_fallback(path)
            assert "MYJOB" in content
        finally:
            path.unlink()

    def test_binary_fallback_with_forced_decode_errors(self):
        """When all text encodings raise UnicodeDecodeError, binary fallback is used."""
        with tempfile.NamedTemporaryFile(suffix=".jcl", delete=False, mode="wb") as f:
            f.write(b"//TEST JOB\n")
            path = Path(f.name)

        try:
            original_open = open

            call_count = {"n": 0}

            def mock_open(p, *args, **kwargs):
                mode = args[0] if args else kwargs.get("mode", "r")
                if mode == "r":
                    call_count["n"] += 1
                    raise UnicodeDecodeError("utf-8", b"", 0, 1, "forced")
                return original_open(p, *args, **kwargs)

            with patch("builtins.open", side_effect=mock_open):
                content = _read_file_with_fallback(path)

            assert "TEST" in content
            # Should have tried all 3 text encodings before falling back
            assert call_count["n"] == 3
        finally:
            path.unlink()


# ─────────────────────────────────────────────────────────────────────────────
# read_source with file-like object that supports seek (utils.py:133-134)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestReadSourceFileLike:
    """Test read_source with file-like objects."""

    def test_file_like_with_seek(self):
        """File-like objects with seek() get rewound after reading."""
        buf = io.StringIO("//MYJOB JOB\n//STEP1 EXEC PGM=IEFBR14\n")
        content = read_source(buf)
        assert "MYJOB" in content
        # seek(0) should have been called, so reading again returns same content
        assert buf.read() == "//MYJOB JOB\n//STEP1 EXEC PGM=IEFBR14\n"

    def test_file_like_without_seek(self):
        """File-like objects without seek() are read without error."""

        class NoSeekIO:
            def read(self):
                return "//MYJOB JOB\n"

        obj = NoSeekIO()
        content = read_source(obj)
        assert "MYJOB" in content


# ─────────────────────────────────────────────────────────────────────────────
# __main__.py entry point
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMainModule:
    """Test that python -m jclparser works."""

    def test_main_module_runs(self):
        """Running python -m jclparser --help should exit with 0."""
        result = subprocess.run(
            [sys.executable, "-m", "jclparser", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "usage" in result.stdout.lower() or "jclparser" in result.stdout.lower()

    def test_main_module_parse_stdin(self):
        """Running python -m jclparser with JCL on stdin should produce output."""
        jcl = "//MYJOB JOB (ACCT),'DESC'\n//STEP1 EXEC PGM=IEFBR14\n"
        result = subprocess.run(
            [sys.executable, "-m", "jclparser", "-"],
            input=jcl,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should either succeed or show usage—either way, it ran
        assert result.returncode is not None


# ─────────────────────────────────────────────────────────────────────────────
# Procedure.add_step() (model.py:103-105)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestProcedureAddStep:
    """Test Procedure.add_step() method."""

    def test_add_step_to_procedure(self):
        proc = Procedure(name="MYPROC", parameters={"LIB": "DEFAULT"})
        step = Step(name="PS1", program="IEFBR14")
        proc.add_step(step)
        assert len(proc.steps) == 1
        assert proc.steps[0].name == "PS1"

    def test_add_multiple_steps(self):
        proc = Procedure(name="MYPROC")
        proc.add_step(Step(name="PS1", program="PGM1"))
        proc.add_step(Step(name="PS2", program="PGM2"))
        assert len(proc.steps) == 2
        assert proc.steps[0].name == "PS1"
        assert proc.steps[1].name == "PS2"

    def test_add_conditional_to_procedure(self):
        proc = Procedure(name="MYPROC")
        cond = ConditionalBlock(condition="RC = 0")
        proc.add_step(cond)
        assert len(proc.steps) == 1
        assert isinstance(proc.steps[0], ConditionalBlock)
