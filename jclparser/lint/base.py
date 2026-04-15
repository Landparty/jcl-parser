"""Lint rule framework.

A :class:`LintRule` is a small analysis plugin with a stable identifier
(``code``), a default severity, and a ``check(job, config)`` method that
returns zero or more :class:`~jclparser.errors.ValidationError` objects
tagged with the rule's code.

Rules are run via :func:`jclparser.lint.runner.lint_job`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterable

from ..errors import ValidationError, ErrorSeverity, ErrorType

if TYPE_CHECKING:
    from ..model import Job
    from .config import LintConfig


class LintRule(ABC):
    """Base class for lint rules.

    Subclasses set ``code`` (e.g. ``"JCL-LINT-001"``), ``description``, and
    ``default_severity``, and implement :meth:`check`.
    """

    code: str = ""
    description: str = ""
    default_severity: ErrorSeverity = ErrorSeverity.WARNING
    error_type: ErrorType = ErrorType.SEMANTIC_ERROR

    @abstractmethod
    def check(self, job: "Job", config: "LintConfig") -> Iterable[ValidationError]:
        """Yield findings for *job* under *config*."""
        raise NotImplementedError

    def _err(
        self,
        message: str,
        *,
        line_number: int | None = None,
        config: "LintConfig | None" = None,
    ) -> ValidationError:
        """Helper: build a ValidationError tagged with this rule's code."""
        severity = self.default_severity
        if config is not None:
            severity = config.severities.get(self.code, severity)
        return ValidationError(
            message=message,
            error_type=self.error_type,
            line_number=line_number,
            severity=severity,
            error_code=self.code,
        )


__all__ = ["LintRule"]
