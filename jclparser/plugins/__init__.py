"""
Plugin system for JCL parser extensibility.

Contains the plugin registry and plugin management functionality
for registering and managing statement and validation plugins.
"""

from dataclasses import dataclass, field
from enum import Enum

from ..errors import ValidationError  # noqa: F401 — re-exported
from .base import StatementPlugin, ValidationPlugin


class ValidationLevel(Enum):
    """Validation level for parser configuration"""

    BASIC = "basic"
    STRUCTURE = "structure"
    SEMANTIC = "semantic"


@dataclass
class ParserConfig:
    """
    Configuration for JCL parser behavior.

    Controls parsing strictness, enabled plugins, and validation levels.
    """

    strict_mode: bool = False
    dialect: str = "standard"
    enabled_plugins: list[str] = field(default_factory=list)
    validation_level: ValidationLevel = ValidationLevel.BASIC
    #: When True, ``parse_jcl`` runs :func:`~jclparser.sql_detector.detect_sql_in_job`
    #: after the parse completes and stashes the results on ``Job.sql_detections``
    #: keyed by step name.  Disabled by default to keep parse time predictable.
    detect_sql: bool = False

    def enable_plugin(self, plugin_name: str) -> None:
        """Enable specific plugin"""
        if plugin_name not in self.enabled_plugins:
            self.enabled_plugins.append(plugin_name)

    def disable_plugin(self, plugin_name: str) -> None:
        """Disable specific plugin"""
        if plugin_name in self.enabled_plugins:
            self.enabled_plugins.remove(plugin_name)


class PluginRegistry:
    """
    Central registry for parser plugins.

    Manages registration and lookup of statement and validation plugins.
    """

    def __init__(self) -> None:
        self._statement_plugins: list[StatementPlugin] = []
        self._validation_plugins: list[ValidationPlugin] = []
        # Class name -> every registration under it, oldest first.  Several
        # instances of one plugin class (e.g. configured differently) may be
        # registered at once; each needs its own entry to be removable.
        self._plugin_names: dict[str, list[StatementPlugin | ValidationPlugin]] = {}

    def register_statement_plugin(self, plugin: StatementPlugin) -> None:
        """Register a statement parsing plugin"""
        self._statement_plugins.append(plugin)
        self._plugin_names.setdefault(plugin.__class__.__name__, []).append(plugin)

    def register_validation_plugin(self, plugin: ValidationPlugin) -> None:
        """Register a validation plugin"""
        self._validation_plugins.append(plugin)
        self._plugin_names.setdefault(plugin.__class__.__name__, []).append(plugin)

    def get_parser_for_line(self, line: str) -> StatementPlugin | None:
        """Find plugin that can parse given line"""
        for plugin in self._statement_plugins:
            if plugin.can_parse(line):
                return plugin
        return None

    def get_validators(self) -> list[ValidationPlugin]:
        """Get all registered validation plugins"""
        return self._validation_plugins.copy()

    def get_statement_plugins(self) -> list[StatementPlugin]:
        """Get all registered statement plugins"""
        return self._statement_plugins.copy()

    def unregister_plugin(
        self, plugin_name: str | StatementPlugin | ValidationPlugin
    ) -> bool:
        """Remove a plugin by class name, or a specific registered instance.

        By name, the most recently registered instance of that class is
        removed; call again to remove earlier instances of the same class.

        Returns:
            True if a plugin was removed, False if none matched.
        """
        if isinstance(plugin_name, str):
            name = plugin_name
            registered = self._plugin_names.get(name)
            if not registered:
                return False
            plugin = registered[-1]
        else:
            plugin = plugin_name
            name = plugin.__class__.__name__
            registered = self._plugin_names.get(name)
            if not registered or not any(p is plugin for p in registered):
                return False

        # Remove this instance (by identity, not equality) -- from both
        # plugin lists, should it have been registered as both kinds.
        registered[:] = [p for p in registered if p is not plugin]
        if not registered:
            del self._plugin_names[name]
        for plugins in (self._statement_plugins, self._validation_plugins):
            for i in range(len(plugins) - 1, -1, -1):
                if plugins[i] is plugin:
                    del plugins[i]
                    break
        return True


# Global plugin registry instance
_global_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry instance"""
    return _global_registry


# Export public API
__all__ = [
    "ParserConfig",
    "PluginRegistry",
    "StatementPlugin",
    "ValidationLevel",
    "ValidationPlugin",
    "get_plugin_registry",
]
