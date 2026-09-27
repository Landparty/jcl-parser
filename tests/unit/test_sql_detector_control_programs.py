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
