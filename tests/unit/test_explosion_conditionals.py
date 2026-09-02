"""
Tests for conditional blocks (IF/THEN/ELSE/ENDIF) inside PROC definitions
during explosion.

This covers the _process_proc_steps() path in expand_proc_invocation()
that handles ConditionalBlock objects within procedure steps.
"""

import pytest

from jclparser.model import (
    ConditionalBlock,
    Step,
)
from jclparser.parser import parse_jcl


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
class TestConditionalAstPreservation:
    """Verify condition_ast is carried through all ConditionalBlock copy sites."""

    def test_condition_ast_preserved_in_proc_expansion(self):
        """condition_ast must survive PROC explosion (_process_proc_steps path)."""
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
        assert cond_blocks, "Expected at least one ConditionalBlock in exploded job"
        # condition_ast should be non-None (parse_condition produces an AST for
        # this well-formed condition).
        assert cond_blocks[0].condition_ast is not None, (
            "condition_ast was lost during PROC explosion"
        )

    def test_condition_ast_preserved_in_top_level_conditionals(self):
        """condition_ast must survive the top-level _process_steps copy path."""
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=PGM1
// IF (STEP1.RC EQ 0) THEN
//STEP2   EXEC PGM=PGM2
// ENDIF
"""
        job = parse_jcl(jcl)
        exploded = job.explode()

        cond_blocks = [s for s in exploded.steps if isinstance(s, ConditionalBlock)]
        assert cond_blocks, "Expected at least one ConditionalBlock"
        assert cond_blocks[0].condition_ast is not None, (
            "condition_ast was lost during top-level step processing"
        )

    def test_condition_ast_preserved_in_nested_proc_explosion(self):
        """condition_ast must survive the _explode_nested copy path.

        Uses a simple one-level step reference so the condition parser can
        produce an AST (three-level refs like OS1.IS1.RC are not supported by
        condition_parser and would yield None both before and after explosion).
        """
        jcl = """\
//MYJOB   JOB CLASS=A
//MYPROC  PROC
//PS1     EXEC PGM=INNER1
// IF (PS1.RC EQ 0) THEN
//PS2     EXEC PGM=OUTER2
// ENDIF
//        PEND
//CALL    EXEC MYPROC
"""
        job = parse_jcl(jcl)

        # Collect condition_ast values from the un-exploded PROC definition
        proc = job.get_procedure("MYPROC")
        assert proc is not None
        orig_ast_by_condition = {}
        for item in proc.steps:
            if isinstance(item, ConditionalBlock):
                orig_ast_by_condition[item.condition] = item.condition_ast

        exploded = job.explode()

        # Collect all ConditionalBlocks anywhere in the exploded tree
        def collect_conds(steps_list):
            conds = []
            for item in steps_list:
                if isinstance(item, ConditionalBlock):
                    conds.append(item)
                    conds.extend(collect_conds(item.then_steps))
                    conds.extend(collect_conds(item.else_steps))
            return conds

        all_conds = collect_conds(exploded.steps)
        assert all_conds, "Expected ConditionalBlocks in nested explosion"

        # Every ConditionalBlock in the explosion must carry the same
        # condition_ast object (or None) that the original PROC had.
        for cond in all_conds:
            if cond.condition in orig_ast_by_condition:
                assert cond.condition_ast is orig_ast_by_condition[cond.condition], (
                    f"condition_ast not preserved for: {cond.condition!r}"
                )


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
