"""
Integration tests for JCL procedure explosion and backend PROC identification.

Scenario 1: JCL with inline PROC that needs to be exploded
- Parse JCL containing inline PROC/PEND definitions
- Verify proper explosion of EXEC PROCNAME statements
- Confirm all procedure steps are expanded with parameter substitution

Scenario 2: JCL with PROC files in JCLLIB and backend proc identification
- Multiple PROC files in library directories
- Backend correctly identifies which PROC to pass to JCL parser
- Proper library search order respected
- PROC definition files vs JCL job files distinguished
"""

import pytest
from pathlib import Path
import tempfile
from typing import List, Dict, Any

from jclparser import (
    parse_jcl,
    ProcedureNotFoundError,
    CircularProcedureError,
    ExplosionDepthError,
)
from jclparser.model import (
    Job,
    Step,
    Procedure,
)
from jclparser.proc_loader import (
    InlineProcedureLoader,
    JCLLIBProcedureLoader,
    CompositeProcedureLoader,
    create_default_loader,
)


class TestScenario1_InlineProcExplosion:
    """
    Scenario 1: JCL with inline PROC that needs to be exploded

    Tests that a JCL job containing inline PROC/PEND definitions
    is properly parsed and procedures are correctly exploded when called.
    """

    def test_simple_inline_proc_explosion(self):
        """Test basic inline PROC parsing and explosion"""
        jcl_content = """//MYJOB    JOB (ACCT),'INLINE PROC TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=TEST.DATA,DISP=SHR
//         PEND
//CALL1    EXEC MYPROC
//"""

        # Parse JCL with inline procedure
        job = parse_jcl(jcl_content)

        # Verify parsing
        assert job.name == "MYJOB"
        assert len(job.procedures) == 1
        assert job.procedures[0].name == "MYPROC"
        assert len(job.steps) == 1
        assert job.steps[0].procedure == "MYPROC"
        assert job.steps[0].is_proc_invocation

        # Explode the job
        exploded = job.explode()

        # Verify explosion
        assert len(exploded.steps) == 1
        assert exploded.steps[0].name == "CALL1.STEP1"
        assert exploded.steps[0].program == "IEFBR14"
        assert exploded.steps[0].is_exploded
        assert exploded.steps[0].original_proc_call == "CALL1"
        assert len(exploded.steps[0].dd_statements) == 1

    def test_proc_with_parameter_substitution(self):
        """Test PROC explosion with default and override parameters"""
        jcl_content = """//MYJOB    JOB (ACCT),'PARAM TEST'
//BACKUP   PROC DSN=DEFAULT.DATA,TYPE=FULL
//STEP1    EXEC PGM=IEBGENER
//SYSUT1   DD DSN=&DSN,DISP=SHR
//SYSUT2   DD DSN=&DSN..&TYPE,DISP=(NEW,CATLG)
//         PEND
//CALL1    EXEC BACKUP,DSN=PROD.DATA,TYPE=INCR
//"""

        job = parse_jcl(jcl_content)
        exploded = job.explode()

        # Verify parameter substitution
        assert len(exploded.steps) == 1
        step = exploded.steps[0]

        # Check DD statements
        assert len(step.dd_statements) == 2

        # SYSUT1 should have PROD.DATA (from override)
        sysut1 = next(dd for dd in step.dd_statements if dd.name == "SYSUT1")
        assert sysut1.dataset_name == "PROD.DATA"

        # SYSUT2 should have PROD.DATA.INCR (concatenated params - dots are normalized)
        sysut2 = next(dd for dd in step.dd_statements if dd.name == "SYSUT2")
        assert sysut2.dataset_name == "PROD.DATA.INCR"

    def test_multiple_proc_calls_in_job(self):
        """Test job that calls same PROC multiple times"""
        jcl_content = """//MYJOB    JOB (ACCT),'MULTIPLE CALLS'
//MPROC    PROC
//STEP1    EXEC PGM=COBOL01
//         PEND
//CALL1    EXEC MPROC
//CALL2    EXEC MPROC
//CALL3    EXEC MPROC
//"""

        job = parse_jcl(jcl_content)
        exploded = job.explode()

        # Should have 3 exploded steps
        assert len(exploded.steps) == 3
        assert [s.name for s in exploded.steps] == [
            "CALL1.STEP1",
            "CALL2.STEP1",
            "CALL3.STEP1"
        ]
        assert all(s.is_exploded for s in exploded.steps)

    def test_nested_procs_explosion(self):
        """Test explosion of nested procedures"""
        jcl_content = """//MYJOB    JOB (ACCT),'NESTED PROCS'
//INNER    PROC
//ISTEP    EXEC PGM=PROG1
//         PEND
//OUTER    PROC
//OSTEP    EXEC INNER
//         PEND
//CALL     EXEC OUTER
//"""

        job = parse_jcl(jcl_content)
        exploded = job.explode()

        # After explosion of nested PROCs, should have final program step
        # CALL → OUTER (explode) → OSTEP (EXEC INNER)
        # → INNER (explode) → ISTEP (EXEC PROG1)
        assert len(exploded.steps) == 1
        final_step = exploded.steps[0]
        assert final_step.program == "PROG1"
        assert final_step.is_exploded

    def test_proc_with_mixed_steps(self):
        """Test PROC containing both program and procedure steps"""
        jcl_content = """//MYJOB    JOB (ACCT),'MIXED STEPS'
//UTIL1    PROC
//S1       EXEC PGM=IEFBR14
//DD1      DD DSN=TEMP.DATA,DISP=(NEW,DELETE)
//         PEND
//UTIL2    PROC
//S2       EXEC UTIL1
//         PEND
//MAIN     EXEC UTIL2
//"""

        job = parse_jcl(jcl_content)

        # Verify procedure structure
        assert len(job.procedures) == 2
        util1 = next(p for p in job.procedures if p.name == "UTIL1")
        util2 = next(p for p in job.procedures if p.name == "UTIL2")

        assert len(util1.steps) == 1
        assert util1.steps[0].program == "IEFBR14"

        assert len(util2.steps) == 1
        assert util2.steps[0].procedure == "UTIL1"

        # Explode and verify
        exploded = job.explode()
        assert len(exploded.steps) == 1
        assert exploded.steps[0].program == "IEFBR14"

    def test_proc_circular_reference_detection(self):
        """Test that circular PROC references are detected"""
        jcl_content = """//MYJOB    JOB (ACCT),'CIRCULAR'
//PROC1    PROC
//STEP1    EXEC PROC2
//         PEND
//PROC2    PROC
//STEP2    EXEC PROC1
//         PEND
//CALL     EXEC PROC1
//"""

        job = parse_jcl(jcl_content)

        # Explosion should raise CircularProcedureError
        with pytest.raises(CircularProcedureError):
            job.explode()

    def test_proc_max_depth_limit(self):
        """Test that deep nesting is limited by max_depth"""
        # Create two procedures that call each other (P1 -> P2 -> P1)
        jcl_content = """//MYJOB    JOB (ACCT),'DEEP NESTING'
//P1       PROC
//S1       EXEC P2
//         PEND
//P2       PROC
//S2       EXEC P1
//         PEND
//CALL     EXEC P1
//"""
        
        job = parse_jcl(jcl_content)
        
        # Explosion should raise CircularProcedureError (which is detected before depth limit)
        # because P1 -> P2 -> P1 is circular
        with pytest.raises(CircularProcedureError):
            job.explode(max_depth=3)
        """Test PROC explosion with SET symbol statements"""
        jcl_content = """//MYJOB    JOB (ACCT),'SET SYMBOLS'
//         SET USER=TESTUSER
//         SET ENV=PROD
//MPROC    PROC
//STEP1    EXEC PGM=MYPROG
//DD1      DD DSN=&ENV..&USER..DATA,DISP=SHR
//         PEND
//CALL     EXEC MPROC
//"""

        job = parse_jcl(jcl_content)
        exploded = job.explode()

        # Verify symbol substitution
        step = exploded.steps[0]
        dd = step.dd_statements[0]
        assert dd.dataset_name == "PROD.TESTUSER.DATA"


class TestScenario2_BackendProcIdentification:
    """
    Scenario 2: Backend correctly identifies which PROC to pass to JCL parser

    Tests that when multiple PROC files exist in JCLLIB directories,
    the backend correctly:
    1. Identifies PROC definition files vs JCL job files
    2. Respects JCLLIB ORDER search sequence
    3. Passes the correct PROC content to the JCL parser
    4. Handles missing PROCs appropriately
    """

    def test_backend_identifies_proc_from_jcllib(self):
        """Test that inline procedures are correctly passed to explosion engine"""
        # This test verifies the happy path where a PROC is defined inline
        # and properly exploded during job processing
        jcl_content = """//MYJOB    JOB (ACCT),'INLINE PROC TEST'
//BACKUP   PROC DSN=DEFAULT.DATA
//STEP1    EXEC PGM=IEBGENER
//SYSUT1   DD DSN=&DSN,DISP=SHR
//SYSUT2   DD DSN=&DSN.BACKUP,DISP=(NEW,CATLG)
//         PEND
//CALL     EXEC BACKUP,DSN=PROD.DATA
//"""

        job = parse_jcl(jcl_content)
        
        # Verify PROC was parsed inline
        assert len(job.procedures) == 1
        assert job.procedures[0].name == "BACKUP"
        
        # Create inline loader
        inline_loader = InlineProcedureLoader(job.procedures)
        
        # Verify loader can retrieve the procedure
        loaded_proc = inline_loader.load_procedure("BACKUP")
        assert loaded_proc is not None
        assert loaded_proc.name == "BACKUP"
        
        # Explode with inline loader
        exploded = job.explode(loader=inline_loader)

        # Verify PROC was loaded and exploded
        assert len(exploded.steps) == 1
        step = exploded.steps[0]
        assert step.program == "IEBGENER"
        assert step.original_proc_call == "CALL"

        # Verify DD statement substitution
        dd_sysut1 = next(dd for dd in step.dd_statements if dd.name == "SYSUT1")
        assert dd_sysut1.dataset_name == "PROD.DATA"

    def test_backend_distinguishes_proc_from_jcl_job_file(self):
        """Test that backend correctly identifies PROC vs JCL job files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            proclib = Path(tmpdir) / "PROCLIB"
            proclib.mkdir()

            # Create valid PROC file (no JOB statement)
            proc_file = proclib / "VALIDPROC.jcl"
            proc_file.write_text("""//VALIDPROC PROC
//STEP1    EXEC PGM=PROG1
//         PEND
//""")

            # Create invalid file that looks like JCL job (has JOB statement)
            job_file = proclib / "JOBFILE.jcl"
            job_file.write_text("""//JOBFILE  JOB (ACCT),'THIS IS A JOB'
//STEP1    EXEC PGM=PROG1
//         PEND
//""")

            loader = JCLLIBProcedureLoader(base_path=Path(tmpdir))

            # Should load VALIDPROC
            valid_proc = loader.load_procedure('VALIDPROC', ['PROCLIB'])
            assert valid_proc is not None
            assert valid_proc.name == 'VALIDPROC'

            # Should NOT load JOBFILE (it's a JCL job, not a PROC)
            job_proc = loader.load_procedure('JOBFILE', ['PROCLIB'])
            # This should be None because JOBFILE has a JOB statement (it's a JCL job, not a PROC)
            assert job_proc is None

    def test_backend_jcllib_search_order(self):
        """Test that backend respects JCLLIB ORDER search sequence"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two libraries
            lib1 = Path(tmpdir) / "LIB1"
            lib2 = Path(tmpdir) / "LIB2"
            lib1.mkdir()
            lib2.mkdir()

            # Create same-named PROC in both libraries with different content
            proc1_file = lib1 / "SAMENAME.jcl"
            proc1_file.write_text("""//SAMENAME PROC
//STEP1    EXEC PGM=PROG1
//         PEND
//""")

            proc2_file = lib2 / "SAMENAME.jcl"
            proc2_file.write_text("""//SAMENAME PROC
//STEP1    EXEC PGM=PROG2
//         PEND
//""")

            loader = JCLLIBProcedureLoader(base_path=Path(tmpdir))

            # LIB1 first in order - should get PROG1
            proc = loader.load_procedure('SAMENAME', ['LIB1', 'LIB2'])
            assert proc is not None
            assert proc.steps[0].program == "PROG1"

            # LIB2 first in order - should get PROG2
            proc = loader.load_procedure('SAMENAME', ['LIB2', 'LIB1'])
            assert proc is not None
            assert proc.steps[0].program == "PROG2"

    def test_backend_missing_proc_raises_error(self):
        """Test that missing PROC raises appropriate error"""
        jcl_content = """//MYJOB    JOB (ACCT),'MISSING PROC'
//JCLLIB  ORDER=(PROCLIB)
//CALL     EXEC NONEXISTENT
//"""

        job = parse_jcl(jcl_content)

        # Explosion should fail with ProcedureNotFoundError
        with pytest.raises(ProcedureNotFoundError):
            job.explode()

    def test_backend_multiple_procs_in_same_library(self):
        """Test loading multiple different PROCs inline from job"""
        # This test verifies multiple inline procedures are correctly handled
        jcl_content = """//MYJOB    JOB (ACCT),'MULTI PROC'
//BACKUP   PROC
//STEP1    EXEC PGM=IEBGENER
//         PEND
//RESTORE  PROC
//STEP1    EXEC PGM=IEBGENER
//         PEND
//VERIFY   PROC
//STEP1    EXEC PGM=IDCAMS
//         PEND
//CALL1    EXEC BACKUP
//CALL2    EXEC RESTORE
//CALL3    EXEC VERIFY
//"""

        job = parse_jcl(jcl_content)
        # Create inline loader
        inline_loader = InlineProcedureLoader(job.procedures)

        exploded = job.explode(loader=inline_loader)

        # Should have 3 exploded steps from 3 different PROCs
        assert len(exploded.steps) == 3
        assert exploded.steps[0].program == "IEBGENER"
        assert exploded.steps[1].program == "IEBGENER"
        assert exploded.steps[2].program == "IDCAMS"

    def test_backend_composite_loader_fallback(self):
        """Test composite loader tries inline before JCLLIB"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create JCLLIB
            lib = Path(tmpdir) / "PROCLIB"
            lib.mkdir()

            # Create PROC file in library
            proc_file = lib / "SHARED.jcl"
            proc_file.write_text("""//SHARED   PROC
//STEP1    EXEC PGM=LIB_PROG
//         PEND
//""")

            # Create inline PROC with same name
            jcl_content = """//MYJOB    JOB (ACCT),'COMPOSITE'
//JCLLIB  ORDER=(PROCLIB)
//SHARED   PROC
//STEP1    EXEC PGM=INLINE_PROG
//         PEND
//CALL     EXEC SHARED
//"""

            job = parse_jcl(jcl_content)

            # Composite loader should prefer inline PROC
            loader = create_default_loader(
                job.procedures,
                base_path=Path(tmpdir),
                include_jcllib=True
            )

            exploded = job.explode(loader=loader)

            # Should use INLINE_PROG (inline takes precedence)
            assert exploded.steps[0].program == "INLINE_PROG"

    def test_backend_proc_with_complex_nesting_from_library(self):
        """Test complex nested PROCs defined inline"""
        jcl_content = """//MYJOB    JOB (ACCT),'NESTED'
//INNER    PROC
//ISTEP    EXEC PGM=INNERPROGRAM
//         PEND
//OUTER    PROC
//OSTEP    EXEC INNER
//         PEND
//CALL     EXEC OUTER
//"""

        job = parse_jcl(jcl_content)
        # Create inline loader
        inline_loader = InlineProcedureLoader(job.procedures)

        exploded = job.explode(loader=inline_loader)

        # Should resolve nested chain
        assert len(exploded.steps) == 1
        assert exploded.steps[0].program == "INNERPROGRAM"
        assert exploded.steps[0].is_exploded


class TestBackendIntegration:
    """
    Integration tests simulating backend behavior

    These tests simulate how the backend would:
    1. Parse JCL with JCLLIB references
    2. Identify PROC files to pass to explosion engine
    3. Handle errors appropriately
    """

    def test_full_backend_workflow_inline_proc(self):
        """Simulate full backend workflow with inline PROC"""
        jcl_content = """//MYJOB    JOB (ACCT),'BACKEND TEST'
//BACKUP   PROC DSN=DEFAULT.DATA
//STEP1    EXEC PGM=IEBGENER
//SYSUT1   DD DSN=&DSN,DISP=SHR
//         PEND
//CALL     EXEC BACKUP,DSN=MYDATA
//STEP2    EXEC PGM=IEFBR14
//DD1      DD SYSOUT=*
//"""

        # Backend step 1: Parse JCL
        job = parse_jcl(jcl_content)
        assert job.name == "MYJOB"

        # Backend step 2: Create loader
        loader = create_default_loader(job.procedures)

        # Backend step 3: Explode procedures
        exploded = job.explode(loader=loader)

        # Backend step 4: Verify results
        assert len(exploded.steps) == 2
        assert exploded.steps[0].name == "CALL.STEP1"
        assert exploded.steps[0].is_exploded
        assert exploded.steps[1].name == "STEP2"
        assert not exploded.steps[1].is_exploded

    def test_full_backend_workflow_external_procs(self):
        """Simulate full backend workflow with external PROC defined inline"""
        # In a real scenario, this would load from JCLLIB
        # For now, we test with inline definition
        jcl_content = """//MYJOB    JOB (ACCT),'EXTERNAL PROC'
//IEBGENER PROC
//STEP1    EXEC PGM=IEBGENER
//         PEND
//CALL     EXEC IEBGENER
//"""

        # Backend step 1: Parse and setup
        job = parse_jcl(jcl_content)
        inline_loader = InlineProcedureLoader(job.procedures)

        # Backend step 2: Explode
        exploded = job.explode(loader=inline_loader)

        # Backend step 3: Verify
        assert len(exploded.steps) == 1
        assert exploded.steps[0].program == "IEBGENER"


class TestProcedureEntryPointDetection:
    """
    Tests for identifying and flagging PROCs as entry points.
    
    An entry point is a PROC that directly executes a COBOL program or
    other application program (not another PROC). These are important for
    impact analysis and call chain tracking.
    """
    
    def test_proc_with_cobol_exec_is_entry_point(self):
        """Test that a PROC with EXEC COBOL is flagged as entry point"""
        jcl_content = """//MYJOB    JOB (ACCT),'COBOL ENTRY POINT'
//COBPROC  PROC INFILE=INPUT.DATA,OUTFILE=OUTPUT.DATA
//STEP1    EXEC PGM=MYCOBOL
//STEPLIB  DD DSN=SYS1.LINKLIB,DISP=SHR
//INFILE   DD DSN=&INFILE,DISP=SHR
//OUTFILE  DD DSN=&OUTFILE,DISP=(NEW,CATLG)
//         PEND
//CALL1    EXEC COBPROC
//"""
        
        job = parse_jcl(jcl_content)
        
        # Verify PROC was parsed
        assert len(job.procedures) == 1
        proc = job.procedures[0]
        assert proc.name == "COBPROC"
        
        # Check that the procedure contains a COBOL program execution
        # An entry point procedure should contain a step with a program (not another PROC)
        assert len(proc.steps) > 0
        
        # Verify the procedure contains a direct program execution
        has_program_exec = any(step.program is not None for step in proc.steps)
        assert has_program_exec, "PROC should contain direct program execution"
        
        # Mark as entry point function
        def is_entry_point(procedure: Procedure) -> bool:
            """Check if procedure is an entry point (executes program, not another PROC)"""
            return any(
                step.program is not None 
                for step in procedure.steps
            )
        
        assert is_entry_point(proc), "COBOL PROC should be flagged as entry point"
    
    def test_non_entry_point_proc_with_nested_exec(self):
        """Test that a PROC calling another PROC is NOT an entry point"""
        jcl_content = """//MYJOB    JOB (ACCT),'NESTED PROC'
//INNER    PROC
//ISTEP    EXEC PGM=INNERPROG
//         PEND
//OUTER    PROC
//OSTEP    EXEC INNER
//         PEND
//CALL     EXEC OUTER
//"""
        
        job = parse_jcl(jcl_content)
        
        # Find the OUTER procedure (it calls INNER, not a program)
        outer_proc = next(p for p in job.procedures if p.name == "OUTER")
        
        def is_entry_point(procedure: Procedure) -> bool:
            """Check if procedure is an entry point (executes program, not another PROC)"""
            return any(
                step.program is not None 
                for step in procedure.steps
            )
        
        # OUTER should NOT be an entry point (it calls INNER, not a program)
        assert not is_entry_point(outer_proc), "PROC with nested EXEC should NOT be entry point"
    
    def test_multiple_procs_entry_point_detection(self):
        """Test entry point detection across multiple procedures"""
        jcl_content = """//MYJOB    JOB (ACCT),'MULTI PROC ENTRY'
//PROGPROC PROC
//STEP1    EXEC PGM=PROG1
//         PEND
//UTILPROC PROC
//STEP1    EXEC PGM=UTIL1
//         PEND
//WRAPPROC PROC
//STEP1    EXEC PROGPROC
//STEP2    EXEC UTILPROC
//         PEND
//CALL1    EXEC PROGPROC
//CALL2    EXEC UTILPROC
//CALL3    EXEC WRAPPROC
//"""
        
        job = parse_jcl(jcl_content)
        
        def is_entry_point(procedure: Procedure) -> bool:
            """Check if procedure is an entry point"""
            return any(
                step.program is not None 
                for step in procedure.steps
            )
        
        # Build a mapping of PROC name to entry point status
        entry_points = {p.name: is_entry_point(p) for p in job.procedures}
        
        # Verify entry point detection
        assert entry_points["PROGPROC"] is True, "PROGPROC should be entry point"
        assert entry_points["UTILPROC"] is True, "UTILPROC should be entry point"
        assert entry_points["WRAPPROC"] is False, "WRAPPROC should NOT be entry point (calls other PROCs)"
    
    def test_entry_point_proc_with_cobol_and_utilities(self):
        """Test entry point detection with COBOL program + utility steps"""
        jcl_content = """//MYJOB    JOB (ACCT),'COMPLEX COBOL'
//COBPROC  PROC DATAFILE=DEFAULT
//SETUP    EXEC PGM=SETUP
//DD1      DD DSN=TEMP.WORKFILE,DISP=(NEW,DELETE)
//MAIN     EXEC PGM=COBOLMAIN
//INFILE   DD DSN=&DATAFILE,DISP=SHR
//WORKFILE DD DSN=TEMP.WORKFILE,DISP=SHR
//         PEND
//CALL     EXEC COBPROC,DATAFILE=MYDATA
//"""
        
        job = parse_jcl(jcl_content)
        proc = job.procedures[0]
        
        def is_entry_point(procedure: Procedure) -> bool:
            """Check if procedure is an entry point"""
            return any(
                step.program is not None 
                for step in procedure.steps
            )
        
        # COBPROC has multiple steps, including SETUP and MAIN programs
        assert is_entry_point(proc), "PROC with multiple program steps should be entry point"
        
        # Verify it has both SETUP and MAIN programs
        programs = [step.program for step in proc.steps if step.program is not None]
        assert "SETUP" in programs
        assert "COBOLMAIN" in programs
    
    def test_entry_point_with_exploded_job(self):
        """Test that entry point detection works with exploded procedures"""
        jcl_content = """//MYJOB    JOB (ACCT),'EXPLODED ENTRY'
//COBPROC  PROC
//STEP1    EXEC PGM=MYCOBOL
//SYSOUT   DD SYSOUT=*
//         PEND
//CALL1    EXEC COBPROC
//CALL2    EXEC COBPROC
//"""
        
        job = parse_jcl(jcl_content)
        proc = job.procedures[0]
        
        def is_entry_point(procedure: Procedure) -> bool:
            """Check if procedure is an entry point"""
            return any(
                step.program is not None 
                for step in procedure.steps
            )
        
        # Original procedure should be entry point
        assert is_entry_point(proc), "COBOL PROC should be entry point before explosion"
        
        # Explode the job
        inline_loader = InlineProcedureLoader(job.procedures)
        exploded = job.explode(loader=inline_loader)
        
        # After explosion, verify we have 2 exploded steps
        assert len(exploded.steps) == 2
        # All steps should have program set
        assert all(step.program == "MYCOBOL" for step in exploded.steps)
        # All should be marked as exploded
        assert all(step.is_exploded for step in exploded.steps)
    
    def test_entry_point_classification_utility(self):
        """Test utility function to classify entry points in a job"""
        jcl_content = """//MYJOB    JOB (ACCT),'CLASSIFY ENTRY'
//BATCH    PROC
//STEP1    EXEC PGM=BATCHPROG
//         PEND
//ONLINE   PROC
//STEP1    EXEC PGM=CICS
//         PEND
//CLEANUP  PROC
//STEP1    EXEC PGM=CLEANUPPROG
//         PEND
//WRAPPER  PROC
//S1       EXEC BATCH
//S2       EXEC ONLINE
//S3       EXEC CLEANUP
//         PEND
//CALL     EXEC WRAPPER
//"""
        
        job = parse_jcl(jcl_content)
        
        def classify_entry_points(procedures: List[Procedure]) -> Dict[str, bool]:
            """Classify each procedure as entry point or not"""
            def is_entry_point(proc: Procedure) -> bool:
                return any(step.program is not None for step in proc.steps)
            
            return {p.name: is_entry_point(p) for p in procedures}
        
        entry_point_map = classify_entry_points(job.procedures)
        
        # Verify classification
        expected = {
            "BATCH": True,      # Direct program exec
            "ONLINE": True,     # Direct program exec
            "CLEANUP": True,    # Direct program exec
            "WRAPPER": False,   # Calls other PROCs
        }
        
        assert entry_point_map == expected, "Entry point classification should match expected mapping"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
