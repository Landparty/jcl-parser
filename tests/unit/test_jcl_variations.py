"""
Comprehensive JCL variation / edge-case regression suite.

This module pins down the breadth of real-world JCL syntax variations the
parser is expected to handle, plus its *graceful-degradation* behaviour on
malformed or pathological input.  Every assertion here reflects the parser's
actual, verified behaviour — the goal is to catch silent regressions in the
supported surface, not to introduce new semantics.

Grouping:
  * Dataset-name variations (PDS members, GDG, referbacks, qualification)
  * Parameter-value variations (sub-lists, COND, VOL=SER, SYSOUT forms)
  * Quoting and apostrophe escaping
  * Continuation-line variations
  * In-stream data (DD *, DD DATA, custom DLM)
  * Symbolic-parameter resolution (SET chains, &&, cycles)
  * Control statements (IF/THEN/ELSE, CNTL/ENDCNTL, JCLLIB, OUTPUT)
  * Robustness / graceful errors (empty input, truncation, encodings)
"""

import pytest

from jclparser import parse_jcl, validate_jcl
from jclparser.explosion import explode_job
from jclparser.errors import JCLSyntaxError

pytestmark = pytest.mark.unit


def _first_dd(job, step=0, index=0):
    return job.steps[step].dd_statements[index]


class TestDatasetNameVariations:
    """Dataset names take many shapes; all must survive parsing intact."""

    def test_pds_member_in_dsn(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD DSN=MY.PDS(MEMBER),DISP=SHR\n"
        )
        assert _first_dd(job).parameters["DSN"] == "MY.PDS(MEMBER)"

    @pytest.mark.parametrize("ref", ["A.B.C(+1)", "A.B.C(-1)", "A.B.C(0)"])
    def test_gdg_relative_generation(self, ref):
        job = parse_jcl(f"//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD DSN={ref},DISP=SHR\n")
        assert _first_dd(job).parameters["DSN"] == ref

    def test_backward_reference_dsn(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD DSN=*.STEP1.DD1,DISP=SHR\n"
        )
        assert _first_dd(job).parameters["DSN"] == "*.STEP1.DD1"

    def test_temporary_dataset_double_ampersand_preserved(self):
        """&&TEMP must NOT be treated as a symbolic reference at parse time."""
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD DSN=&&TEMP,DISP=(NEW,DELETE)\n"
        )
        assert _first_dd(job).parameters["DSN"] == "&&TEMP"


class TestParameterValueVariations:
    """Keyword parameters with sub-lists, empty positions, and nesting."""

    def test_disp_three_position_list(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD DSN=A.B,DISP=(NEW,CATLG,DELETE)\n"
        )
        assert _first_dd(job).parameters["DISP"] == ["NEW", "CATLG", "DELETE"]

    def test_disp_empty_leading_position(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD DSN=A.B,DISP=(,CATLG,DELETE)\n"
        )
        assert _first_dd(job).parameters["DISP"] == ["", "CATLG", "DELETE"]

    def test_sysout_with_empty_writer_and_form(self):
        job = parse_jcl("//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD SYSOUT=(A,,FORM1)\n")
        assert _first_dd(job).parameters["SYSOUT"] == ["A", "", "FORM1"]

    def test_exec_cond_subparameters(self):
        job = parse_jcl("//J JOB (A),'T'\n//S EXEC PGM=X,COND=(0,NE,STEP1)\n")
        assert job.steps[0].parameters["COND"] == ["0", "NE", "STEP1"]

    def test_vol_ser_nested_list_kept_as_value(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n"
            "//D DD DSN=A,VOL=SER=(V1,V2,V3),DISP=SHR\n"
        )
        assert _first_dd(job).parameters["VOL"] == "SER=(V1,V2,V3)"

    def test_nested_parentheses_become_list(self):
        job = parse_jcl("//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD A=(((Z)))\n")
        assert _first_dd(job).parameters["A"] == ["((Z))"]

    def test_dcb_subparameters_parsed_as_list(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n"
            "//D DD DCB=(RECFM=FB,LRECL=80,BLKSIZE=800)\n"
        )
        assert _first_dd(job).parameters["DCB"] == [
            "RECFM=FB",
            "LRECL=80",
            "BLKSIZE=800",
        ]


class TestQuotingVariations:
    """JCL escapes a single quote by doubling it; quotes hide special chars."""

    def test_doubled_apostrophe_in_job_text(self):
        job = parse_jcl("//J JOB (A),'O''BRIEN'\n//S EXEC PGM=X\n")
        assert job.name == "J"

    def test_quoted_parm_with_parens_and_escaped_quote(self):
        job = parse_jcl("//J JOB (A),'T'\n//S EXEC PGM=X,PARM='POSIX(ON),''QUOTED'''\n")
        assert job.steps[0].parameters["PARM"] == "POSIX(ON),'QUOTED'"

    def test_comma_inside_quotes_not_a_separator(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD DSN=A,LABEL='RETPD=30,EXPDT=99'\n"
        )
        assert _first_dd(job).parameters["LABEL"] == "RETPD=30,EXPDT=99"


class TestContinuationVariations:
    """Multi-line statements joined across // continuation records."""

    def test_keyword_continuation(self):
        job = parse_jcl("//J JOB (A),'T'\n//S EXEC PGM=X,\n//             PARM=ABC\n")
        assert job.steps[0].parameters["PARM"] == "ABC"

    def test_trailing_comma_then_eof_does_not_crash(self):
        job = parse_jcl("//J JOB (A),'T',\n//S EXEC PGM=X\n")
        assert job.name == "J"

    def test_long_dd_continuation(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n"
            "//D DD DSN=MY.DATA,DISP=SHR,\n"
            "//             UNIT=SYSDA,SPACE=(CYL,(10,5))\n"
        )
        dd = _first_dd(job)
        assert dd.parameters["DSN"] == "MY.DATA"
        assert dd.parameters["UNIT"] == "SYSDA"
        assert dd.parameters["SPACE"] == ["CYL", "(10,5)"]


class TestInStreamDataVariations:
    """DD * / DD DATA and custom delimiters."""

    def test_dd_star_default_delimiter(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//SYSIN DD *\nrow1\nrow2\n/*\n"
            "//S2 EXEC PGM=Y\n"
        )
        assert _first_dd(job).inline_data == "row1\nrow2"
        assert [s.name for s in job.steps] == ["S", "S2"]

    def test_dd_data_retains_slashslash_records(self):
        """DD DATA exists precisely so // records can be supplied as data."""
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//SYSIN DD DATA\n"
            "//LOOKS LIKE JCL\n/*\n//S2 EXEC PGM=Y\n"
        )
        assert _first_dd(job).inline_data == "//LOOKS LIKE JCL"
        assert [s.name for s in job.steps] == ["S", "S2"]

    def test_custom_dlm_delimiter(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//SYSIN DD *,DLM=@@\n"
            "//STILL DATA\n@@\n//S2 EXEC PGM=Y\n"
        )
        assert _first_dd(job).inline_data == "//STILL DATA"
        assert [s.name for s in job.steps] == ["S", "S2"]

    def test_empty_in_stream_data(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//SYSIN DD *\n/*\n//S2 EXEC PGM=Y\n"
        )
        assert _first_dd(job).inline_data == ""

    def test_dd_star_terminated_by_next_statement_without_delimiter(self):
        """A DD * with no /* is closed by the next // record (z/OS rule)."""
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//SYSIN DD *\nrow1\nrow2\n"
            "//S2 EXEC PGM=Y\n//D2 DD DSN=A,DISP=SHR\n"
        )
        assert _first_dd(job).inline_data == "row1\nrow2"
        # The following statement must NOT be swallowed as data.
        assert [s.name for s in job.steps] == ["S", "S2"]
        assert job.steps[1].dd_statements[0].name == "D2"

    def test_dd_star_terminated_by_end_of_file(self):
        """A DD * that runs to EOF keeps its data instead of dropping it."""
        job = parse_jcl("//J JOB (A),'T'\n//S EXEC PGM=X\n//SYSIN DD *\nfinal\ndata\n")
        assert _first_dd(job).inline_data == "final\ndata"

    def test_dd_data_with_dlm_keeps_slashslash_until_delimiter(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n//SYSIN DD DATA,DLM=##\n"
            "//STEP-LIKE LINE\n/* not the end\n##\n//S2 EXEC PGM=Y\n"
        )
        assert _first_dd(job).inline_data == "//STEP-LIKE LINE\n/* not the end"
        assert [s.name for s in job.steps] == ["S", "S2"]


class TestSymbolicParameterResolution:
    """SET symbols, period concatenation, and pathological references."""

    def test_set_chain_with_period_concatenation(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n// SET HLQ=PROD\n// SET DSN=&HLQ..DATA\n"
            "//S EXEC PGM=X\n//D DD DSN=&DSN,DISP=SHR\n"
        )
        assert _first_dd(job).parameters["DSN"] == "PROD.DATA"

    def test_symbol_cycle_resolves_without_hanging(self):
        """A → B → A must not loop forever; unresolved symbols drop out."""
        job = parse_jcl(
            "//J JOB (A),'T'\n// SET A=&B\n// SET B=&A\n"
            "//S EXEC PGM=X\n//D DD DSN=&A,DISP=SHR\n"
        )
        # The important property is that parsing terminates and yields a Job.
        assert job.steps[0].name == "S"

    def test_long_set_chain_resolves(self):
        lines = ["//J JOB (A),'T'"]
        lines += [f"// SET S{i}=&S{i + 1}" for i in range(20)]
        lines += ["// SET S20=DONE", "//S EXEC PGM=X", "//D DD DSN=&S0,DISP=SHR"]
        job = parse_jcl("\n".join(lines) + "\n")
        assert job.steps[0].name == "S"


class TestControlStatements:
    """IF/THEN/ELSE, CNTL/ENDCNTL, JCLLIB, OUTPUT."""

    def test_if_then_else_endif_branches(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S1 EXEC PGM=A\n// IF (S1.RC=0) THEN\n"
            "//S2 EXEC PGM=B\n// ELSE\n//S3 EXEC PGM=C\n// ENDIF\n"
        )
        assert len(job.conditionals) == 1
        block = job.conditionals[0]
        assert [s.name for s in block.then_steps] == ["S2"]
        assert [s.name for s in block.else_steps] == ["S3"]

    def test_cntl_endcntl_block(self):
        job = parse_jcl("//J JOB (A),'T'\n//S EXEC PGM=X\n//C CNTL\n//E ENDCNTL\n")
        assert [s.name for s in job.steps] == ["S"]

    def test_jcllib_order(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n// JCLLIB ORDER=(MY.PROC.LIB,OTHER.LIB)\n//S EXEC PGM=X\n"
        )
        assert [s.name for s in job.steps] == ["S"]

    def test_output_statement(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//O OUTPUT CLASS=A,DEST=LOCAL\n//S EXEC PGM=X\n"
        )
        assert job.name == "J"
        assert [s.name for s in job.steps] == ["S"]


class TestProcedureExpansionVariations:
    """Inline PROC use and symbolic override resolution through explosion."""

    def test_inline_proc_symbol_override(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//P PROC DSN=DEFAULT\n//S1 EXEC PGM=X\n"
            "//D DD DSN=&DSN,DISP=SHR\n// PEND\n//RUN EXEC P,DSN=OVERRIDE\n"
        )
        exploded = explode_job(job)
        # The override value must win over the PROC default.
        dsns = [
            dd.parameters.get("DSN")
            for step in exploded.steps
            for dd in step.dd_statements
        ]
        assert "OVERRIDE" in dsns

    def test_inline_proc_default_symbol(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//P PROC DSN=DEFAULT\n//S1 EXEC PGM=X\n"
            "//D DD DSN=&DSN,DISP=SHR\n// PEND\n//RUN EXEC P\n"
        )
        exploded = explode_job(job)
        dsns = [
            dd.parameters.get("DSN")
            for step in exploded.steps
            for dd in step.dd_statements
        ]
        assert "DEFAULT" in dsns


class TestRobustnessAndGracefulErrors:
    """Pathological input must fail cleanly (typed errors) — never crash."""

    @pytest.mark.parametrize("src", ["", "   \n  \n", "//* only a comment\n"])
    def test_no_job_card_raises_clean_syntax_error(self, src):
        with pytest.raises(JCLSyntaxError):
            parse_jcl(src)

    @pytest.mark.parametrize("src", ["", "   \n", "//* comment only\n"])
    def test_validate_jcl_is_lenient_on_empty_input(self, src):
        """validate_jcl reports problems rather than raising on trivial input."""
        assert validate_jcl(src) == []

    def test_unbalanced_parentheses_raise_syntax_error(self):
        with pytest.raises(JCLSyntaxError):
            parse_jcl(
                "//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD DSN=A.B,DISP=(NEW,CATLG\n"
            )

    def test_truncated_long_line_raises_rather_than_crashing(self):
        """A statement whose parens are cut off at column 72 fails cleanly."""
        runaway = "//J JOB (A),'T'\n//S EXEC PGM=X\n//D DD A=" + "(" * 100 + "\n"
        with pytest.raises(JCLSyntaxError):
            parse_jcl(runaway)

    def test_crlf_line_endings(self):
        job = parse_jcl("//J JOB (A),'T'\r\n//S EXEC PGM=X\r\n")
        assert [s.name for s in job.steps] == ["S"]

    def test_tab_separated_fields(self):
        job = parse_jcl("//J\tJOB\t(A),'T'\n//S\tEXEC\tPGM=X\n")
        assert job.name == "J"
        assert [s.name for s in job.steps] == ["S"]

    def test_sequence_numbers_in_columns_73_to_80_stripped(self):
        # An 80-column record: cols 73-80 are a sequence number and must be
        # discarded rather than parsed as JCL content.
        body = "//S EXEC PGM=X"
        line = body + " " * (72 - len(body)) + "SEQ00010"
        assert len(line) == 80
        job = parse_jcl("//J JOB (A),'T'\n" + line + "\n")
        assert job.steps[0].name == "S"
        # The trailing "SEQ00010" must not have leaked into the program name.
        assert job.steps[0].program == "X"

    def test_dd_concatenation_with_blank_name(self):
        job = parse_jcl(
            "//J JOB (A),'T'\n//S EXEC PGM=X\n"
            "//D DD DSN=A,DISP=SHR\n//  DD DSN=B,DISP=SHR\n"
        )
        assert len(job.steps[0].dd_statements) == 2
