"""``DISP=(,CATLG,DELETE)`` — an omitted status — means ``NEW``.

Lifecycle analysis, the IEFBR14 profile, ``DDStatement.is_output()`` and lint
rule JCL-LINT-003 all read the empty status as "no DISP", so the most common
way to allocate a dataset was invisible to them.
"""

import pytest

from jclparser import analyze_dataset_lifecycle, parse_jcl
from jclparser.dataset_lifecycle import _parse_disp_tokens, validate_dataset_lifecycle
from jclparser.lint import LintConfig, lint_job
from jclparser.program_profiles import analyze_step

JCL = (
    "//J        JOB (ACCT),'T'\n"
    "//S1       EXEC PGM=IEFBR14\n"
    "//D        DD DSN=PROD.CRIT.A,DISP=(,CATLG,DELETE),SPACE=(TRK,1)\n"
    "//S2       EXEC PGM=IEFBR14\n"
    "//D        DD DSN=PROD.CRIT.A,DISP=(,CATLG,DELETE),SPACE=(TRK,1)\n"
    "//P        DD DSN=&&T,DISP=(,PASS)\n"
)


@pytest.mark.unit
class TestOmittedDispStatus:
    @pytest.mark.parametrize(
        ("disp", "expected"),
        [
            (["", "CATLG", "DELETE"], ("NEW", "CATLG", "DELETE")),
            ("(,CATLG)", ("NEW", "CATLG", "")),
            ("SHR", ("SHR", "", "")),
            (None, ("", "", "")),
        ],
    )
    def test_parse_disp_tokens(self, disp, expected):
        assert _parse_disp_tokens(disp) == expected

    def test_lifecycle_records_allocations(self):
        events = analyze_dataset_lifecycle(parse_jcl(JCL))["PROD.CRIT.A"]
        assert [(e.step_name, e.action) for e in events] == [
            ("S1", "ALLOCATE"),
            ("S2", "ALLOCATE"),
        ]

    def test_duplicate_catalog_is_reported(self):
        errors = validate_dataset_lifecycle(parse_jcl(JCL))
        assert any("already cataloged in step 'S1'" in str(e) for e in errors)

    def test_iefbr14_profile_sees_allocation(self):
        result = analyze_step(parse_jcl(JCL).steps[0])
        assert "allocates PROD.CRIT.A" in result.notes

    def test_is_output_for_omitted_status(self):
        dds = parse_jcl(JCL).steps[1].dd_statements
        assert dds[1].is_output()
        assert not dds[1].is_input()

    def test_lint_critical_dataset_rule(self):
        config = LintConfig(critical_dataset_patterns=["PROD.CRIT"])
        findings = lint_job(parse_jcl(JCL), config)
        assert any("DISP=(NEW,CATLG,DELETE)" in str(f) for f in findings)
