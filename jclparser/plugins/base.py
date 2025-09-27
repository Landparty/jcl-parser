"""
Base plugin interfaces for JCL parser extensions.

Contains abstract base classes for statement and validation plugins
that enable custom JCL dialects and validation rules.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from ..model import Job, Step, DDStatement, Statement
from ..errors import ValidationError


class StatementPlugin(ABC):
    """
    Base class for custom JCL statement parsers.
    
    Enables parsing of custom statement types or alternative syntaxes
    for existing statement types.
    """
    
    @abstractmethod
    def can_parse(self, line: str) -> bool:
        """
        Return True if this plugin can parse the given line.
        
        Args:
            line: JCL line to evaluate
            
        Returns:
            True if this plugin should handle parsing this line
        """
        pass
    
    @abstractmethod
    def parse_statement(self, line: str, line_number: int) -> Statement:
        """
        Parse line into Statement object.
        
        Args:
            line: JCL line to parse
            line_number: Line number for error reporting
            
        Returns:
            Parsed Statement object
            
        Raises:
            JCLSyntaxError: If line cannot be parsed
        """
        pass
    
    @property
    @abstractmethod
    def statement_types(self) -> List[str]:
        """
        List of JCL statement types this plugin handles.
        
        Returns:
            List of statement type strings (e.g., ["JOB", "EXEC", "DD"])
        """
        pass


class ValidationPlugin(ABC):
    """
    Base class for custom validation rules.
    
    Enables additional validation beyond standard JCL syntax and structure
    checking, such as site-specific naming conventions or security rules.
    """
    
    @abstractmethod
    def validate_job(self, job: Job) -> List[ValidationError]:
        """
        Validate complete job structure.
        
        Args:
            job: Job object to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        pass
    
    @abstractmethod
    def validate_step(self, step: Step) -> List[ValidationError]:
        """
        Validate individual step.
        
        Args:
            step: Step object to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        pass
    
    @abstractmethod
    def validate_dd(self, dd: DDStatement) -> List[ValidationError]:
        """
        Validate DD statement.
        
        Args:
            dd: DDStatement object to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        pass