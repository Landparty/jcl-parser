"""
Tests for external PROC loading from file system.

Tests the integration of JCLLIBProcedureLoader with the main parser
to support JCLLIB ORDER and external procedure references.
"""

import pytest
from pathlib import Path
from jclparser import parse_jcl
from jclparser.errors import JCLSyntaxError


# Get path to test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "proclibs"


class TestBasicExternalProcLoading:
    """Test basic external PROC loading functionality."""

    def test_external_proc_with_jcllib_order(self):
        """Test loading external PROC with JCLLIB ORDER."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//STEP1 EXEC TESTPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # Should have loaded PROC
        assert len(job.procedures) >= 1
        proc = job.get_procedure("TESTPROC")
        assert proc is not None
        assert proc.name == "TESTPROC"

        # PROC should have steps
        assert len(proc.steps) >= 1
        assert proc.steps[0].program == "IEFBR14"

    def test_external_proc_from_user_library(self):
        """Test loading PROC from USER.PROCLIB."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=USER.PROCLIB
//STEP1 EXEC MYPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        proc = job.get_procedure("MYPROC")
        assert proc is not None
        assert proc.name == "MYPROC"
        assert proc.steps[0].program == "MYPROG"

    def test_multiple_libraries_in_order(self):
        """Test JCLLIB ORDER with multiple libraries."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=(SYS1.PROCLIB,USER.PROCLIB)
//STEP1 EXEC TESTPROC
//STEP2 EXEC MYPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # Should load from both libraries
        assert job.get_procedure("TESTPROC") is not None
        assert job.get_procedure("MYPROC") is not None

    def test_no_jcllib_no_external_loading(self):
        """Test that without JCLLIB, external PROCs aren't loaded."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
//STEP1 EXEC TESTPROC"""

        # Without JCLLIB, should not find external PROC
        with pytest.raises(JCLSyntaxError, match="not found"):
            parse_jcl(jcl, strict_mode=True, proc_base_path=FIXTURES_DIR)


class TestLibrarySearchOrder:
    """Test library search order behavior."""

    def test_library_search_order(self, tmp_path):
        """Test that libraries are searched in JCLLIB ORDER."""
        # Create two libraries with same PROC name
        lib1 = tmp_path / "LIB1"
        lib2 = tmp_path / "LIB2"
        lib1.mkdir()
        lib2.mkdir()

        (lib1 / "COMMON.jcl").write_text(
            "//COMMON PROC\n//FROMLIB1 EXEC PGM=LIB1PROG\n// PEND"
        )
        (lib2 / "COMMON.jcl").write_text(
            "//COMMON PROC\n//FROMLIB2 EXEC PGM=LIB2PROG\n// PEND"
        )

        # Test LIB1 first
        jcl1 = """//JOB1 JOB (ACCT),'TEST'
// JCLLIB ORDER=(LIB1,LIB2)
//STEP1 EXEC COMMON"""

        job1 = parse_jcl(jcl1, proc_base_path=tmp_path)
        proc1 = job1.get_procedure("COMMON")
        assert proc1 is not None
        # Should load from LIB1 (first in order)
        assert proc1.steps[0].program == "LIB1PROG"

        # Test LIB2 first
        jcl2 = """//JOB2 JOB (ACCT),'TEST'
// JCLLIB ORDER=(LIB2,LIB1)
//STEP1 EXEC COMMON"""

        job2 = parse_jcl(jcl2, proc_base_path=tmp_path)
        proc2 = job2.get_procedure("COMMON")
        assert proc2 is not None
        # Should load from LIB2 (first in order)
        assert proc2.steps[0].program == "LIB2PROG"

    def test_first_library_takes_precedence(self):
        """Test that first library in ORDER takes precedence."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=(SYS1.PROCLIB,USER.PROCLIB)
//STEP1 EXEC SORTPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # SORTPROC exists in SYS1.PROCLIB, should load from there
        proc = job.get_procedure("SORTPROC")
        assert proc is not None
        assert proc.steps[0].program == "SORT"


class TestInlineVsExternalPrecedence:
    """Test precedence between inline and external PROCs."""

    def test_inline_proc_overrides_external(self):
        """Test that inline PROC takes precedence over external."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//TESTPROC PROC
//INLINE EXEC PGM=INLINE
// PEND
//STEP1 EXEC TESTPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # Should use inline PROC, not external
        proc = job.get_procedure("TESTPROC")
        assert proc is not None
        assert proc.steps[0].program == "INLINE"
        assert proc.steps[0].name == "INLINE"

    def test_external_used_when_no_inline(self):
        """Test external PROC used when no inline version exists."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//OTHERPROC PROC
//OTHER EXEC PGM=OTHER
// PEND
//STEP1 EXEC TESTPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # Should use external TESTPROC
        proc = job.get_procedure("TESTPROC")
        assert proc is not None
        assert proc.steps[0].program == "IEFBR14"


class TestErrorHandling:
    """Test error handling for external PROC loading."""

    def test_proc_not_found_strict_mode(self):
        """Test error when PROC not found in strict mode."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//STEP1 EXEC NOTFOUND"""

        with pytest.raises(JCLSyntaxError) as exc_info:
            parse_jcl(jcl, strict_mode=True, proc_base_path=FIXTURES_DIR)

        # Error message should mention the PROC name
        assert "NOTFOUND" in str(exc_info.value)

    def test_proc_not_found_non_strict_mode(self):
        """Test graceful handling when PROC not found in non-strict mode."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//STEP1 EXEC NOTFOUND"""

        # Should parse without error in non-strict mode
        job = parse_jcl(jcl, strict_mode=False, proc_base_path=FIXTURES_DIR)
        assert job.name == "TESTJOB"
        # Step should still be created
        assert len(job.steps) >= 1

    def test_library_not_found(self):
        """Test handling when library directory doesn't exist."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=NONEXISTENT.PROCLIB
//STEP1 EXEC TESTPROC"""

        # Should handle gracefully (library just skipped)
        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl, strict_mode=True, proc_base_path=FIXTURES_DIR)

    def test_invalid_base_path(self, tmp_path):
        """Test handling when base_path doesn't exist."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//STEP1 EXEC TESTPROC"""

        # Use non-existent base path
        bad_path = tmp_path / "nonexistent"

        with pytest.raises(JCLSyntaxError):
            parse_jcl(jcl, strict_mode=True, proc_base_path=bad_path)


class TestConfigurationOptions:
    """Test configuration options for external PROC loading."""

    def test_external_loading_disabled(self):
        """Test that external loading can be disabled."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//STEP1 EXEC TESTPROC"""

        # With external loading disabled, should not find PROC
        with pytest.raises(JCLSyntaxError):
            parse_jcl(
                jcl,
                strict_mode=True,
                proc_base_path=FIXTURES_DIR,
                enable_external_procs=False,
            )

    def test_external_loading_enabled_by_default(self):
        """Test that external loading is enabled by default."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//STEP1 EXEC TESTPROC"""

        # Should work with default settings
        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)
        assert job.get_procedure("TESTPROC") is not None

    def test_env_var_base_path(self, monkeypatch, tmp_path):
        """Test using JCL_PROCLIB_PATH environment variable."""
        # Create test PROC in tmp location
        lib = tmp_path / "ENV.PROCLIB"
        lib.mkdir()
        (lib / "ENVPROC.jcl").write_text(
            "//ENVPROC PROC\n//STEP1 EXEC PGM=ENVTEST\n// PEND"
        )

        # Set environment variable
        monkeypatch.setenv("JCL_PROCLIB_PATH", str(tmp_path))

        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=ENV.PROCLIB
//STEP1 EXEC ENVPROC"""

        # Should use env var path (no proc_base_path specified)
        job = parse_jcl(jcl)
        proc = job.get_procedure("ENVPROC")
        assert proc is not None
        assert proc.steps[0].program == "ENVTEST"


class TestProcWithParameters:
    """Test external PROCs with symbolic parameters."""

    def test_proc_with_default_parameters(self):
        """Test external PROC with default parameter values."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=USER.PROCLIB
//STEP1 EXEC PARMPRC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        proc = job.get_procedure("PARMPRC")
        assert proc is not None
        # Should have DSN parameter with default
        assert "DSN" in proc.parameters

    def test_proc_with_overridden_parameters(self):
        """Test external PROC with parameter override."""
        jcl = """//TESTJOB JOB (ACCT),'TEST'
// JCLLIB ORDER=USER.PROCLIB
//STEP1 EXEC PARMPRC,DSN=MY.CUSTOM.DATA"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # Should have loaded PROC
        proc = job.get_procedure("PARMPRC")
        assert proc is not None


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_multiple_steps_different_procs(self):
        """Test job with multiple steps using different external PROCs."""
        jcl = """//TESTJOB JOB (ACCT),'MULTI PROC TEST'
// JCLLIB ORDER=(SYS1.PROCLIB,USER.PROCLIB)
//STEP1 EXEC TESTPROC
//STEP2 EXEC SORTPROC
//STEP3 EXEC MYPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # Should have loaded all three PROCs
        assert job.get_procedure("TESTPROC") is not None
        assert job.get_procedure("SORTPROC") is not None
        assert job.get_procedure("MYPROC") is not None

    def test_mixed_inline_and_external_procs(self):
        """Test job with both inline and external PROCs."""
        jcl = """//TESTJOB JOB (ACCT),'MIXED TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//INLINE1 PROC
//STEP1 EXEC PGM=INLINE
// PEND
//STEP1 EXEC INLINE1
//STEP2 EXEC TESTPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # Should have both inline and external
        assert job.get_procedure("INLINE1") is not None
        assert job.get_procedure("TESTPROC") is not None

    def test_complex_jcllib_order(self):
        """Test complex JCLLIB ORDER with multiple libraries."""
        jcl = """//TESTJOB JOB (ACCT),'COMPLEX'
// JCLLIB ORDER=(USER.PROCLIB,SYS1.PROCLIB)
//STEP1 EXEC MYPROC
//STEP2 EXEC SORTPROC"""

        job = parse_jcl(jcl, proc_base_path=FIXTURES_DIR)

        # MYPROC from USER.PROCLIB
        assert job.get_procedure("MYPROC") is not None
        # SORTPROC from SYS1.PROCLIB (not in USER.PROCLIB)
        assert job.get_procedure("SORTPROC") is not None
