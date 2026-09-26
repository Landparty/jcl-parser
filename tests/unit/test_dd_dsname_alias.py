"""DSNAME= is the long form of DSN= and must name the DD's dataset.

``//DD1 DD DSNAME=A.B`` used to leave ``dataset_name`` as ``None``: only the
``DSN`` key was read, so the dataset vanished from every inventory built on
``DDStatement.dataset_name`` (and from PROC explosion, which substitutes
symbols in that field).
"""

from jclparser import explode_job, parse_jcl


class TestDsnameAlias:
    def test_dsname_sets_dataset_name(self):
        job = parse_jcl(
            "//TEST JOB (ACCT),'TEST'\n"
            "//STEP1 EXEC PGM=IEFBR14\n"
            "//DD1 DD DSNAME=LONG.FORM.NAME,DISP=OLD\n"
        )
        dd = job.steps[0].get_dd("DD1")
        assert dd is not None
        assert dd.dataset_name == "LONG.FORM.NAME"
        assert dd.disposition == "OLD"

    def test_dsn_still_sets_dataset_name(self):
        job = parse_jcl(
            "//TEST JOB (ACCT),'TEST'\n"
            "//STEP1 EXEC PGM=IEFBR14\n"
            "//DD1 DD DSN=SHORT.FORM,DISP=SHR\n"
        )
        assert job.steps[0].get_dd("DD1").dataset_name == "SHORT.FORM"

    def test_dsname_symbol_substituted_on_explosion(self):
        job = parse_jcl(
            "//TEST JOB (ACCT),'TEST'\n"
            "//MYPROC PROC HLQ=PROD\n"
            "//PS1 EXEC PGM=READER\n"
            "//IN DD DSNAME=&HLQ..INPUT,DISP=SHR\n"
            "// PEND\n"
            "//STEP1 EXEC MYPROC,HLQ=TEST\n"
        )
        exploded = explode_job(job)
        (step,) = [s for s in exploded.steps if getattr(s, "program", None)]
        assert step.get_dd("IN").dataset_name == "TEST.INPUT"


class TestDsnameInContext:
    """DSNAME= behaves exactly like DSN= wherever a DD can appear."""

    H = "//TEST JOB (ACCT),'TEST'\n"

    def test_dsname_on_concatenated_dd(self):
        job = parse_jcl(
            self.H + "//S1 EXEC PGM=P\n"
            "//IN DD DSNAME=A.ONE,DISP=SHR\n"
            "//   DD DSNAME=A.TWO,DISP=SHR\n"
        )
        assert [d.dataset_name for d in job.steps[0].dd_statements] == [
            "A.ONE",
            "A.TWO",
        ]

    def test_dsname_with_member(self):
        job = parse_jcl(
            self.H + "//S1 EXEC PGM=P\n//IN DD DSNAME=A.PDS(MEM),DISP=SHR\n"
        )
        assert job.steps[0].get_dd("IN").dataset_name == "A.PDS(MEM)"

    def test_dsname_temporary_dataset(self):
        job = parse_jcl(
            self.H + "//S1 EXEC PGM=P\n//T1 DD DSNAME=&&WORK,DISP=(NEW,PASS)\n"
        )
        dd = job.steps[0].get_dd("T1")
        assert dd.dataset_name == "&&WORK"
        assert dd.is_temporary()

    def test_dsn_wins_when_both_are_coded(self):
        job = parse_jcl(
            self.H + "//S1 EXEC PGM=P\n//IN DD DSN=WIN.DS,DSNAME=LOSE.DS,DISP=SHR\n"
        )
        assert job.steps[0].get_dd("IN").dataset_name == "WIN.DS"

    def test_dsname_on_procstep_override(self):
        job = parse_jcl(
            self.H + "//MYPROC PROC\n"
            "//PS1 EXEC PGM=R\n"
            "//IN DD DSN=ORIG.DS,DISP=SHR\n"
            "// PEND\n"
            "//S1 EXEC MYPROC\n"
            "//PS1.IN DD DSNAME=OVERRIDE.DS,DISP=OLD\n"
        )
        (step,) = [s for s in explode_job(job).steps if getattr(s, "program", None)]
        dd = step.get_dd("IN")
        assert (dd.dataset_name, dd.disposition) == ("OVERRIDE.DS", "OLD")

    def test_dsname_set_symbol_resolved_at_parse(self):
        job = parse_jcl(
            self.H + "// SET HLQ=PROD\n"
            "//S1 EXEC PGM=P\n"
            "//IN DD DSNAME=&HLQ..INPUT,DISP=SHR\n"
        )
        assert job.steps[0].get_dd("IN").dataset_name == "PROD.INPUT"
