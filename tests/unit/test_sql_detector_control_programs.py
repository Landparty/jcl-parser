"""Utility control statements are not reported as SQL.

IDCAMS ``DELETE`` / ``ALTER``, FTP ``DELETE`` and TSO ``DELETE`` / ``RENAME``
commands share their verbs with SQL, so scanning every in-stream DD for SQL
keywords reported them as DML/DDL.
"""

import pytest

from jclparser import parse_jcl
from jclparser.model import DDStatement, Step
from jclparser.sql_detector import detect_sql_in_job, detect_sql_in_step


@pytest.mark.unit
class TestSqlDetectorControlPrograms:
    @pytest.mark.parametrize(
        ("program", "data"),
        [
            ("IDCAMS", "  DELETE PROD.OLD.FILE PURGE\n  ALTER PROD.X NEWNAME(PROD.Y)"),
            ("FTP", "DELETE REMOTE.FILE\nRENAME A B"),
            ("SORT", "  SORT FIELDS=COPY"),
            ("IEHPROGM", "  RENAME DSNAME=A.B,VOL=3390=V1,NEWNAME=A.C"),
        ],
    )
    def test_control_program_data_not_scanned(self, program, data):
        step = Step(
            name="S",
            program=program,
            dd_statements=[DDStatement(name="SYSIN", inline_data=data)],
        )
        result = detect_sql_in_step(step)
        assert result.sql_statements == []
        assert not result.has_sql

    def test_tso_commands_in_systsin_are_not_sql(self):
        step = Step(
            name="S",
            program="IKJEFT01",
            dd_statements=[
                DDStatement(
                    name="SYSTSIN",
                    inline_data="DELETE 'A.B'\nRENAME 'A.B' 'A.C'\nBIND PLAN(P)",
                )
            ],
        )
        assert detect_sql_in_step(step).sql_statements == [
            ("BIND", "UTILITY", "SYSTSIN")
        ]

    def test_idcams_job_reports_no_sql(self):
        jcl = (
            "//J        JOB (ACCT),'T'\n"
            "//S1       EXEC PGM=IDCAMS\n"
            "//SYSIN    DD *\n"
            "  DELETE PROD.OLD.FILE PURGE\n"
            "/*\n"
            "//S2       EXEC PGM=DSNTEP2\n"
            "//SYSIN    DD *\n"
            "  DELETE FROM T WHERE C = 1;\n"
            "/*\n"
        )
        results = detect_sql_in_job(parse_jcl(jcl))
        assert [r.step_name for r in results] == ["S2"]
        assert results[0].sql_statements == [("DELETE", "DML", "SYSIN")]

    def test_program_name_is_case_insensitive(self):
        step = Step(
            name="S",
            program="idcams",
            dd_statements=[DDStatement(name="SYSIN", inline_data="DELETE X")],
        )
        assert detect_sql_in_step(step).sql_statements == []


def _utility_step(data: str) -> Step:
    return Step(
        name="DSNUPROC",
        program="DSNUTILB",
        dd_statements=[DDStatement(name="SYSIN", inline_data=data)],
    )


@pytest.mark.unit
class TestDb2UtilityControlStatements:
    """DSNUTILB control statements reuse SQL verbs as options."""

    def test_runstats_update_all_is_not_dml(self):
        step = _utility_step(
            "  RUNSTATS TABLESPACE BANKDB.TXNHIST\n"
            "    TABLE(BANK.TRANSACTION_HIST)\n"
            "    INDEX(ALL)\n"
            "    REPORT YES\n"
            "    UPDATE ALL\n"
        )
        result = detect_sql_in_step(step)
        assert result.sql_statements == []
        assert result.is_db2_program

    def test_modify_recovery_delete_age_is_not_dml(self):
        step = _utility_step(
            "  MODIFY RECOVERY TABLESPACE BANKDB.TXNHIST\n    DELETE AGE(90)\n"
        )
        assert detect_sql_in_step(step).sql_statements == []

    def test_sql_inside_exec_sql_utility_statement_still_reported(self):
        step = _utility_step(
            "  EXEC SQL\n"
            "    DELETE FROM BANK.TXN_STAGE\n"
            "  ENDEXEC\n"
            "  RUNSTATS TABLESPACE BANKDB.TXNHIST\n"
        )
        assert detect_sql_in_step(step).sql_statements == [
            ("EXEC SQL", "EMBEDDED", "SYSIN"),
            ("DELETE", "DML", "SYSIN"),
        ]

    def test_one_line_exec_sql_utility_statement(self):
        step = _utility_step(
            "  EXEC SQL CREATE TABLE BANK.T2 (C INT) ENDEXEC\n    UPDATE ALL\n"
        )
        assert detect_sql_in_step(step).sql_statements == [
            ("EXEC SQL", "EMBEDDED", "SYSIN"),
            ("CREATE", "DDL", "SYSIN"),
        ]


_DSNUPROC_JOB = """//J JOB
//STEP1 EXEC DSNUPROC,SYSTEM=DB2P,UID='RUNST'
//SYSIN DD *
  RUNSTATS TABLESPACE DBX.TSX
     UPDATE ALL
  MODIFY RECOVERY TABLESPACE DBX.TSX
     DELETE AGE(90)
/*
"""


@pytest.mark.unit
class TestDb2UtilityProcCall:
    """Issue #106: ``EXEC DSNUPROC`` runs DSNUTILB even when unexploded."""

    def test_unexploded_dsnuproc_options_are_not_dml(self):
        results = detect_sql_in_job(parse_jcl(_DSNUPROC_JOB))
        assert [r.sql_statements for r in results] == [[]]

    def test_exploded_dsnuproc_agrees(self):
        from jclparser import explode_job

        results = detect_sql_in_job(explode_job(parse_jcl(_DSNUPROC_JOB)))
        assert [r.sql_statements for r in results] == [[]]

    def test_sql_in_exec_sql_under_dsnuproc_still_reported(self):
        step = Step(
            name="S",
            procedure="DSNUPROC",
            dd_statements=[
                DDStatement(
                    name="SYSIN",
                    inline_data="  EXEC SQL\n    DELETE FROM T\n  ENDEXEC\n",
                )
            ],
        )
        result = detect_sql_in_step(step)
        assert ("DELETE", "DML", "SYSIN") in result.sql_statements
        assert result.is_db2_program


@pytest.mark.unit
class TestProcCallOverrideDds:
    """Issue #94 / review of #137: //PROCSTEP.DD overrides are scanned."""

    def test_dsnuproc_sysin_override_scanned_as_utility_input(self):
        jcl = (
            "//J JOB\n//S1 EXEC DSNUPROC,SYSTEM=DB2P\n//DSNUPROC.SYSIN DD *\n"
            "  EXEC SQL DELETE FROM T ENDEXEC\n  RUNSTATS TABLESPACE A.B UPDATE ALL\n/*\n"
        )
        (result,) = detect_sql_in_job(parse_jcl(jcl))
        assert result.sql_statements == [
            ("EXEC SQL", "EMBEDDED", "DSNUPROC.SYSIN"),
            ("DELETE", "DML", "DSNUPROC.SYSIN"),
        ]

    def test_override_read_as_input_to_its_procstep_program(self):
        jcl = (
            "//J JOB\n//P PROC\n//PS EXEC PGM=IDCAMS\n//SYSIN DD DUMMY\n"
            "//PT EXEC PGM=DSNTEP2\n//SYSIN DD DUMMY\n// PEND\n//S1 EXEC P\n"
            "//PS.SYSIN DD *\n  DELETE A.B PURGE\n/*\n"
            "//PT.SYSIN DD *\n  SELECT A FROM T;\n/*\n"
        )
        (result,) = detect_sql_in_job(parse_jcl(jcl))
        assert result.sql_statements == [("SELECT", "DML", "PT.SYSIN")]
