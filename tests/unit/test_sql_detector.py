"""Tests for jclparser.sql_detector module."""

import pytest

from jclparser import parse_jcl
from jclparser.model import DDStatement, Step
from jclparser.sql_detector import (
    DB2_PROGRAMS,
    SQLDetectionResult,
    detect_sql_in_dd,
    detect_sql_in_job,
    detect_sql_in_step,
    detect_sql_in_text,
    is_db2_program,
)


class TestIsDb2Program:
    """Tests for is_db2_program()."""

    @pytest.mark.parametrize(
        "pgm",
        [
            "DSNTEP2",
            "DSNTEP4",
            "DSNTIAD",
            "DSNUPROC",
            "DSNUTILB",
            "DSNTEP",
        ],
    )
    def test_known_programs(self, pgm):
        assert is_db2_program(pgm) is True

    def test_case_insensitive(self):
        assert is_db2_program("dsntep2") is True
        assert is_db2_program("Dsntep2") is True

    def test_non_db2_program(self):
        assert is_db2_program("IEFBR14") is False
        # TSO batch on its own is no DB2 program (see TestTsoBatchDb2).
        assert is_db2_program("IKJEFT01") is False
        assert is_db2_program("SORT") is False

    def test_none(self):
        assert is_db2_program(None) is False

    def test_empty(self):
        assert is_db2_program("") is False


class TestDetectSqlInText:
    """Tests for detect_sql_in_text()."""

    def test_select(self):
        result = detect_sql_in_text("SELECT * FROM TABLE1")
        assert len(result) == 1
        assert result[0] == ("SELECT", "DML")

    def test_multiple_statements(self):
        text = "SELECT * FROM T1\nINSERT INTO T2 VALUES(1)\nUPDATE T3 SET X=1"
        result = detect_sql_in_text(text)
        assert len(result) == 3
        keywords = [kw for kw, _ in result]
        assert keywords == ["SELECT", "INSERT", "UPDATE"]

    def test_ddl(self):
        text = "CREATE TABLE FOO (ID INT)\nALTER TABLE FOO ADD COL1 CHAR(10)"
        result = detect_sql_in_text(text)
        assert all(cat == "DDL" for _, cat in result)

    def test_dcl(self):
        text = "GRANT SELECT ON TABLE1 TO USER1"
        result = detect_sql_in_text(text)
        assert result[0] == ("GRANT", "DCL")

    def test_exec_sql(self):
        text = "EXEC SQL SELECT * FROM T1 END-EXEC"
        result = detect_sql_in_text(text)
        assert result[0] == ("EXEC SQL", "EMBEDDED")

    def test_utility(self):
        text = "BIND PACKAGE(MYPKG)"
        result = detect_sql_in_text(text)
        assert result[0] == ("BIND", "UTILITY")

    def test_skips_comments(self):
        text = "-- This is a comment\nSELECT 1"
        result = detect_sql_in_text(text)
        assert len(result) == 1

    def test_skips_blank_lines(self):
        text = "\n\n  \nSELECT 1\n\n"
        result = detect_sql_in_text(text)
        assert len(result) == 1

    def test_no_sql(self):
        text = "SOME RANDOM DATA\nNOT SQL AT ALL"
        result = detect_sql_in_text(text)
        assert result == []

    def test_empty_text(self):
        assert detect_sql_in_text("") == []

    def test_keyword_not_at_word_boundary(self):
        # "SELECTED" should NOT match "SELECT"
        result = detect_sql_in_text("SELECTED ITEMS FROM STORE")
        assert result == []

    def test_case_insensitive(self):
        result = detect_sql_in_text("select * from t1")
        assert len(result) == 1
        assert result[0][0] == "SELECT"

    def test_leading_whitespace(self):
        result = detect_sql_in_text("   SELECT * FROM T1")
        assert len(result) == 1

    def test_delete(self):
        result = detect_sql_in_text("DELETE FROM TABLE1 WHERE ID = 1")
        assert result[0] == ("DELETE", "DML")

    def test_merge(self):
        result = detect_sql_in_text("MERGE INTO T1 USING T2 ON T1.ID=T2.ID")
        assert result[0] == ("MERGE", "DML")

    def test_drop(self):
        result = detect_sql_in_text("DROP TABLE FOO")
        assert result[0] == ("DROP", "DDL")

    def test_truncate(self):
        result = detect_sql_in_text("TRUNCATE TABLE FOO")
        assert result[0] == ("TRUNCATE", "DDL")


class TestDetectSqlInDd:
    """Tests for detect_sql_in_dd()."""

    def test_dd_with_sql(self):
        dd = DDStatement(name="SYSIN", inline_data="SELECT * FROM T1")
        result = detect_sql_in_dd(dd)
        assert len(result) == 1

    def test_dd_without_inline_data(self):
        dd = DDStatement(name="INPUT", dataset_name="MY.DATASET")
        assert detect_sql_in_dd(dd) == []

    def test_dd_with_none_inline_data(self):
        dd = DDStatement(name="INPUT")
        assert detect_sql_in_dd(dd) == []


class TestDetectSqlInStep:
    """Tests for detect_sql_in_step()."""

    def test_db2_program_no_inline(self):
        step = Step(name="RUN", program="DSNTEP2")
        result = detect_sql_in_step(step)
        assert result.has_sql is True
        assert result.is_db2_program is True
        assert result.sql_statements == []

    def test_non_db2_with_sql_inline(self):
        dd = DDStatement(name="SYSIN", inline_data="SELECT * FROM T1")
        step = Step(name="RUN", program="MYPGM", dd_statements=[dd])
        result = detect_sql_in_step(step)
        assert result.has_sql is True
        assert result.is_db2_program is False
        assert len(result.sql_statements) == 1
        assert result.sql_statements[0] == ("SELECT", "DML", "SYSIN")

    def test_db2_program_with_sql_inline(self):
        dd = DDStatement(
            name="SYSIN", inline_data="SELECT * FROM T1\nINSERT INTO T2 VALUES(1)"
        )
        step = Step(name="RUN", program="DSNTEP2", dd_statements=[dd])
        result = detect_sql_in_step(step)
        assert result.has_sql is True
        assert result.is_db2_program is True
        assert len(result.sql_statements) == 2

    def test_no_sql(self):
        dd = DDStatement(name="SYSIN", inline_data="SORT FIELDS=(1,10,CH,A)")
        step = Step(name="SORT", program="SORT", dd_statements=[dd])
        result = detect_sql_in_step(step)
        assert result.has_sql is False

    def test_sql_categories(self):
        dd = DDStatement(
            name="SYSIN",
            inline_data="SELECT * FROM T1\nCREATE TABLE T2 (ID INT)\nGRANT SELECT ON T2 TO USER1",
        )
        step = Step(name="RUN", program="DSNTEP2", dd_statements=[dd])
        result = detect_sql_in_step(step)
        assert result.sql_categories == frozenset({"DML", "DDL", "DCL"})

    def test_multiple_dds(self):
        dd1 = DDStatement(name="SYSIN", inline_data="SELECT * FROM T1")
        dd2 = DDStatement(
            name="SYSTSIN", inline_data="DSN SYSTEM(DB2P)\nBIND PLAN(P) MEMBER(M)"
        )
        step = Step(name="RUN", program="IKJEFT01", dd_statements=[dd1, dd2])
        result = detect_sql_in_step(step)
        assert len(result.sql_statements) == 2
        dd_names = [dn for _, _, dn in result.sql_statements]
        assert "SYSIN" in dd_names
        assert "SYSTSIN" in dd_names


class TestDetectSqlInJob:
    """Tests for detect_sql_in_job()."""

    def test_job_with_sql_step(self):
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=DSNTEP2
//SYSIN   DD *
SELECT * FROM TABLE1
WHERE COL1 > 10
/*
//"""
        job = parse_jcl(jcl)
        results = detect_sql_in_job(job)
        assert len(results) == 1
        assert results[0].step_name == "STEP1"
        assert results[0].is_db2_program is True
        assert results[0].has_sql is True

    def test_job_without_sql(self):
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
//DD1     DD DSN=MY.DATASET,DISP=SHR
//"""
        job = parse_jcl(jcl)
        results = detect_sql_in_job(job)
        assert results == []

    def test_job_multiple_steps_mixed(self):
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=SORT
//SORTIN  DD DSN=MY.INPUT,DISP=SHR
//SORTOUT DD DSN=MY.OUTPUT,DISP=(NEW,CATLG)
//SYSIN   DD *
 SORT FIELDS=(1,10,CH,A)
/*
//STEP2   EXEC PGM=DSNTEP2
//SYSIN   DD *
SELECT * FROM TABLE1
/*
//"""
        job = parse_jcl(jcl)
        results = detect_sql_in_job(job)
        # Only STEP2 should be detected
        assert len(results) == 1
        assert results[0].step_name == "STEP2"

    def test_job_detect_sql_convenience(self):
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=DSNTEP2
//SYSIN   DD *
SELECT 1
/*
//"""
        job = parse_jcl(jcl)
        assert job.has_sql is True
        results = job.detect_sql()
        assert len(results) == 1

    def test_step_detect_sql_convenience(self):
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=DSNTEP2
//SYSIN   DD *
DELETE FROM TABLE1
/*
//"""
        job = parse_jcl(jcl)
        from jclparser.model import iter_execution_steps

        step = next(iter_execution_steps(job.steps))
        assert step.has_sql is True
        result = step.detect_sql()
        assert result.is_db2_program is True
        assert result.sql_statements[0][0] == "DELETE"

    def test_ikjeft01_with_db2_sql(self):
        jcl = """\
//MYJOB   JOB CLASS=A
//STEP1   EXEC PGM=IKJEFT01
//SYSTSIN DD *
DSN SYSTEM(DB2P)
RUN PROGRAM(DSNTEP2) PLAN(DSNTEP2)
/*
//SYSIN   DD *
SELECT COL1, COL2
FROM SCHEMA1.TABLE1
WHERE COL1 = 'VALUE'
/*
//"""
        job = parse_jcl(jcl)
        results = detect_sql_in_job(job)
        assert len(results) == 1
        assert results[0].is_db2_program is True
        # Should detect SELECT in the SYSIN DD
        sql_kws = [kw for kw, _, _ in results[0].sql_statements]
        assert "SELECT" in sql_kws


class TestSQLDetectionResult:
    """Tests for SQLDetectionResult dataclass."""

    def test_has_sql_false(self):
        r = SQLDetectionResult()
        assert r.has_sql is False

    def test_has_sql_via_program(self):
        r = SQLDetectionResult(is_db2_program=True)
        assert r.has_sql is True

    def test_has_sql_via_statements(self):
        r = SQLDetectionResult(sql_statements=[("SELECT", "DML", "SYSIN")])
        assert r.has_sql is True

    def test_sql_categories_empty(self):
        r = SQLDetectionResult()
        assert r.sql_categories == frozenset()

    def test_sql_categories_mixed(self):
        r = SQLDetectionResult(
            sql_statements=[
                ("SELECT", "DML", "SYSIN"),
                ("CREATE", "DDL", "SYSIN"),
            ]
        )
        assert r.sql_categories == frozenset({"DML", "DDL"})


class TestDb2Programs:
    """Tests for DB2_PROGRAMS constant."""

    def test_is_frozenset(self):
        assert isinstance(DB2_PROGRAMS, frozenset)

    def test_contains_key_programs(self):
        assert "DSNTEP2" in DB2_PROGRAMS
        assert "IKJEFT01" not in DB2_PROGRAMS
