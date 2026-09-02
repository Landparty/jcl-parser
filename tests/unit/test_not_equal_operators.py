"""Tests for all real-world 'not equal' character variants in JCL.

IBM z/OS JCL supports these 'not equal' representations in IF/THEN/ELSE conditions:
  - NE     keyword form
  - ¬=     U+00AC NOT SIGN + equals (standard EBCDIC form)
  - ^=     caret + equals (ASCII substitute for ¬)
  - ~=     tilde + equals (ASCII substitute for ¬)

Non-standard but encountered in the wild:
  - !=     exclamation + equals
  - <>     angle brackets (less-than + greater-than)

COND parameters on EXEC only use the keyword form: NE
"""

import pytest

from jclparser.model import ConditionalBlock
from jclparser.parser import parse_jcl


class TestNotEqualInIfConditions:
    """Test not-equal operators in IF/THEN/ELSE conditions."""

    @pytest.mark.parametrize(
        "operator,label",
        [
            ("NE", "NE keyword"),
            ("\u00ac=", "¬= NOT SIGN"),
            ("^=", "^= caret"),
            ("~=", "~= tilde"),
            ("!=", "!= exclamation"),
            ("<>", "<> angle brackets"),
        ],
    )
    def test_not_equal_in_parenthesized_if(self, operator, label):
        """Parenthesized IF conditions preserve not-equal operators."""
        jcl = f"""//MYJOB JOB (1234),'TEST'
//  IF (RC {operator} 0) THEN
//STEP1 EXEC PGM=IEFBR14
//  ENDIF
"""
        job = parse_jcl(jcl)
        assert len(job.steps) == 1
        cond = job.steps[0]
        assert isinstance(cond, ConditionalBlock)
        assert operator in cond.condition, (
            f"{label}: operator '{operator}' not found in condition '{cond.condition}'"
        )

    @pytest.mark.parametrize(
        "operator,label",
        [
            ("NE", "NE keyword"),
            ("\u00ac=", "¬= NOT SIGN"),
            ("^=", "^= caret"),
            ("~=", "~= tilde"),
            ("!=", "!= exclamation"),
            ("<>", "<> angle brackets"),
        ],
    )
    def test_not_equal_in_unparenthesized_if(self, operator, label):
        """Unparenthesized IF conditions preserve not-equal operators."""
        jcl = f"""//MYJOB JOB (1234),'TEST'
//  IF RC {operator} 0 THEN
//STEP1 EXEC PGM=IEFBR14
//  ENDIF
"""
        job = parse_jcl(jcl)
        assert len(job.steps) == 1
        cond = job.steps[0]
        assert isinstance(cond, ConditionalBlock)
        assert operator in cond.condition, (
            f"{label}: operator '{operator}' not found in condition '{cond.condition}'"
        )

    def test_not_equal_with_step_reference(self):
        """Not-equal with step name reference in IF condition."""
        jcl = """//MYJOB JOB (1234),'TEST'
//STEP1 EXEC PGM=IEFBR14
//  IF (STEP1.RC \u00ac= 0) THEN
//STEP2 EXEC PGM=IEFBR14
//  ENDIF
"""
        job = parse_jcl(jcl)
        cond = job.steps[1]
        assert isinstance(cond, ConditionalBlock)
        assert "\u00ac=" in cond.condition

    def test_not_equal_in_compound_condition(self):
        """Not-equal in compound boolean expression."""
        jcl = """//MYJOB JOB (1234),'TEST'
//  IF (RC ^= 0) AND (RC ^= 4) THEN
//STEP1 EXEC PGM=IEFBR14
//  ENDIF
"""
        job = parse_jcl(jcl)
        cond = job.steps[0]
        assert isinstance(cond, ConditionalBlock)
        assert "^=" in cond.condition

    def test_not_equal_with_else_branch(self):
        """Not-equal IF with ELSE branch."""
        jcl = """//MYJOB JOB (1234),'TEST'
//  IF (RC ~= 0) THEN
//STEP1 EXEC PGM=IEFBR14
//  ELSE
//STEP2 EXEC PGM=IEBGENER
//  ENDIF
"""
        job = parse_jcl(jcl)
        cond = job.steps[0]
        assert isinstance(cond, ConditionalBlock)
        assert "~=" in cond.condition
        assert len(cond.then_steps) == 1
        assert len(cond.else_steps) == 1

    def test_nested_not_equal_conditions(self):
        """Nested IF blocks with different not-equal operators."""
        jcl = """//MYJOB JOB (1234),'TEST'
//  IF (RC \u00ac= 0) THEN
//    IF (MAXRC ^= 4) THEN
//STEP1 EXEC PGM=IEFBR14
//    ENDIF
//  ENDIF
"""
        job = parse_jcl(jcl)
        outer = job.steps[0]
        assert isinstance(outer, ConditionalBlock)
        assert "\u00ac=" in outer.condition
        inner = outer.then_steps[0]
        assert isinstance(inner, ConditionalBlock)
        assert "^=" in inner.condition


class TestNotEqualInCondParameter:
    """Test NE keyword in COND parameters on EXEC statements."""

    def test_cond_ne_simple(self):
        """COND=(0,NE) on EXEC."""
        jcl = """//MYJOB JOB (1234),'TEST'
//STEP1 EXEC PGM=IEFBR14,COND=(0,NE)
"""
        job = parse_jcl(jcl)
        assert job.steps[0].parameters["COND"] == ["0", "NE"]

    def test_cond_ne_with_stepref(self):
        """COND=(0,NE,STEP1) on EXEC."""
        jcl = """//MYJOB JOB (1234),'TEST'
//STEP1 EXEC PGM=IEFBR14
//STEP2 EXEC PGM=IEFBR14,COND=(0,NE,STEP1)
"""
        job = parse_jcl(jcl)
        assert job.steps[1].parameters["COND"] == ["0", "NE", "STEP1"]

    def test_cond_ne_multiple_conditions(self):
        """COND with multiple conditions including NE."""
        jcl = """//MYJOB JOB (1234),'TEST'
//STEP1 EXEC PGM=IEFBR14
//STEP2 EXEC PGM=IEFBR14,COND=((0,NE,STEP1),(4,LT))
"""
        job = parse_jcl(jcl)
        cond = job.steps[1].parameters["COND"]
        # Nested COND values are stored as sub-strings within the list
        assert any("NE" in str(c) for c in cond)
        assert any("LT" in str(c) for c in cond)


class TestNotEqualDoesNotBreakKeywordParams:
    """Ensure the operator-aware '=' handling doesn't break normal keyword parameters."""

    def test_dsn_param(self):
        """Standard DSN= keyword parameter still works."""
        jcl = """//MYJOB JOB (1234),'TEST'
//STEP1 EXEC PGM=IEFBR14
//DD1   DD DSN=MY.DATASET,DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["DSN"] == "MY.DATASET"
        assert dd.parameters["DISP"] == "SHR"

    def test_exec_params(self):
        """EXEC parameters with = delimiter still work."""
        jcl = """//MYJOB JOB (1234),'TEST'
//STEP1 EXEC PGM=IEFBR14,REGION=4M,TIME=1440
"""
        job = parse_jcl(jcl)
        step = job.steps[0]
        assert step.program == "IEFBR14"
        assert step.parameters.get("REGION") == "4M"
        assert step.parameters.get("TIME") == "1440"

    def test_job_params(self):
        """JOB parameters with = delimiter still work."""
        jcl = """//MYJOB JOB (1234),'TEST',CLASS=A,MSGCLASS=X
//STEP1 EXEC PGM=IEFBR14
"""
        job = parse_jcl(jcl)
        assert job.parameters.get("CLASS") == "A"
        assert job.parameters.get("MSGCLASS") == "X"
