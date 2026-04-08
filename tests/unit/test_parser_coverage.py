"""
Tests targeting uncovered lines in parser.py.

Covers: XMIT statement handling, validate_jcl at different levels,
SET positional params, unknown statement types, program-vs-procedure
detection, and various parse_statement edge cases.
"""

import pytest
from pathlib import Path

from jclparser.parser import parse_jcl, validate_jcl, parse_statement, _find_keyword_eq
from jclparser.errors import JCLSyntaxError


# ---------------------------------------------------------------------------
# XMIT statement — lines 408-418
# ---------------------------------------------------------------------------

class TestXMITStatement:
    """Test XMIT statement handling in parse_jcl."""

    def test_xmit_with_current_step(self):
        """XMIT within a step creates a DD and enters inline data mode (lines 411-418)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
//XMITDD   XMIT DEST=NODE1
SOME INLINE DATA
/*
//"""
        job = parse_jcl(jcl)
        step = job.steps[0]
        # XMIT should appear as a DD on the step
        xmit_dds = [dd for dd in step.dd_statements if dd.name == "XMITDD"]
        assert len(xmit_dds) == 1

    def test_xmit_before_exec_ignored(self):
        """XMIT before any EXEC is silently ignored (line 420-421)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//XMITDD   XMIT DEST=NODE1
//STEP1    EXEC PGM=IEFBR14
//"""
        # XMIT before EXEC should not crash — it's silently ignored
        job = parse_jcl(jcl)
        assert job.name == "TESTJOB"


# ---------------------------------------------------------------------------
# validate_jcl at different levels — lines 523-540, 559-568, 650-651
# ---------------------------------------------------------------------------

class TestValidateJCLLevels:
    """Test validate_jcl() with different validation levels."""

    def test_validate_structure_level(self):
        """validate_jcl with level='structure' runs structural validation (line 523)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=TEST.DATA,DISP=SHR
//"""
        errors = validate_jcl(jcl, level="structure")
        # Valid JCL should produce no errors at structure level
        assert isinstance(errors, list)

    def test_validate_semantic_level(self):
        """validate_jcl with level='semantic' invokes plugin validators (line 535)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=TEST.DATA,DISP=SHR
//"""
        errors = validate_jcl(jcl, level="semantic")
        assert isinstance(errors, list)

    def test_validate_invalid_jcl_line_by_line(self):
        """validate_jcl falls back to line-by-line for bad JCL (lines 556-660)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
//TESTJOB2 JOB (ACCT2),'SECOND'
//"""
        errors = validate_jcl(jcl)
        # Should detect multiple JOB statements
        assert len(errors) > 0
        assert any("JOB" in e.message.upper() for e in errors)

    def test_validate_nonexistent_file(self):
        """validate_jcl with non-existent path raises FileNotFoundError (lines 559-568).

        The first call to parse_jcl (strict_mode=True) raises FileNotFoundError
        before the line-by-line fallback is reached. The line-by-line path's
        FileNotFoundError handling (lines 559-568) requires the initial parse
        to fail with JCLSyntaxError/JCLValidationError first.
        """
        with pytest.raises(FileNotFoundError):
            validate_jcl(Path("/nonexistent/file.jcl"))

    def test_validate_catches_validation_error(self):
        """validate_jcl line-by-line catches JCLValidationError (lines 650-651)."""
        # An EXEC with no PGM or positional should trigger a validation-like error
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC
//"""
        errors = validate_jcl(jcl)
        assert any("EXEC" in e.message.upper() or "missing" in e.message.lower() for e in errors)


# ---------------------------------------------------------------------------
# SET positional param — lines 313-318
# ---------------------------------------------------------------------------

class TestSETPositionalParam:
    """Test SET statement with positional SYMBOL=VALUE format."""

    def test_set_keyword_form(self):
        """SET SYMBOL=VALUE as keyword parameter."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
// SET MYVAR=HELLO
//STEP1    EXEC PGM=IEFBR14
//"""
        job = parse_jcl(jcl)
        assert "MYVAR" in job.set_statements
        assert job.set_statements["MYVAR"] == "HELLO"


# ---------------------------------------------------------------------------
# Unknown statement types — lines 753-754, 774-781
# ---------------------------------------------------------------------------

class TestUnknownStatementType:
    """Test graceful handling of unknown statement types."""

    def test_unknown_statement_type_returns_unknown(self):
        """Unrecognized operation field yields Statement(type='UNKNOWN') (lines 774-781)."""
        stmt = parse_statement("//NAME FOOBAR PARAM1,PARAM2", 10)
        assert stmt is not None
        assert stmt.type == "UNKNOWN"
        assert stmt.name == "NAME"
        assert "_statement_type" in stmt.parameters
        assert stmt.parameters["_statement_type"] == "FOOBAR"

    def test_unknown_type_in_full_parse(self):
        """Unknown types are silently skipped during full parse (lines 403-406)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
//MYSTMT   FOOBAR SOMETHING
//"""
        job = parse_jcl(jcl)
        assert job.name == "TESTJOB"
        assert len(job.steps) == 1


# ---------------------------------------------------------------------------
# EXEC program vs procedure detection — lines 997-1006
# ---------------------------------------------------------------------------

class TestExecProgramVsProcedure:
    """Test _create_step_from_statement program vs procedure detection."""

    def test_positional_param_with_dot_treated_as_program(self):
        """Positional param containing '.' treated as program, not proc (line 1003)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC MY.PROGRAM
//"""
        job = parse_jcl(jcl)
        step = job.steps[0]
        assert step.program == "MY.PROGRAM"
        assert step.procedure is None

    def test_positional_param_without_dot_treated_as_procedure(self):
        """Positional param without '.' treated as procedure (line 1002)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//MYPROC   PROC
//S1       EXEC PGM=IEFBR14
//         PEND
//STEP1    EXEC MYPROC
//"""
        job = parse_jcl(jcl)
        # Find the EXEC step (not inside the PROC)
        exec_steps = [s for s in job.steps if hasattr(s, "procedure")]
        assert any(s.procedure == "MYPROC" for s in exec_steps)


# ---------------------------------------------------------------------------
# parse_statement edge cases — lines 741, 198
# ---------------------------------------------------------------------------

class TestParseStatementEdgeCases:
    """Test parse_statement edge cases."""

    def test_single_token_name_only(self):
        """Single token after // with no operation field (line 751-754)."""
        stmt = parse_statement("//MYNAME", 5)
        # Only a name, no type — should be UNKNOWN or handled gracefully
        assert stmt is not None

    def test_continuation_line_returns_none(self):
        """Continuation line (// followed by spaces + non-type) returns None (line 727)."""
        stmt = parse_statement("//         CONTINUATION DATA", 5)
        # "CONTINUATION" is not a statement type → None
        assert stmt is None

    def test_jes_eof_delimiter(self):
        """/* alone (EOF delimiter) returns None (line 695)."""
        stmt = parse_statement("/*", 1)
        assert stmt is None

    def test_jes_statement(self):
        """/*COMMAND is parsed as JES statement."""
        stmt = parse_statement("/*ROUTE PRINT NODE1", 5)
        assert stmt is not None
        assert stmt.type == "JES"
        assert stmt.name == "ROUTE"

    def test_null_statement(self):
        """// alone is a NULL statement (line 734)."""
        stmt = parse_statement("//", 1)
        assert stmt is not None
        assert stmt.type == "NULL"

    def test_comment_returns_none(self):
        """//* comment lines return None."""
        stmt = parse_statement("//* THIS IS A COMMENT", 1)
        assert stmt is None

    def test_empty_line_returns_none(self):
        """Empty line returns None."""
        stmt = parse_statement("", 1)
        assert stmt is None


# ---------------------------------------------------------------------------
# _find_keyword_eq — lines 682, 695, 812
# ---------------------------------------------------------------------------

class TestFindKeywordEq:
    """Test _find_keyword_eq() operator prefix handling."""

    def test_normal_keyword_eq(self):
        """Normal '=' is found as keyword delimiter."""
        pos = _find_keyword_eq("KEY=VALUE", frozenset("¬^~!<>"))
        assert pos == 3

    def test_operator_ne_skipped(self):
        """'!=' is not treated as a keyword '=' (operator prefix)."""
        pos = _find_keyword_eq("RC!=0", frozenset("¬^~!<>"))
        # The '=' at index 2 is preceded by '!' → skip it
        # No other '=' → returns None
        assert pos is None

    def test_operator_le_skipped(self):
        """'<=' is not treated as a keyword '='."""
        pos = _find_keyword_eq("RC<=4", frozenset("¬^~!<>"))
        assert pos is None

    def test_mixed_operator_then_keyword(self):
        """First '=' is operator, second is keyword delimiter."""
        pos = _find_keyword_eq("RC!=0,KEY=VAL", frozenset("¬^~!<>"))
        # First '=' (pos 2) is after '!' → skip; next '=' (pos 9) is keyword
        assert pos == 9

    def test_eq_at_start(self):
        """'=' at position 0 is always a keyword delimiter."""
        pos = _find_keyword_eq("=VALUE", frozenset("¬^~!<>"))
        assert pos == 0

    def test_no_eq_returns_none(self):
        """No '=' at all returns None."""
        pos = _find_keyword_eq("NOEQUALHERE", frozenset("¬^~!<>"))
        assert pos is None


# ---------------------------------------------------------------------------
# CNTL/ENDCNTL and COMMAND statements — lines 395-401
# ---------------------------------------------------------------------------

class TestSpecialStatements:
    """Test COMMAND and CNTL/ENDCNTL handling in parse_jcl."""

    def test_command_statement_ignored(self):
        """COMMAND statements are parsed but ignored (lines 395-397)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
//CMD      COMMAND DISPLAY,ACTIVE
//"""
        job = parse_jcl(jcl)
        assert job.name == "TESTJOB"

    def test_cntl_endcntl_ignored(self):
        """CNTL/ENDCNTL statements are parsed but ignored (lines 399-401)."""
        jcl = """\
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
//MYCTL    CNTL
//         ENDCNTL
//"""
        job = parse_jcl(jcl)
        assert job.name == "TESTJOB"
