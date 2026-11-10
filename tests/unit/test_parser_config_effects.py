"""Every ``ParserConfig`` field has an effect (issue #67).

The fields used to be stored and never read: ``ParserConfig(strict_mode=True)``
parsed invalid jobs silently, every registered plugin always ran whatever
``enabled_plugins`` said, ``validation_level`` and ``dialect`` did nothing, and
``validate_jcl(level=ValidationLevel.SEMANTIC)`` degraded to basic validation.
These tests assert the behaviour, not just the storage.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl, validate_jcl
from jclparser.errors import (
    ErrorSeverity,
    ErrorType,
    JCLValidationError,
    ValidationError,
)
from jclparser.jes_statements import Jes3ControlStatement, JobParmStatement
from jclparser.model import Statement
from jclparser.parser import parse_statement
from jclparser.plugins import (
    ALL_PLUGINS,
    ParserConfig,
    StatementPlugin,
    ValidationLevel,
    ValidationPlugin,
    get_plugin_registry,
)

pytestmark = pytest.mark.unit

_INVALID = """//J JOB (A)
//S1 EXEC PGM=X
//DD1 DD DSN=&&T,DISP=(NEW,PASS)
//S1 EXEC PGM=Y
//DD1 DD DSN=&&T,DISP=(NEW,PASS)
"""

_VALID = "//J JOB (A)\n//S1 EXEC PGM=X\n"

# A duplicate DD name is a WARNING from job.validate(): structure level only.
_DUP_DD = (
    "//J JOB (A)\n//S1 EXEC PGM=X\n//D DD DSN=A.B,DISP=SHR\n//D DD DSN=A.C,DISP=SHR\n"
)


class SiteRule(ValidationPlugin):
    def validate_job(self, job):
        return [
            ValidationError(
                message="SITE RULE",
                error_type=ErrorType.SEMANTIC_ERROR,
                severity=ErrorSeverity.WARNING,
            )
        ]

    def validate_step(self, step):
        return []

    def validate_dd(self, dd):
        return []


class MyStat(StatementPlugin):
    def can_parse(self, line: str) -> bool:
        return line.startswith("//") and " MYSTAT " in f"{line} "

    def parse_statement(self, line: str, line_number: int) -> Statement:
        return Statement(
            type="MYSTAT", name="X", parameters={}, line_number=line_number
        )

    @property
    def statement_types(self) -> list[str]:
        return ["MYSTAT"]


@pytest.fixture
def registered():
    """Register SiteRule and MyStat globally for one test."""
    registry = get_plugin_registry()
    site, stat = SiteRule(), MyStat()
    registry.register_validation_plugin(site)
    registry.register_statement_plugin(stat)
    yield
    registry.unregister_plugin(site)
    registry.unregister_plugin(stat)


def _messages(errors):
    return [e.message for e in errors]


class TestStrictMode:
    def test_config_strict_mode_rejects_invalid_job(self):
        with pytest.raises(JCLValidationError, match="created in multiple steps"):
            parse_jcl(_INVALID, config=ParserConfig(strict_mode=True))

    def test_keyword_still_enables_strict_with_a_lenient_config(self):
        with pytest.raises(JCLValidationError):
            parse_jcl(_INVALID, strict_mode=True, config=ParserConfig())

    def test_default_config_is_lenient(self):
        assert parse_jcl(_INVALID, config=ParserConfig()).name == "J"


class TestPluginsAreOptIn:
    def test_registered_validation_plugin_does_not_run_without_config(self, registered):
        assert "SITE RULE" not in _messages(validate_jcl(_VALID, level="semantic"))

    def test_registered_validation_plugin_does_not_run_unless_enabled(self, registered):
        errors = validate_jcl(_VALID, level="semantic", config=ParserConfig())
        assert "SITE RULE" not in _messages(errors)

    def test_enabled_validation_plugin_runs(self, registered):
        config = ParserConfig()
        config.enable_plugin("SiteRule")
        errors = validate_jcl(_VALID, level="semantic", config=config)
        assert "SITE RULE" in _messages(errors)

    def test_disabled_validation_plugin_stops_running(self, registered):
        config = ParserConfig(enabled_plugins=["SiteRule"])
        config.disable_plugin("SiteRule")
        errors = validate_jcl(_VALID, level="semantic", config=config)
        assert "SITE RULE" not in _messages(errors)

    def test_all_plugins_wildcard(self, registered):
        config = ParserConfig(enabled_plugins=[ALL_PLUGINS])
        errors = validate_jcl(_VALID, level="semantic", config=config)
        assert "SITE RULE" in _messages(errors)

    def test_statement_plugin_needs_enabling(self, registered):
        line = "//S1 MYSTAT A=B"
        assert parse_statement(line, 1).type == "UNKNOWN"
        assert parse_statement(line, 1, ParserConfig()).type == "UNKNOWN"
        other = ParserConfig(enabled_plugins=["SiteRule"])
        assert parse_statement(line, 1, other).type == "UNKNOWN"
        enabled = ParserConfig(enabled_plugins=["MyStat"])
        assert parse_statement(line, 1, enabled).type == "MYSTAT"

    def test_parse_jcl_threads_config_to_statement_plugins(self, registered):
        source = _VALID + "//S1 MYSTAT A=B\n"
        seen = []

        class Spy(MyStat):
            def parse_statement(self, line, line_number):
                seen.append(line_number)
                return super().parse_statement(line, line_number)

        registry = get_plugin_registry()
        spy = Spy()
        registry.register_statement_plugin(spy)
        try:
            parse_jcl(source)
            assert seen == []
            parse_jcl(source, config=ParserConfig(enabled_plugins=["Spy"]))
            assert seen == [3]
        finally:
            registry.unregister_plugin(spy)


class TestValidationLevel:
    @pytest.mark.parametrize(
        "level", [ValidationLevel.STRUCTURE, "structure", "STRUCTURE"]
    )
    def test_enum_and_string_levels_agree(self, level):
        assert "Duplicate DD name in step S1: D" in _messages(
            validate_jcl(_DUP_DD, level=level)
        )

    def test_semantic_enum_runs_plugins(self, registered):
        errors = validate_jcl(
            _VALID,
            level=ValidationLevel.SEMANTIC,
            config=ParserConfig(enabled_plugins=["SiteRule"]),
        )
        assert "SITE RULE" in _messages(errors)

    def test_config_level_used_when_level_omitted(self):
        config = ParserConfig(validation_level=ValidationLevel.STRUCTURE)
        assert _messages(validate_jcl(_DUP_DD, config=config))
        assert validate_jcl(_DUP_DD) == []

    def test_explicit_level_overrides_config(self):
        config = ParserConfig(validation_level=ValidationLevel.STRUCTURE)
        assert validate_jcl(_DUP_DD, level="basic", config=config) == []

    def test_config_accepts_string_level(self):
        config = ParserConfig(validation_level="semantic")  # type: ignore[arg-type]
        assert config.validation_level is ValidationLevel.SEMANTIC

    def test_syntax_only_is_basic(self):
        assert validate_jcl(_DUP_DD, level="syntax_only") == []

    def test_unknown_level_raises(self):
        with pytest.raises(ValueError, match="Unknown validation level"):
            validate_jcl(_VALID, level="strict")
        with pytest.raises(ValueError, match="Unknown validation level"):
            ParserConfig(validation_level="strict")  # type: ignore[arg-type]


class TestDialect:
    _SOURCE = "//*MAIN CLASS=A\n//J JOB (A)\n/*JOBPARM LINES=5\n//S1 EXEC PGM=X\n"

    def _typed(self, job, cls):
        return [s for s in job.jes_typed_statements if isinstance(s, cls)]

    def test_standard_recognises_jes2_and_jes3(self):
        job = parse_jcl(self._SOURCE, config=ParserConfig())
        assert self._typed(job, JobParmStatement)
        assert self._typed(job, Jes3ControlStatement)

    def test_jes2_reads_slash_slash_star_as_a_comment(self):
        job = parse_jcl(self._SOURCE, config=ParserConfig(dialect="jes2"))
        assert self._typed(job, JobParmStatement)
        assert not self._typed(job, Jes3ControlStatement)
        assert "//*MAIN CLASS=A" not in job.jes_statements

    def test_jes3_does_not_interpret_jes2_statements(self):
        job = parse_jcl(self._SOURCE, config=ParserConfig(dialect="jes3"))
        assert self._typed(job, Jes3ControlStatement)
        assert not self._typed(job, JobParmStatement)
        # The text is kept, and the reason it was not interpreted is reported.
        assert "/*JOBPARM LINES=5" in job.jes_statements
        assert any("/*JOBPARM" in w and "jes3" in w for w in job.warnings)

    def test_dialect_is_case_insensitive(self):
        assert ParserConfig(dialect=" JES3 ").dialect == "jes3"

    def test_unknown_dialect_raises(self):
        with pytest.raises(ValueError, match="Unknown JCL dialect"):
            ParserConfig(dialect="custom")
