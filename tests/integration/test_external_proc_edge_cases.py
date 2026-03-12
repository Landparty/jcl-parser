"""
Additional edge case tests for external PROC loading.

Tests complex scenarios, nested PROCs, error conditions, and performance.
"""

import pytest
from pathlib import Path
from jclparser import parse_jcl
from jclparser.errors import JCLSyntaxError


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "proclibs"


class TestEdgeCases:
    """Test edge cases and corner scenarios."""
    
    def test_proc_name_case_insensitive(self):
        """Test that PROC names are case-insensitive."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//STEP1 EXEC testproc"""
        
        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)
        
        # Should find TESTPROC.jcl even though we used lowercase
        proc = job.get_procedure('TESTPROC')
        assert proc is not None
    
    def test_multiple_jcllib_statements(self, tmp_path):
        """Test multiple JCLLIB statements (last one wins)."""
        lib1 = tmp_path / "LIB1"
        lib2 = tmp_path / "LIB2"
        lib1.mkdir()
        lib2.mkdir()
        
        (lib1 / "PROC1.jcl").write_text("//PROC1 PROC\n//FROM1 EXEC PGM=LIB1\n// PEND")
        (lib2 / "PROC2.jcl").write_text("//PROC2 PROC\n//FROM2 EXEC PGM=LIB2\n// PEND")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=LIB1
// JCLLIB ORDER=LIB2
//STEP1 EXEC PROC2"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        # Should use LIB2 (last JCLLIB)
        proc = job.get_procedure('PROC2')
        assert proc is not None
    
    def test_empty_jcllib_order(self):
        """Test JCLLIB ORDER with empty list."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=()
//STEP1 EXEC TESTPROC"""
        
        # Should handle gracefully
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl, strict_mode=True, proc_base_path=FIXTURES_DIR)
    
    def test_proc_with_dd_overrides(self, tmp_path):
        """Test external PROC with DD overrides."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        (lib / "DDPROC.jcl").write_text("""//DDPROC PROC
//STEP1 EXEC PGM=MYPROG
//DD1 DD DSN=DEFAULT.DATA,DISP=SHR
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC DDPROC
//STEP1.DD1 DD DSN=OVERRIDE.DATA,DISP=SHR"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        # Should load PROC and have DD override
        proc = job.get_procedure('DDPROC')
        assert proc is not None
        assert len(job.steps[0].dd_overrides) > 0
    
    def test_proc_file_with_comments(self, tmp_path):
        """Test PROC file containing comments."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        (lib / "COMMENTED.jcl").write_text("""//COMMENTED PROC
//* This is a comment
//STEP1 EXEC PGM=MYPROG
//* Another comment
//DD1 DD DUMMY
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC COMMENTED"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        proc = job.get_procedure('COMMENTED')
        assert proc is not None
        assert len(proc.steps) >= 1
    
    def test_proc_with_continuation_lines(self, tmp_path):
        """Test PROC with continuation lines."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        (lib / "CONTINUED.jcl").write_text("""//CONTINUED PROC
//STEP1 EXEC PGM=MYPROG,
//       PARM='LONG PARAMETER VALUE'
//DD1 DD DSN=MY.VERY.LONG.DATASET.NAME,
//       DISP=SHR
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC CONTINUED"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        proc = job.get_procedure('CONTINUED')
        assert proc is not None


class TestNestedPROCs:
    """Test nested PROC scenarios."""
    
    def test_proc_calling_another_proc(self, tmp_path):
        """Test PROC that calls another PROC."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        
        # Inner PROC
        (lib / "INNER.jcl").write_text("""//INNER PROC
//STEP1 EXEC PGM=INNERPROG
//DD1 DD DUMMY
// PEND""")
        
        # Outer PROC calling INNER
        (lib / "OUTER.jcl").write_text("""//OUTER PROC
//STEP1 EXEC INNER
//STEP2 EXEC PGM=OUTERPROG
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC OUTER"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        # Should load both PROCs
        assert job.get_procedure('OUTER') is not None
        # INNER might be loaded during explosion, not during initial parse
    
    def test_mixed_inline_and_external_nested(self, tmp_path):
        """Test inline PROC calling external PROC."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        (lib / "EXTERNAL.jcl").write_text("""//EXTERNAL PROC
//STEP1 EXEC PGM=EXTPROG
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//INLINE PROC
//STEP1 EXEC EXTERNAL
// PEND
//STEP1 EXEC INLINE"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        # Should have inline PROC
        assert job.get_procedure('INLINE') is not None


class TestPerformance:
    """Test performance and caching."""
    
    def test_proc_caching(self, tmp_path):
        """Test that PROCs are cached and not reloaded."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        (lib / "CACHED.jcl").write_text("""//CACHED PROC
//STEP1 EXEC PGM=MYPROG
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC CACHED
//STEP2 EXEC CACHED
//STEP3 EXEC CACHED"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        # Should only have one PROC instance (cached)
        assert len(job.procedures) == 1
        assert job.get_procedure('CACHED') is not None
    
    def test_multiple_jobs_same_proc(self, tmp_path):
        """Test multiple jobs using same PROC (caching across parses)."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        (lib / "SHARED.jcl").write_text("""//SHARED PROC
//STEP1 EXEC PGM=MYPROG
// PEND""")
        
        jcl1 = """//JOB1 JOB (ACCT),'TEST1'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC SHARED"""
        
        jcl2 = """//JOB2 JOB (ACCT),'TEST2'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC SHARED"""
        
        # Parse both jobs
        job1 = parse_jcl(jcl1, proc_base_path=tmp_path)
        job2 = parse_jcl(jcl2, proc_base_path=tmp_path)
        
        # Both should have loaded the PROC
        assert job1.get_procedure('SHARED') is not None
        assert job2.get_procedure('SHARED') is not None


class TestComplexScenarios:
    """Test complex real-world scenarios."""
    
    def test_production_like_job(self, tmp_path):
        """Test production-like job with multiple PROCs and libraries."""
        sys1 = tmp_path / "SYS1.PROCLIB"
        user = tmp_path / "USER.PROCLIB"
        sys1.mkdir()
        user.mkdir()
        
        # System PROCs
        (sys1 / "SORT.jcl").write_text("""//SORT PROC
//STEP1 EXEC PGM=SORT
//SORTIN DD DUMMY
//SORTOUT DD DUMMY
// PEND""")
        
        (sys1 / "IEBGENER.jcl").write_text("""//IEBGENER PROC
//STEP1 EXEC PGM=IEBGENER
//SYSUT1 DD DUMMY
//SYSUT2 DD DUMMY
//SYSPRINT DD SYSOUT=*
// PEND""")
        
        # User PROCs
        (user / "BACKUP.jcl").write_text("""//BACKUP PROC
//STEP1 EXEC PGM=IEBGENER
//SYSUT1 DD DSN=PROD.DATA,DISP=SHR
//SYSUT2 DD DSN=BACKUP.DATA,DISP=(NEW,CATLG)
// PEND""")
        
        jcl = """//PRODJOB JOB (ACCT),'PRODUCTION JOB'
// JCLLIB ORDER=(SYS1.PROCLIB,USER.PROCLIB)
//STEP1 EXEC SORT
//STEP2 EXEC IEBGENER
//STEP3 EXEC BACKUP"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        # Should load all three PROCs
        assert job.get_procedure('SORT') is not None
        assert job.get_procedure('IEBGENER') is not None
        assert job.get_procedure('BACKUP') is not None
        assert len(job.procedures) == 3
    
    def test_proc_with_symbolic_parameters(self, tmp_path):
        """Test PROC with symbolic parameter substitution."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        (lib / "SYMBOLIC.jcl").write_text("""//SYMBOLIC PROC DSN=DEFAULT.DATA,DISP=SHR
//STEP1 EXEC PGM=MYPROG
//DD1 DD DSN=&DSN,DISP=&DISP
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC SYMBOLIC,DSN=MY.DATA,DISP=OLD"""
        
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        
        proc = job.get_procedure('SYMBOLIC')
        assert proc is not None
        # Check that PROC has default parameters
        assert 'DSN' in proc.parameters


class TestErrorRecovery:
    """Test error recovery and graceful degradation."""
    
    def test_malformed_proc_file(self, tmp_path):
        """Test handling of malformed PROC file."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        (lib / "BADPROC.jcl").write_text("""This is not valid JCL
//BADPROC PROC
MISSING SLASHES
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC BADPROC"""
        
        # Should handle gracefully in non-strict mode
        job = parse_jcl(jcl, strict_mode=False, proc_base_path=tmp_path)
        assert job.name == 'TESTJOB'
        
        # Should error in strict mode
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl, strict_mode=True, proc_base_path=tmp_path)
    
    def test_circular_proc_reference(self, tmp_path):
        """Test detection/handling of circular PROC references."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        
        # PROC1 calls PROC2
        (lib / "PROC1.jcl").write_text("""//PROC1 PROC
//STEP1 EXEC PROC2
// PEND""")
        
        # PROC2 calls PROC1 (circular!)
        (lib / "PROC2.jcl").write_text("""//PROC2 PROC
//STEP1 EXEC PROC1
// PEND""")
        
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC PROC1"""
        
        # Should parse without infinite loop
        # (circular detection happens during explosion, not parsing)
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        assert job.get_procedure('PROC1') is not None
    
    @pytest.mark.skipif(
        __import__('sys').platform == 'win32',
        reason="File permissions work differently on Windows"
    )
    def test_permission_denied_proc_file(self, tmp_path):
        """Test handling when PROC file is not readable."""
        lib = tmp_path / "TESTLIB"
        lib.mkdir()
        proc_file = lib / "NOPERM.jcl"
        proc_file.write_text("//NOPERM PROC\n//STEP1 EXEC PGM=TEST\n// PEND")
        
        # Make file unreadable (Unix/Linux only)
        import stat
        try:
            proc_file.chmod(0o000)
            
            jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=TESTLIB
//STEP1 EXEC NOPERM"""
            
            # Should handle gracefully
            with pytest.raises(JCLSyntaxError):
                parse_jcl(jcl, strict_mode=True, proc_base_path=tmp_path)
        finally:
            # Restore permissions for cleanup
            proc_file.chmod(0o644)
