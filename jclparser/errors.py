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

    def __init__(
        self,
        message: str,
        line_number: int = 0,
        context: str = "",
        column_number: int = 0,
    ):
        self.message = message
        self.line_number = line_number
        self.context = context
        self.column_number = column_number
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format error message with context information"""
        if self.line_number > 0 and self.column_number > 0:
            return (
                f"Line {self.line_number}, column {self.column_number}: {self.message}"
            )
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


class UndefinedSymbolError(JCLParseError):
    """Exception raised when a symbolic parameter cannot be resolved"""

    def __init__(
        self,
        symbol: str,
        line_number: int = 0,
        context: str = "",
        source_text: str = "",
    ):
        self.symbol = symbol
        self.source_text = source_text
        message = f"Undefined symbolic parameter: &{symbol}" + (
            f" in '{source_text}'" if source_text else ""
        )
        super().__init__(message, line_number, context)


class ExplosionDepthError(JCLParseError):
    """Exception raised when procedure explosion depth exceeds maximum"""

    def __init__(self, depth: int, max_depth: int, call_chain: list):
        self.depth = depth
        self.max_depth = max_depth
        self.call_chain = call_chain
        message = f"Procedure explosion depth {depth} exceeds maximum {max_depth}. Call chain: {' -> '.join(call_chain)}"
        super().__init__(message)


class CircularProcedureError(JCLParseError):
    """Exception raised when circular procedure references are detected"""

    def __init__(self, procedure_name: str, call_chain: list):
        self.procedure_name = procedure_name
        self.call_chain = call_chain
        message = f"Circular procedure reference detected: {procedure_name}. Call chain: {' -> '.join(call_chain)}"
        super().__init__(message)


class ProcedureNotFoundError(JCLParseError):
    """Exception raised when a referenced procedure cannot be found"""

    def __init__(self, procedure_name: str, line_number: int = 0):
        self.procedure_name = procedure_name
        message = f"Procedure not found: {procedure_name}"
        super().__init__(message, line_number)


class ValidationError:
    """Represents a validation error (non-exception form)"""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.VALIDATION_ERROR,
        line_number: Optional[int] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
    ):
        self.message = message
        self.error_type = error_type
        self.line_number = line_number
        self.severity = severity

    @property
    def is_warning(self) -> bool:
        """True if this is a WARNING-level issue (not necessarily fatal)."""
        return self.severity == ErrorSeverity.WARNING

    def __str__(self) -> str:
        """String representation of validation error"""
        prefix = (
            f"[{self.severity.value.upper()}] "
            if self.severity != ErrorSeverity.ERROR
            else ""
        )
        if self.line_number:
            return f"Line {self.line_number}: {prefix}{self.message}"
        return f"{prefix}{self.message}"
