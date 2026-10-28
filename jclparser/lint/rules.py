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
from ..model import _dataset_dds, iter_execution_steps
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
            for dd in _dataset_dds(step):
                dsn = dd.dataset_name
                if not dsn or dsn.startswith("&&"):
                    continue
                # A backward reference (*.STEP.DD) names no HLQ of its own,
                # and NULLFILE is a dummy data set.
                if dsn.startswith("*.") or dsn.upper() == "NULLFILE":
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
            for dd in _dataset_dds(step):
                unit = dd.parameters.get("UNIT")
                if not unit:
                    continue
                # UNIT=(SYSDA,2) / UNIT=(SYSDA,,DEFER): the device is the
                # first subparameter (issue #114).
                unit_val = unit if isinstance(unit, str) else str(unit[0])
                if unit_val.strip("()").split(",")[0].strip().upper() == "SYSDA":
                    yield self._err(
                        f"DD '{dd.name}' in step '{step.name}' uses UNIT=SYSDA",
                        line_number=dd.line_number,
                        config=config,
                    )


class CriticalDatasetDeleteRule(LintRule):
    code = "JCL-LINT-003"
    description = (
        "Critical dataset allocated DISP=(NEW,CATLG,DELETE) or "
        "DISP=(NEW,KEEP,DELETE) — a successful run keeps it, but the abnormal "
        "DELETE discards the data if the step fails."
    )
    default_severity = ErrorSeverity.WARNING

    #: Normal dispositions that retain a new dataset after a successful run.
    #: An omitted one defaults to DELETE (and PASS hands the dataset on), so
    #: an abnormal DELETE then loses nothing a successful run would keep.
    _RETAINING = frozenset({"CATLG", "KEEP"})

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        patterns = [p.upper() for p in config.critical_dataset_patterns]
        if not patterns:
            return
        for step in iter_execution_steps(job.steps):
            for dd in _dataset_dds(step):
                if not dd.dataset_name:
                    continue
                upper = dd.dataset_name.upper()
                if not any(p in upper for p in patterns):
                    continue
                tokens = dd._disp_tokens() if dd.disposition else []
                if (
                    len(tokens) >= 3
                    and tokens[0] == "NEW"
                    and tokens[1] in self._RETAINING
                    and tokens[2] == "DELETE"
                ):
                    yield self._err(
                        f"Critical dataset '{dd.dataset_name}' has "
                        f"DISP=({','.join(tokens)})",
                        line_number=dd.line_number,
                        config=config,
                    )


class MissingJobTimeRule(LintRule):
    code = "JCL-LINT-004"
    description = "JOB card should specify TIME= to cap runaway CPU usage."
    default_severity = ErrorSeverity.INFO

    def check(self, job: Job, config: LintConfig) -> Iterable[ValidationError]:
        if job.parameters.get("TIME") is None and not job.is_procedure_member:
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
        if job.parameters.get("REGION") is None and not job.is_procedure_member:
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
