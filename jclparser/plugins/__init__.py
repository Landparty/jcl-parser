"""
Plugin system for JCL parser extensibility.

Contains the plugin registry and plugin management functionality
for registering and managing statement and validation plugins.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict
from .base import StatementPlugin, ValidationPlugin
from ..errors import ValidationError  # noqa: F401 — re-exported


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
    enabled_plugins: List[str] = field(default_factory=list)
    validation_level: ValidationLevel = ValidationLevel.BASIC
    
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
    
    def __init__(self):
        self._statement_plugins: List[StatementPlugin] = []
        self._validation_plugins: List[ValidationPlugin] = []
        self._plugin_names: Dict[str, object] = {}
    
    def register_statement_plugin(self, plugin: StatementPlugin) -> None:
        """Register a statement parsing plugin"""
        self._statement_plugins.append(plugin)
        plugin_name = plugin.__class__.__name__
        self._plugin_names[plugin_name] = plugin
    
    def register_validation_plugin(self, plugin: ValidationPlugin) -> None:
        """Register a validation plugin"""
        self._validation_plugins.append(plugin)
        plugin_name = plugin.__class__.__name__
        self._plugin_names[plugin_name] = plugin
    
    def get_parser_for_line(self, line: str) -> Optional[StatementPlugin]:
        """Find plugin that can parse given line"""
        for plugin in self._statement_plugins:
            if plugin.can_parse(line):
                return plugin
        return None
    
    def get_validators(self) -> List[ValidationPlugin]:
        """Get all registered validation plugins"""
        return self._validation_plugins.copy()
    
    def get_statement_plugins(self) -> List[StatementPlugin]:
        """Get all registered statement plugins"""
        return self._statement_plugins.copy()
    
    def unregister_plugin(self, plugin_name: str) -> bool:
        """Remove plugin by name"""
        if plugin_name in self._plugin_names:
            plugin = self._plugin_names[plugin_name]
            
            # Remove from appropriate list
            if isinstance(plugin, StatementPlugin):
                self._statement_plugins.remove(plugin)
            elif isinstance(plugin, ValidationPlugin):
                self._validation_plugins.remove(plugin)
            
            # Remove from name registry
            del self._plugin_names[plugin_name]
            return True
        return False


# Global plugin registry instance
_global_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry instance"""
    return _global_registry


# Export public API
__all__ = [
    'StatementPlugin',
    'ValidationPlugin', 
    'PluginRegistry',
    'ParserConfig',
    'ValidationLevel',
    'get_plugin_registry'
]