"""#179: a deleting job runs after every reader; #180: continued SET feeds INCLUDE."""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.include_loader import DictMemberLoader
from jclparser.lineage import build_lineage

pytestmark = pytest.mark.unit


def _job(name: str, dd: str) -> object:
    return parse_jcl(f"//{name} JOB 1\n//S1 EXEC PGM=X\n{dd}\n")


PRODUCER = "//OUT DD DSN=PROD.EXTRACT,DISP=(NEW,CATLG),UNIT=SYSDA"
DELETER = "//IN DD DSN=PROD.EXTRACT,DISP=(OLD,DELETE)"
READER = "//IN DD DSN=PROD.EXTRACT,DISP=SHR"


class TestDeleteAfterReaders:
    def test_deleter_follows_other_reader(self) -> None:
        report = build_lineage(
            {
                "JA": _job("JA", PRODUCER),
                "JB": _job("JB", DELETER),
                "JC": _job("JC", READER),
            }
        )
        assert report.run_order == ["JA", "JC", "JB"]
        edges = {(d.producer, d.consumer) for d in report.dependencies}
        assert ("JC", "JB") in edges
        assert report.datasets["PROD.EXTRACT"].readers[0].deletes is True
        assert report.to_dict()["datasets"][0]["readers"][0]["deletes"] is True

    def test_two_deleters_reading_each_other_are_a_cycle(self) -> None:
        report = build_lineage(
            {
                "JA": _job("JA", PRODUCER),
                "JB": _job("JB", DELETER),
                "JD": _job("JD", DELETER),
            }
        )
        assert report.run_order == ["JA"]
        assert report.cycles == ["JB", "JD"]

    def test_library_delete_follows_member_reader(self) -> None:
        report = build_lineage(
            {
                "JB": _job("JB", "//L DD DSN=P.LIB,DISP=(OLD,DELETE)"),
                "JC": _job("JC", "//M DD DSN=P.LIB(MEM),DISP=SHR"),
            }
        )
        assert report.run_order == ["JC", "JB"]
        assert [d.datasets for d in report.dependencies] == [("P.LIB(MEM)",)]

    def test_plain_reader_order_unchanged(self) -> None:
        report = build_lineage({"JA": _job("JA", PRODUCER), "JC": _job("JC", READER)})
        assert [(d.producer, d.consumer) for d in report.dependencies] == [("JA", "JC")]


LOADER = DictMemberLoader({"MEMB": "//STEPB EXEC PGM=BBB\n"})
CONTINUED = (
    "//J JOB 1,'X'\n"
    "// SET X=1,\n"
    "//* a comment between\n"
    "//   M=MEMB      the member\n"
    "// INCLUDE MEMBER=&M\n"
    "//S9 EXEC PGM=Z,PARM='&M'\n"
)


class TestContinuedSetIncludeMember:
    def test_symbol_on_continuation_record_expands_include(self) -> None:
        job = parse_jcl(CONTINUED, include_loader=LOADER)
        assert [s.name for s in job.steps] == ["STEPB", "S9"]
        assert job.warnings == []

    def test_undefined_symbol_is_named_in_warning(self) -> None:
        job = parse_jcl(
            CONTINUED.replace("MEMBER=&M", "MEMBER=&Q"), include_loader=LOADER
        )
        assert [s.name for s in job.steps] == ["S9"]
        assert job.warnings == [
            (
                "Line 5: INCLUDE member &Q uses a symbol with no SET value before "
                "it; its statements are missing from the job"
            )
        ]

    def test_missing_resolved_member_is_named(self) -> None:
        job = parse_jcl(CONTINUED.replace("M=MEMB", "M=NOPE"), include_loader=LOADER)
        assert job.warnings == [
            (
                "Line 5: INCLUDE member NOPE (from &M) not found in the JCLLIB / "
                "procedure libraries; its statements are missing from the job"
            )
        ]

    def test_continued_set_feeds_jcllib_order(self) -> None:
        from jclparser._statement_parser import _extract_jcllib_order

        src = "// SET A=1,\n//   LIB=MY.PROCS\n//J JCLLIB ORDER=&LIB\n"
        assert _extract_jcllib_order(src) == ["MY.PROCS"]
