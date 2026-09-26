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
