"""
Tests targeting uncovered lines in plugins/__init__.py.

Covers: disable_plugin no-op, unregister ValidationPlugin,
unregister nonexistent plugin.
"""

from jclparser.plugins import (
    PluginRegistry,
    ParserConfig,
    ValidationPlugin,
)
from jclparser.model import Job, Step, DDStatement
from jclparser.errors import ValidationError
from typing import List


class _DummyValidationPlugin(ValidationPlugin):
    """Minimal validation plugin for testing."""

    def validate_job(self, job: Job) -> List[ValidationError]:
        return []

    def validate_step(self, step: Step) -> List[ValidationError]:
        return []

    def validate_dd(self, dd: DDStatement) -> List[ValidationError]:
        return []


class TestPluginCoverageGaps:
    """Tests for specific untested branches in plugins/__init__.py."""

    def test_disable_plugin_not_in_list(self):
        """disable_plugin() is a no-op when the plugin is not enabled (line 43)."""
        config = ParserConfig(enabled_plugins=["A", "B"])
        config.disable_plugin("NONEXISTENT")
        assert config.enabled_plugins == ["A", "B"]

    def test_unregister_validation_plugin(self):
        """unregister_plugin() removes a ValidationPlugin (lines 94-95)."""
        registry = PluginRegistry()
        plugin = _DummyValidationPlugin()
        registry.register_validation_plugin(plugin)

        assert len(registry.get_validators()) == 1
        result = registry.unregister_plugin("_DummyValidationPlugin")
        assert result is True
        assert len(registry.get_validators()) == 0

    def test_unregister_nonexistent_plugin(self):
        """unregister_plugin() returns False for unknown name (line 100)."""
        registry = PluginRegistry()
        result = registry.unregister_plugin("DoesNotExist")
        assert result is False
