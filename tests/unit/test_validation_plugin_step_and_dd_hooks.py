"""validate_jcl(level="semantic") runs every ValidationPlugin hook."""

from __future__ import annotations

import pytest

from jclparser import ValidationPlugin, get_plugin_registry, validate_jcl
from jclparser.errors import ErrorType, ValidationError
from jclparser.plugins import ALL_PLUGINS, ParserConfig

pytestmark = pytest.mark.unit

_SOURCE = (
    "//J        JOB 1\n"
    "//S1       EXEC PGM=A\n"
    "//D        DD DSN=TEST.X,DISP=SHR\n"
    "//         IF RC = 0 THEN\n"
    "//S2       EXEC PGM=B\n"
    "//E        DD DSN=PROD.Y,DISP=SHR\n"
    "//         ENDIF\n"
)


class _SiteRules(ValidationPlugin):
    def validate_job(self, job):
        return [ValidationError(f"job {job.name}", ErrorType.VALIDATION_ERROR)]

    def validate_step(self, step):
        return [
            ValidationError(
                f"step {step.name}",
                ErrorType.VALIDATION_ERROR,
                line_number=step.line_number,
            )
        ]

    def validate_dd(self, dd):
        if dd.dataset_name and not dd.dataset_name.startswith("PROD."):
            return [
                ValidationError(
                    f"dsn {dd.dataset_name}",
                    ErrorType.VALIDATION_ERROR,
                    line_number=dd.line_number,
                )
            ]
        return []


@pytest.fixture
def site_rules():
    registry = get_plugin_registry()
    registry.register_validation_plugin(_SiteRules())
    yield
    registry.unregister_plugin("_SiteRules")


def test_step_and_dd_hooks_run_with_line_numbers(site_rules):
    found = {
        (e.message, e.line_number)
        for e in validate_jcl(
            _SOURCE, "semantic", config=ParserConfig(enabled_plugins=[ALL_PLUGINS])
        )
    }
    assert found == {
        ("job J", 0),
        ("step S1", 2),
        ("step S2", 5),  # inside an IF branch
        ("dsn TEST.X", 3),
    }


def test_plugins_not_run_below_semantic_level(site_rules):
    assert validate_jcl(_SOURCE, "structure") == []
