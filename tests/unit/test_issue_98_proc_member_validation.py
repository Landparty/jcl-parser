"""Regression tests for issue #98.

A JOB-less cataloged PROC member keeps its steps in ``job.procedures``, so
``job.steps`` is empty.  ``validate_jcl`` and a strict parse reported its DDs
as orphans, and its synthetic ``Job(name="")`` failed the job-name and
"at least one execution step" checks; ``lint`` flagged the missing JOB card
TIME= / REGION=.
"""

from __future__ import annotations

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl
from jclparser.errors import JCLStructureError, JCLValidationError
from jclparser.lint import lint_job

pytestmark = pytest.mark.unit

_MEMBER_WITH_DD = """//MYPROC PROC
//S1 EXEC PGM=IEBGENER
//SYSUT1 DD DSN=A.B,DISP=SHR
// PEND
"""

_MEMBER_NO_PEND = """//MYPROC PROC
//S1 EXEC PGM=IEBGENER
//SYSUT1 DD DSN=A.B,DISP=SHR
"""

_MEMBER_NO_DD = """//MYPROC PROC
//S1 EXEC PGM=IEBGENER
// PEND
"""


@pytest.mark.parametrize("src", [_MEMBER_WITH_DD, _MEMBER_NO_PEND, _MEMBER_NO_DD])
def test_proc_member_validates_clean(src):
    assert validate_jcl(src) == []


@pytest.mark.parametrize("src", [_MEMBER_WITH_DD, _MEMBER_NO_PEND, _MEMBER_NO_DD])
def test_proc_member_strict_parse(src):
    job = parse_jcl(src, strict_mode=True)
    assert job.is_procedure_member
    assert job.validate() == []


def test_proc_member_flag_survives_explosion():
    assert explode_job(parse_jcl(_MEMBER_WITH_DD)).is_procedure_member


def test_real_job_is_not_a_procedure_member():
    assert not parse_jcl("//J JOB\n//S EXEC PGM=X\n").is_procedure_member


def test_lint_skips_job_card_rules_for_proc_member():
    codes = {f.error_code for f in lint_job(parse_jcl(_MEMBER_WITH_DD))}
    assert not codes & {"JCL-LINT-004", "JCL-LINT-005"}


def test_job_with_only_instream_proc_is_not_an_orphan_dd_error():
    src = "//J JOB\n" + _MEMBER_WITH_DD
    messages = [e.message for e in validate_jcl(src)]
    assert not any("DD statement found before any EXEC" in m for m in messages)
    # A JOB whose only content is in-stream PROCs is how a PROC-library
    # member is wrapped for parsing (the backend's synthetic JOB card), so
    # its procedures count as its content (#100).
    assert "Job must contain at least one execution step" not in messages
    parse_jcl(src, strict_mode=True)


def test_job_with_nothing_to_run_is_still_an_error():
    src = "//J JOB 1\n//* only a comment\n"
    messages = [e.message for e in validate_jcl(src)]
    assert "Job must contain at least one execution step" in messages
    with pytest.raises(JCLValidationError):
        parse_jcl(src, strict_mode=True)


def test_job_level_orphan_dd_still_reported():
    src = "//J JOB 1\n//D DD DSN=A.B,DISP=SHR\n"
    with pytest.raises(JCLStructureError):
        parse_jcl(src, strict_mode=True)


def test_orphan_dd_after_pend_still_reported():
    src = "//J JOB 1\n" + _MEMBER_WITH_DD + "//D DD DSN=A.B,DISP=SHR\n"
    with pytest.raises(JCLStructureError):
        parse_jcl(src, strict_mode=True)
