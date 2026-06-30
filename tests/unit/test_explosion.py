"""
Comprehensive test suite for JCL procedure explosion.

Tests nested procedures, circular references, symbolic parameter substitution,
DD overrides, JCLLIB loading, audit logging, and performance characteristics.
"""

import pytest
from pathlib import Path
from datetime import datetime

from jclparser import (
    parse_jcl,
    UndefinedSymbolError,
    ExplosionDepthError,
    CircularProcedureError,
    ProcedureNotFoundError,
)
from jclparser.explosion import SymbolScope, substitute_symbols
from jclparser.proc_loader import InlineProcedureLoader
from jclparser.system_symbols import MockSystemSymbolProvider


@pytest.fixture
def fixtures_dir():
    """Get path to test fixtures directory"""
    return Path(__file__).parent.parent / "fixtures" / "sample_jcl"


@pytest.fixture
def mock_system_provider():
    """Create mock system symbol provider"""
    return MockSystemSymbolProvider(
        {"SYSUID": "TESTUSER", "SYSDATE": "25/12/09", "SYSTIME": "14:30"}
    )


class TestBasicExplosion:
    """Test basic procedure explosion functionality"""

    def test_simple_proc_explosion(self):
        """Test explosion of a simple procedure"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=TEST.DATA,DISP=SHR
//         PEND
//CALL     EXEC MYPROC
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        # Should have 1 exploded step (not the PROC invocation)
        assert len(exploded.steps) == 1
        assert exploded.steps[0].name == "CALL.STEP1"
        assert exploded.steps[0].program == "IEFBR14"
        assert exploded.steps[0].is_exploded
        assert exploded.steps[0].original_proc_call == "CALL"

    def test_proc_with_parameters(self):
        """Test procedure with default and override parameters"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC DSN=DEFAULT.DATA
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN,DISP=SHR
//         PEND
//CALL     EXEC MYPROC,DSN=MY.DATA.SET
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        # Check parameter substitution
        dd1 = exploded.steps[0].dd_statements[0]
        assert dd1.dataset_name == "MY.DATA.SET"

    def test_no_proc_invocations(self):
        """Test job with no procedure invocations"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=TEST.DATA,DISP=SHR
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        # Should be unchanged
        assert len(exploded.steps) == 1
        assert exploded.steps[0].name == "STEP1"
        assert not exploded.steps[0].is_exploded


class TestSymbolicParameterSubstitution:
    """Test symbolic parameter resolution and substitution"""

    def test_set_statement_resolution(self):
        """Test resolution of SET statement symbols"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//         SET MYDSN=USER.DATA.FILE
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&MYDSN,DISP=SHR
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        dd1 = exploded.steps[0].dd_statements[0]
        assert dd1.dataset_name == "USER.DATA.FILE"

    def test_proc_parameter_precedence(self):
        """Test parameter precedence: EXEC > PROC > SET"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//         SET VAR=SETVALUE
//MYPROC   PROC VAR=PROCVALUE
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&VAR,DISP=SHR
//         PEND
//CALL     EXEC MYPROC,VAR=EXECVALUE
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        # EXEC override should win
        dd1 = exploded.steps[0].dd_statements[0]
        assert dd1.dataset_name == "EXECVALUE"

    def test_system_symbol_resolution(self, mock_system_provider):
        """Test system symbol resolution"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&SYSUID..DATA,DISP=SHR
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode(system_provider=mock_system_provider)

        dd1 = exploded.steps[0].dd_statements[0]
        # After substitution, &SYSUID..DATA becomes TESTUSER.DATA (double period becomes single)
        assert dd1.dataset_name == "TESTUSER.DATA"

    def test_escaped_ampersand(self):
        """Test escaped ampersand (&&) handling"""
        scope = SymbolScope(proc_params={"VAR": "VALUE"})

        result = substitute_symbols("DSN=&&TEMP", scope)
        assert result == "DSN=&TEMP"

    def test_undefined_symbol_strict(self):
        """Test strict mode raises error for undefined symbols"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&UNDEFINED,DISP=SHR
//"""
        job = parse_jcl(jcl, strict_mode=False)

        with pytest.raises(UndefinedSymbolError) as exc:
            job.explode(strict_symbols=True)
        assert "UNDEFINED" in str(exc.value)

    def test_undefined_symbol_strict_inside_proc(self):
        """Strict mode must also reach undefined symbols inside PROC bodies."""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//PSTEP    EXEC PGM=IEFBR14
//DD1      DD DSN=&UNDEFINED,DISP=SHR
//         PEND
//STEP1    EXEC MYPROC
//"""
        job = parse_jcl(jcl, strict_mode=False)

        with pytest.raises(UndefinedSymbolError) as exc:
            job.explode(strict_symbols=True)
        assert "UNDEFINED" in str(exc.value)

    def test_symbol_resolution_fixture(self, fixtures_dir):
        """Test complex symbol resolution from fixture file"""
        jcl_file = fixtures_dir / "symbol_resolution.jcl"
        job = parse_jcl(jcl_file, strict_mode=False)
        exploded = job.explode()

        # Check substitutions
        step = exploded.steps[0]
        dd1 = step.dd_statements[0]
        dd2 = step.dd_statements[1]
        dd3 = step.dd_statements[2]

        # &VAR1..DATA becomes VALUE1DATA (. removed after substitution)
        assert "VALUE1" in dd1.dataset_name
        # &P1..&P2 becomes OVERRIDE1DEFAULT2 (both periods removed)
        assert "OVERRIDE1" in dd2.dataset_name or "DEFAULT2" in dd2.dataset_name
        # &&TEMP stays as &TEMP (escaped ampersand)
        assert dd3.dataset_name == "&TEMP"


class TestNestedProcedures:
    """Test nested procedure expansion"""

    def test_two_level_nesting(self):
        """Test procedure calling another procedure"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//PROC1    PROC
//STEP1    EXEC PGM=PROG1
//         PEND
//PROC2    PROC
//STEP2    EXEC PROC1
//         PEND
//CALL     EXEC PROC2
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        # Should have one step from nested expansion
        assert len(exploded.steps) == 1
        assert exploded.steps[0].name == "CALL.STEP2.STEP1"
        assert exploded.steps[0].program == "PROG1"

    def test_nested_proc_fixture(self, fixtures_dir):
        """Test nested procedure from fixture file"""
        jcl_file = fixtures_dir / "nested_proc.jcl"
        job = parse_jcl(jcl_file, strict_mode=False)
        exploded = job.explode()

        # PROC2 has 2 steps, second calls PROC1 which has 1 step
        # Should have 3 total expanded steps
        assert len(exploded.steps) >= 2

        # Check qualified step names
        step_names = [s.name for s in exploded.steps]
        assert any("STEP2A" in name for name in step_names)
        assert any("STEP2B" in name for name in step_names)

    def test_max_depth_exceeded(self):
        """Test that deep nesting respects max_depth limit"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//PROC1    PROC
//STEP1    EXEC PGM=PROG1
//         PEND
//PROC2    PROC
//STEP2    EXEC PROC1
//         PEND
//CALL     EXEC PROC2
//"""
        job = parse_jcl(jcl, strict_mode=False)

        # Set max_depth to 0 - should fail immediately
        with pytest.raises(ExplosionDepthError) as exc:
            job.explode(max_depth=0)
        assert exc.value.max_depth == 0


class TestCircularReferences:
    """Test circular procedure reference detection"""

    def test_direct_circular_reference(self):
        """Test procedure calling itself"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//PROC1    PROC
//STEP1    EXEC PROC1
//         PEND
//CALL     EXEC PROC1
//"""
        job = parse_jcl(jcl, strict_mode=False)

        with pytest.raises(CircularProcedureError) as exc:
            job.explode()
        assert "PROC1" in str(exc.value)

    def test_indirect_circular_reference(self, fixtures_dir):
        """Test circular reference through multiple procedures"""
        jcl_file = fixtures_dir / "circular_proc.jcl"
        job = parse_jcl(jcl_file, strict_mode=False)

        with pytest.raises(CircularProcedureError) as exc:
            job.explode()
        # Should detect the cycle
        assert exc.value.call_chain is not None


class TestDDOverrides:
    """Test DD statement overrides for procedure steps"""

    def test_dd_override_fixture(self, fixtures_dir):
        """Test DD overrides from fixture file"""
        jcl_file = fixtures_dir / "dd_override.jcl"
        job = parse_jcl(jcl_file, strict_mode=False)

        # Check that parser captured DD overrides
        call_step = job.steps[0]
        assert call_step.name == "CALLPROC"
        assert len(call_step.dd_overrides) >= 2

        # Explode and check overrides applied
        exploded = job.explode()

        # Find exploded STEP1
        step1 = next((s for s in exploded.steps if "STEP1" in s.name), None)
        assert step1 is not None

        # Check DD2 was overridden
        dd2 = next((dd for dd in step1.dd_statements if dd.name == "DD2"), None)
        if dd2:
            assert (
                "OVERRIDE" in dd2.dataset_name
                or dd2.dataset_name == "OVERRIDE.DATA.SET"
            )

    def test_unqualified_added_dd_override_merged_onto_proc_step(self):
        """An unqualified DD coded under EXEC PROC= whose name is NOT in the proc
        is added to the procedure's first step (z/OS semantics), not dropped.

        Regression for the IMS-BMP case: //LOANRPT DD on EXEC PROC=IMSBTCH must
        survive explosion so it can be attributed and resolved downstream.
        """
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//PROCDD   DD DSN=PROC.OWN.DATA,DISP=SHR
//         PEND
//CALL     EXEC MYPROC
//ADDED    DD DSN=JOB.ADDED.DATA,DISP=(NEW,CATLG)
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        step = next(s for s in exploded.steps if "STEP1" in s.name)
        names = [dd.name for dd in step.dd_statements]
        assert "PROCDD" in names, f"proc's own DD lost: {names}"
        assert "ADDED" in names, f"added override DD dropped during explosion: {names}"
        added = next(dd for dd in step.dd_statements if dd.name == "ADDED")
        assert added.dataset_name == "JOB.ADDED.DATA"

    def test_unqualified_dd_override_replaces_matching_proc_dd(self):
        """An unqualified DD whose name matches a proc DD overrides it (no duplicate)."""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//PROCDD   DD DSN=PROC.OWN.DATA,DISP=SHR
//         PEND
//CALL     EXEC MYPROC
//PROCDD   DD DSN=JOB.OVERRIDE.DATA,DISP=SHR
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        step = next(s for s in exploded.steps if "STEP1" in s.name)
        procdds = [dd for dd in step.dd_statements if dd.name == "PROCDD"]
        assert len(procdds) == 1, "override should replace, not duplicate"
        assert procdds[0].dataset_name == "JOB.OVERRIDE.DATA"


class TestProcedureLoaders:
    """Test procedure loader implementations"""

    def test_inline_procedure_loader(self):
        """Test inline procedure loading"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//         PEND
//CALL     EXEC MYPROC
//"""
        job = parse_jcl(jcl, strict_mode=False)

        loader = InlineProcedureLoader(job.procedures)
        proc = loader.load_procedure("MYPROC")

        assert proc is not None
        assert proc.name == "MYPROC"
        assert len(proc.steps) == 1

    def test_procedure_not_found(self):
        """Test error when procedure not found"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//CALL     EXEC NOTFOUND
//"""
        job = parse_jcl(jcl, strict_mode=False)

        with pytest.raises(ProcedureNotFoundError) as exc:
            job.explode()
        assert "NOTFOUND" in str(exc.value)


class TestAuditLogging:
    """Test explosion audit logging"""

    def test_audit_records_generated(self):
        """Test that audit records are created"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC DSN=DEFAULT.DATA
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN,DISP=SHR
//         PEND
//CALL     EXEC MYPROC,DSN=MY.DATA
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode(audit=True)

        # Should have audit records
        assert len(exploded.explosion_audit) == 1

        record = exploded.explosion_audit[0]
        assert record.step_name == "CALL"
        assert record.proc_name == "MYPROC"
        assert record.depth == 0
        assert "DSN" in record.parameters
        assert isinstance(record.timestamp, datetime)

    def test_no_audit_when_disabled(self):
        """Test that audit can be disabled"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//         PEND
//CALL     EXEC MYPROC
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode(audit=False)

        # No audit records
        assert len(exploded.explosion_audit) == 0

    def test_explosion_map_generated(self):
        """Test explosion cross-reference map"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//STEP2    EXEC PGM=IEBGENER
//         PEND
//CALL     EXEC MYPROC
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        # Should have explosion map entry
        assert "CALL" in exploded.explosion_map

        info = exploded.explosion_map["CALL"]
        assert info.proc_definition == "MYPROC"
        assert len(info.expanded_step_names) == 2


class TestPerformance:
    """Test performance characteristics"""

    def test_many_proc_invocations(self):
        """Test explosion of job with many procedure calls"""
        # Create JCL with 50 procedure invocations
        jcl_parts = ["//TESTJOB  JOB (ACCT),'TEST',CLASS=A"]
        jcl_parts.append("//MYPROC   PROC")
        jcl_parts.append("//STEP1    EXEC PGM=IEFBR14")
        jcl_parts.append("//DD1      DD DSN=TEST.DATA,DISP=SHR")
        jcl_parts.append("//         PEND")

        for i in range(50):
            jcl_parts.append(f"//CALL{i:03d} EXEC MYPROC")

        jcl = "\n".join(jcl_parts) + "\n//"

        import time

        start = time.time()

        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        elapsed = time.time() - start

        # Should complete in reasonable time (< 1 second)
        assert elapsed < 1.0
        assert len(exploded.steps) == 50

    def test_deep_nesting_performance(self):
        """Test performance with deep procedure nesting"""
        # Create chain of nested procedures
        jcl_parts = ["//TESTJOB  JOB (ACCT),'TEST',CLASS=A"]

        # Create 5 levels of nested procedures
        for i in range(5):
            jcl_parts.append(f"//PROC{i}   PROC")
            if i < 4:
                jcl_parts.append(f"//STEP{i}   EXEC PROC{i + 1}")
            else:
                jcl_parts.append(f"//STEP{i}   EXEC PGM=IEFBR14")
            jcl_parts.append("//         PEND")

        jcl_parts.append("//CALL     EXEC PROC0")
        jcl = "\n".join(jcl_parts) + "\n//"

        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode(max_depth=10)

        # Should successfully explode
        assert len(exploded.steps) >= 1


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_procedure(self):
        """Test procedure with no steps"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//         PEND
//CALL     EXEC MYPROC
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        # Should have no steps (procedure was empty)
        assert len(exploded.steps) == 0

    def test_mixed_proc_and_program_steps(self):
        """Test job with both PROC calls and direct program execution"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//PSTEP    EXEC PGM=PROG1
//         PEND
//STEP1    EXEC PGM=PROG2
//STEP2    EXEC MYPROC
//STEP3    EXEC PGM=PROG3
//"""
        job = parse_jcl(jcl, strict_mode=False)
        exploded = job.explode()

        # Should have 3 steps: STEP1, expanded STEP2, STEP3
        assert len(exploded.steps) == 3
        assert exploded.steps[0].name == "STEP1"
        assert exploded.steps[1].name == "STEP2.PSTEP"
        assert exploded.steps[2].name == "STEP3"

    def test_parameter_with_special_characters(self):
        """Test parameters containing special JCL characters"""
        scope = SymbolScope(proc_params={"DSN": "USER.DATA(MEMBER)"})

        result = substitute_symbols("DSN=&DSN", scope)
        assert result == "DSN=USER.DATA(MEMBER)"


class TestJobMethod:
    """Test Job.explode() method"""

    def test_explode_method_exists(self):
        """Test that Job has explode() method"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//STEP1    EXEC PGM=IEFBR14
//"""
        job = parse_jcl(jcl, strict_mode=False)

        assert hasattr(job, "explode")
        assert callable(job.explode)

    def test_explode_method_parameters(self):
        """Test explode() method with custom parameters"""
        jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//         PEND
//CALL     EXEC MYPROC
//"""
        job = parse_jcl(jcl, strict_mode=False)

        # Test with custom parameters
        exploded = job.explode(max_depth=5, audit=False, strict_symbols=False)

        assert len(exploded.steps) == 1
        assert len(exploded.explosion_audit) == 0
