"""Lint runner: execute registered :class:`LintRule` instances against a job."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..errors import ValidationError, ErrorType, ErrorSeverity
from .base import LintRule
from .config import LintConfig
from .rules import BUILTIN_RULES

if TYPE_CHECKING:
    from ..model import Job


#: Pseudo-code used for the synthetic ValidationError emitted when a rule
#: raises.  Severity is overridable via :attr:`LintConfig.severities` so
#: consumers can downgrade rule crashes to INFO or suppress them outright.
_RULE_CRASH_CODE = "JCL-LINT-000"

_RULES: list[LintRule] = list(BUILTIN_RULES)


def register_rule(rule: LintRule) -> None:
    """Append *rule* to the lint rule list.

    Duplicate instances are not added; same-code replacements are allowed
    (a rule subclass sharing the code of a builtin will *not* replace the
    builtin — use :func:`unregister_rule` first if you want to swap it).
    """
    if rule in _RULES:
        return
    _RULES.append(rule)


def unregister_rule(code: str) -> bool:
    """Remove the (first) rule with *code* from the list.  Return True if removed."""
    for i, r in enumerate(_RULES):
        if r.code == code:
            del _RULES[i]
            return True
    return False


def all_rules() -> list[LintRule]:
    """Return a copy of the current rule list."""
    return list(_RULES)


def lint_job(job: "Job", config: LintConfig | None = None) -> list[ValidationError]:
    """Run every enabled :class:`LintRule` against *job* and collect findings."""
    cfg = config or LintConfig()
    findings: list[ValidationError] = []
    for rule in _RULES:
        if not cfg.should_run(rule.code):
            continue
        try:
            findings.extend(rule.check(job, cfg))
        except Exception as exc:  # noqa: BLE001 — a broken rule must not stop the run
            # Synthetic finding for a rule that crashed.  Use SEMANTIC_ERROR
            # to match normal lint findings, and default to WARNING severity
            # (overridable via LintConfig.severities[_RULE_CRASH_CODE]).
            severity = cfg.severities.get(_RULE_CRASH_CODE, ErrorSeverity.WARNING)
            findings.append(
                ValidationError(
                    message=(
                        f"Lint rule {rule.code} raised {type(exc).__name__}: {exc}"
                    ),
                    error_type=ErrorType.SEMANTIC_ERROR,
                    severity=severity,
                    error_code=_RULE_CRASH_CODE,
                )
            )
    return findings


def to_sarif(errors: list[ValidationError], tool_name: str = "jclparser") -> dict:
    """Render a minimal SARIF 2.1.0 report for *errors*.

    Produces a single-run document with every distinct ``error_code`` as a
    rule.  Findings without a code are mapped to rule ``JCL-GEN-000``.
    """
    severity_map = {
        "error": "error",
        "warning": "warning",
        "info": "note",
    }
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for err in errors:
        code = err.error_code or "JCL-GEN-000"
        if code not in rules:
            rules[code] = {
                "id": code,
                "name": code,
                "shortDescription": {"text": code},
                "fullDescription": {"text": err.message[:120]},
            }
        results.append(
            {
                "ruleId": code,
                "level": severity_map.get(err.severity.value, "warning"),
                "message": {"text": err.message},
                "locations": (
                    [
                        {
                            "physicalLocation": {
                                "region": {"startLine": err.line_number},
                            }
                        }
                    ]
                    if err.line_number
                    else []
                ),
            }
        )
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool_name,
                        "informationUri": "https://example.invalid/jclparser",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }


__all__ = [
    "register_rule",
    "unregister_rule",
    "all_rules",
    "lint_job",
    "to_sarif",
]
