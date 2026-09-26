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

