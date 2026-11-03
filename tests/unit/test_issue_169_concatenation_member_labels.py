"""Regression tests for issue #169.

Lint rules and validators named an unnamed DD concatenation member by its
own empty name (``DD ''``, ``DD  has ...``). They now use the label the
dataset-lifecycle checker uses: ``IN, concatenation member 2``.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl, validate_jcl
from jclparser.lint import LintConfig, lint_job
from jclparser.model import DDStatement, dd_label
from jclparser.validators import validate_dd_statement

pytestmark = pytest.mark.unit

_JCL = (
    "//J   JOB 1,TIME=1,REGION=0M\n"
    "//S1  EXEC PGM=A\n"
    "//IN  DD DSN=PROD.A,DISP=SHR\n"
    "//    DD DSN=PROD.B,DISP=SHR,UNIT=SYSDA\n"
    "//    DD DSN=X.C,DISP=FOO\n"
    "//    DD DSN=X.D,DISP=SHR,SYSOUT=A\n"
)


def test_lint_names_the_owning_dd() -> None:
    cfg = LintConfig(enabled={"JCL-LINT-001", "JCL-LINT-002"})
    messages = {(f.line_number, f.message) for f in lint_job(parse_jcl(_JCL), cfg)}
    assert (
        4,
        "DD 'IN, concatenation member 2' in step 'S1' uses UNIT=SYSDA",
    ) in messages
    assert not any("DD ''" in m for _, m in messages)


def test_validation_names_the_owning_dd() -> None:
    messages = {
        (e.line_number, e.message) for e in validate_jcl(_JCL, level="structure")
    }
    assert (5, "Invalid DISP parameter 'FOO' on DD IN, concatenation member 3") in (
        messages
    )
    assert (
        6,
        "DD IN, concatenation member 4 has conflicting data source specifications",
    ) in messages


def test_dd_label_and_default() -> None:
    named = DDStatement(name="IN")
    first = DDStatement(name="")
    second = DDStatement(name="")
    stray = DDStatement(name="")
    assert dd_label([named, first, second], second) == "IN, concatenation member 3"
    assert dd_label([named], named) == "IN"
    assert dd_label([stray, named], stray) == "(unnamed)"
    # Without a label the message keeps the DD's own name (public API).
    bad = DDStatement(name="OUT", disposition="FOO")
    assert any("on DD OUT" in e.message for e in validate_dd_statement(bad))
