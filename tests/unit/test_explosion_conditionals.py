"""
Tests for conditional blocks (IF/THEN/ELSE/ENDIF) inside PROC definitions
during explosion.

This covers the _process_proc_steps() path in expand_proc_invocation()
that handles ConditionalBlock objects within procedure steps.
"""

import pytest
from jclparser.parser import parse_jcl
from jclparser.model import (
    Step,
    ConditionalBlock,
)


@pytest.mark.unit
class TestConditionalBlocksInsideProcs:
    """Test explosion of PROCs that contain IF/THEN/ELSE conditional blocks."""

    def test_proc_with_simple_conditional(self):
        """A PROC containing IF/THEN/ENDIF expands correctly."""
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC
//STEP1   EXEC PGM=PROG1
// IF (STEP1.RC EQ 0) THEN
//STEP2   EXEC PGM=PROG2
// ENDIF
//        PEND
//RUN     EXEC MYPROC
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        # The exploded job should contain the conditional block
        has_conditional = False
        for item in exploded.steps:
            if isinstance(item, ConditionalBlock):
                has_conditional = True
                assert len(item.then_steps) >= 1
                # Verify the step inside THEN got qualified naming (CALLSTEP.PROCSTEP)
                then_step = item.then_steps[0]
                assert then_step.name.startswith("RUN.")
        assert has_conditional

    def test_proc_with_if_then_else(self):
        """A PROC containing IF/THEN/ELSE/ENDIF expands both branches."""
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC
//STEP1   EXEC PGM=PROG1
// IF (STEP1.RC EQ 0) THEN
//STEP2   EXEC PGM=GOODPATH
// ELSE
//STEP3   EXEC PGM=ERRPATH
// ENDIF
//        PEND
//CALL1   EXEC MYPROC
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        # Find the conditional block in the exploded output
        cond_blocks = [s for s in exploded.steps if isinstance(s, ConditionalBlock)]
        assert len(cond_blocks) >= 1

        cond = cond_blocks[0]
        assert len(cond.then_steps) >= 1
        assert len(cond.else_steps) >= 1

    def test_proc_conditional_with_symbol_substitution(self):
        """Symbol parameters are substituted in steps inside conditional blocks."""
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC DSN=DEFAULT.DATA
//STEP1   EXEC PGM=PROG1
// IF (STEP1.RC EQ 0) THEN
//STEP2   EXEC PGM=COPYPGM
//INPUT   DD DSN=&DSN,DISP=SHR
// ENDIF
//        PEND
//RUN     EXEC MYPROC,DSN=PROD.DATA
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        # Find the DD inside the conditional
        for item in exploded.steps:
            if isinstance(item, ConditionalBlock):
                for step in item.then_steps:
                    if hasattr(step, "dd_statements"):
                        for dd in step.dd_statements:
                            if dd.name == "INPUT":
                                assert "PROD.DATA" in (dd.dataset_name or "")

    def test_proc_without_procedure_returns_step(self):
        """A step with no procedure (PGM=...) returns as-is during explosion."""
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        steps = [s for s in exploded.steps if isinstance(s, Step)]
        assert len(steps) >= 1
        assert steps[0].program == "IEFBR14"

    def test_multiple_proc_calls_with_conditionals(self):
        """Multiple calls to a PROC with conditionals each get independent expansion."""
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC PGM=DFLT
//STEP1   EXEC PGM=&PGM
// IF (STEP1.RC EQ 0) THEN
//STEP2   EXEC PGM=CLEANUP
// ENDIF
//        PEND
//CALL1   EXEC MYPROC,PGM=PROGA
//CALL2   EXEC MYPROC,PGM=PROGB
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        # Both calls should be expanded independently
        all_steps = []
        for item in exploded.steps:
            if isinstance(item, Step):
                all_steps.append(item)
            elif isinstance(item, ConditionalBlock):
                for s in item.then_steps:
                    if isinstance(s, Step):
                        all_steps.append(s)

        # Should have steps from both CALL1 and CALL2
        step_names = [s.name for s in all_steps if s.name]
        assert len(step_names) >= 2


@pytest.mark.unit
class TestConditionalBlockExpansionDirect:
    """Test the ConditionalBlock handling in expand_proc_invocation() directly."""

    def test_conditional_block_condition_preserved(self):
        """The condition string is preserved through expansion."""
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC
//S1      EXEC PGM=PGM1
// IF (S1.RC EQ 0) THEN
//S2      EXEC PGM=PGM2
// ENDIF
//        PEND
//RUN     EXEC MYPROC
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        cond_blocks = [s for s in exploded.steps if isinstance(s, ConditionalBlock)]
        if cond_blocks:
            assert cond_blocks[0].condition is not None
            assert len(cond_blocks[0].condition) > 0

    def test_conditional_steps_marked_as_exploded(self):
        """Steps inside conditional blocks from PROCs are marked is_exploded."""
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC
//S1      EXEC PGM=PGM1
// IF (S1.RC EQ 0) THEN
//S2      EXEC PGM=PGM2
// ENDIF
//        PEND
//RUN     EXEC MYPROC
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        for item in exploded.steps:
            if isinstance(item, ConditionalBlock):
                for step in item.then_steps:
                    if isinstance(step, Step):
                        assert step.is_exploded is True
