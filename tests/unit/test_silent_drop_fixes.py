"""
Regression tests for silent-data-loss fixes found during a parser audit.

Each test pins down a case where JCL content (a parameter, a step, an
operand) was previously discarded with no error and no diagnostic. The
fixes route these cases through ``Job.warnings`` instead of vanishing.
"""

from jclparser import parse_jcl
from jclparser.continuation_handler import ContinuationLineHandler
from jclparser.errors import JCLStructureError
from jclparser.explosion import SymbolScope, substitute_dd_statement
from jclparser.model import DDStatement
from jclparser.parser import _parse_parameters, validate_jcl


class TestDuplicateParameterWarning:
    """A repeated keyword parameter overwrites the earlier value; that must
    now be recorded on Job.warnings instead of vanishing silently."""

    def test_duplicate_dsn_overwrites_but_warns(self):
        jcl = (
            "//J JOB 1\n//S EXEC PGM=X\n//D1 DD DSN=FIRST.DSN,DISP=SHR,DSN=SECOND.DSN\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.parameters["DSN"] == "SECOND.DSN"
        assert any("duplicate parameter 'DSN'" in w for w in job.warnings)
        assert any("FIRST.DSN" in w and "SECOND.DSN" in w for w in job.warnings)

    def test_no_warning_when_no_duplicate(self):
        jcl = "//J JOB 1\n//S EXEC PGM=X\n//D1 DD DSN=A.B,DISP=SHR\n"
        job = parse_jcl(jcl)
        assert job.warnings == []

    def test_parse_parameters_records_duplicate_directly(self):
        warnings: list[str] = []
        params = _parse_parameters(
            "DSN=A,DSN=B,DSN=C", line_number=5, warnings=warnings
        )
        assert params["DSN"] == "C"
        assert len(warnings) == 2
        assert all("Line 5" in w for w in warnings)

    def test_parse_parameters_no_warnings_list_is_safe(self):
        # Default call (no warnings list) must not raise or change behavior.
        params = _parse_parameters("DSN=A,DSN=B")
        assert params["DSN"] == "B"


class TestCommentInsideContinuation:
    """A //* comment must not terminate a statement with a pending
    comma-continuation; the operand data after the comment must survive."""

    def test_comment_inside_comma_continuation_preserves_operand(self):
        jcl = "//J JOB 1\n//S1 EXEC PGM=X,\n//* inline comment\n//         PARM=VALUE\n"
        job = parse_jcl(jcl)
        assert job.steps[0].parameters.get("PARM") == "VALUE"

    def test_comment_between_complete_statements_still_breaks(self):
        # A comment that is NOT inside a pending continuation must still
        # separate two independent statements as before.
        jcl = (
            "//J JOB 1\n"
            "//S1 EXEC PGM=X\n"
            "//* a normal comment\n"
            "//D1 DD DSN=A.B,DISP=SHR\n"
        )
        job = parse_jcl(jcl)
        assert job.steps[0].dd_statements[0].dataset_name == "A.B"

    def test_interspersed_comment_does_not_reorder_before_its_statement(self):
        # The statement must keep its place in the merged output; a comment
        # discovered mid-continuation is emitted right after it, not before.
        handler = ContinuationLineHandler()
        lines = [
            "//DD1 DD DSN=MY.DATA,",
            "//* This is a comment",
            "//             DISP=SHR,",
            "//             UNIT=SYSDA",
        ]
        merged = handler.merge_continuation_lines(lines)
        assert len(merged) == 2
        assert merged[0][0].startswith("//DD1")
        assert merged[1][0] == "//* This is a comment"


class TestDanglingCommaDoesNotSwallowNextStatement:
    """A trailing comma with no real continuation must not absorb the next
    named statement into the previous one's parameters."""

    def test_next_named_exec_survives(self):
        jcl = "//J JOB 1\n//S1 EXEC PGM=X,\n//S2 EXEC PGM=Y\n"
        job = parse_jcl(jcl)
        assert [s.name for s in job.steps] == ["S1", "S2"]
        assert job.steps[0].parameters == {}
        assert job.steps[1].program == "Y"

    def test_next_named_dd_survives(self):
        jcl = "//J JOB 1\n//S1 EXEC PGM=X\n//D1 DD DSN=A.B,\n//D2 DD DSN=C.D,DISP=SHR\n"
        job = parse_jcl(jcl)
        names = [dd.name for dd in job.steps[0].dd_statements]
        assert names == ["D1", "D2"]
        assert job.steps[0].get_dd("D2").dataset_name == "C.D"

    def test_next_named_statement_with_unrecognized_keyword_survives(self):
        # A name field is non-blank regardless of whether the operation
        # keyword is one this parser recognizes; the name-field rule alone
        # must exclude it from being swallowed as a continuation.
        jcl = "//J JOB 1\n//S1 EXEC PGM=X,\n//S2 UNKNOWNOP FOO=BAR\n"
        job = parse_jcl(jcl)
        assert [s.name for s in job.steps] == ["S1"]
        assert job.steps[0].parameters == {}
        assert any("UNKNOWNOP" in w for w in job.warnings)


class TestUnknownStatementWarning:
    """An unrecognized statement type must be recorded, not just DEBUG-logged
    and forgotten."""

    def test_unknown_statement_recorded_on_job_warnings(self):
        jcl = "//J JOB 1\n//S EXEC PGM=IEFBR14\n//BOGUS FROBNICATE FOO=BAR\n"
        job = parse_jcl(jcl)
        assert any("FROBNICATE" in w for w in job.warnings)
        assert len(job.steps) == 1


class TestUnresolvedSymbolWarning:
    """A &SYMBOL that resolves to nothing is blanked in the dataset name;
    that must now be recorded on Job.warnings."""

    def test_unresolved_symbol_in_dsn_warns(self):
        jcl = "//J JOB 1\n// SET FOO=BAR\n//S EXEC PGM=X\n//D1 DD DSN=&UNDEF..FILE\n"
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.dataset_name == ".FILE"
        assert any("&UNDEF" in w and "D1" in w for w in job.warnings)

    def test_resolved_symbol_produces_no_warning(self):
        jcl = "//J JOB 1\n// SET FOO=BAR\n//S EXEC PGM=X\n//D1 DD DSN=&FOO..FILE\n"
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.dataset_name == "BAR.FILE"
        assert job.warnings == []


class TestListValuedDispositionSubstitution:
    """DISP=(&SYM,CATLG,DELETE) parses to a list; substitute_dd_statement()
    must substitute each element instead of skipping the whole list because
    substitute_symbols() no-ops on non-str input."""

    def test_unresolved_symbol_in_list_disposition_warns(self):
        dd = DDStatement(
            name="D1",
            dataset_name="A.B",
            disposition=["&STATUS", "CATLG", "DELETE"],
            line_number=4,
        )
        warnings: list[str] = []
        substitute_dd_statement(dd, SymbolScope(), strict=False, warnings=warnings)
        assert dd.disposition == ["", "CATLG", "DELETE"]
        assert any("&STATUS" in w and "D1" in w for w in warnings)

    def test_resolved_symbol_in_list_disposition_substitutes(self):
        dd = DDStatement(
            name="D1",
            dataset_name="A.B",
            disposition=["&STATUS", "CATLG", "DELETE"],
            line_number=4,
        )
        scope = SymbolScope(set_symbols={"STATUS": "NEW"})
        warnings: list[str] = []
        substitute_dd_statement(dd, scope, strict=False, warnings=warnings)
        assert dd.disposition == ["NEW", "CATLG", "DELETE"]
        assert warnings == []

    def test_full_pipeline_resolves_list_disposition_symbol(self):
        jcl = (
            "//J JOB 1\n"
            "// SET STATUS=NEW\n"
            "//S EXEC PGM=X\n"
            "//D1 DD DSN=A.B,DISP=(&STATUS,CATLG,DELETE)\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.disposition == ["NEW", "CATLG", "DELETE"]
        assert job.warnings == []


class TestValidateJclReturnsStructureErrors:
    """validate_jcl() must return a list of ParseError, never raise, even
    for structural failures like a DD statement with no EXEC in the job."""

    def test_dd_before_any_exec_returns_error_not_raise(self):
        jcl = "//J JOB 1\n//DD1 DD DSN=ORPHAN,DISP=SHR\n"
        errors = validate_jcl(jcl, level="semantic")
        assert len(errors) == 1
        assert "DD statement found before any EXEC step" in errors[0].message

    def test_strict_parse_still_raises_directly(self):
        import pytest

        jcl = "//J JOB 1\n//DD1 DD DSN=ORPHAN,DISP=SHR\n"
        with pytest.raises(JCLStructureError):
            parse_jcl(jcl, strict_mode=True)
