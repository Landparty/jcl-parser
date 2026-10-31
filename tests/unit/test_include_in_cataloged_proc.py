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


SYMP = (
    "//SYMP PROC MEM=DDSET1\n"
    "//STEP2 EXEC PGM=IEFBR14\n"
    "// INCLUDE MEMBER=&MEM\n"
    "// PEND\n"
)
SYM_MEMBERS = {
    "DDSET1": "//OUT1 DD DSN=X.Y1,DISP=SHR\n",
    "DDSET3": "//OUT3 DD DSN=X.Y3,DISP=SHR\n",
}


def _explode_sym(job_text: str, procs: dict[str, str] | None = None):
    job = parse_jcl(
        job_text,
        include_loader=DictMemberLoader(SYM_MEMBERS),
        enable_external_procs=False,
    )
    return explode_job(job, proc_loader=DictProcedureLoader(procs or {"SYMP": SYMP}))


@pytest.mark.unit
class TestSymbolicIncludeInCatalogedProc:
    """INCLUDE MEMBER=&SYM in a cataloged PROC resolves &SYM in the
    scope of each call: EXEC value, PROC default, then SET (issue #160)."""

    def test_exec_override(self) -> None:
        exploded = _explode_sym("//J JOB 1\n//RUN EXEC SYMP,MEM=DDSET3\n")
        assert _shape(exploded) == [("RUN.STEP2", "IEFBR14", ["OUT3"])]
        assert exploded.warnings == []
        assert exploded.includes == ["DDSET3"]

    def test_proc_default(self) -> None:
        exploded = _explode_sym("//J JOB 1\n//RUN EXEC SYMP\n")
        assert _shape(exploded) == [("RUN.STEP2", "IEFBR14", ["OUT1"])]
        assert exploded.warnings == []

    def test_each_call_uses_its_own_value(self) -> None:
        exploded = _explode_sym(
            "//J JOB 1\n//A EXEC SYMP,MEM=DDSET3\n//B EXEC SYMP\n"
            "//C EXEC SYMP,MEM=DDSET3\n"
        )
        assert [d for _, _, d in _shape(exploded)] == [["OUT3"], ["OUT1"], ["OUT3"]]
        assert exploded.includes == ["DDSET3", "DDSET1"]

    def test_job_set_symbol(self) -> None:
        proc = SYMP.replace("&MEM", "&INC")
        exploded = _explode_sym(
            "//J JOB 1\n// SET INC=DDSET3\n//RUN EXEC SYMP\n", {"SYMP": proc}
        )
        assert _shape(exploded) == [("RUN.STEP2", "IEFBR14", ["OUT3"])]

    def test_set_inside_proc(self) -> None:
        proc = (
            "//SYMP PROC\n// SET INC=DDSET3\n//STEP2 EXEC PGM=IEFBR14\n"
            "// INCLUDE MEMBER=&INC\n// PEND\n"
        )
        exploded = _explode_sym("//J JOB 1\n//RUN EXEC SYMP\n", {"SYMP": proc})
        assert _shape(exploded) == [("RUN.STEP2", "IEFBR14", ["OUT3"])]

    def test_nested_call_override(self) -> None:
        outer = "//OUTER PROC\n//IN EXEC SYMP,MEM=DDSET3\n// PEND\n"
        exploded = _explode_sym(
            "//J JOB 1\n//RUN EXEC OUTER\n", {"SYMP": SYMP, "OUTER": outer}
        )
        assert _shape(exploded) == [("RUN.IN.STEP2", "IEFBR14", ["OUT3"])]

    def test_missing_resolved_member_is_one_warning(self) -> None:
        exploded = _explode_sym(
            "//J JOB 1\n//A EXEC SYMP,MEM=NOPE\n//B EXEC SYMP,MEM=NOPE\n"
        )
        assert exploded.warnings == [
            (
                "INCLUDE member NOPE in PROC SYMP not found; "
                "its statements are missing from the exploded job"
            )
        ]

    def test_undefined_symbol_is_a_warning(self) -> None:
        proc = SYMP.replace("&MEM", "&UNDEF")
        exploded = _explode_sym("//J JOB 1\n//RUN EXEC SYMP\n", {"SYMP": proc})
        assert any("INCLUDE member &UNDEF" in w for w in exploded.warnings)

    def test_filesystem_issue_repro(self, tmp_path: Path) -> None:
        lib = tmp_path / "MY.PROCLIB"
        lib.mkdir()
        (lib / "MYPROC.jcl").write_text(SYMP.replace("SYMP", "MYPROC"))
        for name, text in SYM_MEMBERS.items():
            (lib / f"{name}.jcl").write_text(text)
        job = parse_jcl(
            "//J      JOB 1\n//       JCLLIB ORDER=(MY.PROCLIB)\n"
            "//RUN    EXEC MYPROC,MEM=DDSET3\n",
            proc_base_path=tmp_path,
        )
        exploded = explode_job(job)
        assert _shape(exploded) == [("RUN.STEP2", "IEFBR14", ["OUT3"])]
        assert exploded.warnings == []
