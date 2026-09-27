"""JCL-LINT-001 does not flag a dataset name built from a symbol.

SET substitution at parse time (and PROC explosion) resolve ``&HLQ..DATA`` to
``PROD.DATA`` before lint runs, so the rule used to flag exactly the
symbolic names it recommends. ``DDStatement.coded_dataset_name`` keeps the
name as coded.
"""

import pytest

from jclparser import parse_jcl
from jclparser.lint import lint_job

JCL = (
    "//J        JOB (ACCT),'T'\n"
    "//         SET HLQ=PROD\n"
    "//P        PROC SFX=A\n"
    "//PS       EXEC PGM=X\n"
    "//IN       DD DSN=&HLQ..&SFX,DISP=SHR\n"
    "//         PEND\n"
    "//S1       EXEC P\n"
    "//PS.IN    DD DISP=OLD\n"
    "//S2       EXEC PGM=Y\n"
    "//SYM      DD DSN=&HLQ..DATA,DISP=SHR\n"
    "//LIT      DD DSN=PROD.LITERAL,DISP=SHR\n"
)


def _hlq_findings(job):
    return [str(f) for f in lint_job(job) if "JCL-LINT-001" in str(f)]


@pytest.mark.unit
class TestLintSymbolicHlq:
    def test_coded_name_is_kept(self):
        dd = parse_jcl(JCL).steps[1].dd_statements[0]
        assert dd.dataset_name == "PROD.DATA"
        assert dd.coded_dataset_name == "&HLQ..DATA"

    def test_literal_name_has_no_coded_name(self):
        dd = parse_jcl(JCL).steps[1].dd_statements[1]
        assert dd.coded_dataset_name is None

    def test_only_literal_name_flagged(self):
        findings = _hlq_findings(parse_jcl(JCL))
        assert len(findings) == 1
        assert "PROD.LITERAL" in findings[0]

    def test_exploded_proc_dd_not_flagged(self):
        job = parse_jcl(JCL).explode()
        findings = _hlq_findings(job)
        assert len(findings) == 1
        assert "PROD.LITERAL" in findings[0]
        proc_dd = job.steps[0].dd_statements[0]
        assert proc_dd.dataset_name == "PROD.A"
        assert proc_dd.disposition == "OLD"
        assert proc_dd.coded_dataset_name == "&HLQ..&SFX"
