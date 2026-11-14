"""Issues #199, #201, #202 and #204 (2026-11-13 sweep)."""

from __future__ import annotations

import pytest

import jclparser as jp
from jclparser.program_profiles import analyze_job
from jclparser.sql_detector import detect_sql_in_job

pytestmark = pytest.mark.unit


def _analysis(src: str) -> dict[str, object]:
    return {r.step_name: r for r in analyze_job(jp.parse_jcl(src))}


class TestTsoStepWithSystsinInADataset:
    """#199: SYSTSIN in a dataset hides the DSN command, not the SQL."""

    SQL = (
        "//SYSIN DD *\n"
        "  SELECT ACCT_NO FROM PROD.ACCOUNT WHERE BAL < 0;\n"
        "  DELETE FROM PROD.TEMP_ROWS;\n"
        "/*\n"
    )

    def test_sysin_sql_is_reported_and_the_step_is_db2(self) -> None:
        src = (
            "//J JOB 1\n//S1 EXEC PGM=IKJEFT01\n//SYSTSPRT DD SYSOUT=*\n"
            "//SYSTSIN DD DSN=PROD.CNTL(RUNTEP2),DISP=SHR\n" + self.SQL
        )
        (result,) = detect_sql_in_job(jp.parse_jcl(src))
        assert result.is_db2_program
        assert [kw for kw, _, _ in result.sql_statements] == ["SELECT", "DELETE"]

    def test_ddname_to_a_dataset_is_unread_too(self) -> None:
        src = (
            "//J JOB 1\n//S1 EXEC PGM=IKJEFT01\n//SYSTSIN DD DDNAME=CMDS\n"
            "//CMDS DD DSN=PROD.CNTL(X),DISP=SHR\n" + self.SQL
        )
        (result,) = detect_sql_in_job(jp.parse_jcl(src))
        assert result.is_db2_program

    def test_in_stream_commands_without_dsn_stay_tso_only(self) -> None:
        # The #196 case: commands readable via DDNAME=, no DSN, so no SQL.
        src = (
            "//J JOB 1\n//S1 EXEC PGM=IKJEFT01\n//SYSTSIN DD DDNAME=RACF\n"
            "//RACF DD *\n  LISTUSER IBMUSER\n  DELETE PROFILE(X)\n/*\n"
        )
        assert detect_sql_in_job(jp.parse_jcl(src)) == []


def test_dfsrrc00_batch_region_names_its_application_program() -> None:
    # #201
    src = (
        "//IMSJOB   JOB (ACCT),'IMS',CLASS=A\n"
        "//BMP      EXEC PGM=DFSRRC00,PARM='BMP,ACCTUPD,ACCTPSB'\n"
        "//DLI      EXEC PGM=DFSRRC00,PARM=(DLI,LOANPMT,LOANPSB)\n"
        "//MSG      EXEC PGM=DFSRRC00,PARM='MSG,001'\n"
    )
    by_step = _analysis(src)
    assert by_step["BMP"].invoked_programs == ["ACCTUPD"]
    assert by_step["DLI"].invoked_programs == ["LOANPMT"]
    assert by_step["MSG"].invoked_programs == []


def test_iebupdte_labelled_control_statement() -> None:
    # #202
    src = (
        "//J1       JOB (A),'X',CLASS=A\n"
        "//S1       EXEC PGM=IEBUPDTE,PARM=NEW\n"
        "//SYSUT2   DD DSN=MY.PDS,DISP=OLD\n"
        "//SYSIN    DD DATA,DLM=$$\n"
        "./ ADD NAME=MEM1,LIST=ALL\n LINE ONE\n"
        "./LBL2 ADD NAME=MEM2\n LINE TWO\n"
        "./ ADD   LIST=ALL,NAME=MEM3\n./ ENDUP\n$$\n"
    )
    assert _analysis(src)["S1"].notes == [
        "ADD NAME=MEM1",
        "ADD NAME=MEM2",
        "ADD NAME=MEM3",
    ]


def test_iebptpch_and_iebdg_labelled_statements() -> None:
    # #204
    src = (
        "//J1       JOB (A),'X',CLASS=A\n"
        "//S1       EXEC PGM=IEBPTPCH\n"
        "//SYSUT1   DD DSN=MY.PDS,DISP=SHR\n"
        "//SYSIN    DD *\n"
        "PRT1     PRINT TYPORG=PO,MAXNAME=2\n"
        "LBL2     MEMBER NAME=MEMA\n"
        "         MEMBER NAME=MEMB\n/*\n"
        "//S2       EXEC PGM=IEBDG\n"
        "//OUT1     DD DSN=TEST.DATA,DISP=(NEW,CATLG),UNIT=SYSDA,SPACE=(TRK,1)\n"
        "//SYSIN    DD *\n"
        "GEN1     DSD   OUTPUT=(OUT1)\n"
        "         FD    NAME=F1,LENGTH=10,FORMAT=AL\n"
        "         CREATE QUANTITY=5,NAME=F1\n"
        "         END\n/*\n"
    )
    by_step = _analysis(src)
    assert by_step["S1"].notes == [
        "PRINT",
        "MEMBER MEMA",
        "MEMBER MEMB",
        "reads MY.PDS",
    ]
    assert by_step["S2"].notes == ["DSD OUTPUT=OUT1", "FD fields: F1", "CREATE"]


IEHINITT_JCL = """\
//J1       JOB (1),'X',CLASS=A
//S1       EXEC PGM=IEHINITT
//SYSPRINT DD SYSOUT=*
//TAPE1    DD UNIT=(TAPE,1,DEFER),LABEL=(,SL)
//SYSIN    DD *
TAPE1    INITT SER=TAP001,OWNER='J SMITH',NUMBTAPE=2
TAPE1    INITT SER=TAP010,DISP=UNLOAD
* a comment
         INITT VOL=SER=OLD001
/*
"""


def test_iehinitt_reads_ibm_initt_statements() -> None:
    # #206: the ddname name field, SER= and a quoted OWNER=.
    results = analyze_job(jp.parse_jcl(IEHINITT_JCL))
    assert results[0].summary == "IEHINITT: 3 tape initialization(s)"
    assert results[0].notes == [
        "INITT TAPE1 (SER=TAP001, OWNER=J SMITH, NUMBTAPE=2)",
        "INITT TAPE1 (SER=TAP010)",
        "INITT (SER=OLD001)",
    ]
