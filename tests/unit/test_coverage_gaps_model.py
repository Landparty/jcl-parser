"""
Tests targeting coverage gaps in jclparser/model.py.

Covers:
- OutputStatement integer-property error paths (copies, prty, outlim, lrecl, index)
- OutputStatement simple getters (chars, fcb, flash)
- DDStatement.dcb / .space with list-form parameter values
- Step.get_dd returning None
- Step.steplib concatenation break when a named DD follows STEPLIB
- Job.prty with non-numeric value
- iter_execution_steps recursing into else_steps
"""

import pytest

from jclparser.model import (
    ConditionalBlock,
    DDStatement,
    Job,
    OutputStatement,
    Step,
    iter_execution_steps,
)


# ---------------------------------------------------------------------------
# OutputStatement — integer property error paths
# ---------------------------------------------------------------------------


class TestOutputStatementIntegerErrorPaths:
    """Each integer property must return None for non-numeric stored values."""

    def test_copies_invalid_string_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={"COPIES": "MANY"})
        assert stmt.copies is None

    def test_copies_missing_key_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.copies is None

    def test_prty_invalid_string_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={"PRTY": "HIGH"})
        assert stmt.prty is None

    def test_prty_missing_key_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.prty is None

    def test_outlim_invalid_string_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={"OUTLIM": "NOLIM"})
        assert stmt.outlim is None

    def test_outlim_missing_key_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.outlim is None

    def test_lrecl_invalid_string_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={"LRECL": "VARIABLE"})
        assert stmt.lrecl is None

    def test_lrecl_missing_key_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.lrecl is None

    def test_index_invalid_string_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={"INDEX": "LEFT"})
        assert stmt.index is None

    def test_index_missing_key_returns_none(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.index is None

    def test_copies_valid_int_string_returns_int(self):
        stmt = OutputStatement(name="OUT1", parameters={"COPIES": "3"})
        assert stmt.copies == 3

    def test_prty_valid_returns_int(self):
        stmt = OutputStatement(name="OUT1", parameters={"PRTY": "5"})
        assert stmt.prty == 5

    def test_outlim_valid_returns_int(self):
        stmt = OutputStatement(name="OUT1", parameters={"OUTLIM": "1000"})
        assert stmt.outlim == 1000

    def test_lrecl_valid_returns_int(self):
        stmt = OutputStatement(name="OUT1", parameters={"LRECL": "80"})
        assert stmt.lrecl == 80

    def test_index_valid_returns_int(self):
        stmt = OutputStatement(name="OUT1", parameters={"INDEX": "2"})
        assert stmt.index == 2


# ---------------------------------------------------------------------------
# OutputStatement — simple string getters (chars, fcb, flash)
# ---------------------------------------------------------------------------


class TestOutputStatementStringGetters:
    """chars, fcb, flash, and recfm are simple dict-lookup properties."""

    def test_chars_returns_value(self):
        stmt = OutputStatement(name="OUT1", parameters={"CHARS": "GT15"})
        assert stmt.chars == "GT15"

    def test_chars_returns_none_when_missing(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.chars is None

    def test_fcb_returns_value(self):
        stmt = OutputStatement(name="OUT1", parameters={"FCB": "FCB2"})
        assert stmt.fcb == "FCB2"

    def test_fcb_returns_none_when_missing(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.fcb is None

    def test_flash_returns_value(self):
        stmt = OutputStatement(name="OUT1", parameters={"FLASH": "OVERLAY1"})
        assert stmt.flash == "OVERLAY1"

    def test_flash_returns_none_when_missing(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.flash is None

    def test_recfm_returns_value(self):
        stmt = OutputStatement(name="OUT1", parameters={"RECFM": "FA"})
        assert stmt.recfm == "FA"

    def test_recfm_returns_none_when_missing(self):
        stmt = OutputStatement(name="OUT1", parameters={})
        assert stmt.recfm is None

    def test_chars_list_value(self):
        stmt = OutputStatement(name="OUT1", parameters={"CHARS": ["GT15", "DUMP"]})
        assert stmt.chars == ["GT15", "DUMP"]

    def test_flash_list_value(self):
        stmt = OutputStatement(name="OUT1", parameters={"FLASH": ["OVR1", "OVR2"]})
        assert stmt.flash == ["OVR1", "OVR2"]


# ---------------------------------------------------------------------------
# DDStatement — DCB and SPACE list-form parameter values
# ---------------------------------------------------------------------------


class TestDDStatementDCBListForm:
    """DDStatement.dcb parses list-format DCB values."""

    def test_dcb_list_form_is_parsed(self):
        dd = DDStatement(
            name="DD1",
            parameters={"DCB": ["RECFM=FB", "LRECL=80", "BLKSIZE=3200"]},
            line_number=1,
        )
        dcb = dd.dcb
        assert dcb is not None

    def test_dcb_string_form_still_works(self):
        dd = DDStatement(
            name="DD1",
            parameters={"DCB": "RECFM=FB,LRECL=80"},
            line_number=1,
        )
        dcb = dd.dcb
        assert dcb is not None

    def test_dcb_absent_returns_none(self):
        dd = DDStatement(name="DD1", parameters={}, line_number=1)
        assert dd.dcb is None

    def test_dcb_unexpected_type_returns_none(self):
        """DCB value that is neither str nor list → neither branch taken → None."""
        dd = DDStatement(name="DD1", parameters={"DCB": 42}, line_number=1)
        assert dd.dcb is None


class TestDDStatementSPACEListForm:
    """DDStatement.space parses list-format SPACE values."""

    def test_space_list_form_is_parsed(self):
        dd = DDStatement(
            name="DD1",
            parameters={"SPACE": ["CYL", "(10,5)"]},
            line_number=1,
        )
        space = dd.space
        assert space is not None

    def test_space_string_form_still_works(self):
        dd = DDStatement(
            name="DD1",
            parameters={"SPACE": "(CYL,(10,5))"},
            line_number=1,
        )
        space = dd.space
        assert space is not None

    def test_space_absent_returns_none(self):
        dd = DDStatement(name="DD1", parameters={}, line_number=1)
        assert dd.space is None

    def test_space_unexpected_type_returns_none(self):
        """SPACE value that is neither str nor list → neither branch taken → None."""
        dd = DDStatement(name="DD1", parameters={"SPACE": 999}, line_number=1)
        assert dd.space is None


# ---------------------------------------------------------------------------
# Step.get_dd — None path
# ---------------------------------------------------------------------------


class TestStepGetDD:
    """Step.get_dd returns None when the named DD is not present."""

    def test_get_dd_returns_none_for_unknown_name(self):
        step = Step(name="STEP1", program="IEFBR14", line_number=1)
        dd = DDStatement(name="SYSOUT", parameters={}, line_number=2)
        step.add_dd(dd)
        assert step.get_dd("NONEXISTENT") is None

    def test_get_dd_returns_correct_dd(self):
        step = Step(name="STEP1", program="IEFBR14", line_number=1)
        dd1 = DDStatement(name="INPUT", parameters={}, line_number=2)
        dd2 = DDStatement(name="OUTPUT", parameters={}, line_number=3)
        step.add_dd(dd1)
        step.add_dd(dd2)
        assert step.get_dd("INPUT") is dd1
        assert step.get_dd("OUTPUT") is dd2

    def test_get_dd_empty_step_returns_none(self):
        step = Step(name="STEP1", program="IEFBR14", line_number=1)
        assert step.get_dd("ANYTHING") is None

    def test_sysin_property_present(self):
        """Step.sysin is a convenience property backed by get_dd('SYSIN')."""
        step = Step(name="STEP1", program="IEFBR14", line_number=1)
        sysin = DDStatement(name="SYSIN", parameters={}, line_number=2)
        step.add_dd(sysin)
        assert step.sysin is sysin

    def test_sysin_property_absent(self):
        step = Step(name="STEP1", program="IEFBR14", line_number=1)
        assert step.sysin is None


# ---------------------------------------------------------------------------
# Step.steplib — concatenation break
# ---------------------------------------------------------------------------


class TestStepSteplibConcatenationBreak:
    """
    STEPLIB concatenation ends when a non-empty-named DD that is not STEPLIB
    follows the concatenation members.
    """

    def test_named_dd_after_steplib_breaks_concatenation(self):
        step = Step(name="STEP1", program="IEFBR14", line_number=1)

        steplib_dd = DDStatement(
            name="STEPLIB",
            dataset_name="USER.LOADLIB",
            parameters={},
            line_number=2,
        )
        concat_dd = DDStatement(
            name="",  # unnamed — part of concatenation
            dataset_name="SYS2.LOADLIB",
            parameters={},
            line_number=3,
        )
        other_dd = DDStatement(
            name="SYSOUT",  # named — breaks concatenation
            dataset_name="SOME.OTHER.DS",
            parameters={},
            line_number=4,
        )
        step.dd_statements = [steplib_dd, concat_dd, other_dd]

        result = step.steplib
        assert "USER.LOADLIB" in result
        assert "SYS2.LOADLIB" in result
        assert "SOME.OTHER.DS" not in result

    def test_steplib_without_concatenation(self):
        step = Step(name="STEP1", program="IEFBR14", line_number=1)
        steplib_dd = DDStatement(
            name="STEPLIB",
            dataset_name="USER.LOADLIB",
            parameters={},
            line_number=2,
        )
        step.dd_statements = [steplib_dd]
        assert step.steplib == ["USER.LOADLIB"]

    def test_steplib_missing_returns_empty_list(self):
        step = Step(name="STEP1", program="IEFBR14", line_number=1)
        sysout = DDStatement(name="SYSOUT", parameters={}, line_number=2)
        step.dd_statements = [sysout]
        assert step.steplib == []


# ---------------------------------------------------------------------------
# Job.prty — error path
# ---------------------------------------------------------------------------


class TestJobPrty:
    """Job.prty returns None for non-numeric PRTY values."""

    def test_prty_invalid_returns_none(self):
        job = Job(name="MYJOB", parameters={"PRTY": "URGENT"}, accounting_info="")
        assert job.prty is None

    def test_prty_valid_returns_int(self):
        job = Job(name="MYJOB", parameters={"PRTY": "8"}, accounting_info="")
        assert job.prty == 8

    def test_prty_missing_returns_none(self):
        job = Job(name="MYJOB", parameters={}, accounting_info="")
        assert job.prty is None


# ---------------------------------------------------------------------------
# iter_execution_steps — else_steps branch
# ---------------------------------------------------------------------------


class TestIterExecutionSteps:
    """iter_execution_steps must recurse into else_steps."""

    def test_else_steps_are_yielded(self):
        then_step = Step(name="THEN1", program="PGM1", line_number=2)
        else_step = Step(name="ELSE1", program="PGM2", line_number=4)

        block = ConditionalBlock(condition="RC = 0", line_number=1)
        block.then_steps = [then_step]
        block.else_steps = [else_step]

        result = list(iter_execution_steps([block]))
        assert then_step in result
        assert else_step in result

    def test_nested_conditional_in_else(self):
        inner_step = Step(name="INNER", program="PGM3", line_number=6)
        inner_block = ConditionalBlock(condition="RC = 4", line_number=5)
        inner_block.then_steps = [inner_step]

        outer_block = ConditionalBlock(condition="RC = 0", line_number=1)
        outer_block.then_steps = []
        outer_block.else_steps = [inner_block]

        result = list(iter_execution_steps([outer_block]))
        assert inner_step in result

    def test_plain_steps_pass_through(self):
        step = Step(name="STEP1", program="PGM1", line_number=1)
        result = list(iter_execution_steps([step]))
        assert result == [step]

    def test_mixed_list(self):
        step1 = Step(name="S1", program="P1", line_number=1)
        step2 = Step(name="S2", program="P2", line_number=5)
        block = ConditionalBlock(condition="RC = 0", line_number=2)
        block.then_steps = [step2]
        block.else_steps = []

        result = list(iter_execution_steps([step1, block]))
        assert step1 in result
        assert step2 in result

    def test_conditional_block_followed_by_step(self):
        """ConditionalBlock as non-last element triggers loop-continue branch."""
        block_step = Step(name="BS", program="PB", line_number=2)
        block = ConditionalBlock(condition="RC = 0", line_number=1)
        block.then_steps = [block_step]
        block.else_steps = []

        tail_step = Step(name="TAIL", program="PT", line_number=5)

        # block is FIRST so the loop must continue to tail_step afterwards
        result = list(iter_execution_steps([block, tail_step]))
        assert block_step in result
        assert tail_step in result
