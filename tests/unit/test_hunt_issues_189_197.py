"""Regression tests for hunt issues #189, #190, #191, #194 and #197."""

from __future__ import annotations

import pytest

from jclparser import parse_jcl

pytestmark = pytest.mark.unit


class TestJesQuotedComma:
    """#190: a quoted value keeps its comma."""

    def test_netacct_pname_with_comma(self):
        job = parse_jcl(
            "//MYJOB JOB (1),'X'\n"
            "//*NETACCT PNAME='SMITH,J',DEPT=D1\n"
            "//S1 EXEC PGM=IEFBR14\n"
        )
        assert job.jes_typed_statements[0].parameters == {
            "PNAME": "'SMITH,J'",
            "DEPT": "D1",
        }

    def test_jobparm_forms_with_comma_and_doubled_quote(self):
        job = parse_jcl(
            "//MYJOB JOB (1),'X'\n"
            "/*JOBPARM ROOM=A1,FORMS='AB,C''D'\n"
            "//S1 EXEC PGM=IEFBR14\n"
        )
        params = job.jes_typed_statements[0].parameters
        assert params["ROOM"] == "A1"
        assert params["FORMS"] == "'AB,C''D'"
        assert "_pos0" not in params


class TestUseAfterDelete:
    """#191: VOL=SER only excuses a use after UNCATLG, not after DELETE."""

    @staticmethod
    def _msgs(jcl: str) -> list[str]:
        from jclparser.dataset_lifecycle import validate_dataset_lifecycle

        return [str(m) for m in validate_dataset_lifecycle(parse_jcl(jcl))]

    def test_use_after_delete_with_vol_ser_is_reported(self):
        msgs = self._msgs(
            "//J JOB 1\n"
            "//S1 EXEC PGM=IEFBR14\n"
            "//D1 DD DSN=A.B.C,DISP=(OLD,DELETE)\n"
            "//S2 EXEC PGM=X\n"
            "//D2 DD DSN=A.B.C,DISP=SHR,VOL=SER=V1,UNIT=3390\n"
        )
        assert len(msgs) == 1
        assert "after being deleted in step 'S1'" in msgs[0]

    def test_use_after_uncatlg_with_vol_ser_is_not_reported(self):
        assert not self._msgs(
            "//J JOB 1\n"
            "//S1 EXEC PGM=IEFBR14\n"
            "//D1 DD DSN=A.B.C,DISP=(OLD,UNCATLG)\n"
            "//S2 EXEC PGM=X\n"
            "//D2 DD DSN=A.B.C,DISP=SHR,VOL=SER=V1,UNIT=3390\n"
        )

    def test_vol_ref_dsname_names_the_volume(self):
        assert not self._msgs(
            "//J JOB 1\n"
            "//S1 EXEC PGM=IEFBR14\n"
            "//D1 DD DSN=A.B.C,DISP=(OLD,UNCATLG)\n"
            "//S2 EXEC PGM=X\n"
            "//D2 DD DSN=A.B.C,DISP=SHR,VOL=REF=OTHER.DS\n"
        )


class TestIncludeSecondLineNumber:
    """#194: the second line number of a warning is translated too."""

    def test_pend_and_null_statement_warnings(self):
        from jclparser.include_loader import DictMemberLoader

        member = (
            "//STEP0   EXEC PGM=IEFBR14\n//DD1      DD DUMMY\n"
            "//DD2      DD DUMMY\n//DD3      DD DUMMY\n//DD4      DD DUMMY\n"
        )
        src = (
            "//MYJOB   JOB (ACCT),'TEST'\n"
            "// INCLUDE MEMBER=COMMON\n"
            "//MYPROC  PROC\n"
            "//S1      EXEC PGM=IEFBR14\n"
            "//        IF (S1.RC = 0) THEN\n"
            "//S2      EXEC PGM=IEFBR14\n"
            "//        PEND\n"
            "//RUN     EXEC MYPROC\n"
            "//\n"
            "//EXTRA   DD DUMMY\n"
        )
        job = parse_jcl(src, include_loader=DictMemberLoader({"COMMON": member}))
        text = "\n".join(job.warnings)
        assert "closed at PEND (line 7)" in text
        assert "(lines 10-10)" in text


class TestLineageProcRecreate:
    """#189: a delete then a PROC-step recreate is not a deleter job."""

    def test_no_cycle_when_recreate_comes_from_inline_proc(self, tmp_path):
        from jclparser.lineage import build_lineage, load_job_stream

        (tmp_path / "JOBA.jcl").write_text(
            "//JOBA     JOB 1,CLASS=A\n"
            "//MKFILE   PROC\n"
            "//CREATE   EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD DSN=IN.DATA,DISP=SHR\n"
            "//SYSUT2   DD DSN=PROD.MASTER,DISP=(NEW,CATLG,DELETE),\n"
            "//            SPACE=(CYL,(1,1))\n"
            "//         PEND\n"
            "//DEL      EXEC PGM=IEFBR14\n"
            "//DD1      DD DSN=PROD.MASTER,DISP=(MOD,DELETE),SPACE=(TRK,0)\n"
            "//RUN      EXEC MKFILE\n"
        )
        (tmp_path / "JOBB.jcl").write_text(
            "//JOBB     JOB 1,CLASS=A\n"
            "//S1       EXEC PGM=REPORT\n"
            "//IN       DD DSN=PROD.MASTER,DISP=SHR\n"
        )
        lineage = build_lineage(load_job_stream(tmp_path).jobs).to_dict()
        assert lineage["cycles"] == []
        assert lineage["run_order"] == ["JOBA.jcl", "JOBB.jcl"]


class TestInstreamSymbolsAtTheDD:
    """#197: in-stream data gets the SET value in effect at its DD."""

    SRC = (
        "//J JOB 1\n"
        "// EXPORT SYMLIST=*\n"
        "// SET H=PROD\n"
        "//S1 EXEC PGM=IDCAMS\n"
        "//IN DD DSN=&H..KSDS,DISP=SHR\n"
        "//SYSIN DD *,SYMBOLS=JCLONLY\n"
        " DELETE &H..OLD CLUSTER &L..X\n"
        "/*\n"
        "// SET H=TEST\n"
        "// SET L=LATE\n"
        "//S2 EXEC PGM=IEFBR14\n"
    )

    def _sysin(self, job):
        step = job.steps[0]
        return next(dd for dd in step.dd_statements if dd.name == "SYSIN")

    def test_parse_uses_the_value_at_the_dd(self):
        job = parse_jcl(self.SRC)
        assert self._sysin(job).inline_data.strip() == "DELETE PROD.OLD CLUSTER &L..X"
        assert job.steps[0].dd_statements[0].dataset_name == "PROD.KSDS"

    def test_explode_keeps_it(self):
        from jclparser.explosion import explode_job

        job = explode_job(parse_jcl(self.SRC))
        assert "PROD.OLD" in self._sysin(job).inline_data
