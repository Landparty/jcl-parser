"""System symbols survive the parse-time SET substitution pass."""

from jclparser import explode_job, parse_jcl


class TestSystemSymbolsSurviveSetPass:
    """A job-level SET must not blank system symbols explode_job resolves.

    With any ``// SET`` present, ``resolve_set_symbols`` elided every symbol
    no SET defined -- including ``&SYSUID`` -- so ``DSN=&SYSUID..WORK.DATA``
    became ``.WORK.DATA`` and explosion could no longer resolve it.
    """

    JCL = (
        "//TEST JOB (ACCT),'TEST'\n"
        "// SET OTHER=X\n"
        "//STEP1 EXEC PGM=IEFBR14,PARM='&LYYMMDD'\n"
        "//DD1 DD DSN=&SYSUID..WORK.DATA,DISP=SHR\n"
    )

    def test_parse_keeps_system_symbol(self):
        job = parse_jcl(self.JCL)
        assert job.steps[0].get_dd("DD1").dataset_name == "&SYSUID..WORK.DATA"
        assert job.steps[0].parameters["PARM"] == "&LYYMMDD"
        assert not any("SYSUID" in w for w in job.warnings)

    def test_explosion_resolves_system_symbol(self):
        from jclparser.system_symbols import MockSystemSymbolProvider

        exploded = explode_job(
            parse_jcl(self.JCL), system_provider=MockSystemSymbolProvider()
        )
        assert exploded.steps[0].get_dd("DD1").dataset_name == "TESTUSER.WORK.DATA"

    def test_other_undefined_symbols_still_elided(self):
        job = parse_jcl(
            "//TEST JOB (ACCT),'TEST'\n"
            "// SET KNOWN=VALUE\n"
            "//STEP1 EXEC PGM=IEFBR14\n"
            "//DD1 DD DSN=&KNOWN..&UNKNOWN..SUFFIX,DISP=SHR\n"
        )
        assert job.steps[0].get_dd("DD1").dataset_name == "VALUE..SUFFIX"


class TestSymbolValuesThatAreSystemSymbols:
    """A symbol whose *value* is a system symbol must resolve through it.

    ``SET HLQ=&SYSUID`` (or a PROC default / EXEC override ``HLQ=&SYSUID``)
    followed by ``DSN=&HLQ..DATA`` means ``<userid>.DATA``. The value used to
    be substituted once and never re-examined -- and, in the SET pass, the
    whole symbol was dropped as "unresolved" and blanked to ``.DATA``. The
    period after ``&HLQ`` must also stay a separator: a bare ``&SYSUID``
    spliced in front of ``.DATA`` would otherwise swallow it (``&SYSUID.DATA``
    -> ``TESTUSERDATA``).
    """

    H = "//TEST JOB (ACCT),'TEST'\n"

    def _explode(self, jcl):
        from jclparser.model import Step
        from jclparser.system_symbols import MockSystemSymbolProvider

        exploded = explode_job(
            parse_jcl(jcl), system_provider=MockSystemSymbolProvider()
        )
        return {
            dd.name: dd.dataset_name
            for s in exploded.steps
            if isinstance(s, Step)
            for dd in s.dd_statements
        }

    def test_set_value_is_system_symbol(self):
        jcl = self.H + (
            "// SET HLQ=&SYSUID\n//S1 EXEC PGM=P\n//D1 DD DSN=&HLQ..DATA,DISP=SHR\n"
        )
        job = parse_jcl(jcl)
        assert job.get_dd_statements()[0].dataset_name == "&SYSUID..DATA"
        assert self._explode(jcl) == {"D1": "TESTUSER.DATA"}

    def test_set_value_embeds_system_symbol(self):
        jcl = self.H + (
            "// SET HLQ=&SYSUID..TEST\n"
            "//S1 EXEC PGM=P\n"
            "//D1 DD DSN=&HLQ..DATA,DISP=SHR\n"
        )
        assert self._explode(jcl) == {"D1": "TESTUSER.TEST.DATA"}

    def test_exec_override_is_system_symbol(self):
        jcl = self.H + (
            "//MYPROC PROC HLQ=PROD\n"
            "//PS1 EXEC PGM=R\n"
            "//IN DD DSN=&HLQ..IN,DISP=SHR\n"
            "// PEND\n"
            "//S1 EXEC MYPROC,HLQ=&SYSUID\n"
        )
        assert self._explode(jcl) == {"IN": "TESTUSER.IN"}

    def test_proc_default_is_system_symbol(self):
        jcl = self.H + (
            "//MYPROC PROC HLQ=&SYSUID\n"
            "//PS1 EXEC PGM=R\n"
            "//IN DD DSN=&HLQ..IN,DISP=SHR\n"
            "// PEND\n"
            "//S1 EXEC MYPROC\n"
        )
        assert self._explode(jcl) == {"IN": "TESTUSER.IN"}

    def test_value_with_temp_dataset_is_untouched(self):
        # ``&&WORK`` is an escaped literal, not a reference: no period added.
        jcl = self.H + (
            "// SET TMP=&&WORK\n//S1 EXEC PGM=P\n//D1 DD DSN=&TMP,DISP=(NEW,PASS)\n"
        )
        assert parse_jcl(jcl).get_dd_statements()[0].dataset_name == "&&WORK"

    def test_self_referencing_set_terminates(self):
        jcl = self.H + (
            "// SET A=&B\n// SET B=&A\n//S1 EXEC PGM=P\n//D1 DD DSN=X.&A..Y,DISP=SHR\n"
        )
        # Unresolvable cycle: still elided (unchanged behaviour), no hang.
        assert parse_jcl(jcl).get_dd_statements()[0].dataset_name == "X..Y"
