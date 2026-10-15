"""
Base plugin interfaces for JCL parser extensions.

Contains abstract base classes for statement and validation plugins
that enable custom JCL dialects and validation rules.
"""

from abc import ABC, abstractmethod

from ..errors import ValidationError
from ..model import DDStatement, Job, Statement, Step


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

    @property
    @abstractmethod
    def statement_types(self) -> list[str]:
        """
        List of JCL statement types this plugin handles.

        Advisory metadata describing the ``Statement.type`` values
        :meth:`parse_statement` returns; the parser does not dispatch on it
        (:meth:`can_parse` selects the plugin).  A returned statement whose
        type is a built-in one (``"EXEC"``, ``"DD"``, ...) is processed like a
        native statement of that type; any other (custom) type is kept
        verbatim, in source order, in :attr:`jclparser.model.Job.custom_statements`.

        Returns:
            List of statement type strings (e.g., ["JOB", "EXEC", "DD"])
        """


class ValidationPlugin(ABC):
    """
    Base class for custom validation rules.

    Enables additional validation beyond standard JCL syntax and structure
    checking, such as site-specific naming conventions or security rules.
    """

    @abstractmethod
    def validate_job(self, job: Job) -> list[ValidationError]:
        """
        Validate complete job structure.

        Args:
            job: Job object to validate

        Returns:
            List of validation errors (empty if valid)
        """

    @abstractmethod
    def validate_step(self, step: Step) -> list[ValidationError]:
        """
        Validate individual step.

        Args:
            step: Step object to validate

        Returns:
            List of validation errors (empty if valid)
        """

    @abstractmethod
    def validate_dd(self, dd: DDStatement) -> list[ValidationError]:
        """
        Validate DD statement.

        Args:
            dd: DDStatement object to validate

        Returns:
            List of validation errors (empty if valid)
        """
