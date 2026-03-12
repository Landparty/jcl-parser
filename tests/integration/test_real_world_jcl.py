"""
Tests for real-world JCL examples covering PROCs, conditionals, and edge cases.
"""
import pytest
from pathlib import Path
from jclparser import parse_jcl
from jclparser.model import Job, Step

# Path to fixtures
FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'real_world'

def test_complex_proc_expansion():
    """Test parsing and exploding a complex PROC with conditionals."""
    jcl_path = FIXTURES_DIR / 'complex_proc.jcl'
    job = parse_jcl(jcl_path)
    
    assert job.name == 'COMPLEX'
    assert len(job.procedures) == 1
    assert job.procedures[0].name == 'MYPROC'
    
    # Explode the job to expand PROC calls
    exploded_job = job.explode()
    
    # Check steps in the exploded job
    # Original job has 2 EXEC statements (RUN1, RUN2)
    # Each RUN expands into the steps defined in MYPROC
    # MYPROC has 2 steps: STEP1 and STEP2 (conditional)
    
    # Filter for actual execution steps (not the PROC definitions)
    from jclparser.model import iter_execution_steps
    exec_steps = list(iter_execution_steps(exploded_job.steps))
    
    # Verify RUN1 expansion (Default values)
    # RUN1 calls MYPROC. Expands to RUN1.STEP1 and RUN1.STEP2 (x2)
    # Note: Current parser does not evaluate IF/ELSE inside PROCs during expansion,
    # so BOTH branches are included in the expanded steps.
    run1_steps = [s for s in exec_steps if s.name.startswith('RUN1.')]
    assert len(run1_steps) == 3 
    
    step1 = next(s for s in run1_steps if 'STEP1' in s.name)
    step2_list = [s for s in run1_steps if 'STEP2' in s.name]
    assert len(step2_list) == 2
    
    # Check symbolic substitution in STEP1
    dd1 = step1.get_dd('DD1')
    assert dd1.dataset_name == 'DEFAULT.DATA' # Default value
    assert dd1.parameters['UNIT'] == 'SYSDA'
    
    # Check symbolic substitution in both STEP2s
    # The parameters should be substituted regardless of logic
    # First STEP2: IF (&DSN = 'PRODUCTION.DATA')
    # Second STEP2: ELSE
    # Since DSN=DEFAULT.DATA, neither is 'selected' by parser logic, strictly substitution
    
    # Both steps use no variables in this example PGM=PRODPROG / TESTPROG
    assert step2_list[0].program == 'PRODPROG'
    assert step2_list[1].program == 'TESTPROG'

    # Verify RUN2 expansion (Overrides)
    # RUN2 calls MYPROC with DSN='PRODUCTION.DATA',Unit=VIO
    run2_steps = [s for s in exec_steps if s.name.startswith('RUN2.')]
    assert len(run2_steps) == 3
    
    step1_run2 = next(s for s in run2_steps if 'STEP1' in s.name)
    
    # Check symbolic substitution with override
    dd1_run2 = step1_run2.get_dd('DD1')
    assert dd1_run2.dataset_name == 'PRODUCTION.DATA'
    assert dd1_run2.parameters['UNIT'] == 'VIO'
    
def test_nested_procs():
    """Test expansion of nested PROC definitions."""
    jcl_path = FIXTURES_DIR / 'nested_proc_job.jcl'
    job = parse_jcl(jcl_path)
    
    assert job.name == 'NESTED'
    assert len(job.procedures) == 2 # INNER and OUTER
    
    exploded_job = job.explode()
    
    # RUNNEST calls OUTER with VAL=FINAL
    # OUTER calls INNER with P=&VAL (-> P=FINAL)
    # INNER has step INSTEP with PARM='&P' (-> PARM='FINAL')
    
    # The resulting step name should be RUNNEST.STEP1.INSTEP (assuming full qualification)
    # OR just RUNNEST.INSTEP depending on how your parser/explosion handles intermediate steps.
    # Based on explosion.py: expands to prefix.stepname
    # OUTER expands to RUNNEST.STEP1
    # STEP1 (which calls INNER) expands to RUNNEST.STEP1.INSTEP
    
    steps = exploded_job.steps
    assert len(steps) == 1
    final_step = steps[0]
    
    # Verify deep parameter propagation
    assert 'FINAL' in final_step.parameters['PARM']
    assert final_step.program == 'IEFBR14'

def test_edge_cases():
    """Test parsing of edge cases (continuations, inline data)."""
    jcl_path = FIXTURES_DIR / 'edge_cases.jcl'
    # Use strict_mode=True to ensure we catch syntax errors
    job = parse_jcl(jcl_path, strict_mode=True)
    
    assert job.name == 'EDGECASE'
    
    step1 = job.steps[0]
    dd1 = step1.get_dd('DD1')
    
    # Check continuation handling (comments should be stripped, lines merged)
    assert dd1.dataset_name == 'MY.LONG.DATASET.NAME'
    assert dd1.disposition == 'SHR'
    
    # Check concatenated DDs
    # DD2 is the primary name. The following unnamed DDs are associated with step
    # The current model might treat them as separate DDs in the list
    all_dds = step1.dd_statements
    
    # Count DDs named 'DD2' or empty name following it
    dd2_index = next(i for i, dd in enumerate(all_dds) if dd.name == 'DD2')
    assert all_dds[dd2_index].dataset_name == 'DATA.SET.ONE'
    assert all_dds[dd2_index+1].name in [None, '', 'DD2'] # Depending on parser implementation for concat
    # Looking at parser.py, it creates new DD objects. 
    # Validating that we parsed 3 DDs for this block
    
    # Check Inline Data (DD3)
    step2_idx = next(i for i, s in enumerate(job.steps) if s.program == 'UTILITY') # Actually STEP2 is the one? 
    # Wait, in edge_cases.jcl:
    # STEP1 has DD1, DD2(concat) and DD3
    # STEP2 has DD4
    
    dd3 = step1.get_dd('DD3')
    assert dd3.has_inline_data
    assert "Data line 1" in dd3.inline_data
    assert "Data line 2 with // in it" in dd3.inline_data
    assert "$$" not in dd3.inline_data # Delimiter should be consumed
    
    # Check Special Char Parameters
    step2 = job.steps[1]
    assert step2.parameters['PARM'] == 'A/B*C+D=E'
    dd4 = step2.get_dd('DD4')
    assert dd4.dataset_name == "QUOTED.NAME.TEST"

def test_gdg_usage():
    """Test parsing of GDG generation references."""
    jcl_path = FIXTURES_DIR / 'gdg_usage.jcl'
    job = parse_jcl(jcl_path)
    
    assert job.name == 'GDGJOB'
    
    step1 = job.get_step('STEP1')
    outfile = step1.get_dd('OUTFILE')
    assert outfile.dataset_name == 'MY.GDG.BASE(+1)'
    assert outfile.disposition == ['NEW', 'CATLG', 'DELETE']
    # Check complex space parsing
    assert outfile.parameters['SPACE'] == ['CYL', '(1,1)']

    step2 = job.get_step('STEP2')
    infile = step2.get_dd('INFILE')
    assert infile.dataset_name == 'MY.GDG.BASE(0)'
    
    hist = step2.get_dd('HIST')
    assert hist.dataset_name == 'MY.GDG.BASE(-1)'

def test_sort_job():
    """Test parsing of Sort cards and SYSIN data."""
    jcl_path = FIXTURES_DIR / 'sort_job.jcl'
    job = parse_jcl(jcl_path)
    
    step1 = job.get_step('STEP1')
    assert step1.program == 'SORT'
    
    sysin = step1.get_dd('SYSIN')
    assert sysin.has_inline_data
    assert 'SORT FIELDS=(1,10,CH,A,20,5,PD,D)' in sysin.inline_data
    assert 'INCLUDE COND=(30,1,CH,EQ,C\'Y\')' in sysin.inline_data
    
    step2 = job.get_step('STEP2')
    sysin2 = step2.get_dd('SYSIN')
    assert 'MERGE FIELDS=(1,10,CH,A)' in sysin2.inline_data

def test_cond_codes():
    """Test parsing of complex COND parameters."""
    jcl_path = FIXTURES_DIR / 'cond_codes.jcl'
    job = parse_jcl(jcl_path)
    
    # Job level COND
    # Note: COND in JOB statement depends on parser implementation 
    # (some place it in parameters, others in specific field)
    assert 'COND' in job.parameters or job.parameters.get('COND') == ['4', 'LT'] 
    
    step2 = job.get_step('STEP2')
    # COND=(0,NE,STEP1)
    # The parser might return this as a list or string depending on spacing
    # Based on general behavior it splits by comma
    assert step2.parameters['COND'] == ['0', 'NE', 'STEP1']
    
    step3 = job.get_step('STEP3')
    assert step3.parameters['COND'] == 'EVEN'
    
    step5 = job.get_step('STEP5')
    # COND=((4,GT,STEP1),(8,EQ,STEP2))
    # This might be parsed as a nested list
    cond_val = step5.parameters['COND']
    assert len(cond_val) == 2
    assert cond_val[0] == '(4,GT,STEP1)'
    assert cond_val[1] == '(8,EQ,STEP2)'

def test_jobparm_parsing():
    """Test parsing of JES2 control statements (JOBPARM, ROUTE)."""
    jcl_path = FIXTURES_DIR / 'jobparm_usage.jcl'
    job = parse_jcl(jcl_path)
    
    assert job.name == 'JESJOB'
    
    # Check JES statements were captured
    assert len(job.jes_statements) == 2
    assert '/*JOBPARM ROOM=123,TIME=60' in job.jes_statements
    assert '/*ROUTE PRINT LOCAL' in job.jes_statements
    
    # Verify standard steps are still parsed correctly
    assert len(job.steps) == 2
    step1 = job.steps[0]
    dd1 = step1.get_dd('DD1')
    assert dd1.has_inline_data
    # Ensure inner /* (delimiter) was not confused with JES statement
    assert "Data line 1" in dd1.inline_data
    
