from jclparser.model import ConditionalBlock, Step
from jclparser.parser import parse_jcl


def test_if_then_hierarchy():
    """Test that an IF/THEN block successfully nests a Step."""
    jcl = """//MYJOB JOB (1234),'TEST',CLASS=A
//STEP1 EXEC PGM=IEFBR14
//  IF (RC=0) THEN
//STEP2 EXEC PGM=IEBGENER
//  ENDIF
//STEP3 EXEC PGM=IEFBR14
"""
    job = parse_jcl(jcl)
    assert len(job.steps) == 3
    assert isinstance(job.steps[0], Step)
    assert job.steps[0].name == "STEP1"

    assert isinstance(job.steps[1], ConditionalBlock)
    cond1 = job.steps[1]
    assert cond1.condition == "(RC=0)"
    assert len(cond1.then_steps) == 1
    assert cond1.then_steps[0].name == "STEP2"
    assert len(cond1.else_steps) == 0

    assert isinstance(job.steps[2], Step)
    assert job.steps[2].name == "STEP3"


def test_if_then_else_hierarchy():
    """Test that an IF/THEN/ELSE block successfully routes steps into branches."""
    jcl = """//MYJOB JOB (1234),'TEST',CLASS=A
//  IF (RC=4) THEN
//STEP1 EXEC PGM=IEBGENER
//STEP2 EXEC PGM=IEFBR14
//  ELSE
//STEP3 EXEC PGM=SORT
//  ENDIF
"""
    job = parse_jcl(jcl)
    assert len(job.steps) == 1

    cond = job.steps[0]
    assert isinstance(cond, ConditionalBlock)
    assert cond.condition == "(RC=4)"

    assert len(cond.then_steps) == 2
    assert cond.then_steps[0].name == "STEP1"
    assert cond.then_steps[1].name == "STEP2"

    assert len(cond.else_steps) == 1
    assert cond.else_steps[0].name == "STEP3"


def test_nested_ifs():
    """Test nested IFs are successfully tracked and nested."""
    jcl = """//MYJOB JOB (1234),'TEST',CLASS=A
//  IF (RC=0) THEN
//    IF (MAXRC=0) THEN
//STEP1 EXEC PGM=IEFBR14
//    ELSE
//STEP2 EXEC PGM=SORT
//    ENDIF
//  ENDIF
"""
    job = parse_jcl(jcl)
    assert len(job.steps) == 1

    outer_cond = job.steps[0]
    assert isinstance(outer_cond, ConditionalBlock)
    assert outer_cond.condition == "(RC=0)"

    assert len(outer_cond.then_steps) == 1
    inner_cond = outer_cond.then_steps[0]
    assert isinstance(inner_cond, ConditionalBlock)
    assert inner_cond.condition == "(MAXRC=0)"

    assert len(inner_cond.then_steps) == 1
    assert inner_cond.then_steps[0].name == "STEP1"

    assert len(inner_cond.else_steps) == 1
    assert inner_cond.else_steps[0].name == "STEP2"


def test_job_get_step_hierarchical():
    """Test Job.get_step retrieves nested steps correctly."""
    jcl = """//MYJOB JOB (1234),'TEST',CLASS=A
//  IF (RC=0) THEN
//STEP1 EXEC PGM=IEFBR14
//  ELSE
//STEP2 EXEC PGM=IEBGENER
//  ENDIF
"""
    job = parse_jcl(jcl)
    assert len(job.steps) == 1

    step1 = job.get_step("STEP1")
    assert step1 is not None and step1.name == "STEP1"

    step2 = job.get_step("STEP2")
    assert step2 is not None and step2.name == "STEP2"

    step3 = job.get_step("STEP_NOT_FOUND")
    assert step3 is None


def _only_conditional(jcl):
    job = parse_jcl(jcl)
    blocks = [s for s in job.steps if isinstance(s, ConditionalBlock)]
    assert len(blocks) == 1
    return blocks[0]


def test_named_if_label_is_not_part_of_condition():
    """``//CHK1 IF ...``: the label used to be spliced into the condition,
    leaving ``condition == 'CHK1 (S1.RC = 0)'`` and ``condition_ast`` None."""
    cond = _only_conditional(
        "//J JOB 1\n"
        "//S1 EXEC PGM=A\n"
        "//CHK1 IF (S1.RC = 0) THEN\n"
        "//S2 EXEC PGM=B\n"
        "//     ENDIF\n"
    )
    assert cond.condition == "(S1.RC = 0)"
    assert cond.condition_ast is not None
    assert [s.name for s in cond.then_steps] == ["S2"]


def test_comment_after_then_else_endif_is_dropped():
    """The comment field follows THEN / ELSE / ENDIF.  One containing an
    apostrophe used to raise ``JCLSyntaxError: Unclosed quote``; one without
    ended up inside the condition."""
    cond = _only_conditional(
        "//J JOB 1\n"
        "//S1 EXEC PGM=A\n"
        "// IF (S1.RC = 0) THEN     RUN IF S1'S OK\n"
        "//S2 EXEC PGM=B\n"
        "// ELSE           DON'T\n"
        "//S3 EXEC PGM=C\n"
        "// ENDIF          END OF S1'S CHECK\n"
    )
    assert cond.condition == "(S1.RC = 0)"
    assert cond.condition_ast is not None
    assert [s.name for s in cond.then_steps] == ["S2"]
    assert [s.name for s in cond.else_steps] == ["S3"]


def test_if_condition_continued_on_next_record():
    """A relational expression broken at a blank continues on the next record;
    ``S1.ABEND THEN`` used to be read as a THEN statement named ``S1.ABEND``,
    silently dropping half the condition."""
    cond = _only_conditional(
        "//J JOB 1\n"
        "//S1 EXEC PGM=A\n"
        "//CHK IF S1.RC = 0 |\n"
        "//      S1.ABEND THEN\n"
        "//S2 EXEC PGM=B\n"
        "//    ENDIF\n"
    )
    assert "S1.ABEND" in cond.condition
    assert type(cond.condition_ast).__name__ == "OrCondition"
    assert [s.name for s in cond.then_steps] == ["S2"]
