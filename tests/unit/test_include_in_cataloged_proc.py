"""INCLUDE inside a cataloged (external) PROC is expanded on explosion,
with the job's include loader and JCLLIB order (issue #153)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jclparser import explode_job, parse_jcl
from jclparser.include_loader import DictMemberLoader
from jclparser.proc_loader import DictProcedureLoader

MEMBERS = {"DDS": "//SYSPRINT DD SYSOUT=*\n", "PSTEP": "//E3 EXEC PGM=EX3\n"}
EXTP = (
    "//EXTP PROC\n"
    "//E1 EXEC PGM=EX1\n"
    "//         INCLUDE MEMBER=DDS\n"
    "//E2 EXEC PGM=EX2\n"
    "//         INCLUDE MEMBER=PSTEP\n"
    "// PEND\n"
)
EXPECTED = [
    ("S1.E1", "EX1", ["SYSPRINT"]),
    ("S1.E2", "EX2", []),
    ("S1.E3", "EX3", []),
]


def _shape(job):
    return [(s.name, s.program, [d.name for d in s.dd_statements]) for s in job.steps]


@pytest.mark.unit
class TestIncludeInCatalogedProc:
    def test_dict_loaders(self) -> None:
        job = parse_jcl(
            "//J JOB 1\n//S1 EXEC EXTP\n",
            include_loader=DictMemberLoader(MEMBERS),
            enable_external_procs=False,
        )
        exploded = explode_job(job, proc_loader=DictProcedureLoader({"EXTP": EXTP}))
        assert _shape(exploded) == EXPECTED
        assert exploded.warnings == []
        assert exploded.includes == ["DDS", "PSTEP"]

    def test_explicit_include_loader(self) -> None:
        job = parse_jcl("//J JOB 1\n//S1 EXEC EXTP\n", enable_external_procs=False)
        exploded = explode_job(
            job,
            proc_loader=DictProcedureLoader({"EXTP": EXTP}),
            include_loader=DictMemberLoader(MEMBERS),
        )
        assert _shape(exploded) == EXPECTED

    def test_missing_member_is_a_warning(self) -> None:
        job = parse_jcl(
            "//J JOB 1\n//S1 EXEC EXTP\n",
            include_loader=DictMemberLoader({"DDS": MEMBERS["DDS"]}),
            enable_external_procs=False,
        )
        exploded = explode_job(job, proc_loader=DictProcedureLoader({"EXTP": EXTP}))
        assert _shape(exploded)[:2] == EXPECTED[:2]
        assert any(
            "INCLUDE member PSTEP in PROC EXTP not found" in w
            for w in exploded.warnings
        )

    def test_filesystem_jcllib_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "SYS1.PROCLIB").mkdir()
        (tmp_path / "MY.JCLLIB").mkdir()
        (tmp_path / "SYS1.PROCLIB" / "EXTP.jcl").write_text(EXTP)
        for name, text in MEMBERS.items():
            (tmp_path / "MY.JCLLIB" / f"{name}.jcl").write_text(text)
        monkeypatch.setenv("JCL_PROCLIB_PATH", str(tmp_path))
        job = parse_jcl(
            "//J JOB 1\n//LIB JCLLIB ORDER=(MY.JCLLIB)\n//S1 EXEC EXTP\n",
            proc_base_path=tmp_path,
        )
        exploded = explode_job(job)
        assert _shape(exploded) == EXPECTED
        assert exploded.warnings == []

    def test_in_stream_proc_is_unchanged(self) -> None:
        job = parse_jcl(
            "//J JOB 1\n" + EXTP.replace("EXTP", "P") + "//S1 EXEC P\n",
            include_loader=DictMemberLoader(MEMBERS),
        )
        assert _shape(explode_job(job)) == EXPECTED
