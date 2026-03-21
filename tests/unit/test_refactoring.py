"""
Tests for the P0-P3 refactoring tasks described in plans/TODO.md.

Each test class covers one TASK from the TODO.  All tests verify the new
behaviour works correctly and that the old (buggy / duplicated) behaviour is
gone.
"""

import io
from pathlib import Path
from typing import List

import pytest

# ---------------------------------------------------------------------------
# TASK-01: _explode_step jcllib_order fix
# ---------------------------------------------------------------------------


class TestExplodeStepJcllibOrder:
    """Tests for TASK-01: _explode_step now forwards jcllib_order correctly."""

    def test_jcllib_order_forwarded_to_loader(self):
        """jcllib_order from the job is forwarded to proc_loader.load_procedure."""
        from jclparser.explosion import _explode_step
        from jclparser.model import Step, Procedure
        from jclparser.proc_loader import ProcedureLoader

        captured = {}

        class CapturingLoader(ProcedureLoader):
            def load_procedure(self, name, libraries=None):
                captured["libraries"] = libraries
                proc = Procedure(name=name, steps=[])
                # Make the step not a proc invocation so recursion stops
                inner = Step("INNER", program="PGM1")
                proc.steps.append(inner)
                return proc

        step = Step("STEP", procedure="MYPROC")
        from jclparser.explosion import ProcExpansionInfo
        from jclparser.explosion import SymbolScope

        result = _explode_step(
            step=step,
            proc_loader=CapturingLoader(),
            base_scope=SymbolScope(),
            call_chain=[],
            depth=0,
            max_depth=10,
            audit_records=None,
            expansion_map={},
            strict_symbols=False,
            jcllib_order=["MYLIB"],
        )
        assert captured["libraries"] == ("MYLIB",), (
            "jcllib_order should be forwarded as a tuple to load_procedure"
        )

    def test_jcllib_order_none_when_not_provided(self):
        """If no jcllib_order is given, load_procedure receives None."""
        from jclparser.explosion import _explode_step
        from jclparser.model import Step, Procedure
        from jclparser.proc_loader import ProcedureLoader
        from jclparser.explosion import SymbolScope

        captured = {}

        class CapturingLoader(ProcedureLoader):
            def load_procedure(self, name, libraries=None):
                captured["libraries"] = libraries
                proc = Procedure(name=name, steps=[])
                proc.steps.append(Step("INNER", program="PGM1"))
                return proc

        step = Step("STEP", procedure="MYPROC")
        _explode_step(
            step=step,
            proc_loader=CapturingLoader(),
            base_scope=SymbolScope(),
            call_chain=[],
            depth=0,
            max_depth=10,
            audit_records=None,
            expansion_map={},
            strict_symbols=False,
            jcllib_order=None,  # default
        )
        assert captured["libraries"] is None

    def test_jcllib_order_list_forwarded_as_tuple(self):
        """jcllib_order is always forwarded as tuple (hashable) for LRU-cache loaders."""
        from jclparser.explosion import _explode_step
        from jclparser.model import Step, Procedure
        from jclparser.proc_loader import CompositeProcedureLoader, InlineProcedureLoader
        from jclparser.explosion import SymbolScope

        proc = Procedure(name="MYPROC", steps=[Step("INNER", program="PGM1")])
        loader = CompositeProcedureLoader([InlineProcedureLoader([proc])])
        step = Step("STEP", procedure="MYPROC")
        # Should not raise TypeError (unhashable type: list)
        result = _explode_step(
            step=step,
            proc_loader=loader,
            base_scope=SymbolScope(),
            call_chain=[],
            depth=0,
            max_depth=10,
            audit_records=None,
            expansion_map={},
            strict_symbols=False,
            jcllib_order=["LIBX", "LIBY"],  # list — must be converted internally
        )
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# TASK-02: validate_dataset_name / validate_disposition wrappers
# ---------------------------------------------------------------------------


class TestValidateDatasetNameWrapper:
    """Tests for TASK-02: validate_dataset_name delegates to DatasetNameValidator."""

    def test_multi_level_name_valid(self):
        from jclparser.validators import validate_dataset_name
        assert validate_dataset_name("MY.DATA.SET")

    def test_hyphen_in_qualifier_is_valid(self):
        """Per IBM spec hyphens ARE allowed inside qualifiers."""
        from jclparser.validators import validate_dataset_name
        assert validate_dataset_name("MY-DATA.SET")

    def test_44_char_total_valid(self):
        """DatasetNameValidator allows up to 44 total characters."""
        from jclparser.validators import validate_dataset_name
        # 44 chars: 5 qualifiers of 8 chars + 4 dots = 44
        name = ".".join(["A" * 8] * 5)
        assert len(name) == 44
        assert validate_dataset_name(name)

    def test_empty_dsn_invalid(self):
        from jclparser.validators import validate_dataset_name
        assert not validate_dataset_name("")

    def test_asterisk_invalid(self):
        from jclparser.validators import validate_dataset_name
        assert not validate_dataset_name("MY*.SET")

    def test_qualifier_starts_with_number_invalid(self):
        from jclparser.validators import validate_dataset_name
        assert not validate_dataset_name("MY.1DATA")

    def test_temporary_dataset_valid(self):
        from jclparser.validators import validate_dataset_name
        assert validate_dataset_name("&&TMPDATA")


class TestValidateDispositionWrapper:
    """Tests for TASK-02: validate_disposition delegates to DISPValidator."""

    def test_simple_new_valid(self):
        from jclparser.validators import validate_disposition
        assert validate_disposition("NEW")

    def test_simple_shr_valid(self):
        from jclparser.validators import validate_disposition
        assert validate_disposition("SHR")

    def test_complex_three_part_valid(self):
        from jclparser.validators import validate_disposition
        assert validate_disposition("(NEW,CATLG,DELETE)")

    def test_empty_string_invalid(self):
        from jclparser.validators import validate_disposition
        assert not validate_disposition("")

    def test_none_like_empty_invalid(self):
        from jclparser.validators import validate_disposition
        assert not validate_disposition("")

    def test_invalid_status_invalid(self):
        from jclparser.validators import validate_disposition
        assert not validate_disposition("(BOGUS,CATLG)")

    def test_missing_status_invalid(self):
        from jclparser.validators import validate_disposition
        assert not validate_disposition("(,CATLG)")

    def test_list_form_new_valid(self):
        """Parser sometimes stores DISP as a list; wrapper must handle it."""
        from jclparser.validators import validate_disposition
        assert validate_disposition(["NEW", "CATLG", "DELETE"])

    def test_list_form_invalid_status(self):
        from jclparser.validators import validate_disposition
        assert not validate_disposition(["BOGUS", "CATLG"])

    def test_list_form_empty_list_invalid(self):
        from jclparser.validators import validate_disposition
        assert not validate_disposition([])


# ---------------------------------------------------------------------------
# TASK-03: read_source helper
# ---------------------------------------------------------------------------


class TestReadSource:
    """Tests for TASK-03: read_source() in utils.py."""

    def test_string_content_returned_as_is(self):
        from jclparser.utils import read_source
        jcl = "//MYJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEBGENER"
        assert read_source(jcl) == jcl

    def test_file_like_object(self):
        from jclparser.utils import read_source
        content = "//MYJOB JOB\n"
        buf = io.StringIO(content)
        result = read_source(buf)
        assert result == content
        # Should be reset for reuse
        assert buf.tell() == 0

    def test_path_object(self, tmp_path):
        from jclparser.utils import read_source
        jcl_file = tmp_path / "test.jcl"
        jcl_file.write_text("//MYJOB JOB\n")
        assert read_source(jcl_file) == "//MYJOB JOB\n"

    def test_path_string_with_jcl_extension(self, tmp_path):
        from jclparser.utils import read_source
        jcl_file = tmp_path / "test.jcl"
        jcl_file.write_text("//MYJOB JOB\n")
        assert read_source(str(jcl_file)) == "//MYJOB JOB\n"

    def test_missing_path_raises_file_not_found(self, tmp_path):
        from jclparser.utils import read_source
        with pytest.raises(FileNotFoundError):
            read_source(tmp_path / "nonexistent.jcl")

    def test_missing_path_string_raises_file_not_found(self, tmp_path):
        from jclparser.utils import read_source
        with pytest.raises(FileNotFoundError):
            read_source(str(tmp_path / "nonexistent.jcl"))

    def test_jcl_content_string_not_treated_as_path(self):
        from jclparser.utils import read_source
        jcl = "//MYJOB JOB CLASS=A\n//STEP1 EXEC PGM=FOO"
        # Should not try to open a file
        assert read_source(jcl) == jcl


# ---------------------------------------------------------------------------
# TASK-04: _STATEMENT_TYPES constant
# ---------------------------------------------------------------------------


class TestStatementTypesConstant:
    """Tests for TASK-04: single _STATEMENT_TYPES frozenset in parser.py."""

    def test_constant_exported(self):
        from jclparser.parser import _STATEMENT_TYPES
        assert isinstance(_STATEMENT_TYPES, frozenset)

    def test_all_expected_keywords_present(self):
        from jclparser.parser import _STATEMENT_TYPES
        required = {"JOB", "EXEC", "DD", "PROC", "PEND", "JCLLIB", "INCLUDE",
                    "SET", "IF", "THEN", "ELSE", "ENDIF", "NULL", "COMMAND",
                    "CNTL", "ENDCNTL"}
        assert required.issubset(_STATEMENT_TYPES)

    def test_no_duplicate_literals_in_parse_statement(self):
        """parse_statement should use the constant, not three inline lists."""
        import ast, inspect, textwrap
        from jclparser import parser
        source = inspect.getsource(parser.parse_statement)
        tree = ast.parse(textwrap.dedent(source))
        # Count list literals whose elements are all-uppercase strings matching JCL keywords
        jcl_kw = {"JOB", "EXEC", "DD", "PROC"}
        list_defs = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.List)
            and any(
                isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value in jcl_kw
                for e in node.elts
            )
        ]
        assert len(list_defs) == 0, (
            "parse_statement should not contain inline statement-type list literals"
        )


# ---------------------------------------------------------------------------
# TASK-07: ParameterParser._split_parameters canonical behaviour
# ---------------------------------------------------------------------------


class TestSplitParametersCanonical:
    """Tests for TASK-07: split_jcl_parameters delegates to ParameterParser."""

    def test_simple_split(self):
        from jclparser.utils import split_jcl_parameters
        assert split_jcl_parameters("A=1,B=2,C=3") == ["A=1", "B=2", "C=3"]

    def test_quoted_string_not_split(self):
        from jclparser.utils import split_jcl_parameters
        params = split_jcl_parameters("A='X,Y',B=Z")
        assert len(params) == 2
        assert params[0] == "A='X,Y'"

    def test_doubled_quote_in_string(self):
        """JCL escape: '' inside a quoted string is a literal apostrophe."""
        from jclparser.utils import split_jcl_parameters
        params = split_jcl_parameters("A='X''Y',B='P''Q''R'")
        assert len(params) == 2, f"Expected 2 parts, got {len(params)}: {params}"
        assert params[0] == "A='X''Y'"
        assert params[1] == "B='P''Q''R'"

    def test_nested_parentheses_not_split(self):
        from jclparser.utils import split_jcl_parameters
        params = split_jcl_parameters("A=(B,(C,D),E),F=G")
        assert len(params) == 2
        assert params[0] == "A=(B,(C,D),E)"

    def test_empty_string(self):
        from jclparser.utils import split_jcl_parameters
        assert split_jcl_parameters("") == []
        assert split_jcl_parameters("   ") == []

    def test_parameter_parser_split_doubled_quotes(self):
        """Canonical implementation in ParameterParser handles '' correctly."""
        from jclparser.parameter_ast import ParameterParser
        pp = ParameterParser()
        parts = pp._split_parameters("A='X''Y',B='P''Q''R'")
        assert len(parts) == 2


# ---------------------------------------------------------------------------
# TASK-08: JCLLIBProcedureLoader cache initialised in __init__
# ---------------------------------------------------------------------------


class TestJCLLIBProcedureLoaderCache:
    """Tests for TASK-08: _cache is initialised in __init__, not lazily."""

    def test_cache_exists_after_init(self, tmp_path):
        from jclparser.proc_loader import JCLLIBProcedureLoader
        loader = JCLLIBProcedureLoader(base_path=tmp_path)
        assert hasattr(loader, "_cache"), "_cache must be an attribute after __init__"
        assert isinstance(loader._cache, dict)

    def test_cache_empty_after_init(self, tmp_path):
        from jclparser.proc_loader import JCLLIBProcedureLoader
        loader = JCLLIBProcedureLoader(base_path=tmp_path)
        assert loader._cache == {}

    def test_cache_stores_result(self, tmp_path):
        from jclparser.proc_loader import JCLLIBProcedureLoader
        loader = JCLLIBProcedureLoader(base_path=tmp_path)
        result = loader.load_procedure("NONEXISTENT", [])
        assert result is None
        # Result should be cached
        assert ("NONEXISTENT", ()) in loader._cache


# ---------------------------------------------------------------------------
# TASK-09: POSITIONAL_PARAM_PREFIX constant and is_positional_key helper
# ---------------------------------------------------------------------------


class TestPositionalParamConstants:
    """Tests for TASK-09: POSITIONAL_PARAM_PREFIX and is_positional_key."""

    def test_prefix_value(self):
        from jclparser.utils import POSITIONAL_PARAM_PREFIX
        assert POSITIONAL_PARAM_PREFIX == "_pos_"

    def test_is_positional_key_true(self):
        from jclparser.utils import is_positional_key
        assert is_positional_key("_pos_0")
        assert is_positional_key("_pos_1")
        assert is_positional_key("_pos_99")

    def test_is_positional_key_false(self):
        from jclparser.utils import is_positional_key
        assert not is_positional_key("PGM")
        assert not is_positional_key("DSN")
        assert not is_positional_key("")
        assert not is_positional_key("DISP")

    def test_parser_uses_constant_for_positional(self):
        """Parser stores positional parameters using the constant prefix."""
        from jclparser.parser import parse_statement
        from jclparser.utils import POSITIONAL_PARAM_PREFIX
        stmt = parse_statement("//MYJOB JOB (ACCT1,'PROJECT X')", 1)
        positional_keys = [k for k in stmt.parameters if k.startswith(POSITIONAL_PARAM_PREFIX)]
        assert len(positional_keys) > 0, "Job accounting info should be stored as positional key"


# ---------------------------------------------------------------------------
# TASK-10: Step.is_procedure
# ---------------------------------------------------------------------------


class TestIsProcedure:
    """Tests for Step.is_procedure property."""

    def test_proc_step_is_true(self):
        from jclparser.model import Step
        step = Step("STEP1", procedure="MYPROC")
        assert step.is_procedure is True

    def test_pgm_step_is_false(self):
        from jclparser.model import Step
        step = Step("STEP1", program="IEBGENER")
        assert step.is_procedure is False

    def test_setting_procedure_makes_true(self):
        from jclparser.model import Step
        step = Step("STEP1")
        step.procedure = "NEWPROC"
        assert step.is_procedure is True

    def test_clearing_procedure_makes_false(self):
        from jclparser.model import Step
        step = Step("STEP1", procedure="MYPROC")
        step.procedure = None
        assert step.is_procedure is False


# ---------------------------------------------------------------------------
# TASK-06: Job.validate() delegates to validate_job_structure
# ---------------------------------------------------------------------------


class TestJobValidateDelegation:
    """Tests for TASK-06: Job.validate() must call validate_data_dependencies."""

    def test_returns_list(self):
        from jclparser.model import Job, Step
        job = Job("MYJOB")
        job.add_step(Step("STEP1", program="IEBGENER"))
        result = job.validate()
        assert isinstance(result, list)

    def test_includes_data_dependency_errors(self):
        """Temporary dataset used without being created should now surface."""
        from jclparser.model import Job, Step, DDStatement
        from jclparser.errors import ErrorType
        job = Job("MYJOB")
        step = Step("STEP1", program="IEBGENER")
        # Use a temp dataset that is never created
        dd = DDStatement("INDD", dataset_name="&&TMPDATA", disposition="OLD")
        step.add_dd(dd)
        job.add_step(step)
        errors = job.validate()
        types = [e.error_type for e in errors]
        # The delegation to validate_job_structure calls validate_data_dependencies
        # which checks for temp datasets used but never created
        assert any(t == ErrorType.VALIDATION_ERROR for t in types)

    def test_valid_job_no_errors(self):
        from jclparser.model import Job, Step
        job = Job("MYJOB")
        job.add_step(Step("STEP1", program="IEBGENER"))
        assert job.validate() == []


# ---------------------------------------------------------------------------
# Integration: parse_jcl / validate_jcl use the shared read_source
# ---------------------------------------------------------------------------


class TestParseJclUsesReadSource:
    """Ensure parse_jcl / validate_jcl use the shared read_source helper."""

    def test_parse_jcl_accepts_path(self, tmp_path):
        from jclparser.parser import parse_jcl
        jcl_file = tmp_path / "test.jcl"
        jcl_file.write_text("//MYJOB JOB\n//STEP1 EXEC PGM=IEBGENER\n//DD1 DD SYSOUT=*\n")
        job = parse_jcl(jcl_file)
        assert job.name == "MYJOB"

    def test_parse_jcl_accepts_string_content(self):
        from jclparser.parser import parse_jcl
        jcl = "//MYJOB JOB\n//STEP1 EXEC PGM=IEBGENER\n//DD1 DD SYSOUT=*\n"
        job = parse_jcl(jcl)
        assert job.name == "MYJOB"

    def test_parse_jcl_accepts_file_like(self):
        from jclparser.parser import parse_jcl
        jcl = "//MYJOB JOB\n//STEP1 EXEC PGM=IEBGENER\n//DD1 DD SYSOUT=*\n"
        job = parse_jcl(io.StringIO(jcl))
        assert job.name == "MYJOB"

    def test_validate_jcl_accepts_path(self, tmp_path):
        from jclparser.parser import validate_jcl
        jcl_file = tmp_path / "test.jcl"
        jcl_file.write_text("//MYJOB JOB\n//STEP1 EXEC PGM=IEBGENER\n//DD1 DD SYSOUT=*\n")
        errors = validate_jcl(jcl_file)
        assert isinstance(errors, list)

    def test_validate_jcl_missing_file(self, tmp_path):
        from jclparser.parser import validate_jcl
        with pytest.raises(FileNotFoundError):
            validate_jcl(tmp_path / "missing.jcl")
