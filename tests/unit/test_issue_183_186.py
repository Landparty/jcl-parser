"""#183-#186: delete-and-recreate lineage, nameless PROC members, JES3
continuations, and VOL=SER opens after an uncatalog."""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.lineage import build_lineage

pytestmark = pytest.mark.unit


RECREATE = (
    "//JA       JOB (1),'A'\n"
    "//DEL      EXEC PGM=IEFBR14\n"
    "//D        DD DSN=P.EXTRACT,DISP=(MOD,DELETE),SPACE=(TRK,1)\n"
    "//EXT      EXEC PGM=EXTRACT\n"
    "//O        DD DSN=P.EXTRACT,DISP=(NEW,CATLG),SPACE=(TRK,1)\n"
)
READER = "//JB       JOB (1),'B'\n//S1       EXEC PGM=RPT\n//I        DD DSN=P.EXTRACT,DISP=SHR\n"


class TestDeleteThenRecreate:
    def test_recreating_job_is_the_producer(self) -> None:
        report = build_lineage({"JA": parse_jcl(RECREATE), "JB": parse_jcl(READER)})
        assert report.run_order == ["JA", "JB"]
        assert report.cycles == []
        assert [(d.producer, d.consumer) for d in report.dependencies] == [("JA", "JB")]

    def test_delete_after_write_still_runs_last(self) -> None:
        # The #179 case: the deleting job's last use is the delete.
        writes = "//JW JOB 1\n//S1 EXEC PGM=X\n//O DD DSN=P.X,DISP=(NEW,CATLG)\n"
        deletes = (
            "//JD JOB 1\n//S1 EXEC PGM=IEFBR14\n//D DD DSN=P.X,DISP=(OLD,DELETE)\n"
        )
        reads = "//JR JOB 1\n//S1 EXEC PGM=X\n//I DD DSN=P.X,DISP=SHR\n"
        report = build_lineage(
            {"JW": parse_jcl(writes), "JD": parse_jcl(deletes), "JR": parse_jcl(reads)}
        )
        assert report.run_order == ["JW", "JR", "JD"]


class TestMemberNameGovernsProc:
    @pytest.mark.parametrize(
        "content",
        [
            "//MYPROC PROC A=1\n//S1 EXEC PGM=IEFBR14\n",
            "//COMPILE PROC A=1\n//S1 EXEC PGM=IEFBR14\n",
            "//COMPILE PROC A=1\n//S1 EXEC PGM=IEFBR14\n// PEND\n",
            "//  PROC A=1\n//S1 EXEC PGM=IEFBR14\n",
        ],
    )
    def test_member_with_one_proc_loads_under_member_name(self, content: str) -> None:
        from jclparser.proc_loader import DictProcedureLoader

        proc = DictProcedureLoader({"MYPROC": content}).load_procedure("MYPROC")
        assert proc is not None
        assert proc.name == "MYPROC"
        assert proc.parameters == {"A": "1"}
        assert [s.name for s in proc.steps] == ["S1"]

    def test_nameless_proc_expands_through_jclllib(self, tmp_path) -> None:
        from jclparser import explode_job

        lib = tmp_path / "MY.PROCLIB"
        lib.mkdir()
        (lib / "CBLCOMP.jcl").write_text(
            "//  PROC MBR=X\n//COMP EXEC PGM=IGYCRCTL,PARM='&MBR'\n"
        )
        job = parse_jcl(
            "//J JOB 1\n//PL JCLLIB ORDER=MY.PROCLIB\n//S1 EXEC CBLCOMP,MBR=PAYROLL\n",
            proc_base_path=str(tmp_path),
        )
        exploded = explode_job(job)
        programs = [s.program for s in exploded.steps]
        assert "IGYCRCTL" in programs


class TestJes3Continuation:
    def test_continued_format_keeps_its_keywords(self) -> None:
        job = parse_jcl(
            "//J1 JOB (1),'X'\n"
            "//*FORMAT PR,DDNAME=S1.DD1,DEST=ANYLOCAL,\n"
            "//*COPIES=3\n"
            "//S1 EXEC PGM=IEFBR14\n"
        )
        assert job.jes_statements == [
            "//*FORMAT PR,DDNAME=S1.DD1,DEST=ANYLOCAL,COPIES=3"
        ]
        params = job.jes_typed_statements[0].parameters
        assert params["COPIES"] == "3" and params["DEST"] == "ANYLOCAL"

    def test_blank_indented_continuation_and_comment_after(self) -> None:
        job = parse_jcl(
            "//J1 JOB (1),'X'\n"
            "//*MAIN CLASS=A,   first line\n"
            "//*      LINES=(10,W),\n"
            "//*      HOLD=YES\n"
            "//* AN ORDINARY COMMENT\n"
            "//S1 EXEC PGM=IEFBR14\n"
        )
        assert len(job.jes_typed_statements) == 1
        params = job.jes_typed_statements[0].parameters
        assert params["CLASS"] == "A"
        assert params["LINES"] == "(10,W)"
        assert params["HOLD"] == "YES"

    def test_statement_without_trailing_comma_takes_no_continuation(self) -> None:
        job = parse_jcl(
            "//J1 JOB (1),'X'\n//*MAIN CLASS=A\n//*COPIES=3\n//S1 EXEC PGM=IEFBR14\n"
        )
        assert job.jes_typed_statements[0].parameters == {"CLASS": "A"}


class TestVolumeBypassesCatalog:
    @pytest.mark.parametrize(
        "vol", ["VOL=SER=V1,UNIT=3390", "VOL=(,,,,SER=V1),UNIT=3390"]
    )
    def test_open_with_volume_after_uncatalog_is_fine(self, vol: str) -> None:
        from jclparser.dataset_lifecycle import validate_dataset_lifecycle

        job = parse_jcl(
            "//J1 JOB (1),X\n//S1 EXEC PGM=P\n//D DD DSN=A.B,DISP=(OLD,UNCATLG)\n"
            f"//S2 EXEC PGM=P\n//D DD DSN=A.B,DISP=SHR,{vol}\n"
        )
        assert validate_dataset_lifecycle(job) == []

    def test_open_without_volume_after_uncatalog_still_warns(self) -> None:
        from jclparser.dataset_lifecycle import validate_dataset_lifecycle

        job = parse_jcl(
            "//J1 JOB (1),X\n//S1 EXEC PGM=P\n//D DD DSN=A.B,DISP=(OLD,UNCATLG)\n"
            "//S2 EXEC PGM=P\n//D DD DSN=A.B,DISP=SHR\n"
        )
        assert any("uncataloged" in str(e) for e in validate_dataset_lifecycle(job))

    def test_forward_reference_with_volume_is_fine(self) -> None:
        from jclparser.dataset_lifecycle import validate_dataset_lifecycle

        job = parse_jcl(
            "//J1 JOB (1),X\n//S1 EXEC PGM=P\n//D DD DSN=A.B,DISP=OLD,VOL=SER=V1,UNIT=3390\n"
            "//S2 EXEC PGM=P\n//D DD DSN=A.B,DISP=(NEW,CATLG),UNIT=3390\n"
        )
        assert validate_dataset_lifecycle(job) == []
