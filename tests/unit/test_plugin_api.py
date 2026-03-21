"""
Contract tests for Plugin System API

These tests define the expected behavior of the plugin architecture.
All tests should FAIL initially, then pass as implementation is added.
"""

import pytest
from typing import List

# Import the plugin system classes we expect to exist
from jclparser.plugins import (
    StatementPlugin, 
    ValidationPlugin, 
    PluginRegistry, 
    ParserConfig,
    get_plugin_registry
)
from jclparser.model import Job, Step, DDStatement, Statement
from jclparser.errors import ValidationError, ErrorType


# Test plugin implementations for testing
class MockStatementPlugin(StatementPlugin):
    """Mock statement plugin for testing"""
    
    def can_parse(self, line: str) -> bool:
        return line.strip().startswith("//") and "MOCK" in line.upper()
    
    def parse_statement(self, line: str, line_number: int) -> Statement:
        # Return a mock statement
        class MockStatement:
            def __init__(self, line: str, line_number: int):
                self.type = "MOCK"
                self.name = "MOCKSTMT"
                self.line = line
                self.line_number = line_number
                self.parameters = {}
        return MockStatement(line, line_number)
    
    @property
    def statement_types(self) -> List[str]:
        return ["MOCK"]


class MockValidationPlugin(ValidationPlugin):
    """Mock validation plugin for testing"""
    
    def validate_job(self, job: Job) -> List[ValidationError]:
        errors = []
        if job.name.startswith("INVALID"):
            errors.append(ValidationError(
                message="Job name should not start with INVALID",
                error_type=ErrorType.VALIDATION_ERROR
            ))
        return errors
    
    def validate_step(self, step: Step) -> List[ValidationError]:
        errors = []
        if step.program == "BADPROG":
            errors.append(ValidationError(
                message="BADPROG is not allowed",
                error_type=ErrorType.VALIDATION_ERROR
            ))
        return errors
    
    def validate_dd(self, dd: DDStatement) -> List[ValidationError]:
        errors = []
        if dd.name == "INVALID_DD":
            errors.append(ValidationError(
                message="DD name INVALID_DD is not allowed",
                error_type=ErrorType.VALIDATION_ERROR
            ))
        return errors


class TestStatementPluginInterface:
    """Contract tests for StatementPlugin abstract base class"""
    
    def test_statement_plugin_abstract_methods(self):
        """GIVEN StatementPlugin base class WHEN inspected THEN has required abstract methods"""
        # Verify that StatementPlugin is abstract
        assert hasattr(StatementPlugin, 'can_parse')
        assert hasattr(StatementPlugin, 'parse_statement')
        assert hasattr(StatementPlugin, 'statement_types')
        
        # Should not be able to instantiate abstract class directly
        with pytest.raises(TypeError):
            StatementPlugin()
    
    def test_mock_statement_plugin_implementation(self):
        """GIVEN MockStatementPlugin WHEN methods called THEN behaves correctly"""
        plugin = MockStatementPlugin()
        
        # Test can_parse method
        assert plugin.can_parse("//MOCK STATEMENT")
        assert not plugin.can_parse("//REGULAR JOB")
        assert not plugin.can_parse("//* COMMENT")
        
        # Test parse_statement method
        stmt = plugin.parse_statement("//MOCK TEST", 10)
        assert stmt is not None
        assert stmt.type == "MOCK"
        assert stmt.line_number == 10
        
        # Test statement_types property
        types = plugin.statement_types
        assert isinstance(types, list)
        assert "MOCK" in types


class TestValidationPluginInterface:
    """Contract tests for ValidationPlugin abstract base class"""
    
    def test_validation_plugin_abstract_methods(self):
        """GIVEN ValidationPlugin base class WHEN inspected THEN has required abstract methods"""
        # Verify that ValidationPlugin is abstract
        assert hasattr(ValidationPlugin, 'validate_job')
        assert hasattr(ValidationPlugin, 'validate_step')
        assert hasattr(ValidationPlugin, 'validate_dd')
        
        # Should not be able to instantiate abstract class directly
        with pytest.raises(TypeError):
            ValidationPlugin()
    
    def test_mock_validation_plugin_implementation(self):
        """GIVEN MockValidationPlugin WHEN validation methods called THEN behaves correctly"""
        plugin = MockValidationPlugin()
        
        # Test job validation
        valid_job = Job(name="GOODJOB")
        invalid_job = Job(name="INVALIDJOB")
        
        valid_errors = plugin.validate_job(valid_job)
        invalid_errors = plugin.validate_job(invalid_job)
        
        assert len(valid_errors) == 0
        assert len(invalid_errors) > 0
        assert "INVALID" in invalid_errors[0].message
        
        # Test step validation
        valid_step = Step(name="STEP1", program="GOODPROG")
        invalid_step = Step(name="STEP2", program="BADPROG")
        
        valid_step_errors = plugin.validate_step(valid_step)
        invalid_step_errors = plugin.validate_step(invalid_step)
        
        assert len(valid_step_errors) == 0
        assert len(invalid_step_errors) > 0
        assert "BADPROG" in invalid_step_errors[0].message
        
        # Test DD validation
        valid_dd = DDStatement(name="GOODDD")
        invalid_dd = DDStatement(name="INVALID_DD")
        
        valid_dd_errors = plugin.validate_dd(valid_dd)
        invalid_dd_errors = plugin.validate_dd(invalid_dd)
        
        assert len(valid_dd_errors) == 0
        assert len(invalid_dd_errors) > 0
        assert "INVALID_DD" in invalid_dd_errors[0].message


class TestPluginRegistry:
    """Contract tests for PluginRegistry class"""
    
    def test_plugin_registry_creation(self):
        """GIVEN PluginRegistry class WHEN instantiated THEN creates empty registry"""
        registry = PluginRegistry()
        
        assert registry is not None
        assert hasattr(registry, 'register_statement_plugin')
        assert hasattr(registry, 'register_validation_plugin')
        assert hasattr(registry, 'get_parser_for_line')
        assert hasattr(registry, 'get_validators')
    
    def test_statement_plugin_registration(self):
        """GIVEN PluginRegistry and StatementPlugin WHEN register_statement_plugin() called THEN plugin registered"""
        registry = PluginRegistry()
        plugin = MockStatementPlugin()
        
        # Should not raise an exception
        registry.register_statement_plugin(plugin)
        
        # Plugin should be available for parsing
        found_plugin = registry.get_parser_for_line("//MOCK STATEMENT")
        assert found_plugin is not None
        assert isinstance(found_plugin, MockStatementPlugin)
    
    def test_validation_plugin_registration(self):
        """GIVEN PluginRegistry and ValidationPlugin WHEN register_validation_plugin() called THEN plugin registered"""
        registry = PluginRegistry()
        plugin = MockValidationPlugin()
        
        # Should not raise an exception
        registry.register_validation_plugin(plugin)
        
        # Plugin should be available in validators list
        validators = registry.get_validators()
        assert len(validators) > 0
        assert any(isinstance(v, MockValidationPlugin) for v in validators)
    
    def test_parser_selection_by_line(self):
        """GIVEN multiple registered plugins WHEN get_parser_for_line() called THEN returns correct plugin"""
        registry = PluginRegistry()
        mock_plugin = MockStatementPlugin()
        registry.register_statement_plugin(mock_plugin)
        
        # Should find plugin for MOCK statements
        found = registry.get_parser_for_line("//MOCK TEST STATEMENT")
        assert found is not None
        assert isinstance(found, MockStatementPlugin)
        
        # Should not find plugin for non-MOCK statements
        not_found = registry.get_parser_for_line("//REGULAR JOB")
        assert not_found is None
    
    def test_plugin_unregistration(self):
        """GIVEN registered plugin WHEN unregister_plugin() called THEN plugin removed"""
        registry = PluginRegistry()
        plugin = MockStatementPlugin()
        registry.register_statement_plugin(plugin)
        
        # Verify plugin is registered
        assert registry.get_parser_for_line("//MOCK TEST") is not None
        
        # Unregister plugin (implementation might vary on how plugins are named)
        registry.unregister_plugin("MockStatementPlugin")
        
        # Plugin should no longer be found
        assert registry.get_parser_for_line("//MOCK TEST") is None
    
    def test_multiple_plugin_priority(self):
        """GIVEN multiple plugins that can parse same line WHEN selection occurs THEN uses FIFO order"""
        registry = PluginRegistry()
        
        # Create two plugins that can both parse the same line type
        plugin1 = MockStatementPlugin()
        plugin2 = MockStatementPlugin()
        
        registry.register_statement_plugin(plugin1)
        registry.register_statement_plugin(plugin2)
        
        # Should return the first registered plugin
        found = registry.get_parser_for_line("//MOCK TEST")
        assert found is plugin1  # First registered should be returned


class TestParserConfig:
    """Contract tests for ParserConfig class"""
    
    def test_parser_config_creation(self):
        """GIVEN ParserConfig class WHEN instantiated THEN has correct default values"""
        config = ParserConfig()
        
        assert not config.strict_mode
        assert config.dialect == "standard"
        assert isinstance(config.enabled_plugins, list)
        assert len(config.enabled_plugins) == 0
        assert hasattr(config, 'validation_level')
    
    def test_parser_config_with_parameters(self):
        """GIVEN ParserConfig parameters WHEN instantiated THEN values set correctly"""
        config = ParserConfig(
            strict_mode=True,
            dialect="custom",
            enabled_plugins=["plugin1", "plugin2"]
        )
        
        assert config.strict_mode
        assert config.dialect == "custom"
        assert config.enabled_plugins == ["plugin1", "plugin2"]
    
    def test_enable_plugin(self):
        """GIVEN ParserConfig WHEN enable_plugin() called THEN plugin added to enabled list"""
        config = ParserConfig()
        
        config.enable_plugin("test_plugin")
        
        assert "test_plugin" in config.enabled_plugins
        assert len(config.enabled_plugins) == 1
    
    def test_disable_plugin(self):
        """GIVEN ParserConfig with enabled plugin WHEN disable_plugin() called THEN plugin removed"""
        config = ParserConfig(enabled_plugins=["plugin1", "plugin2"])
        
        config.disable_plugin("plugin1")
        
        assert "plugin1" not in config.enabled_plugins
        assert "plugin2" in config.enabled_plugins
        assert len(config.enabled_plugins) == 1
    
    def test_enable_plugin_idempotent(self):
        """GIVEN ParserConfig WHEN enable_plugin() called twice THEN plugin only added once"""
        config = ParserConfig()
        
        config.enable_plugin("test_plugin")
        config.enable_plugin("test_plugin")
        
        assert config.enabled_plugins.count("test_plugin") == 1


class TestGlobalPluginRegistry:
    """Contract tests for global plugin registry access"""
    
    def test_get_plugin_registry(self):
        """GIVEN get_plugin_registry() function WHEN called THEN returns PluginRegistry instance"""
        registry = get_plugin_registry()
        
        assert registry is not None
        assert isinstance(registry, PluginRegistry)
    
    def test_global_registry_singleton(self):
        """GIVEN multiple calls to get_plugin_registry() WHEN called THEN returns same instance"""
        registry1 = get_plugin_registry()
        registry2 = get_plugin_registry()
        
        # Should be the same instance (singleton pattern)
        assert registry1 is registry2


class TestPluginIntegration:
    """Integration tests for plugin system working together"""
    
    def test_custom_statement_parsing_integration(self):
        """GIVEN custom statement plugin WHEN used with parser THEN custom statements parsed"""
        # This test would require integration with the main parser
        # For now, test the plugin registration and selection
        
        registry = get_plugin_registry()
        plugin = MockStatementPlugin()
        registry.register_statement_plugin(plugin)
        
        # Verify the plugin is available for parsing
        parser = registry.get_parser_for_line("//MOCK CUSTOM STATEMENT")
        assert parser is not None
        
        # Parse a statement using the plugin
        stmt = parser.parse_statement("//MOCK CUSTOM STATEMENT", 1)
        assert stmt.type == "MOCK"
    
    def test_custom_validation_integration(self):
        """GIVEN custom validation plugin WHEN used with job validation THEN custom rules applied"""
        registry = get_plugin_registry()
        validator = MockValidationPlugin()
        registry.register_validation_plugin(validator)
        
        # Create job that should trigger custom validation
        job = Job(name="INVALIDTEST")
        
        # Get all validators and apply them
        validators = registry.get_validators()
        all_errors = []
        for validator in validators:
            all_errors.extend(validator.validate_job(job))
        
        # Should include errors from our custom validator
        assert len(all_errors) > 0
        assert any("INVALID" in error.message for error in all_errors)
    
    def test_parser_config_plugin_filtering(self):
        """GIVEN ParserConfig with enabled plugins WHEN used THEN only enabled plugins active"""
        config = ParserConfig()
        config.enable_plugin("MockStatementPlugin")
        
        # This would be used by the main parser to filter active plugins
        assert "MockStatementPlugin" in config.enabled_plugins
        
        config.disable_plugin("MockStatementPlugin")
        assert "MockStatementPlugin" not in config.enabled_plugins