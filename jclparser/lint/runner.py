"""Lint runner: execute registered :class:`LintRule` instances against a job."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..errors import ErrorSeverity, ErrorType, ValidationError
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


def lint_job(job: Job, config: LintConfig | None = None) -> list[ValidationError]:
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


#: Descriptions of the pseudo-codes that no registered rule carries.
_PSEUDO_RULE_DESCRIPTIONS = {
    _RULE_CRASH_CODE: "A lint rule raised an exception while checking the job.",
    "JCL-GEN-000": "Finding reported without a rule code.",
}


def _rule_descriptions() -> dict[str, str]:
    """Each registered rule's ``description`` by code (first rule wins)."""
    descriptions = dict(_PSEUDO_RULE_DESCRIPTIONS)
    for rule in _RULES:
        if rule.code and rule.description:
            descriptions.setdefault(rule.code, rule.description)
    return descriptions


def _sarif_rule(code: str, description: str | None) -> dict[str, object]:
    """SARIF ``reportingDescriptor`` for *code*.

    The descriptions come from the rule itself, not from one of its
    findings (whose message describes that one finding, issue #88).  Rules
    carry no separate short title, so ``shortDescription`` repeats the
    description.  A code no registered rule carries (a finding from
    elsewhere) gets its code as ``shortDescription`` and no
    ``fullDescription``, rather than an invented one.
    """
    descriptor: dict[str, object] = {"id": code, "name": code}
    if description is None:
        descriptor["shortDescription"] = {"text": code}
        return descriptor
    descriptor["shortDescription"] = {"text": description}
    descriptor["fullDescription"] = {"text": description}
    return descriptor


def to_sarif(
    errors: list[ValidationError],
    tool_name: str = "jclparser",
    artifact_uri: str | None = None,
) -> dict:
    """Render a minimal SARIF 2.1.0 report for *errors*.

    Produces a single-run document with every distinct ``error_code`` as a
    rule, described by the registered rule's ``description``.  Findings
    without a code are mapped to rule ``JCL-GEN-000``.

    SARIF 2.1.0 requires every ``physicalLocation`` to carry an
    ``artifactLocation`` (or an ``address``), so one is always emitted;
    pass *artifact_uri* (the linted file's path or URI) to fill in its
    ``uri``, which consumers such as GitHub code scanning need to place a
    result in a file.
    """
    artifact_location: dict = {} if artifact_uri is None else {"uri": artifact_uri}
    severity_map = {
        "error": "error",
        "warning": "warning",
        "info": "note",
    }
    descriptions = _rule_descriptions()
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for err in errors:
        code = err.error_code or "JCL-GEN-000"
        if code not in rules:
            rules[code] = _sarif_rule(code, descriptions.get(code))
        results.append(
            {
                "ruleId": code,
                "level": severity_map.get(err.severity.value, "warning"),
                "message": {"text": err.message},
                "locations": (
                    [
                        {
                            "physicalLocation": {
                                "artifactLocation": dict(artifact_location),
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
    "all_rules",
    "lint_job",
    "register_rule",
    "to_sarif",
    "unregister_rule",
]
