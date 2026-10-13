"""Regression tests for issue #88.

JCL-LINT-003 fired on ``DISP=(NEW,,DELETE)`` (labelled ``CATLG``),
``(NEW,DELETE,DELETE)`` and ``(NEW,PASS,DELETE)``; and ``to_sarif`` described
each rule by its code and the first finding's message.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.errors import ErrorSeverity, ValidationError
from jclparser.lint import LintConfig, lint_job, to_sarif
from jclparser.lint.rules import BUILTIN_RULES, CriticalDatasetDeleteRule

pytestmark = pytest.mark.unit

_CFG = LintConfig(critical_dataset_patterns=["PROD.CRIT"], enabled={"JCL-LINT-003"})


def _findings(disp: str) -> list[ValidationError]:
    job = parse_jcl(
        "//J        JOB  1\n"
        "//S        EXEC PGM=IEFBR14\n"
        f"//D        DD DSN=PROD.CRIT.A,DISP={disp},SPACE=(TRK,1)\n"
    )
    return lint_job(job, _CFG)


class TestCriticalDatasetDispositions:
    @pytest.mark.parametrize(
        "disp",
        [
            "(NEW,CATLG,DELETE)",
            "(NEW,KEEP,DELETE)",
            "(,CATLG,DELETE)",
            "(new,keep,delete)",
        ],
    )
    def test_retaining_normal_disposition_fires(self, disp):
        findings = _findings(disp)
        assert [f.error_code for f in findings] == ["JCL-LINT-003"]

    @pytest.mark.parametrize(
        ("disp", "shown"),
        [
            ("(NEW,CATLG,DELETE)", "DISP=(NEW,CATLG,DELETE)"),
            ("(NEW,KEEP,DELETE)", "DISP=(NEW,KEEP,DELETE)"),
        ],
    )
    def test_message_shows_disposition_as_coded(self, disp, shown):
        (finding,) = _findings(disp)
        assert shown in finding.message

    @pytest.mark.parametrize(
        "disp",
        [
            "(NEW,,DELETE)",
            "(NEW,DELETE,DELETE)",
            "(NEW,PASS,DELETE)",
            "(NEW,CATLG,CATLG)",
            "(NEW,CATLG,KEEP)",
            "(NEW,CATLG)",
            "(OLD,KEEP,DELETE)",
            "(MOD,CATLG,DELETE)",
            "NEW",
        ],
    )
    def test_other_dispositions_do_not_fire(self, disp):
        assert _findings(disp) == []

    def test_description_names_keep(self):
        assert "KEEP" in CriticalDatasetDeleteRule.description
        assert "CATLG" in CriticalDatasetDeleteRule.description


class TestSarifRuleDescriptors:
    def _rules(self, findings: list[ValidationError]) -> dict[str, dict]:
        driver = to_sarif(findings)["runs"][0]["tool"]["driver"]
        return {r["id"]: r for r in driver["rules"]}

    def test_builtin_rules_described_by_their_description(self):
        findings = _findings("(NEW,CATLG,DELETE)")
        findings += lint_job(parse_jcl("//J JOB 1\n//S EXEC PGM=X\n"))
        rules = self._rules(findings)
        by_code = {rule.code: rule for rule in BUILTIN_RULES}
        assert {"JCL-LINT-003", "JCL-LINT-004", "JCL-LINT-005"} <= set(rules)
        for code, descriptor in rules.items():
            description = by_code[code].description
            assert descriptor["shortDescription"] == {"text": description}
            assert descriptor["fullDescription"] == {"text": description}
            assert descriptor["fullDescription"]["text"] != findings[0].message

    def test_crash_and_codeless_pseudo_rules(self):
        findings = [
            ValidationError("x", severity=ErrorSeverity.WARNING),
            ValidationError(
                "Lint rule X raised ValueError: y",
                severity=ErrorSeverity.WARNING,
                error_code="JCL-LINT-000",
            ),
        ]
        rules = self._rules(findings)
        assert "without a rule code" in rules["JCL-GEN-000"]["fullDescription"]["text"]
        assert "raised an exception" in rules["JCL-LINT-000"]["fullDescription"]["text"]

    def test_unknown_code_has_no_invented_description(self):
        finding = ValidationError(
            "some specific message",
            severity=ErrorSeverity.WARNING,
            error_code="OTHER-001",
        )
        descriptor = self._rules([finding])["OTHER-001"]
        assert descriptor["shortDescription"] == {"text": "OTHER-001"}
        assert "fullDescription" not in descriptor
