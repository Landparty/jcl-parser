"""
End-to-end integration tests for the plugin system.

Tests that plugins are actually invoked during real parsing and validation,
not just that the registry API works in isolation.
"""

import pytest

from jclparser.errors import ValidationError
from jclparser.model import DDStatement, Job, Statement, Step
from jclparser.parser import parse_statement, validate_jcl
from jclparser.plugins import get_plugin_registry
from jclparser.plugins.base import StatementPlugin, ValidationPlugin

# ---------------------------------------------------------------------------
# Concrete plugin implementations for testing
# ---------------------------------------------------------------------------


class CustomStatementPlugin(StatementPlugin):
    """A plugin that intercepts lines containing '//CUSTOM'."""

    def __init__(self):
        self.invoked = False
        self.last_line = None

    def can_parse(self, line: str) -> bool:
        return "CUSTOM" in line.upper() and line.strip().startswith("//")

    def parse_statement(self, line: str, line_number: int) -> Statement:
        self.invoked = True
        self.last_line = line
        return Statement(
            type="CUSTOM",
            name="MYPLUGIN",
            parameters={"_raw": line},
            line_number=line_number,
        )

    @property
    def statement_types(self):
        return ["CUSTOM"]


class NamingConventionValidator(ValidationPlugin):
    """A plugin that enforces job names must start with 'T' (test convention)."""

    def __init__(self):
        self.validate_job_called = False
        self.validate_step_called = False
        self.validate_dd_called = False

    def validate_job(self, job: Job) -> list[ValidationError]:
        self.validate_job_called = True
        errors = []
        if job.name and not job.name.startswith("T"):
            errors.append(
                ValidationError(
                    f"Job name '{job.name}' must start with 'T'",
                )
            )
        return errors

    def validate_step(self, step: Step) -> list[ValidationError]:
        self.validate_step_called = True
        return []

    def validate_dd(self, dd: DDStatement) -> list[ValidationError]:
        self.validate_dd_called = True
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure the global plugin registry is clean before and after each test."""
    registry = get_plugin_registry()
    # Snapshot current state using the public API.
    old_stmt = list(registry.get_statement_plugins())
    old_val = list(registry.get_validators())

    # Clean for test using the public API.
    for plugin in old_stmt:
        registry.unregister_plugin(plugin.__class__.__name__)
    for plugin in old_val:
        registry.unregister_plugin(plugin.__class__.__name__)

    yield

    # Remove anything registered during the test.
    for plugin in list(registry.get_statement_plugins()):
        registry.unregister_plugin(plugin.__class__.__name__)
    for plugin in list(registry.get_validators()):
        registry.unregister_plugin(plugin.__class__.__name__)

    # Restore original plugins in their original order.
    for plugin in old_stmt:
        registry.register_statement_plugin(plugin)
    for plugin in old_val:
        registry.register_validation_plugin(plugin)


# ---------------------------------------------------------------------------
# StatementPlugin end-to-end tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStatementPluginEndToEnd:
    """Verify that a registered StatementPlugin is actually invoked during parsing."""

    def test_plugin_invoked_during_parse_statement(self):
        """parse_statement() delegates to plugin when can_parse returns True."""
        plugin = CustomStatementPlugin()
        registry = get_plugin_registry()
        registry.register_statement_plugin(plugin)

        result = parse_statement("//CUSTOM MYSTMT PARAM=VALUE", line_number=5)

        assert plugin.invoked is True
        assert result is not None
        assert result.type == "CUSTOM"
        assert result.name == "MYPLUGIN"
        assert result.line_number == 5

    def test_plugin_not_invoked_for_normal_jcl(self):
        """Plugin is skipped for standard JCL lines it cannot handle."""
        plugin = CustomStatementPlugin()
        registry = get_plugin_registry()
        registry.register_statement_plugin(plugin)

        result = parse_statement("//STEP1 EXEC PGM=IEFBR14", line_number=1)

        assert plugin.invoked is False
        assert result is not None
        assert result.type == "EXEC"

    def test_plugin_lifecycle_register_parse_unregister_parse(self):
        """After unregistering a plugin, it is no longer invoked."""
        plugin = CustomStatementPlugin()
        registry = get_plugin_registry()
        registry.register_statement_plugin(plugin)

        # First parse — plugin handles it
        result1 = parse_statement("//CUSTOM LINE1", line_number=1)
        assert result1.type == "CUSTOM"

        # Unregister
        registry.unregister_plugin("CustomStatementPlugin")
        plugin.invoked = False

        # Second parse — standard parsing (unknown type)
        result2 = parse_statement("//CUSTOM LINE2", line_number=2)
        assert plugin.invoked is False
        # Without the plugin, "CUSTOM" is an unknown statement type
        assert result2.type == "UNKNOWN"


# ---------------------------------------------------------------------------
# ValidationPlugin end-to-end tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidationPluginEndToEnd:
    """Verify that registered ValidationPlugins are invoked in validate_jcl()."""

    def test_validation_plugin_invoked_at_semantic_level(self):
        """validate_jcl(level='semantic') calls plugin.validate_job()."""
        plugin = NamingConventionValidator()
        registry = get_plugin_registry()
        registry.register_validation_plugin(plugin)

        jcl = """\
//BADJOB  JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
"""
        errors = validate_jcl(jcl, level="semantic")

        assert plugin.validate_job_called is True
        # The plugin should report an error: name doesn't start with 'T'
        error_messages = [e.message for e in errors]
        assert any("must start with 'T'" in msg for msg in error_messages)

    def test_validation_plugin_not_invoked_at_basic_level(self):
        """validate_jcl(level='basic') does NOT invoke plugin validators."""
        plugin = NamingConventionValidator()
        registry = get_plugin_registry()
        registry.register_validation_plugin(plugin)

        jcl = """\
//BADJOB  JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
"""
        validate_jcl(jcl, level="basic")

        assert plugin.validate_job_called is False

    def test_validation_plugin_no_errors_when_valid(self):
        """Plugin returns no errors for compliant JCL."""
        plugin = NamingConventionValidator()
        registry = get_plugin_registry()
        registry.register_validation_plugin(plugin)

        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
"""
        errors = validate_jcl(jcl, level="semantic")

        assert plugin.validate_job_called is True
        # Name starts with 'T' — plugin should produce no errors
        plugin_errors = [e for e in errors if "must start with" in e.message]
        assert len(plugin_errors) == 0

    def test_validation_plugin_not_invoked_at_structure_level(self):
        """validate_jcl(level='structure') does structure validation but NOT plugin."""
        plugin = NamingConventionValidator()
        registry = get_plugin_registry()
        registry.register_validation_plugin(plugin)

        jcl = """\
//BADJOB  JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
"""
        validate_jcl(jcl, level="structure")

        # Plugins only run at semantic level
        assert plugin.validate_job_called is False

    def test_multiple_validation_plugins_all_invoked(self):
        """All registered validation plugins are called at semantic level."""

        class SecondValidator(ValidationPlugin):
            def __init__(self):
                self.called = False

            def validate_job(self, job):
                self.called = True
                return [ValidationError("second plugin error")]

            def validate_step(self, step):
                return []

            def validate_dd(self, dd):
                return []

        plugin1 = NamingConventionValidator()
        plugin2 = SecondValidator()
        registry = get_plugin_registry()
        registry.register_validation_plugin(plugin1)
        registry.register_validation_plugin(plugin2)

        jcl = """\
//TESTJOB JOB CLASS=A
//STEP1   EXEC PGM=IEFBR14
"""
        errors = validate_jcl(jcl, level="semantic")

        assert plugin1.validate_job_called is True
        assert plugin2.called is True
        assert any("second plugin error" in e.message for e in errors)
