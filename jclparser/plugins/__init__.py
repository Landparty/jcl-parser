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


#: Dialects :class:`ParserConfig` accepts.  ``standard`` recognises both JES2
#: (``/*JOBPARM``) and JES3 (``//*MAIN``) control statements; ``jes2`` treats
#: ``//*`` records as the plain comments they are under JES2; ``jes3`` does not
#: interpret ``/*`` JES2 control statements (they are reported in
#: ``job.warnings`` instead).
SUPPORTED_DIALECTS: tuple[str, ...] = ("standard", "jes2", "jes3")

#: Put this in :attr:`ParserConfig.enabled_plugins` to enable every registered
#: plugin (the behaviour before plugins became opt-in).
ALL_PLUGINS = "*"


def normalize_validation_level(level: "ValidationLevel | str") -> ValidationLevel:
    """Return *level* as a :class:`ValidationLevel`.

    Accepts a member or its string value (case-insensitive).  ``"syntax_only"``
    is an alias of ``"basic"``.

    Raises:
        ValueError: *level* names no validation level.
    """
    if isinstance(level, ValidationLevel):
        return level
    value = str(level).strip().lower()
    if value == "syntax_only":
        value = ValidationLevel.BASIC.value
    try:
        return ValidationLevel(value)
    except ValueError:
        allowed = ", ".join(repr(m.value) for m in ValidationLevel)
        raise ValueError(
            f"Unknown validation level {level!r}; expected one of {allowed}"
        ) from None


@dataclass
class ParserConfig:
    """
    Configuration for JCL parser behavior.

    Controls parsing strictness, enabled plugins, and validation levels.

    * ``strict_mode`` -- same as ``parse_jcl(strict_mode=True)``; either one
      turns strict parsing on.
    * ``dialect`` -- one of :data:`SUPPORTED_DIALECTS` (case-insensitive).
    * ``enabled_plugins`` -- class names of the registered plugins that may
      run.  Plugins are **opt-in**: a plugin in the global registry runs only
      when its class name (or :data:`ALL_PLUGINS`) is listed here, and a parse
      without a config runs none.
    * ``validation_level`` -- the level ``validate_jcl`` uses when it is not
      given ``level=``.  A string value (``"semantic"``) is accepted.
    """

    strict_mode: bool = False
    dialect: str = "standard"
    enabled_plugins: list[str] = field(default_factory=list)
    validation_level: ValidationLevel = ValidationLevel.BASIC
    #: When True, ``parse_jcl`` runs :func:`~jclparser.sql_detector.detect_sql_in_job`
    #: after the parse completes and stashes the results on ``Job.sql_detections``
    #: keyed by step name.  Disabled by default to keep parse time predictable.
    detect_sql: bool = False

    def __post_init__(self) -> None:
        dialect = str(self.dialect).strip().lower()
        if dialect not in SUPPORTED_DIALECTS:
            raise ValueError(
                f"Unknown JCL dialect {self.dialect!r}; expected one of "
                + ", ".join(repr(d) for d in SUPPORTED_DIALECTS)
            )
        self.dialect = dialect
        self.validation_level = normalize_validation_level(self.validation_level)

    def is_plugin_enabled(
        self, plugin: "str | StatementPlugin | ValidationPlugin"
    ) -> bool:
        """True when *plugin* (an instance or a class name) may run."""
        name = plugin if isinstance(plugin, str) else plugin.__class__.__name__
        return ALL_PLUGINS in self.enabled_plugins or name in self.enabled_plugins

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
    "ALL_PLUGINS",
    "SUPPORTED_DIALECTS",
    "ParserConfig",
    "PluginRegistry",
    "StatementPlugin",
    "ValidationLevel",
    "ValidationPlugin",
    "get_plugin_registry",
    "normalize_validation_level",
]
