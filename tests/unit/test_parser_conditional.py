import pytest
from jclparser.parser import parse_jcl
from jclparser.model import ConditionalBlock, Step, Job

def test_if_then_hierarchy():
    '''Test that an IF/THEN block successfully nests a Step.'''
    jcl = '''//MYJOB JOB (1234),'TEST',CLASS=A
//STEP1 EXEC PGM=IEFBR14
//  IF (RC=0) THEN
//STEP2 EXEC PGM=IEBGENER
//  ENDIF
//STEP3 EXEC PGM=IEFBR14
'''
    job = parse_jcl(jcl)
    assert len(job.steps) == 3
    assert isinstance(job.steps[0], Step)
    assert job.steps[0].name == 'STEP1'
    
    assert isinstance(job.steps[1], ConditionalBlock)
    cond1 = job.steps[1]
    assert cond1.condition == '(RC=0)'
    assert len(cond1.then_steps) == 1
    assert cond1.then_steps[0].name == 'STEP2'
    assert len(cond1.else_steps) == 0
    
    assert isinstance(job.steps[2], Step)
    assert job.steps[2].name == 'STEP3'


def test_if_then_else_hierarchy():
    '''Test that an IF/THEN/ELSE block successfully routes steps into branches.'''
    jcl = '''//MYJOB JOB (1234),'TEST',CLASS=A
//  IF (RC=4) THEN
//STEP1 EXEC PGM=IEBGENER
//STEP2 EXEC PGM=IEFBR14
//  ELSE
//STEP3 EXEC PGM=SORT
//  ENDIF
'''
    job = parse_jcl(jcl)
    assert len(job.steps) == 1
    
    cond = job.steps[0]
    assert isinstance(cond, ConditionalBlock)
    assert cond.condition == '(RC=4)'
    
    assert len(cond.then_steps) == 2
    assert cond.then_steps[0].name == 'STEP1'
    assert cond.then_steps[1].name == 'STEP2'
    
    assert len(cond.else_steps) == 1
    assert cond.else_steps[0].name == 'STEP3'


def test_nested_ifs():
    '''Test nested IFs are successfully tracked and nested.'''
    jcl = '''//MYJOB JOB (1234),'TEST',CLASS=A
//  IF (RC=0) THEN
//    IF (MAXRC=0) THEN
//STEP1 EXEC PGM=IEFBR14
//    ELSE
//STEP2 EXEC PGM=SORT
//    ENDIF
//  ENDIF
'''
    job = parse_jcl(jcl)
    assert len(job.steps) == 1
    
    outer_cond = job.steps[0]
    assert isinstance(outer_cond, ConditionalBlock)
    assert outer_cond.condition == '(RC=0)'
    
    assert len(outer_cond.then_steps) == 1
    inner_cond = outer_cond.then_steps[0]
    assert isinstance(inner_cond, ConditionalBlock)
    assert inner_cond.condition == '(MAXRC=0)'
    
    assert len(inner_cond.then_steps) == 1
    assert inner_cond.then_steps[0].name == 'STEP1'
    
    assert len(inner_cond.else_steps) == 1
    assert inner_cond.else_steps[0].name == 'STEP2'


def test_job_get_step_hierarchical():
    '''Test Job.get_step retrieves nested steps correctly.'''
    jcl = '''//MYJOB JOB (1234),'TEST',CLASS=A
//  IF (RC=0) THEN
//STEP1 EXEC PGM=IEFBR14
//  ELSE
//STEP2 EXEC PGM=IEBGENER
//  ENDIF
'''
    job = parse_jcl(jcl)
    assert len(job.steps) == 1 
    
    step1 = job.get_step('STEP1')
    assert step1 is not None and step1.name == 'STEP1'
    
    step2 = job.get_step('STEP2')
    assert step2 is not None and step2.name == 'STEP2'

    step3 = job.get_step('STEP_NOT_FOUND')
    assert step3 is None
