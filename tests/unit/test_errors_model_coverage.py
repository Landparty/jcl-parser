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
