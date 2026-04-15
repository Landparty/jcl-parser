"""Configuration for the lint runner."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ErrorSeverity


@dataclass
class LintConfig:
    """User-facing lint configuration.

    Attributes:
        enabled: Set of rule codes to run.  Empty set means "run every
            registered rule" (the default).
        disabled: Set of rule codes to skip.  Takes precedence over
            :attr:`enabled`.
        severities: Per-rule severity override map, e.g.
            ``{"JCL-LINT-002": ErrorSeverity.INFO}``.
        critical_dataset_patterns: Dataset-name fragments (uppercased
            substring match) that mark a dataset as *critical* for rule
            JCL-LINT-003.  Example: ``["PROD.", ".MASTER."]``.
    """

    enabled: set[str] = field(default_factory=set)
    disabled: set[str] = field(default_factory=set)
    severities: dict[str, ErrorSeverity] = field(default_factory=dict)
    critical_dataset_patterns: list[str] = field(default_factory=list)

    def should_run(self, code: str) -> bool:
        if code in self.disabled:
            return False
        if not self.enabled:
            return True
        return code in self.enabled


__all__ = ["LintConfig"]
