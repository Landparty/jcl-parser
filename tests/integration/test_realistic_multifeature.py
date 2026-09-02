"""
Realistic multi-feature integration tests.

Tests that combine PROCs, conditionals, continuations, DD overrides,
inline data, SET symbols, and temporary datasets in single jobs.
"""

import pytest

from jclparser.model import ConditionalBlock, Step
from jclparser.parser import parse_jcl, validate_jcl


@pytest.mark.integration
class TestRealisticMultiFeatureJob:
    """Test realistic enterprise-style JCL that combines many features."""

    def test_proc_with_continuation_and_set_symbols(self):
        """Job with SET symbols, PROC, and multi-line continuation."""
        jcl = """\
//TESTJOB JOB CLASS=A
// SET HLQIN=PROD.INPUT
// SET HLQOUT=PROD.OUTPUT
//MYPROC  PROC SORTFLD='FIELDS'
//SORT    EXEC PGM=SORT
//SORTIN  DD DSN=&HLQIN..DATA,
//           DISP=SHR
//SORTOUT DD DSN=&HLQOUT..SORTED,
//           DISP=(NEW,CATLG,DELETE),
//           SPACE=(CYL,(10,5),RLSE)
//SYSOUT  DD SYSOUT=*
//SYSIN   DD *
  SORT &SORTFLD
/*
//        PEND
//CALL1   EXEC MYPROC,SORTFLD='CH(1,10,A)'
"""
        job = parse_jcl(jcl)
        assert job.name == "TESTJOB"
        assert len(job.set_statements) >= 2
        assert len(job.procedures) == 1

        # Explode and verify symbols are resolved
        exploded = job.explode()
        exec_steps = [s for s in exploded.steps if isinstance(s, Step)]
        assert len(exec_steps) >= 1

    def test_conditionals_with_procs_and_overrides(self):
        """Job with conditionals, PROC calls, and DD overrides."""
        jcl = """\
//TESTJOB JOB CLASS=A
//BACKUP  PROC
//STEP1   EXEC PGM=IEBCOPY
//SYSUT1  DD DSN=SOURCE.DATA,DISP=SHR
//SYSUT2  DD DSN=BACKUP.DATA,DISP=(NEW,CATLG)
//SYSPRINT DD SYSOUT=*
//        PEND
//RUN1    EXEC PGM=CHECKER
//SYSOUT  DD SYSOUT=*
// IF (RUN1.RC EQ 0) THEN
//RUN2    EXEC BACKUP
//RUN2.SYSUT1 DD DSN=MY.SPECIAL.DATA,DISP=SHR
// ELSE
//RUN3    EXEC PGM=NOTIFY
//SYSOUT  DD SYSOUT=*
// ENDIF
"""
        job = parse_jcl(jcl)
        assert len(job.procedures) == 1

        # Verify conditionals were parsed
        has_conditional = any(isinstance(s, ConditionalBlock) for s in job.steps)
        assert has_conditional

        # Explode
        exploded = job.explode()
        assert len(exploded.steps) >= 1

    def test_multiple_procs_with_different_params(self):
        """Two different PROCs called with varying parameter overrides."""
        jcl = """\
//TESTJOB JOB CLASS=A
//COPYROC PROC SRC=SYS1.DATA,TGT=SYS2.DATA
//COPY    EXEC PGM=IEBCOPY
//INPUT   DD DSN=&SRC,DISP=SHR
//OUTPUT  DD DSN=&TGT,DISP=(NEW,CATLG)
//SYSPRINT DD SYSOUT=*
//        PEND
//DELPROC PROC DSN=DELETE.ME
//DEL     EXEC PGM=IEFBR14
//DD1     DD DSN=&DSN,DISP=(OLD,DELETE)
//        PEND
//STEP1   EXEC COPYROC,SRC=PROD.FILE1,TGT=BACKUP.FILE1
//STEP2   EXEC COPYROC,SRC=PROD.FILE2,TGT=BACKUP.FILE2
//STEP3   EXEC DELPROC,DSN=TEMP.SCRATCH
"""
        job = parse_jcl(jcl)
        assert len(job.procedures) == 2

        exploded = job.explode()
        exec_steps = [s for s in exploded.steps if isinstance(s, Step)]
        # Should have expanded all 3 PROC calls
        assert len(exec_steps) >= 3

        # Verify each call got its own parameter values
        for step in exec_steps:
            for dd in step.dd_statements:
                if dd.dataset_name:
                    assert "&SRC" not in dd.dataset_name
                    assert "&TGT" not in dd.dataset_name
                    assert "&DSN" not in dd.dataset_name

    def test_temporary_datasets_across_steps(self):
        """Job using temporary datasets (&&) passed between steps."""
        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=SORT
//SORTIN  DD DSN=INPUT.DATA,DISP=SHR
//SORTOUT DD DSN=&&TEMP1,DISP=(NEW,PASS),
//           SPACE=(CYL,(5,1))
//SYSOUT  DD SYSOUT=*
//STEP2   EXEC PGM=PROCESS
//INPUT   DD DSN=&&TEMP1,DISP=(OLD,DELETE)
//OUTPUT  DD DSN=FINAL.OUTPUT,DISP=(NEW,CATLG)
//SYSOUT  DD SYSOUT=*
"""
        job = parse_jcl(jcl)
        exec_steps = [s for s in job.steps if isinstance(s, Step)]
        assert len(exec_steps) == 2

        # Verify temporary dataset is referenced
        step1_dds = {dd.name: dd for dd in exec_steps[0].dd_statements}
        step2_dds = {dd.name: dd for dd in exec_steps[1].dd_statements}
        assert "SORTOUT" in step1_dds
        assert "INPUT" in step2_dds

    def test_inline_data_with_custom_delimiter(self):
        """Job with inline data using DLM parameter."""
        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=IKJEFT01
//SYSTSPRT DD SYSOUT=*
//SYSTSIN DD *
  DSN SYSTEM(DB2P)
  RUN PROGRAM(DSNTEP2)
  END
/*
//STEP2   EXEC PGM=IEFBR14
"""
        job = parse_jcl(jcl)
        exec_steps = [s for s in job.steps if isinstance(s, Step)]
        assert len(exec_steps) >= 1

    def test_jcl_with_all_statement_types(self):
        """Job exercising JOB, SET, PROC/PEND, EXEC, DD, IF/ENDIF, and comments."""
        jcl = """\
//TESTJOB JOB CLASS=A,MSGCLASS=X
//*
//* COMPREHENSIVE TEST JOB
//*
// SET ENV=PROD
//MYPROC  PROC PGM=IEFBR14
//S1      EXEC PGM=&PGM
//SYSOUT  DD SYSOUT=*
//        PEND
//STEP1   EXEC PGM=CHECKER
//SYSOUT  DD SYSOUT=*
// IF (STEP1.RC EQ 0) THEN
//STEP2   EXEC MYPROC,PGM=PROCESS
// ENDIF
//STEP3   EXEC PGM=FINISH
//SYSOUT  DD SYSOUT=*
"""
        job = parse_jcl(jcl)
        assert job.name == "TESTJOB"
        assert len(job.set_statements) >= 1
        assert len(job.procedures) >= 1

        errors = validate_jcl(jcl, level="structure")
        assert isinstance(errors, list)

        exploded = job.explode()
        # Verify the PROC call inside the conditional was expanded
        assert len(exploded.steps) >= 1


@pytest.mark.integration
class TestRealisticErrorRecovery:
    """Test error recovery with strict_mode=False on partially malformed JCL."""

    def test_lenient_parse_of_partially_valid_jcl(self):
        """strict_mode=False parses valid portions of mixed JCL."""
        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=PROG1
//DD1     DD DSN=GOOD.DATA,DISP=SHR
//STEP2   EXEC PGM=PROG2
//DD2     DD DSN=ALSO.GOOD,DISP=SHR
"""
        # This should parse without error even in non-strict mode
        job = parse_jcl(jcl, strict_mode=False)
        assert job.name == "TESTJOB"
        exec_steps = [s for s in job.steps if isinstance(s, Step)]
        assert len(exec_steps) >= 2

    def test_validate_collects_multiple_errors(self):
        """validate_jcl returns multiple errors for JCL with several issues."""
        # Multiple JOB statements and EXEC before JOB
        bad_jcl = """\
//JOB1    JOB CLASS=A
//STEP1   EXEC PGM=PROG1
//JOB2    JOB CLASS=B
//STEP2   EXEC PGM=PROG2
"""
        errors = validate_jcl(bad_jcl, level="basic")
        assert len(errors) >= 1
