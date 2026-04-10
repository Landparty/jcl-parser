"""
Tests targeting minor coverage gaps in errors.py and model.py.

Covers: ValidationError.__str__ with line_number, DDStatement.dcb with
list-format, DDStatement.space with list-format, Job.get_sysin_statements.
"""

from jclparser.errors import ValidationError, ErrorType
from jclparser.model import Job, Step, DDStatement


# ---------------------------------------------------------------------------
# errors.py — line 141
# ---------------------------------------------------------------------------


class TestValidationErrorStr:
    """Test ValidationError.__str__ with and without line_number."""

    def test_str_with_line_number(self):
        """__str__ includes line number when set (line 140-141)."""
        err = ValidationError(message="Something wrong", line_number=42)
        assert "Line 42" in str(err)
        assert "Something wrong" in str(err)

    def test_str_without_line_number(self):
        """__str__ returns just the message when no line_number."""
        err = ValidationError(message="Something wrong")
        assert str(err) == "Something wrong"

    def test_str_with_error_type(self):
        """ValidationError stores error_type correctly."""
        err = ValidationError(
            message="Bad structure",
            error_type=ErrorType.STRUCTURE_ERROR,
            line_number=10,
        )
        assert err.error_type == ErrorType.STRUCTURE_ERROR


# ---------------------------------------------------------------------------
# model.py — DDStatement.dcb with list-format — lines 159-163
# ---------------------------------------------------------------------------


class TestDDStatementDCBList:
    """Test DDStatement.dcb property with list-format DCB."""

    def test_dcb_list_format(self):
        """DCB as a list of strings is joined and parsed (lines 160-163)."""
        dd = DDStatement(
            name="DD1",
            parameters={"DCB": ["RECFM=FB", "LRECL=80", "BLKSIZE=27920"]},
        )
        dcb = dd.dcb
        assert dcb is not None
        assert dcb.recfm == "FB"
        assert dcb.lrecl == 80
        assert dcb.blksize == 27920

    def test_dcb_string_format(self):
        """DCB as a string is parsed normally."""
        dd = DDStatement(
            name="DD1",
            parameters={"DCB": "RECFM=VB,LRECL=255"},
        )
        dcb = dd.dcb
        assert dcb is not None
        assert dcb.recfm == "VB"
        assert dcb.lrecl == 255

    def test_dcb_absent_returns_none(self):
        """No DCB parameter returns None."""
        dd = DDStatement(name="DD1", parameters={})
        assert dd.dcb is None


# ---------------------------------------------------------------------------
# model.py — DDStatement.space with list-format — lines 185-188
# ---------------------------------------------------------------------------


class TestDDStatementSPACEList:
    """Test DDStatement.space property with list-format SPACE."""

    def test_space_list_format(self):
        """SPACE as a list of strings is joined and parsed (lines 186-188)."""
        dd = DDStatement(
            name="DD1",
            parameters={"SPACE": ["CYL", "(10,5)"]},
        )
        space = dd.space
        assert space is not None
        assert space.unit == "CYL"
        assert space.primary == 10
        assert space.secondary == 5

    def test_space_string_format(self):
        """SPACE as a string is parsed normally."""
        dd = DDStatement(
            name="DD1",
            parameters={"SPACE": "TRK,(100,50,10)"},
        )
        space = dd.space
        assert space is not None
        assert space.unit == "TRK"
        assert space.primary == 100

    def test_space_absent_returns_none(self):
        """No SPACE parameter returns None."""
        dd = DDStatement(name="DD1", parameters={})
        assert dd.space is None


# ---------------------------------------------------------------------------
# model.py — Job.get_sysin_statements — line 485
# ---------------------------------------------------------------------------


class TestJobGetSysinStatements:
    """Test Job.get_sysin_statements()."""

    def test_get_sysin_statements(self):
        """get_sysin_statements returns only SYSIN DDs across all steps (line 485)."""
        sysin = DDStatement(name="SYSIN", inline_data="SOME DATA")
        other = DDStatement(name="SYSOUT", parameters={"SYSOUT": "*"})
        step = Step(name="S1", program="IEFBR14", dd_statements=[sysin, other])
        job = Job(name="TESTJOB", steps=[step])

        result = job.get_sysin_statements()
        assert len(result) == 1
        assert result[0].name == "SYSIN"

    def test_get_sysin_statements_empty(self):
        """get_sysin_statements returns empty list when no SYSIN DDs."""
        step = Step(
            name="S1",
            program="IEFBR14",
            dd_statements=[
                DDStatement(name="SYSOUT"),
            ],
        )
        job = Job(name="TESTJOB", steps=[step])
        assert job.get_sysin_statements() == []


# ---------------------------------------------------------------------------
# Tests for the fixes added in review-improvements pass
# ---------------------------------------------------------------------------

class TestJCLParseErrorColumnNumber:
    """JCLParseError must carry and format a column_number."""

    def test_column_included_in_str_when_set(self):
        from jclparser.errors import JCLSyntaxError
        err = JCLSyntaxError("bad param", line_number=5, column_number=12)
        assert "column 12" in str(err)
        assert "Line 5" in str(err)

    def test_no_column_when_zero(self):
        from jclparser.errors import JCLSyntaxError
        err = JCLSyntaxError("bad param", line_number=5)
        assert "column" not in str(err)

    def test_check_param_balance_reports_quote_column(self):
        """_check_param_balance must include column for unclosed quote."""
        from jclparser.parser import _check_param_balance
        from jclparser.errors import JCLSyntaxError
        import pytest
        with pytest.raises(JCLSyntaxError) as exc_info:
            _check_param_balance("DSN='MY.FILE", line_number=10)
        err = exc_info.value
        assert err.column_number > 0
        # The opening quote is at position 5 (1-based)
        assert err.column_number == 5

    def test_check_param_balance_reports_paren_column(self):
        """_check_param_balance must include column for unmatched paren."""
        from jclparser.parser import _check_param_balance
        from jclparser.errors import JCLSyntaxError
        import pytest
        with pytest.raises(JCLSyntaxError) as exc_info:
            _check_param_balance("SPACE=(CYL,(10,5)", line_number=3)
        err = exc_info.value
        assert err.column_number > 0


class TestValidationErrorSeverity:
    """ValidationError must carry an ErrorSeverity and expose is_warning."""

    def test_default_severity_is_error(self):
        from jclparser.errors import ValidationError, ErrorSeverity
        err = ValidationError("something wrong")
        assert err.severity == ErrorSeverity.ERROR
        assert not err.is_warning

    def test_warning_severity(self):
        from jclparser.errors import ValidationError, ErrorSeverity
        warn = ValidationError("advisory issue", severity=ErrorSeverity.WARNING)
        assert warn.severity == ErrorSeverity.WARNING
        assert warn.is_warning

    def test_warning_str_includes_label(self):
        from jclparser.errors import ValidationError, ErrorSeverity
        warn = ValidationError("dup dd", severity=ErrorSeverity.WARNING)
        assert "WARNING" in str(warn).upper()

    def test_duplicate_dd_is_warning_in_validation(self):
        """Duplicate DD names in a step produce a WARNING, not an ERROR."""
        from jclparser.parser import parse_jcl
        from jclparser.errors import ErrorSeverity
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
//DD1     DD DSN=MY.FILE,DISP=SHR
//DD1     DD DSN=MY.OTHER,DISP=SHR
"""
        job = parse_jcl(jcl)
        errors = job.validate()
        dup_errors = [e for e in errors if "Duplicate DD" in e.message]
        assert dup_errors, "Expected a duplicate-DD validation issue"
        assert all(e.severity == ErrorSeverity.WARNING for e in dup_errors)


class TestUndefinedSymbolErrorContext:
    """UndefinedSymbolError must include the source text in its message."""

    def test_source_text_in_message(self):
        from jclparser.errors import UndefinedSymbolError
        err = UndefinedSymbolError("MYPGM", source_text="PGM=&MYPGM")
        assert "&MYPGM" in err.message
        assert "PGM=&MYPGM" in err.message

    def test_strict_substitution_includes_source(self):
        """When strict=True and symbol is undefined, error message includes source."""
        from jclparser.explosion import substitute_symbols, SymbolScope
        from jclparser.errors import UndefinedSymbolError
        import pytest
        scope = SymbolScope()
        with pytest.raises(UndefinedSymbolError) as exc_info:
            substitute_symbols("PGM=&MISSING", scope, strict=True)
        assert "PGM=&MISSING" in exc_info.value.message


class TestExplosionMaxSteps:
    """explode_job must raise JCLStructureError when max_steps is exceeded."""

    def test_max_steps_not_exceeded(self):
        from jclparser.parser import parse_jcl
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC
//S1      EXEC PGM=IEFBR14
//        PEND
//CALL1   EXEC MYPROC
//CALL2   EXEC MYPROC
"""
        job = parse_jcl(jcl)
        # 2 steps total — limit of 10 must not trigger
        exploded = job.explode(max_steps=10)
        assert exploded is not None

    def test_max_steps_exceeded_raises(self):
        from jclparser.parser import parse_jcl
        from jclparser.errors import JCLStructureError
        import pytest
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC
//S1      EXEC PGM=IEFBR14
//S2      EXEC PGM=IEFBR14
//        PEND
//CALL1   EXEC MYPROC
//CALL2   EXEC MYPROC
//CALL3   EXEC MYPROC
"""
        job = parse_jcl(jcl)
        # 3 proc calls × 2 steps each = 6 total, limit of 5 must trigger
        with pytest.raises(JCLStructureError, match="max_steps"):
            job.explode(max_steps=5)

    def test_zero_max_steps_means_unlimited(self):
        from jclparser.parser import parse_jcl
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC
//S1      EXEC PGM=IEFBR14
//        PEND
"""
        # Add many calls
        calls = "\n".join(f"//CALL{i:02d}  EXEC MYPROC" for i in range(50))
        jcl += calls + "\n"
        job = parse_jcl(jcl)
        exploded = job.explode(max_steps=0)  # 0 = unlimited
        assert exploded is not None
