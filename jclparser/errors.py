"""
Error classes and exception hierarchy for JCL parser.

Provides comprehensive error handling with detailed context information
for syntax errors, validation errors, and parsing failures.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ErrorType(Enum):
    """Types of errors that can occur during JCL parsing"""
    SYNTAX_ERROR = "syntax_error"
    VALIDATION_ERROR = "validation_error"
    STRUCTURE_ERROR = "structure_error"
    SEMANTIC_ERROR = "semantic_error"


class ErrorSeverity(Enum):
    """Severity levels for parsing errors"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ParseError:
    """
    Represents a parsing error with detailed context information.
    
    Attributes:
        error_type: Type of error (syntax, validation, etc.)
        message: Human-readable error description
        line_number: Source line where error occurred
        column_number: Character position if available
        context: Surrounding text context
        severity: Error severity level
    """
    error_type: ErrorType
    message: str
    line_number: int
    column_number: Optional[int] = None
    context: str = ""
    severity: ErrorSeverity = ErrorSeverity.ERROR


class JCLParseError(Exception):
    """Base exception class for JCL parsing errors"""
    
    def __init__(self, message: str, line_number: int = 0, context: str = ""):
        self.message = message
        self.line_number = line_number
        self.context = context
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        """Format error message with context information"""
        if self.line_number > 0:
            return f"Line {self.line_number}: {self.message}"
        return self.message


class JCLSyntaxError(JCLParseError):
    """Exception raised for JCL syntax errors"""
    pass


class JCLValidationError(JCLParseError):
    """Exception raised for JCL validation errors"""
    pass


class JCLStructureError(JCLParseError):
    """Exception raised for JCL structure errors"""
    pass


class ValidationError:
    """Represents a validation error (non-exception form)"""
    
    def __init__(self, message: str, error_type: ErrorType = ErrorType.VALIDATION_ERROR):
        self.message = message
        self.error_type = error_type