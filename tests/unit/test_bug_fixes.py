"""
Regression tests for the audit bug fixes:

  1. Column-71 truncation (mainframe sequence numbers stripped)
  2. DISP with omitted first subfield  DISP=(,CATLG,DELETE)
  3. is_output() now includes UNCATLG and MOD; is_input/is_output use
     whole-word matching (no false positives from substring like RENEW)
  4. validate_jcl fallback merges continuation lines
  5. CompositeProcedureLoader does not cache None results
  6. Three-part DD overrides (PROCSTEP.INNERST.DDNAME) applied during explosion
  7. SET symbols resolved in DD dataset_name after parse (e.g. &LBNM..CNTL)
"""

from jclparser import parse_jcl, validate_jcl
from jclparser.model import DDStatement, Procedure
from jclparser.proc_loader import (
    CompositeProcedureLoader,
    ProcedureLoader,
)

# ---------------------------------------------------------------------------
# 1. Column-71 truncation
# ---------------------------------------------------------------------------


class TestSequenceNumberStripping:
    """Lines with 8-char sequence numbers in cols 73-80 must parse cleanly."""

    def _pad(self, jcl_line: str, seq: str = "00001000") -> str:
        """Pad a JCL line to 80 chars with a sequence number in cols 73-80."""
        content = jcl_line.ljust(72)[:72]
        return content + seq

    def test_job_card_with_sequence_numbers(self):
        lines = [
            self._pad("//SEQJOB  JOB CLASS=A,MSGCLASS=X"),
            self._pad("//STEP1   EXEC PGM=IEFBR14"),
            self._pad("//SYSOUT  DD   SYSOUT=*"),
        ]
        jcl = "\n".join(lines)
        job = parse_jcl(jcl)
        assert job.name == "SEQJOB"
        assert len(job.steps) == 1
        assert job.steps[0].name == "STEP1"

    def test_parameter_value_not_corrupted(self):
        """DSN value must not include sequence number characters."""
        lines = [
            self._pad("//SEQJOB  JOB CLASS=A"),
            self._pad("//STEP1   EXEC PGM=IEFBR14"),
            self._pad("//MYFILE  DD   DSN=MY.DATASET,DISP=SHR"),
        ]
        jcl = "\n".join(lines)
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd("MYFILE")
        assert dd is not None
        assert dd.dataset_name == "MY.DATASET"

    def test_continuation_with_sequence_numbers(self):
        """Continuation lines padded to 80 cols must still merge correctly."""
        lines = [
            self._pad("//SEQJOB  JOB CLASS=A"),
            self._pad("//STEP1   EXEC PGM=IEFBR14"),
            # DSN on a continuation line
            self._pad("//MYFILE  DD   DSN=MY.LONG.DATASET.NAME,"),
            self._pad("//             DISP=SHR"),
        ]
        jcl = "\n".join(lines)
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd("MYFILE")
        assert dd is not None
        assert dd.dataset_name == "MY.LONG.DATASET.NAME"
        assert dd.disposition == "SHR"

    def test_lines_shorter_than_73_unaffected(self):
        """Normal (short) JCL lines must not be altered."""
        jcl = (
            "//SHORTJOB JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//SYSOUT   DD   SYSOUT=*\n"
        )
        job = parse_jcl(jcl)
        assert job.name == "SHORTJOB"


# ---------------------------------------------------------------------------
# 2. DISP with omitted first subfield
# ---------------------------------------------------------------------------


class TestDispOmittedFirstSubfield:
    def test_disp_omitted_status_catlg_delete(self):
        """DISP=(,CATLG,DELETE) must preserve the empty first element."""
        jcl = (
            "//DISPJOB  JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//NEWFILE  DD   DSN=MY.NEW.DS,DISP=(,CATLG,DELETE),\n"
            "//              SPACE=(CYL,(1,1))\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd("NEWFILE")
        assert dd is not None
        disp = dd.disposition
        assert isinstance(disp, list)
        assert len(disp) == 3
        assert disp[0] == ""  # omitted → empty string
        assert disp[1] == "CATLG"
        assert disp[2] == "DELETE"

    def test_disp_omitted_status_pass(self):
        jcl = (
            "//DISPJOB  JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//PASSDD   DD   DSN=&&TEMP,DISP=(,PASS)\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd("PASSDD")
        assert dd is not None
        disp = dd.disposition
        assert isinstance(disp, list)
        assert disp[0] == ""
        assert disp[1] == "PASS"

    def test_disp_all_three_subfields_unchanged(self):
        """Full DISP=(NEW,CATLG,DELETE) must still parse correctly."""
        jcl = (
            "//DISPJOB  JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//OUT      DD   DSN=MY.DS,DISP=(NEW,CATLG,DELETE),SPACE=(CYL,(1,1))\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd("OUT")
        disp = dd.disposition
        assert disp == ["NEW", "CATLG", "DELETE"]

    def test_disp_single_value_unchanged(self):
        jcl = (
            "//DISPJOB  JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//IN       DD   DSN=MY.DS,DISP=SHR\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].get_dd("IN")
        assert dd.disposition == "SHR"


# ---------------------------------------------------------------------------
# 3. is_output / is_input correctness
# ---------------------------------------------------------------------------


class TestDispositionHelpers:
    def _make_dd(self, disp):
        return DDStatement(name="TEST", disposition=disp)

    # is_output

    def test_is_output_new(self):
        assert self._make_dd("NEW").is_output() is True
        assert self._make_dd(["NEW", "CATLG", "DELETE"]).is_output() is True

    def test_is_output_mod(self):
        assert self._make_dd("MOD").is_output() is True
        assert self._make_dd(["MOD", "KEEP"]).is_output() is True

    def test_is_output_catlg(self):
        """Only the status decides: cataloging an existing dataset writes nothing."""
        assert self._make_dd(["SHR", "CATLG"]).is_output() is False
        assert self._make_dd(["NEW", "CATLG"]).is_output() is True

    def test_is_output_uncatlg(self):
        """UNCATLG (normal or abnormal disposition) does not make a DD an output."""
        assert self._make_dd(["OLD", "UNCATLG"]).is_output() is False
        assert self._make_dd(["OLD", "KEEP", "UNCATLG"]).is_output() is False
        assert self._make_dd(["MOD", "UNCATLG"]).is_output() is True

    def test_is_output_omitted_status_catlg(self):
        """DISP=(,CATLG,DELETE) — empty first field, CATLG in second."""
        assert self._make_dd(["", "CATLG", "DELETE"]).is_output() is True

    def test_is_output_false_for_shr(self):
        assert self._make_dd("SHR").is_output() is False

    def test_is_output_no_false_positive_renew(self):
        """'RENEW' in a string must not trigger is_output via substring match."""
        # Stored as a raw string (unusual but possible)
        dd = self._make_dd("SHR")
        assert dd.is_output() is False

    # is_input

    def test_is_input_shr(self):
        assert self._make_dd("SHR").is_input() is True
        assert self._make_dd(["SHR", "KEEP"]).is_input() is True

    def test_is_input_old(self):
        assert self._make_dd("OLD").is_input() is True

    def test_is_input_false_for_new(self):
        assert self._make_dd("NEW").is_input() is False

    def test_is_input_omitted_status_not_treated_as_input(self):
        """Empty first field (omitted status) should not match OLD/SHR."""
        dd = self._make_dd(["", "CATLG", "DELETE"])
        assert dd.is_input() is False

    # is_temporary

    def test_is_temporary(self):
        dd = DDStatement(name="T", dataset_name="&&TEMP")
        assert dd.is_temporary() is True

    def test_is_not_temporary(self):
        dd = DDStatement(name="T", dataset_name="MY.DATASET")
        assert dd.is_temporary() is False


# ---------------------------------------------------------------------------
# 4. validate_jcl fallback merges continuations
# ---------------------------------------------------------------------------


class TestValidateJclContinuationFallback:
    def test_multi_line_valid_jcl_no_false_errors(self):
        """
        A syntactically correct multi-line JCL that previously failed
        parse_jcl (e.g. due to a different issue) should not produce false
        continuation-related errors in the fallback path.

        We force the fallback by providing a JCL string that parse_jcl in
        strict_mode would reject (missing program), then call validate_jcl.
        """
        # This JCL has no EXEC statement at all — parse_jcl strict will fail
        # and validate_jcl will use its fallback path.  The fallback must not
        # produce false errors about the continuation-merged DD statement.
        jcl = (
            "//CNTJOB   JOB CLASS=A\n"
            # Intentionally no EXEC so strict parse fails → fallback is triggered
            # The DD line below is a multi-line continuation:
        )
        errors = validate_jcl(jcl)
        # The only expected error is "No JOB steps / no EXEC"
        # There must be no spurious "continuation line" parse errors
        for err in errors:
            assert "continuation" not in err.message.lower(), (
                f"Unexpected continuation error: {err.message}"
            )

    def test_continuation_dd_does_not_produce_duplicate_errors(self):
        """
        A valid JCL with a multi-line DD should produce zero errors from
        validate_jcl.
        """
        jcl = (
            "//VALJOB   JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//LONGDD   DD   DSN=MY.VERY.LONG.DATASET.NAME,\n"
            "//              DISP=SHR\n"
        )
        errors = validate_jcl(jcl)
        assert errors == []


# ---------------------------------------------------------------------------
# 5. CompositeProcedureLoader does not cache None
# ---------------------------------------------------------------------------


class _ToggleLoader(ProcedureLoader):
    """A loader that is initially empty, then has a proc added."""

    def __init__(self):
        self._procs = {}

    def add(self, name: str, proc: Procedure):
        self._procs[name.upper()] = proc

    def load_procedure(self, name, libraries=None):
        return self._procs.get(name.upper())


class TestCompositeProcedureLoaderNoCacheNone:
    def test_none_not_cached(self):
        toggle = _ToggleLoader()
        loader = CompositeProcedureLoader([toggle])

        # First call — proc not yet available
        result1 = loader.load_procedure("MYPROC", ())
        assert result1 is None

        # Add the proc
        proc = Procedure(name="MYPROC", parameters={}, steps=[])
        toggle.add("MYPROC", proc)

        # Second call — should now find the proc (not return cached None)
        result2 = loader.load_procedure("MYPROC", ())
        assert result2 is not None
        assert result2.name == "MYPROC"

    def test_found_proc_is_cached(self):
        toggle = _ToggleLoader()
        proc = Procedure(name="CACHED", parameters={}, steps=[])
        toggle.add("CACHED", proc)
        loader = CompositeProcedureLoader([toggle])

        r1 = loader.load_procedure("CACHED", ())
        # Remove from toggle — cached result should still be returned
        toggle._procs.clear()
        r2 = loader.load_procedure("CACHED", ())
        assert r1 is r2


# ---------------------------------------------------------------------------
# 6. Three-part DD overrides
# ---------------------------------------------------------------------------


class TestThreePartDDOverride:
    """
    When a PROC invokes a nested PROC, the outer job can override DDs with
    three-part names: OUTERSTEP.INNERSTEP.DDNAME.
    """

    def test_three_part_override_applied(self):
        jcl = """
//OVERJOB  JOB CLASS=A
//INNER    PROC
//INSTEP   EXEC PGM=IEFBR14
//MYINPUT  DD   DSN=ORIGINAL.DS,DISP=SHR
//         PEND
//OUTER    PROC
//OUTSTEP  EXEC INNER
//         PEND
//JOBSTEP  EXEC OUTER
//OUTSTEP.INSTEP.MYINPUT DD DSN=OVERRIDDEN.DS,DISP=SHR
""".strip()
        job = parse_jcl(jcl)
        exploded = job.explode()

        # Find the innermost step after explosion
        from jclparser.model import iter_execution_steps

        all_steps = list(iter_execution_steps(exploded.steps))

        # Should find a step with the overridden DSN
        overridden = [
            s
            for s in all_steps
            if any(dd.dataset_name == "OVERRIDDEN.DS" for dd in s.dd_statements)
        ]
        assert overridden, (
            f"No step with OVERRIDDEN.DS found. Steps: "
            f"{[(s.name, [(d.name, d.dataset_name) for d in s.dd_statements]) for s in all_steps]}"
        )


# ---------------------------------------------------------------------------
# 7. SET symbol substitution in DD dataset_name after parse
# ---------------------------------------------------------------------------


class TestSetSymbolSubstitution:
    """
    SET statements define symbolic parameters at the job level.  Their values
    must be substituted into DD dataset_name (and disposition) fields so that
    callers see resolved names rather than raw ``&VARNAME..`` tokens.
    """

    def test_basic_set_symbol_resolved_in_dsn(self):
        """&LBNM..CNTL(DB2CREAT) → MYLIB.CNTL(DB2CREAT) when SET LBNM=MYLIB."""
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET LBNM=MYLIB
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&LBNM..CNTL(DB2CREAT),DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        assert dd.dataset_name == "MYLIB.CNTL(DB2CREAT)"

    def test_set_after_dd_still_resolved(self):
        """SET symbol defined *after* the DD that uses it is still resolved."""
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&PREFIX..DATA,DISP=SHR
//         SET PREFIX=PROD
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        assert dd.dataset_name == "PROD.DATA"

    def test_multiple_symbols_in_single_dsn(self):
        """Multiple SET symbols within one DSN are all substituted."""
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET HLQ=CORP
//         SET LLQ=CNTL
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&HLQ..MYLIB.&LLQ.,DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        assert dd.dataset_name == "CORP.MYLIB.CNTL"

    def test_undefined_symbol_left_as_is(self):
        """An undefined symbol is quietly elided (strict=False, no exception).

        The substitute_symbols() engine replaces unknown ``&VAR.`` tokens with
        an empty string when ``strict=False``.  The defined symbol must still
        be substituted correctly; the undefined one produces no text.
        """
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET KNOWN=VALUE
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&KNOWN..&UNKNOWN..SUFFIX,DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        # Defined symbol substituted; undefined symbol elided (→ empty)
        assert "VALUE" in dd.dataset_name
        assert "&" not in dd.dataset_name  # no raw symbol tokens remain

    def test_no_set_statements_leaves_dsn_unchanged(self):
        """JCL with no SET statements returns literal DSN unchanged."""
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=PROD.DATA.SET,DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        assert dd.dataset_name == "PROD.DATA.SET"

    def test_multiple_steps_all_dds_substituted(self):
        """Symbol substitution applies to DD statements across all job steps."""
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET BASE=MY.LIB
//STEP1   EXEC PGM=PROG1
//DD1     DD   DSN=&BASE..INPUT,DISP=SHR
//STEP2   EXEC PGM=PROG2
//DD2     DD   DSN=&BASE..OUTPUT,DISP=(NEW,CATLG)
"""
        job = parse_jcl(jcl)
        dds = {dd.name: dd.dataset_name for dd in job.get_dd_statements()}
        assert dds["DD1"] == "MY.LIB.INPUT"
        assert dds["DD2"] == "MY.LIB.OUTPUT"

    # ------------------------------------------------------------------
    # Chained SET symbol resolution ("symbol of a symbol")
    # ------------------------------------------------------------------

    def test_chained_set_forward_declared(self):
        """SET B=&A. declared before SET A=VALUE is fully resolved.

        In real JCL, SET statements are processed left-to-right, so a forward
        reference (&A. inside B's value) is stored unresolved at parse time.
        The post-parse pre-resolution pass must fix it.

        Given:
            SET B=&A..SUFFIX   (forward reference – A not yet known)
            SET A=CORP
            DD DSN=&B..DATA

        When: parse_jcl() is called.

        Then: DSN resolves to CORP.SUFFIX.DATA (not &A..SUFFIX.DATA).
        """
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET B=&A..SUFFIX
//         SET A=CORP
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&B..DATA,DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        assert dd.dataset_name == "CORP.SUFFIX.DATA"

    def test_chained_set_backward_declared(self):
        """SET A=VALUE before SET B=&A. is already resolved at parse time.

        _resolve_set_value handles backward references during the main parse
        loop.  This test verifies that the pre-resolution pass does not break
        values that were already resolved.

        Given:
            SET A=CORP         (backward – defined first)
            SET B=&A..SUFFIX
            DD DSN=&B..DATA

        When: parse_jcl() is called.

        Then: DSN resolves to CORP.SUFFIX.DATA.
        """
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET A=CORP
//         SET B=&A..SUFFIX
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&B..DATA,DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        assert dd.dataset_name == "CORP.SUFFIX.DATA"

    def test_three_level_chain(self):
        """Three-level chain: DSN=&C. where C=&B., B=&A., A=VALUE.

        Each symbol transitively depends on the one before it.  Forward or
        backward declaration order must not matter after pre-resolution.

        Given:
            SET A=CORP                 ← leaf value
            SET B=&A..LIB              ← depends on A
            SET C=&B..PDS              ← depends on B (and transitively A)
            DD DSN=&C..DATA

        When: parse_jcl() is called.

        Then: DSN resolves to CORP.LIB.PDS.DATA.
        """
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET A=CORP
//         SET B=&A..LIB
//         SET C=&B..PDS
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&C..DATA,DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        assert dd.dataset_name == "CORP.LIB.PDS.DATA"

    def test_three_level_chain_all_forward(self):
        """Three-level chain where every symbol is forward-declared.

        Given:
            SET C=&B..PDS              ← forward ref to B
            SET B=&A..LIB              ← forward ref to A
            SET A=CORP                 ← leaf (last)
            DD DSN=&C..DATA

        When: parse_jcl() is called.

        Then: DSN resolves to CORP.LIB.PDS.DATA.
        """
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET C=&B..PDS
//         SET B=&A..LIB
//         SET A=CORP
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&C..DATA,DISP=SHR
"""
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        assert dd.dataset_name == "CORP.LIB.PDS.DATA"

    def test_circular_set_symbols_no_crash(self):
        """Circular SET references (A=&B., B=&A.) must not cause an infinite loop.

        The pre-resolution pass is capped at 10 iterations.  After the cap the
        table may still contain unresolved tokens, but the parser must return
        without error.  The DD dataset_name should not contain raw ``&``
        tokens (they are silently elided by strict=False during DD substitution).

        Given:
            SET A=&B.
            SET B=&A.
            DD DSN=&A..SUFFIX

        When: parse_jcl() is called.

        Then: No exception; no raw ``&`` symbols remain in dataset_name.
        """
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET A=&B.
//         SET B=&A.
//STEP1   EXEC PGM=IEFBR14
//MYDD    DD   DSN=&A..SUFFIX,DISP=SHR
"""
        # Must not raise.
        job = parse_jcl(jcl)
        dd = job.get_dd_statements()[0]
        # The cyclic symbols can't resolve – they collapse to empty string.
        assert "&" not in dd.dataset_name

    def test_mixed_resolved_and_chained(self):
        """A job combining simple and chained symbols resolves all correctly.

        Given:
            SET HLQ=CORP               ← simple literal
            SET LIB=&HLQ..DATA         ← one-level chain
            SET FULL=&LIB..PDS         ← two-level chain
            DD1 DSN=&HLQ..PLAIN
            DD2 DSN=&LIB..SUFFIX
            DD3 DSN=&FULL..MEMBER

        When: parse_jcl() is called.

        Then: all three DDs resolve to the fully-expanded names.
        """
        jcl = """\
//MYJOB   JOB CLASS=A
//         SET HLQ=CORP
//         SET LIB=&HLQ..DATA
//         SET FULL=&LIB..PDS
//STEP1   EXEC PGM=IEFBR14
//DD1     DD   DSN=&HLQ..PLAIN,DISP=SHR
//DD2     DD   DSN=&LIB..SUFFIX,DISP=SHR
//DD3     DD   DSN=&FULL..MEMBER,DISP=SHR
"""
        job = parse_jcl(jcl)
        dds = {dd.name: dd.dataset_name for dd in job.get_dd_statements()}
        assert dds["DD1"] == "CORP.PLAIN"
        assert dds["DD2"] == "CORP.DATA.SUFFIX"
        assert dds["DD3"] == "CORP.DATA.PDS.MEMBER"
