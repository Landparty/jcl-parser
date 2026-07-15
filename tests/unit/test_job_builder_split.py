"""Tests for the _job_builder.py decomposition into _model_factories / _post_parse.

The split is layout-only: ``JobBuilder`` stays the statement-dispatch state
machine in ``_job_builder.py``; the ``Statement -> model`` factories moved to
``_model_factories.py``; the post-parse passes moved to ``_post_parse.py``.
Every helper must remain importable from its historical locations
(``jclparser._job_builder`` and ``jclparser.parser``).
"""

import pytest

from jclparser.model import Statement

pytestmark = pytest.mark.unit

FACTORY_HELPERS = [
    "_SET_SYMBOL_PATTERN",
    "_resolve_set_value",
    "_has_unresolved_symbol_ref",
    "_exec_has_program_spec",
    "_create_job_from_statement",
    "_create_step_from_statement",
    "_create_dd_from_statement",
]

POST_PARSE_HELPERS = [
    "_extract_output_ref_names",
    "_resolve_output_refs",
    "load_external_procedures",
    "enforce_strict_dd_structure",
    "resolve_set_symbols",
]


class TestBackwardCompatibleReExports:
    """Historical import paths must keep working after the split."""

    @pytest.mark.parametrize("name", FACTORY_HELPERS + POST_PARSE_HELPERS)
    def test_importable_from_job_builder(self, name):
        from jclparser import _job_builder

        assert hasattr(_job_builder, name)

    @pytest.mark.parametrize("name", FACTORY_HELPERS + POST_PARSE_HELPERS)
    def test_importable_from_parser(self, name):
        """jclparser.parser must keep re-exporting all historical helpers."""
        from jclparser import parser

        assert hasattr(parser, name)

    @pytest.mark.parametrize("name", FACTORY_HELPERS)
    def test_job_builder_reexports_are_the_factory_objects(self, name):
        from jclparser import _job_builder, _model_factories

        assert getattr(_job_builder, name) is getattr(_model_factories, name)

    @pytest.mark.parametrize("name", POST_PARSE_HELPERS)
    def test_job_builder_reexports_are_the_post_parse_objects(self, name):
        from jclparser import _job_builder, _post_parse

        assert getattr(_job_builder, name) is getattr(_post_parse, name)

    def test_jobbuilder_lives_in_job_builder(self):
        from jclparser._job_builder import JobBuilder
        from jclparser.parser import JobBuilder as ParserJobBuilder

        assert JobBuilder is ParserJobBuilder


class TestModelFactories:
    """Direct unit coverage for the relocated factory helpers."""

    def test_create_job_extracts_accounting_info(self):
        from jclparser._model_factories import _create_job_from_statement

        stmt = Statement(
            type="JOB",
            name="MYJOB",
            parameters={"_pos_0": "(ACCT)", "CLASS": "A"},
            line_number=1,
        )
        job = _create_job_from_statement(stmt)
        assert job.name == "MYJOB"
        assert job.accounting_info == "ACCT"
        assert job.parameters == {"CLASS": "A"}
        assert job.line_number == 1

    def test_create_step_pgm(self):
        from jclparser._model_factories import _create_step_from_statement

        stmt = Statement(
            type="EXEC",
            name="STEP1",
            parameters={"PGM": "IEBGENER", "REGION": "4M"},
            line_number=2,
        )
        step = _create_step_from_statement(stmt)
        assert step.program == "IEBGENER"
        assert step.procedure is None
        assert step.parameters == {"REGION": "4M"}

    def test_create_step_positional_proc(self):
        from jclparser._model_factories import _create_step_from_statement

        stmt = Statement(
            type="EXEC", name="STEP1", parameters={"_pos_0": "MYPROC"}, line_number=2
        )
        step = _create_step_from_statement(stmt)
        assert step.procedure == "MYPROC"
        assert step.program is None

    def test_create_dd_reads_dsn_and_disp(self):
        from jclparser._model_factories import _create_dd_from_statement

        stmt = Statement(
            type="DD",
            name="SYSUT1",
            parameters={"DSN": "MY.DATA", "DISP": "SHR"},
            line_number=3,
        )
        dd = _create_dd_from_statement(stmt)
        assert dd.dataset_name == "MY.DATA"
        assert dd.disposition == "SHR"

    def test_exec_has_program_spec(self):
        from jclparser._model_factories import _exec_has_program_spec

        assert _exec_has_program_spec({"PGM": "X"})
        assert _exec_has_program_spec({"PROC": "X"})
        assert _exec_has_program_spec({"_pos_0": "X"})
        assert not _exec_has_program_spec({"REGION": "4M"})

    def test_resolve_set_value_preserves_double_amp(self):
        from jclparser._model_factories import _resolve_set_value

        assert _resolve_set_value("&&WORK", {"WORK": "NOPE"}) == "&&WORK"
        assert _resolve_set_value("&HLQ..DATA", {"HLQ": "CORP"}) == "CORP.DATA"

    def test_has_unresolved_symbol_ref(self):
        from jclparser._model_factories import _has_unresolved_symbol_ref

        assert _has_unresolved_symbol_ref("&B.")
        assert not _has_unresolved_symbol_ref("&&WORK")
        assert not _has_unresolved_symbol_ref("PLAIN")


class TestPostParse:
    """Direct unit coverage for the relocated post-parse helpers."""

    def test_extract_output_ref_names_forms(self):
        from jclparser._post_parse import _extract_output_ref_names

        assert _extract_output_ref_names("*.NAME") == ["NAME"]
        assert _extract_output_ref_names("(*.N1,*.N2)".strip("()").split(",")) == [
            "N1",
            "N2",
        ]
        assert _extract_output_ref_names("*.STEP.NAME") == ["NAME"]
        assert _extract_output_ref_names("BARE") == []
        assert _extract_output_ref_names(None) == []

    def test_enforce_strict_dd_structure_raises(self):
        from jclparser._post_parse import enforce_strict_dd_structure
        from jclparser.errors import JCLStructureError

        with pytest.raises(JCLStructureError):
            enforce_strict_dd_structure("//DD1 DD DSN=X,DISP=SHR\n")

    def test_enforce_strict_dd_structure_ignores_comments(self):
        from jclparser._post_parse import enforce_strict_dd_structure

        enforce_strict_dd_structure("//* just a comment\n//MYJOB JOB\n")

    def test_resolve_set_symbols_forward_reference(self):
        """End-to-end: forward SET references resolve via the post-parse pass."""
        from jclparser.parser import parse_jcl

        jcl = (
            "//MYJOB JOB\n"
            "// SET LIB=&HLQ..DATA\n"
            "// SET HLQ=CORP\n"
            "//STEP1 EXEC PGM=IEBGENER\n"
            "//DD1 DD DSN=&LIB..FILE,DISP=SHR\n"
        )
        job = parse_jcl(jcl)
        dd = job.steps[0].dd_statements[0]
        assert dd.dataset_name == "CORP.DATA.FILE"
