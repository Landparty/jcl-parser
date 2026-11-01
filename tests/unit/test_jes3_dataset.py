"""JES3 //*DATASET ... //*ENDDATASET records are data (issue #162)."""

from __future__ import annotations

import pytest

from jclparser import parse_jcl, validate_jcl
from jclparser.jes_statements import Jes3ControlStatement
from jclparser.plugins import ParserConfig

pytestmark = pytest.mark.unit

SRC = """//J JOB 1
//S1 EXEC PGM=PROG1
//IN DD DSN=A.B,DISP=SHR
//*DATASET DDNAME=SYSUT1
RECORD ONE
//INNER EXEC PGM=NOTREAL
//*ENDDATASET
//S2 EXEC PGM=PROG2
"""


def _dataset(job):
    return next(
        s
        for s in job.jes_typed_statements
        if isinstance(s, Jes3ControlStatement) and s.name == "DATASET"
    )


@pytest.mark.parametrize("dialect", ["standard", "jes3"])
def test_dataset_records_are_its_content(dialect):
    job = parse_jcl(SRC, config=ParserConfig(dialect=dialect))
    assert [s.name for s in job.steps] == ["S1", "S2"]
    assert [dd.name for dd in job.steps[0].dd_statements] == ["IN"]
    assert not any("SYSIN" in w for w in job.warnings)
    assert _dataset(job).data == ["RECORD ONE", "//INNER EXEC PGM=NOTREAL"]


def test_jes2_keeps_comment_reading():
    job = parse_jcl(SRC, config=ParserConfig(dialect="jes2"))
    assert [s.name for s in job.steps] == ["S1", "INNER", "S2"]


def test_end_terminator():
    src = SRC.replace("SYSUT1", "SYSUT1,END=XYZ").replace("//*ENDDATASET", "XYZ")
    job = parse_jcl(src, config=ParserConfig(dialect="jes3"))
    assert [s.name for s in job.steps] == ["S1", "S2"]
    assert _dataset(job).data == ["RECORD ONE", "//INNER EXEC PGM=NOTREAL"]


def test_unterminated_dataset_warns():
    src = "//J JOB 1\n//S1 EXEC PGM=P\n//*DATASET DDNAME=X\nDATA\n"
    job = parse_jcl(src)
    assert any("//*DATASET has no matching //*ENDDATASET" in w for w in job.warnings)
    assert _dataset(job).data == ["DATA"]


def test_validate_skips_dataset_records():
    errors = validate_jcl(SRC.replace("//INNER EXEC PGM=NOTREAL", "//BAD XYZZY ,,"))
    assert not [e for e in errors if e.line_number == 6]
