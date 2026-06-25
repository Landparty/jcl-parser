"""Unit tests for invoked-program extraction from SYSTSIN/SYSIN control text.

Covers the shared :func:`extract_invoked_programs` helper and the
IKJEFT01 / DB2-batch profiles that surface application programs hidden behind
TSO / DSN wrappers.
"""

from __future__ import annotations

import jclparser as jp
from jclparser.program_profiles import analyze_job, get_profile
from jclparser.program_profiles._invoked import extract_invoked_programs


class TestExtractInvokedPrograms:
    def test_empty_and_none(self):
        assert extract_invoked_programs(None) == []
        assert extract_invoked_programs("") == []
        assert extract_invoked_programs("  LISTCAT ENTRIES(X)\n") == []

    def test_run_program(self):
        progs = extract_invoked_programs(
            "DSN SYSTEM(DB2P)\nRUN PROGRAM(PAYROLL) PLAN(PAYPLAN)"
        )
        assert [(p.name, p.via) for p in progs] == [("PAYROLL", "RUN PROGRAM")]

    def test_call_quoted_dataset_member(self):
        progs = extract_invoked_programs("CALL 'PROD.LOAD.LIB(BILLRUN)'")
        assert [(p.name, p.via) for p in progs] == [("BILLRUN", "CALL")]

    def test_call_current_lib_member(self):
        progs = extract_invoked_programs("CALL *(REPORTX)")
        assert [p.name for p in progs] == ["REPORTX"]

    def test_call_bare_name_with_parms(self):
        progs = extract_invoked_programs("CALL PGMABC 'PARM1,PARM2'")
        assert [p.name for p in progs] == ["PGMABC"]

    def test_call_quoted_simple_name(self):
        progs = extract_invoked_programs("CALL 'PGMXYZ'")
        assert [p.name for p in progs] == ["PGMXYZ"]

    def test_dotted_dataset_without_member_is_ambiguous(self):
        # No member, dotted name -> not an extractable module name.
        assert extract_invoked_programs("CALL 'PROD.LOAD.LIB'") == []

    def test_dedup_preserves_first_occurrence(self):
        progs = extract_invoked_programs(
            "RUN PROGRAM(PAYROLL)\nCALL 'X.LOAD(PAYROLL)'\nRUN PROGRAM(AUDIT)"
        )
        assert [p.name for p in progs] == ["PAYROLL", "AUDIT"]

    def test_case_insensitive(self):
        progs = extract_invoked_programs("run program(payroll)\ncall mypgm")
        assert {p.name for p in progs} == {"PAYROLL", "MYPGM"}


class TestIKJEFT01InvokedPrograms:
    def test_run_program_surfaced_as_invoked(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IKJEFT01\n"
            "//SYSTSIN  DD *\n"
            "  DSN SYSTEM(DB2P)\n"
            "  RUN PROGRAM(PAYROLL) PLAN(PAYPLAN)\n"
            "  END\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].invoked_programs == ["PAYROLL"]

    def test_tso_call_surfaced_as_invoked(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IKJEFT1B\n"
            "//SYSTSIN  DD *\n"
            "  CALL 'PROD.LOAD.LIB(BILLRUN)'\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert results[0].invoked_programs == ["BILLRUN"]

    def test_no_invocation_leaves_list_empty(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IKJEFT01\n"
            "//SYSTSIN  DD *\n"
            "  LISTCAT LEVEL(PROD)\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert results[0].invoked_programs == []


class TestDB2BatchInvokedPrograms:
    def test_profile_registered(self):
        assert get_profile("DSNTEP2") is not None
        assert get_profile("DSNTIAD") is not None

    def test_call_in_sysin_surfaced(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=DSNTEP2\n"
            "//SYSIN    DD *\n"
            "  CALL RPTGEN\n"
            "  SELECT * FROM T1;\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].invoked_programs == ["RPTGEN"]
        notes = " | ".join(results[0].notes)
        assert "embedded SQL" in notes
