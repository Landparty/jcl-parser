"""Regression tests for issue #115.

In-stream data records were normalized like JCL statements: columns 72-80
were dropped from 80-column card images and tabs were expanded.  Data now
reaches the DD as coded (only trailing blanks are trimmed); the program
profiles and SQL detection, which read control statements, still see
columns 1-71 only.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.program_profiles import analyze_step
from jclparser.sql_detector import detect_sql_in_job
from jclparser.utils import control_card_text

pytestmark = pytest.mark.unit


def _card(text: str) -> str:
    return text.ljust(80)


def _numbered(text: str, seq: int) -> str:
    return text.ljust(72) + f"{seq:08d}"


def _job(*data: str, program: str = "IEBGENER", dd: str = "SYSUT1") -> str:
    return "\n".join(
        [
            _card("//J1 JOB (A),'X',CLASS=A"),
            _card(f"//S1 EXEC PGM={program}"),
            _card(f"//{dd} DD *"),
            *data,
            _card("/*"),
        ]
    )


def test_columns_72_to_80_and_tabs_are_kept():
    jcl = _job(
        "CUST0001 SMITH JOHN".ljust(71) + "X12345678",
        "RECORD2" + " " * 63 + " Z",
        "A\tB",
    )
    data = parse_jcl(jcl).steps[0].dd_statements[0].inline_data
    assert data == "\n".join(
        [
            "CUST0001 SMITH JOHN".ljust(71) + "X12345678",
            "RECORD2" + " " * 63 + " Z",
            "A\tB",
        ]
    )


def test_trailing_blanks_of_fixed_records_are_trimmed():
    data = parse_jcl(_job(_card("DATA1"))).steps[0].dd_statements[0].inline_data
    assert data == "DATA1"


def test_dd_data_and_dlm_keep_columns_too():
    jcl = "\n".join(
        [
            _card("//J1 JOB (A),'X'"),
            _card("//S1 EXEC PGM=X"),
            _card("//IN DD DATA,DLM=$$"),
            "//NOT JCL".ljust(72) + "00000100",
            _card("$$"),
        ]
    )
    data = parse_jcl(jcl).steps[0].dd_statements[0].inline_data
    assert data == "//NOT JCL".ljust(72) + "00000100"


def test_delimiter_with_sequence_number_still_ends_data():
    jcl = "\n".join(
        [
            _card("//J1 JOB (A),'X'"),
            _card("//S1 EXEC PGM=X"),
            _card("//IN DD *"),
            _numbered("REC1", 10),
            _numbered("/*", 20),
            _card("//S2 EXEC PGM=Y"),
        ]
    )
    job = parse_jcl(jcl)
    assert [s.name for s in job.steps] == ["S1", "S2"]
    assert job.steps[0].dd_statements[0].inline_data == _numbered("REC1", 10)


def test_control_card_text_drops_columns_72_to_80():
    assert control_card_text(_numbered("  DELETE A.B", 1) + "\nSHORT") == (
        "  DELETE A.B\nSHORT"
    )


def test_numbered_idcams_continuation_still_continues():
    # IDCAMS continues a command when "-" is the last character of columns
    # 2-72; the sequence field after it must not hide that.
    jcl = _job(
        _numbered("  DELETE -", 100),
        _numbered("         PROD.OLD.FILE PURGE", 200),
        program="IDCAMS",
        dd="SYSIN",
    )
    analysis = analyze_step(parse_jcl(jcl).steps[0])
    assert analysis is not None
    assert analysis.notes == ["IDCAMS DELETE PROD.OLD.FILE"]


def test_numbered_sort_deck_profile_ignores_sequence_field():
    jcl = _job(
        _numbered("  SORT FIELDS=COPY", 100),
        program="SORT",
        dd="SYSIN",
    )
    analysis = analyze_step(parse_jcl(jcl).steps[0])
    assert analysis is not None
    assert "COPY" in analysis.notes
    assert not any("00000100" in note for note in analysis.notes)


def test_sequence_field_not_scanned_for_sql():
    jcl = _job(
        _numbered("  SELECT A FROM T;", 100),
        " " * 72 + "DROP    ",
        program="DSNTEP2",
        dd="SYSIN",
    )
    results = detect_sql_in_job(parse_jcl(jcl))
    assert results[0].sql_statements == [("SELECT", "DML", "SYSIN")]
