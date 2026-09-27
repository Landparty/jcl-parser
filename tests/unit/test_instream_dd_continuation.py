"""A DD * / DD DATA statement continued onto further records is read whole.

The pre-merge classification pass decided "in-stream data starts here" from
the DD's first record, so ``//SYSIN DD DATA,`` / ``//   DLM=$$`` swallowed the
continuation record as data, lost ``DLM=`` and ran the data to end of file,
taking every later statement with it.
"""

import pytest

from jclparser import parse_jcl


def _dds(jcl: str):
    job = parse_jcl(jcl)
    return [(d.name, d.parameters, d.inline_data) for d in job.steps[0].dd_statements]


HEAD = "//J        JOB (A),'B'\n//S        EXEC PGM=SORT\n"


@pytest.mark.unit
class TestInstreamDdContinuation:
    def test_dd_data_with_dlm_on_continuation(self):
        jcl = HEAD + (
            "//SYSIN    DD DATA,\n"
            "//            DLM=$$\n"
            " SORT FIELDS=COPY\n"
            "//NOTJCL\n"
            "$$\n"
            "//OUT      DD SYSOUT=*\n"
        )
        assert _dds(jcl) == [
            ("SYSIN", {"DATA": True, "DLM": "$$"}, " SORT FIELDS=COPY\n//NOTJCL"),
            ("OUT", {"SYSOUT": "*"}, None),
        ]

    def test_dd_star_with_dlm_on_continuation_after_comment(self):
        jcl = HEAD + (
            "//SYSIN    DD *,        FIRST RECORD COMMENT\n"
            "//            DLM=@@\n"
            " SORT FIELDS=COPY\n"
            "/* NOT THE END\n"
            "@@\n"
            "//OUT      DD SYSOUT=*\n"
        )
        assert _dds(jcl) == [
            (
                "SYSIN",
                {"_pos_0": "*", "DLM": "@@"},
                " SORT FIELDS=COPY\n/* NOT THE END",
            ),
            ("OUT", {"SYSOUT": "*"}, None),
        ]

    def test_dd_star_with_dcb_over_three_records(self):
        jcl = HEAD + (
            "//SYSIN    DD *,\n"
            "//            DCB=(RECFM=FB,\n"
            "//            LRECL=80)\n"
            " SORT FIELDS=COPY\n"
            "/*\n"
            "//OUT      DD SYSOUT=*\n"
        )
        assert _dds(jcl) == [
            (
                "SYSIN",
                {"_pos_0": "*", "DCB": ["RECFM=FB", "LRECL=80"]},
                " SORT FIELDS=COPY",
            ),
            ("OUT", {"SYSOUT": "*"}, None),
        ]

    def test_dlm_in_comment_field_is_ignored(self):
        jcl = HEAD + (
            "//IN       DD DSN=A.B,DISP=SHR    NOTE DLM=XX\n//OUT      DD SYSOUT=*\n"
        )
        assert [name for name, _, _ in _dds(jcl)] == ["IN", "OUT"]

    def test_single_record_forms_unchanged(self):
        jcl = (
            HEAD + "//SYSIN    DD *,DLM=$$\n SORT FIELDS=COPY\n$$\n//OUT DD SYSOUT=*\n"
        )
        assert _dds(jcl)[0][2] == " SORT FIELDS=COPY"
        assert _dds(jcl)[1][0] == "OUT"
