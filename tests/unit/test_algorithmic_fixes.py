"""
Characterization tests for the three algorithmic fixes.
These exercise the specific scenarios each fix targets and act as
regression guards ensuring refactored code produces identical output.
"""

import pytest

from jclparser import parse_jcl
from jclparser.continuation_handler import ContinuationContext, ContinuationLineHandler


@pytest.mark.unit
class TestInlineDataOrdering:
    """Fix 1: DD * inline data must not be merged with surrounding statements."""

    def test_statement_after_inline_data_is_parsed(self):
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=SORT\n"
            "//SYSIN    DD   *\n"
            "  SORT FIELDS=(1,10,CH,A)\n"
            "  RECORD TYPE=F\n"
            "/*\n"
            "//SYSOUT   DD   SYSOUT=*\n"
        )
        job = parse_jcl(jcl)
        dd_names = [dd.name for dd in job.steps[0].dd_statements]
        assert "SYSIN" in dd_names
        assert "SYSOUT" in dd_names

    def test_multiple_inline_data_blocks_interleaved(self):
        """5 DD * blocks — all steps must be parsed correctly."""
        jcl = "//DDJOB    JOB CLASS=A\n" + "".join(
            f"//STEP{i:02d}   EXEC PGM=IEFBR14\n"
            f"//DD{i:02d}     DD   *\n"
            f"DATA LINE {i}\n"
            "/*\n"
            for i in range(1, 6)
        )
        job = parse_jcl(jcl)
        assert len(job.steps) == 5
        for i, step in enumerate(job.steps, 1):
            assert len(step.dd_statements) == 1
            assert step.dd_statements[0].name == f"DD{i:02d}"

    def test_custom_delimiter_inline_data(self):
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=SORT\n"
            "//SYSIN    DD   DATA,DLM=@@\n"
            "  SORT FIELDS=(1,10,CH,A)\n"
            "@@\n"
            "//SYSOUT   DD   SYSOUT=*\n"
        )
        job = parse_jcl(jcl)
        dd_names = [dd.name for dd in job.steps[0].dd_statements]
        assert "SYSOUT" in dd_names


@pytest.mark.unit
class TestContinuationContextCaching:
    """Fix 2: Context caching must produce identical merged output."""

    def test_multi_continuation_with_nested_parens(self):
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//DD1      DD   DSN=MY.DATASET,\n"
            "//              DISP=(NEW,CATLG,DELETE),\n"
            "//              SPACE=(CYL,(10,5),RLSE),\n"
            "//              DCB=(RECFM=FB,\n"
            "//              LRECL=80,\n"
            "//              BLKSIZE=27920)\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["DSN"] == "MY.DATASET"
        assert dd.parameters["DISP"] == ["NEW", "CATLG", "DELETE"]
        dcb = dd.parameters["DCB"]
        assert isinstance(dcb, list)
        assert any("BLKSIZE" in item for item in dcb)

    def test_analyze_line_context_accepts_starting_ctx(self):
        """_analyze_line_context must accept and use a starting_ctx parameter."""
        handler = ContinuationLineHandler()
        # Simulate mid-quote state: starting inside a quote
        starting = ContinuationContext(in_quotes=True, paren_depth=0)
        ctx = handler._analyze_line_context("VALUE'", starting_ctx=starting)
        # Starting in-quotes, then hits a quote -> toggles back to not-in-quotes
        assert ctx.in_quotes is False

    def test_is_continuation_line_accepts_ctx(self):
        """is_continuation_line must accept ctx kwarg and use it."""
        handler = ContinuationLineHandler()
        # Unclosed paren context: should treat indented line as continuation
        open_ctx = ContinuationContext(in_quotes=False, paren_depth=1)
        result = handler.is_continuation_line(
            "//              LRECL=80,",
            previous_line="//DD1      DD   DCB=(RECFM=FB,",
            ctx=open_ctx,
        )
        assert result is True


@pytest.mark.unit
class TestParameterIndexSlicing:
    """Fix 3: Index-slice approach must produce identical parameter dicts."""

    def test_many_keyword_params_parsed_correctly(self):
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//DD1      DD   DSN=MY.DS,\n"
            "//              DISP=(NEW,CATLG,DELETE),\n"
            "//              SPACE=(CYL,(10,5),RLSE),\n"
            "//              DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920),\n"
            "//              UNIT=SYSDA,LABEL=(1,SL),RETPD=30\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["DSN"] == "MY.DS"
        assert dd.parameters["UNIT"] == "SYSDA"
        assert dd.parameters["RETPD"] == "30"
        assert dd.parameters["DISP"] == ["NEW", "CATLG", "DELETE"]

    def test_quoted_value_with_embedded_comma(self):
        """Quoted values containing commas must not be split."""
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//DD1      DD   DSN=MY.DS,LABEL='A,B',UNIT=SYSDA\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["LABEL"] == "A,B"
        assert dd.parameters["UNIT"] == "SYSDA"

    def test_escaped_quotes_in_value(self):
        """Escaped '' inside quotes must collapse to a single quote."""
        jcl = (
            "//JOB1     JOB CLASS=A\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//DD1      DD   DSN=MY.DS,LABEL='IT''S OK',UNIT=SYSDA\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["LABEL"] == "IT'S OK"
