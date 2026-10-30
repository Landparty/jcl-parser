"""Lint runner: execute registered :class:`LintRule` instances against a job."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from ..errors import ErrorSeverity, ErrorType, ValidationError
from .base import LintRule
from .config import LintConfig
from .rules import BUILTIN_RULES
from .suppress import parse_suppressions

if TYPE_CHECKING:
    from ..model import Job, Procedure


#: Pseudo-code used for the synthetic ValidationError emitted when a rule
#: raises.  Severity is overridable via :attr:`LintConfig.severities` so
#: consumers can downgrade rule crashes to INFO or suppress them outright.
_RULE_CRASH_CODE = "JCL-LINT-000"

#: Pseudo-code of the finding the CLI reports for a file that does not parse.
PARSE_ERROR_CODE = "JCL-PARSE-000"

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


def _run_rules(job: Job, cfg: LintConfig) -> list[ValidationError]:
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


def procedure_body_job(proc: Procedure) -> Job:
    """A JOB-less job holding *proc*'s steps, each named ``PROC.step``, so
    the step and DD rules can run over a PROC body (issue #149)."""
    from ..model import Job, iter_execution_steps

    steps = copy.deepcopy(proc.steps)
    for step in iter_execution_steps(steps):
        step.name = f"{proc.name}.{step.name}" if step.name else proc.name
    return Job(
        name=proc.name,
        steps=steps,
        set_statements=dict(proc.set_statements),
        line_number=proc.line_number,
        is_procedure_member=True,
    )


def lint_job(
    job: Job, config: LintConfig | None = None, *, source: str | None = None
) -> list[ValidationError]:
    """Run every enabled :class:`LintRule` against *job* and collect findings.

    The steps of each PROC body coded in the job's own source (an in-stream
    ``PROC ... PEND``, or the PROCs of a PROC member) are linted too, named
    ``PROC.step``; a finding the exploded copy of a body already reported
    (same code and line) is not repeated.

    With *source* (the JCL text *job* was parsed from), findings switched off
    by its ``//* jcl-lint: disable=...`` comments are left out (see
    :mod:`jclparser.lint.suppress`).
    """
    cfg = config or LintConfig()
    findings = _run_rules(job, cfg)
    seen = {(f.error_code, f.line_number) for f in findings}
    for proc in job.procedures:
        if proc.is_external:
            continue  # its lines are another file's
        for finding in _run_rules(procedure_body_job(proc), cfg):
            key = (finding.error_code, finding.line_number)
            if finding.line_number and key in seen:
                continue
            seen.add(key)
            findings.append(finding)
    if source is not None:
        findings = parse_suppressions(source).filter(findings)
    return findings


#: Descriptions of the pseudo-codes that no registered rule carries.
_PSEUDO_RULE_DESCRIPTIONS = {
    _RULE_CRASH_CODE: "A lint rule raised an exception while checking the job.",
    PARSE_ERROR_CODE: "The file could not be parsed as JCL.",
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
) -> dict[str, Any]:
    """Render a minimal SARIF 2.1.0 report for *errors*.

    Produces a single-run document with every distinct ``error_code`` as a
    rule, described by the registered rule's ``description``.  Findings
    without a code are mapped to rule ``JCL-GEN-000``.

    SARIF 2.1.0 requires every ``physicalLocation`` to carry an
    ``artifactLocation`` (or an ``address``), so one is always emitted;
    pass *artifact_uri* (the linted file's path or URI) to fill in its
    ``uri``, which consumers such as GitHub code scanning need to place a
    result in a file.  :func:`to_sarif_files` reports several files.
    """
    return to_sarif_files([(artifact_uri, errors)], tool_name=tool_name)


_SARIF_LEVELS = {"error": "error", "warning": "warning", "info": "note"}


def _sarif_result(err: ValidationError, artifact_uri: str | None) -> dict[str, Any]:
    location: dict[str, Any] = {
        "artifactLocation": {} if artifact_uri is None else {"uri": artifact_uri}
    }
    if err.line_number:
        location["region"] = {"startLine": err.line_number}
    # A finding with neither a line nor a file has nowhere to point.
    has_location = bool(err.line_number) or artifact_uri is not None
    return {
        "ruleId": err.error_code or "JCL-GEN-000",
        "level": _SARIF_LEVELS.get(err.severity.value, "warning"),
        "message": {"text": err.message},
        "locations": [{"physicalLocation": location}] if has_location else [],
    }


def to_sarif_files(
    files: Iterable[tuple[str | None, Sequence[ValidationError]]],
    tool_name: str = "jclparser",
) -> dict[str, Any]:
    """Render one SARIF 2.1.0 run for the findings of several files.

    *files* pairs each file's URI (``None`` if unknown) with its findings;
    see :func:`to_sarif` for how a finding is rendered.  A finding without a
    line number but with a URI points at the file as a whole.
    """
    descriptions = _rule_descriptions()
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for artifact_uri, errors in files:
        for err in errors:
            code = err.error_code or "JCL-GEN-000"
            if code not in rules:
                rules[code] = _sarif_rule(code, descriptions.get(code))
            results.append(_sarif_result(err, artifact_uri))
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool_name,
                        "informationUri": "https://github.com/landparty/jcl-parser",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }


__all__ = [
    "PARSE_ERROR_CODE",
    "all_rules",
    "lint_job",
    "register_rule",
    "to_sarif",
    "to_sarif_files",
    "unregister_rule",
]
