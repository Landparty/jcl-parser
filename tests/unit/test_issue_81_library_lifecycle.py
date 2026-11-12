"""Regression tests for issue #81: dataset lifecycle tracked each PDS member
(and each spelling of a GDG generation) as a dataset of its own.

A DISP applies to the whole library, so ``validate_dataset_lifecycle`` checks
``P.L(M1)``, ``P.L(M2)`` and ``P.L`` as one dataset.  Relative generations of
a GDG stay separate datasets, with ``(+01)`` the same as ``(+1)``.
``analyze_dataset_lifecycle`` keeps keying its log by the name as coded.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.dataset_lifecycle import (
    _library_key,
    analyze_dataset_lifecycle,
    validate_dataset_lifecycle,
)

pytestmark = pytest.mark.unit


def _messages(src: str) -> list[str]:
    return [e.message for e in validate_dataset_lifecycle(parse_jcl(src))]


class TestLibraryKey:
    @pytest.mark.parametrize(
        ("dsn", "key"),
        [
            ("P.L", "P.L"),
            ("P.L(M1)", "P.L"),
            ("&&TEMP(MEM)", "&&TEMP"),
            ("P.L(&MEM)", "P.L"),
            ("G.H(0)", "G.H(0)"),
            ("G.H(00)", "G.H(0)"),
            ("G.H(-0)", "G.H(0)"),
            ("G.H(+1)", "G.H(+1)"),
            ("G.H(+01)", "G.H(+1)"),
            ("G.H(-01)", "G.H(-1)"),
        ],
    )
    def test_key(self, dsn: str, key: str) -> None:
        assert _library_key(dsn) == key


class TestMembersShareTheLibrary:
    def test_new_catlg_of_two_members_is_a_duplicate(self) -> None:
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "//O DD DSN=P.L(M1),DISP=(NEW,CATLG),SPACE=(TRK,(1,1,5))\n"
            "//S2 EXEC PGM=B\n"
            "//O DD DSN=P.L(M2),DISP=(NEW,CATLG),SPACE=(TRK,(1,1,5))\n"
        )
        assert len(msgs) == 1
        assert "'P.L' allocated with DISP=NEW,CATLG in step 'S2'" in msgs[0]
        assert "already cataloged in step 'S1'" in msgs[0]

    def test_member_used_after_library_deleted(self) -> None:
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "//D DD DSN=P.L,DISP=(OLD,DELETE)\n"
            "//S2 EXEC PGM=B\n"
            "//I DD DSN=P.L(M2),DISP=SHR\n"
        )
        assert len(msgs) == 1
        assert "'P.L' opened in step 'S2'" in msgs[0]
        assert "after being deleted in step 'S1'" in msgs[0]

    def test_analyze_keys_unchanged(self) -> None:
        events = analyze_dataset_lifecycle(
            parse_jcl(
                "//J JOB 1\n"
                "//S1 EXEC PGM=A\n"
                "//O DD DSN=P.L(M1),DISP=(NEW,CATLG)\n"
                "//S2 EXEC PGM=B\n"
                "//O DD DSN=P.L(M2),DISP=SHR\n"
            )
        )
        assert list(events) == ["P.L(M1)", "P.L(M2)"]

    def test_member_open_before_library_allocated_later(self) -> None:
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "//I DD DSN=P.L(M1),DISP=OLD\n"
            "//S2 EXEC PGM=B\n"
            "//O DD DSN=P.L(M2),DISP=(NEW,CATLG)\n"
        )
        assert len(msgs) == 1
        assert "before it is allocated in a later step" in msgs[0]

    def test_errors_ordered_by_event_across_members(self) -> None:
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "//O DD DSN=P.L(M1),DISP=(NEW,CATLG)\n"
            "//S2 EXEC PGM=B\n"
            "//O DD DSN=P.L,DISP=(NEW,CATLG)\n"
            "//S3 EXEC PGM=C\n"
            "//O DD DSN=P.L(M3),DISP=(OLD,DELETE)\n"
            "//S4 EXEC PGM=D\n"
            "//I DD DSN=P.L(M4),DISP=SHR\n"
        )
        assert len(msgs) == 2
        assert "step 'S2'" in msgs[0] and "already cataloged" in msgs[0]
        assert "opened in step 'S4'" in msgs[1]

    def test_temporary_member_still_skipped(self) -> None:
        assert (
            _messages(
                "//J JOB 1\n"
                "//S1 EXEC PGM=A\n"
                "//O DD DSN=&&T(M1),DISP=(NEW,CATLG)\n"
                "//S2 EXEC PGM=B\n"
                "//O DD DSN=&&T(M2),DISP=(NEW,CATLG)\n"
            )
            == []
        )


class TestGdgGenerations:
    def test_padded_generation_is_the_same_dataset(self) -> None:
        msgs = _messages(
            "//J JOB 1\n"
            "//S1 EXEC PGM=A\n"
            "//O DD DSN=G.H(+01),DISP=(NEW,CATLG)\n"
            "//S2 EXEC PGM=B\n"
            "//O DD DSN=G.H(+1),DISP=(NEW,CATLG)\n"
        )
        assert len(msgs) == 1
        assert "'G.H(+1)' allocated" in msgs[0]

    def test_current_and_next_generation_not_merged(self) -> None:
        assert (
            _messages(
                "//J JOB 1\n"
                "//S1 EXEC PGM=A\n"
                "//I DD DSN=G.H(0),DISP=SHR\n"
                "//O DD DSN=G.H(+1),DISP=(NEW,CATLG)\n"
                "//S2 EXEC PGM=B\n"
                "//D DD DSN=G.H(0),DISP=(OLD,DELETE)\n"
                "//S3 EXEC PGM=C\n"
                "//I DD DSN=G.H(+1),DISP=SHR\n"
            )
            == []
        )
