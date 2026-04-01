"""Tests for OUTPUT statement parsing and modeling."""

from jclparser import parse_jcl


class TestOutputStatementParsing:
    """Verify OUTPUT statements are captured on the Job model."""

    def test_single_output_statement(self):
        jcl = (
            "//MYJOB   JOB (ACCT),'TEST'\n"
            "//OUT1    OUTPUT DEST=LOCAL,CLASS=A\n"
            "//STEP1   EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        assert len(job.output_statements) == 1
        stmt = job.output_statements[0]
        assert stmt.name == "OUT1"
        assert stmt.type == "OUTPUT"
        assert stmt.parameters.get("DEST") == "LOCAL"
        assert stmt.parameters.get("CLASS") == "A"

    def test_multiple_output_statements(self):
        jcl = (
            "//MYJOB   JOB (ACCT),'TEST'\n"
            "//OUT1    OUTPUT DEST=LOCAL\n"
            "//OUT2    OUTPUT DEST=REMOTE,COPIES=3\n"
            "//STEP1   EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        assert len(job.output_statements) == 2
        assert job.output_statements[0].name == "OUT1"
        assert job.output_statements[1].name == "OUT2"
        assert job.output_statements[1].parameters.get("COPIES") == "3"

    def test_output_statement_with_many_parameters(self):
        jcl = (
            "//MYJOB   JOB (ACCT),'TEST'\n"
            "//OUTDD   OUTPUT DEST=LOCAL,CLASS=A,COPIES=2,FORMS=STD\n"
            "//STEP1   EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        assert len(job.output_statements) == 1
        stmt = job.output_statements[0]
        assert stmt.parameters.get("DEST") == "LOCAL"
        assert stmt.parameters.get("CLASS") == "A"
        assert stmt.parameters.get("COPIES") == "2"
        assert stmt.parameters.get("FORMS") == "STD"

    def test_no_output_statements(self):
        jcl = "//MYJOB   JOB (ACCT),'TEST'\n//STEP1   EXEC PGM=IEFBR14\n"
        job = parse_jcl(jcl)
        assert len(job.output_statements) == 0

    def test_output_statement_preserves_line_number(self):
        jcl = (
            "//MYJOB   JOB (ACCT),'TEST'\n"
            "//OUT1    OUTPUT DEST=LOCAL\n"
            "//STEP1   EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        assert len(job.output_statements) == 1
        assert job.output_statements[0].line_number > 0
