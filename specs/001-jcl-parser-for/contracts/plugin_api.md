# Plugin System API Contract

**Module**: `jclparser.plugins`  
**Purpose**: Extensible plugin architecture for custom JCL dialects and validation

## Plugin Base Class Interface

**Description**: Abstract base class for all JCL parser extensions.

### StatementPlugin
```python
from abc import ABC, abstractmethod

class StatementPlugin(ABC):
    """Base class for custom JCL statement parsers"""
    
    @abstractmethod
    def can_parse(self, line: str) -> bool:
        """Return True if this plugin can parse the given line"""
    
    @abstractmethod
    def parse_statement(self, line: str, line_number: int) -> Statement:
        """Parse line into Statement object"""
    
    @property
    @abstractmethod
    def statement_types(self) -> List[str]:
        """List of JCL statement types this plugin handles"""
```

### ValidationPlugin
```python
class ValidationPlugin(ABC):
    """Base class for custom validation rules"""
    
    @abstractmethod
    def validate_job(self, job: Job) -> List[ValidationError]:
        """Validate complete job structure"""
    
    @abstractmethod
    def validate_step(self, step: Step) -> List[ValidationError]:
        """Validate individual step"""
    
    @abstractmethod
    def validate_dd(self, dd: DDStatement) -> List[ValidationError]:
        """Validate DD statement"""
```

---

## Plugin Registry Interface

**Description**: System for registering and managing plugins.

### PluginRegistry
```python
class PluginRegistry:
    """Central registry for parser plugins"""
    
    def register_statement_plugin(self, plugin: StatementPlugin) -> None:
        """Register a statement parsing plugin"""
    
    def register_validation_plugin(self, plugin: ValidationPlugin) -> None:
        """Register a validation plugin"""
    
    def get_parser_for_line(self, line: str) -> Optional[StatementPlugin]:
        """Find plugin that can parse given line"""
    
    def get_validators(self) -> List[ValidationPlugin]:
        """Get all registered validation plugins"""
    
    def unregister_plugin(self, plugin_name: str) -> bool:
        """Remove plugin by name"""
```

---

## Configuration Interface

**Description**: Parser configuration with plugin support.

### ParserConfig
```python
@dataclass
class ParserConfig:
    """Configuration for JCL parser behavior"""
    
    strict_mode: bool = False
    dialect: str = "standard"
    enabled_plugins: List[str] = field(default_factory=list)
    validation_level: ValidationLevel = ValidationLevel.BASIC
    
    def enable_plugin(self, plugin_name: str) -> None:
        """Enable specific plugin"""
    
    def disable_plugin(self, plugin_name: str) -> None:
        """Disable specific plugin"""
```

## Contract Tests Required

### test_statement_plugin_registration()
- GIVEN custom StatementPlugin implementation
- WHEN register_statement_plugin() called
- THEN plugin available for line parsing

### test_statement_plugin_selection()
- GIVEN multiple registered plugins
- WHEN get_parser_for_line() called
- THEN returns correct plugin based on can_parse()

### test_validation_plugin_execution()
- GIVEN registered ValidationPlugin
- WHEN job validation performed
- THEN custom plugin validate methods called

### test_plugin_unregistration()
- GIVEN registered plugin
- WHEN unregister_plugin() called
- THEN plugin no longer used for parsing

### test_parser_config_plugin_enable()
- GIVEN ParserConfig instance
- WHEN enable_plugin() called
- THEN plugin name added to enabled list

### test_parser_config_plugin_disable()
- GIVEN ParserConfig with enabled plugin
- WHEN disable_plugin() called
- THEN plugin name removed from enabled list

### test_custom_statement_parsing()
- GIVEN custom statement type plugin
- WHEN parse_jcl() encounters custom statement
- THEN custom plugin used for parsing

### test_custom_validation_rules()
- GIVEN custom ValidationPlugin with specific rules
- WHEN job validation performed  
- THEN custom validation errors included in results

### test_plugin_priority_handling()
- GIVEN multiple plugins that can_parse same line
- WHEN parser selection occurs
- THEN uses first registered plugin (FIFO)