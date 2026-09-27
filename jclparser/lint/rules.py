"""Built-in lint rules.

Each rule has a stable code ``JCL-LINT-NNN``.  Rules are deliberately
simple and self-contained — add new ones by subclassing
:class:`~jclparser.lint.base.LintRule` and registering them with
:func:`~jclparser.lint.runner.register_rule`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..errors import ErrorSeverity, ValidationError
from ..model import iter_execution_steps
from .base import LintRule

if TYPE_CHECKING:
    from ..model import Job
    from .config import LintConfig


class HardcodedHLQRule(LintRule):
    code = "JCL-LINT-001"
    description = "Dataset name should use a symbolic HLQ (&HLQ) rather than a literal."
    default_severity = ErrorSeverity.INFO

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        for step in iter_execution_steps(job.steps):
            for dd in step.dd_statements:
                dsn = dd.dataset_name
                if not dsn or dsn.startswith("&&"):
                    continue
                # A name built from symbols (&HLQ..DATA) is what this rule
                # asks for, even after SET / PROC substitution resolved it.
                if "&" in dsn or "&" in (dd.coded_dataset_name or ""):
                    continue
                # Only warn on real (production-looking) names — at least two
                # qualifiers — to avoid being noisy on tiny test JCL.
                if "." not in dsn:
                    continue
                yield self._err(
                    f"DD '{dd.name}' in step '{step.name}' uses literal HLQ "
                    f"in dataset '{dsn}' — consider &HLQ",
                    line_number=dd.line_number,
                    config=config,
                )


class LiteralSysdaUnitRule(LintRule):
    code = "JCL-LINT-002"
    description = "UNIT=SYSDA is a generic device group; prefer site-specific unit."
    default_severity = ErrorSeverity.INFO

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        for step in iter_execution_steps(job.steps):
            for dd in step.dd_statements:
                unit = dd.parameters.get("UNIT")
                if not unit:
                    continue
                unit_val = unit if isinstance(unit, str) else ",".join(map(str, unit))
                if unit_val.upper() == "SYSDA":
                    yield self._err(
                        f"DD '{dd.name}' in step '{step.name}' uses UNIT=SYSDA",
                        line_number=dd.line_number,
                        config=config,
                    )


class CriticalDatasetDeleteRule(LintRule):
    code = "JCL-LINT-003"
    description = (
        "Critical dataset allocated DISP=(NEW,CATLG,DELETE) — normal CATLG but "
        "abnormal DELETE may discard data on failure."
    )
    default_severity = ErrorSeverity.WARNING

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        patterns = [p.upper() for p in config.critical_dataset_patterns]
        if not patterns:
            return
        for step in iter_execution_steps(job.steps):
            for dd in step.dd_statements:
                if not dd.dataset_name:
                    continue
                upper = dd.dataset_name.upper()
                if not any(p in upper for p in patterns):
                    continue
                tokens = dd._disp_tokens() if dd.disposition else []
                if len(tokens) >= 3 and tokens[0] == "NEW" and tokens[2] == "DELETE":
                    yield self._err(
                        f"Critical dataset '{dd.dataset_name}' has "
                        f"DISP=(NEW,{tokens[1] or 'CATLG'},DELETE)",
                        line_number=dd.line_number,
                        config=config,
                    )


class MissingJobTimeRule(LintRule):
    code = "JCL-LINT-004"
    description = "JOB card should specify TIME= to cap runaway CPU usage."
    default_severity = ErrorSeverity.INFO

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        if job.parameters.get("TIME") is None:
            yield self._err(
                f"JOB '{job.name}' has no TIME= parameter",
                line_number=job.line_number,
                config=config,
            )


class MissingJobRegionRule(LintRule):
    code = "JCL-LINT-005"
    description = "JOB card should specify REGION= to bound memory usage."
    default_severity = ErrorSeverity.INFO

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        if job.parameters.get("REGION") is None:
            yield self._err(
                f"JOB '{job.name}' has no REGION= parameter",
                line_number=job.line_number,
                config=config,
            )


class DuplicateStepNameRule(LintRule):
    code = "JCL-LINT-007"
    description = "Step names must be unique within a job."
    default_severity = ErrorSeverity.ERROR

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        seen: set[str] = set()
        for step in iter_execution_steps(job.steps):
            if not step.name:
                continue
            if step.name in seen:
                yield self._err(
                    f"Duplicate step name '{step.name}'",
                    line_number=step.line_number,
                    config=config,
                )
            else:
                seen.add(step.name)


class UndefinedOutputRefRule(LintRule):
    code = "JCL-LINT-008"
    description = "DD OUTPUT=*.name references an undefined //X OUTPUT statement."
    default_severity = ErrorSeverity.WARNING

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        for step_name, ref, line_number in getattr(job, "unresolved_output_refs", []):
            step_label = f" in step '{step_name}'" if step_name else ""
            yield self._err(
                f"OUTPUT=*.{ref}{step_label} does not match any OUTPUT statement",
                line_number=line_number,
                config=config,
            )


BUILTIN_RULES: list[LintRule] = [
    HardcodedHLQRule(),
    LiteralSysdaUnitRule(),
    CriticalDatasetDeleteRule(),
    MissingJobTimeRule(),
    MissingJobRegionRule(),
    DuplicateStepNameRule(),
    UndefinedOutputRefRule(),
]


__all__ = [
    "BUILTIN_RULES",
    "CriticalDatasetDeleteRule",
    "DuplicateStepNameRule",
    "HardcodedHLQRule",
    "LiteralSysdaUnitRule",
    "MissingJobRegionRule",
    "MissingJobTimeRule",
    "UndefinedOutputRefRule",
]
