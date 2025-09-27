"""
JCL Parser for Python 3.13

A Python package for parsing IBM JCL (Job Control Language) scripts.
Provides a simple API for extracting, analyzing, and manipulating JCL statements.
"""

# Package metadata
__version__ = "0.1.0"
__author__ = "JCL Parser Team"
__description__ = "Parse IBM JCL scripts into Python objects"

# Import main API functions
from .parser import parse_jcl, validate_jcl, parse_statement
from .model import Job, Step, DDStatement, Parameter, Statement
from .errors import (
    JCLSyntaxError, JCLValidationError, JCLStructureError,
    ParseError, ErrorType, ErrorSeverity, ValidationError
)
from .plugins import (
    StatementPlugin, ValidationPlugin, PluginRegistry, 
    ParserConfig, ValidationLevel, get_plugin_registry
)
from .validators import (
    validate_jcl_identifier, validate_dataset_name,
    validate_job_structure, validate_step_structure,
    validate_dd_statement
)

# Initialize global plugin registry
_registry = get_plugin_registry()

# Public API - what gets imported with "from jclparser import *"
__all__ = [
    # Core parsing functions
    'parse_jcl',
    'validate_jcl', 
    'parse_statement',
    
    # Data model classes
    'Job',
    'Step', 
    'DDStatement',
    'Parameter',
    'Statement',
    
    # Error classes
    'JCLSyntaxError',
    'JCLValidationError', 
    'JCLStructureError',
    'ParseError',
    'ValidationError',
    'ErrorType',
    'ErrorSeverity',
    
    # Plugin system
    'StatementPlugin',
    'ValidationPlugin',
    'PluginRegistry',
    'ParserConfig',
    'ValidationLevel',
    'get_plugin_registry',
    
    # Validation functions
    'validate_jcl_identifier',
    'validate_dataset_name',
    'validate_job_structure',
    'validate_step_structure',
    'validate_dd_statement',
    
    # Package metadata
    '__version__',
]

# Convenience function for quick parsing
def parse(source, **kwargs):
    """
    Convenience function for parsing JCL.
    
    Alias for parse_jcl() with simpler name.
    """
    return parse_jcl(source, **kwargs)

# Add to exports
__all__.append('parse')