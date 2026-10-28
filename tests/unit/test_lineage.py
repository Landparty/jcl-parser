"""Tests for cross-job dataset lineage (jclparser.lineage) and `jcl-parser DIR`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jclparser import build_lineage, load_job_stream, parse_jcl
from jclparser.cli import main
from jclparser.lineage import _first_line, dataset_key, library_of

EXTRACT = """\
//EXTRACT  JOB (ACCT),'PGMR'
//S1       EXEC PGM=IEBGENER
//SYSUT1   DD DSN=EXT.MASTER,DISP=SHR
//SYSUT2   DD DSN=PROD.RAW,DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(1,1))
//S2       EXEC PGM=IEBGENER
//SYSUT1   DD DSN=*.S1.SYSUT2,DISP=SHR
//SYSUT2   DD DSN=PROD.HIST(+1),DISP=(NEW,CATLG)
//TEMP     DD DSN=&&WORK,DISP=(NEW,PASS)
"""

SUMMARY = """\
//SUMMARY  JOB (ACCT),'PGMR'
//MYPROC   PROC HLQ=PROD
//PS1      EXEC PGM=SORT
//SORTIN   DD DSN=&HLQ..RAW,DISP=SHR
//SORTIN2  DD DSN=&HLQ..HIST(0),DISP=SHR
//SORTOUT  DD DSN=&HLQ..SUMMARY,DISP=(NEW,CATLG)
//         PEND
//S1       EXEC MYPROC
"""

REPORT = """\
//REPORT   JOB (ACCT),'PGMR'
//S1       EXEC PGM=REPORTER
//IN       DD DSN=PROD.SUMMARY,DISP=SHR
//LIB      DD DSN=PROD.PARMLIB(RPT),DISP=SHR
//OUT      DD SYSOUT=*
//NULL     DD DSN=NULLFILE
"""

PROC_MEMBER = """\
//LIBPROC  PROC
//P1       EXEC PGM=IEFBR14
"""

MISSING_PROC = """\
//BROKEN   JOB (ACCT),'PGMR'
//S1       EXEC NOSUCHPR
//S1.DD1   DD DSN=PROD.OVERRIDE,DISP=(NEW,CATLG)
"""


@pytest.fixture
def library(tmp_path: Path) -> Path:
    (tmp_path / "extract.jcl").write_text(EXTRACT)
    (tmp_path / "summary.jcl").write_text(SUMMARY)
    (tmp_path / "report.jcl").write_text(REPORT)
    (tmp_path / "libproc.jcl").write_text(PROC_MEMBER)
    (tmp_path / "readme.txt").write_text("not jcl at all\n")
    (tmp_path / ".hidden.jcl").write_text(EXTRACT)
    (tmp_path / "sub").mkdir()
    return tmp_path


@pytest.mark.unit
class TestDatasetKey:
    @pytest.mark.parametrize(
        ("coded", "key"),
        [
            ("prod.raw", "PROD.RAW"),
            ("PROD.LIB(MEM)", "PROD.LIB(MEM)"),
            ("prod.lib(mem)", "PROD.LIB(MEM)"),
            ("G.H(-1)", "G.H"),
            ("G.H(+1)", "G.H"),
            ("G.H(0)", "G.H"),
            (" A.B ", "A.B"),
        ],
    )
    def test_key(self, coded, key):
        assert dataset_key(coded) == key


@pytest.mark.unit
class TestLoadJobStream:
    def test_classifies_files(self, library):
        stream = load_job_stream(library)
        assert list(stream.jobs) == ["extract.jcl", "report.jcl", "summary.jcl"]
        assert stream.procedures == ["libproc.jcl"]
        assert list(stream.errors) == ["readme.txt"]
        assert "\n" not in stream.errors["readme.txt"]
        assert stream.warnings == {}

    def test_jobs_are_exploded(self, library):
        job = load_job_stream(library).jobs["summary.jcl"]
        assert [s.name for s in job.steps] == ["S1.PS1"]

    def test_explode_false_keeps_proc_calls(self, library):
        job = load_job_stream(library, explode=False).jobs["summary.jcl"]
        assert job.steps[0].procedure == "MYPROC"

    def test_glob_pattern_and_recursion(self, library):
        (library / "sub" / "deep.jcl").write_text(REPORT.replace("REPORT ", "DEEP   "))
        assert list(load_job_stream(library, "*.txt").jobs) == []
        assert "sub/deep.jcl" in load_job_stream(library, "**/*.jcl").jobs

    def test_failed_explosion_is_a_warning(self, tmp_path):
        (tmp_path / "broken.jcl").write_text(MISSING_PROC)
        stream = load_job_stream(tmp_path)
        assert "broken.jcl" in stream.jobs
        assert stream.warnings["broken.jcl"].startswith("not exploded: ")
        # the unexploded job's PROC-step override still counts
        lineage = stream.lineage()
        assert lineage.datasets["PROD.OVERRIDE"].writer_jobs == ["broken.jcl"]

    def test_not_a_directory(self, tmp_path):
        f = tmp_path / "x.jcl"
        f.write_text(REPORT)
        with pytest.raises(NotADirectoryError):
            load_job_stream(f)

    def test_error_message_is_one_bounded_line(self):
        assert _first_line("a\nb") == "a"
        assert _first_line("") == ""
        cut = _first_line("x" * 500)
        assert len(cut) == 200
        assert cut.endswith("...")


@pytest.mark.unit
class TestBuildLineage:
    @pytest.fixture
    def report(self, library):
        return load_job_stream(library).lineage()

    def test_dependencies(self, report):
        edges = {(d.producer, d.consumer): d.datasets for d in report.dependencies}
        assert edges == {
            ("extract.jcl", "summary.jcl"): ("PROD.HIST", "PROD.RAW"),
            ("summary.jcl", "report.jcl"): ("PROD.SUMMARY",),
        }

    def test_run_order(self, report):
        assert report.run_order == ["extract.jcl", "summary.jcl", "report.jcl"]
        assert report.cycles == []

    def test_external_inputs_and_final_outputs(self, report):
        assert report.external_inputs == ["EXT.MASTER", "PROD.PARMLIB(RPT)"]
        assert report.final_outputs == []

    def test_uses_record_where_and_how(self, report):
        raw = report.datasets["PROD.RAW"]
        assert raw.writer_jobs == ["extract.jcl"]
        # the backward reference DSN=*.S1.SYSUT2 is a read of PROD.RAW too
        assert [(u.job, u.step, u.dd) for u in raw.readers] == [
            ("extract.jcl", "S2", "SYSUT1"),
            ("summary.jcl", "S1.PS1", "SORTIN"),
        ]
        (writer,) = raw.writers
        assert writer.disp == "NEW"
        assert writer.line_number == 4
        hist = report.datasets["PROD.HIST"]
        assert [u.dataset for u in hist.writers + hist.readers] == [
            "PROD.HIST(+1)",
            "PROD.HIST(0)",
        ]

    def test_temporary_sysout_and_nullfile_are_left_out(self, report):
        assert not any(k.startswith("&&") for k in report.datasets)
        assert "NULLFILE" not in report.datasets

    def test_delete_is_a_read_and_scratch_is_ignored(self):
        creator = parse_jcl(
            "//A JOB\n//S EXEC PGM=X\n//O DD DSN=D.ONE,DISP=(NEW,CATLG)\n"
        )
        cleaner = parse_jcl(
            "//B JOB\n//S EXEC PGM=IEFBR14\n//D DD DSN=D.ONE,DISP=(MOD,DELETE)\n"
            "//W DD DSN=D.WORK,DISP=(NEW,DELETE)\n"
        )
        report = build_lineage({"B": cleaner, "A": creator})
        assert report.datasets["D.ONE"].writer_jobs == ["A"]
        assert report.datasets["D.ONE"].reader_jobs == ["B"]
        assert report.run_order == ["A", "B"]
        assert not report.datasets["D.WORK"].writers
        assert not report.datasets["D.WORK"].readers

    def test_cycle(self):
        a = parse_jcl(
            "//A JOB\n//S EXEC PGM=X\n//I DD DSN=D.TWO,DISP=SHR\n"
            "//O DD DSN=D.ONE,DISP=(NEW,CATLG)\n"
        )
        b = parse_jcl(
            "//B JOB\n//S EXEC PGM=X\n//I DD DSN=D.ONE,DISP=SHR\n"
            "//O DD DSN=D.TWO,DISP=(MOD,CATLG)\n"
        )
        c = parse_jcl("//C JOB\n//S EXEC PGM=X\n//I DD DSN=D.TWO,DISP=OLD\n")
        report = build_lineage({"A": a, "B": b, "C": c})
        assert report.run_order == []
        assert report.cycles == ["A", "B", "C"]

    def test_to_dict_is_json(self, report):
        doc = report.to_dict()
        assert json.loads(json.dumps(doc)) == doc
        assert doc["run_order"] == report.run_order
        assert doc["dependencies"][0] == {
            "producer": "extract.jcl",
            "consumer": "summary.jcl",
            "datasets": ["PROD.HIST", "PROD.RAW"],
        }

    def test_to_dot(self, report):
        dot = report.to_dot()
        assert dot.startswith("digraph lineage {\n")
        assert '"extract.jcl" -> "summary.jcl" [label="PROD.HIST\\nPROD.RAW"];' in dot
        assert dot.endswith("}\n")

    def test_to_dot_escapes_quotes(self):
        job = parse_jcl("//A JOB\n//S EXEC PGM=X\n")
        assert '"a\\"b"' in build_lineage({'a"b': job}).to_dot()

    def test_to_mermaid(self, report):
        mermaid = report.to_mermaid()
        assert mermaid.startswith("flowchart LR\n")
        assert '  j0["extract.jcl"]' in mermaid
        assert '  j0 -->|"PROD.HIST<br>PROD.RAW"| j2' in mermaid


@pytest.mark.unit
class TestCLI:
    def test_text_report(self, library, capsys):
        assert main([str(library)]) == 0
        out = capsys.readouterr().out
        assert "Run order: extract.jcl -> summary.jcl -> report.jcl" in out
        assert "  summary.jcl -> report.jcl: PROD.SUMMARY" in out
        assert "PROC members (used to explode the jobs): libproc.jcl" in out
        assert "Not parsed: readme.txt:" in out
        assert "External inputs" in out

    def test_json(self, library, capsys):
        assert main([str(library), "lineage", "--json"]) == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["job_names"]["summary.jcl"] == "SUMMARY"
        assert doc["jobs"] == ["extract.jcl", "report.jcl", "summary.jcl"]
        assert doc["run_order"] == ["extract.jcl", "summary.jcl", "report.jcl"]

    @pytest.mark.parametrize("fmt", ["dot", "mermaid"])
    def test_graph_formats(self, library, capsys, fmt):
        assert main([str(library), "lineage", fmt]) == 0
        out = capsys.readouterr().out
        assert out.startswith("digraph" if fmt == "dot" else "flowchart")

    def test_glob_flag(self, library, capsys):
        assert main([str(library), "--glob", "report.jcl"]) == 0
        assert "Jobs: 1" in capsys.readouterr().out

    def test_no_dependencies_and_cycle_text(self, tmp_path, capsys):
        (tmp_path / "a.jcl").write_text(
            "//A JOB\n//S EXEC PGM=X\n//I DD DSN=D.TWO,DISP=SHR\n"
            "//O DD DSN=D.ONE,DISP=(NEW,CATLG)\n"
        )
        (tmp_path / "b.jcl").write_text(
            "//B JOB\n//S EXEC PGM=X\n//I DD DSN=D.ONE,DISP=SHR\n"
            "//O DD DSN=D.TWO,DISP=(NEW,CATLG)\n"
        )
        (tmp_path / "c.jcl").write_text("//C JOB\n//S EXEC PGM=X\n")
        assert main([str(tmp_path), "--glob", "c.jcl"]) == 0
        out = capsys.readouterr().out
        assert "Run order: c.jcl" in out
        assert "  (none)" in out
        assert main([str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "Not orderable (dependency cycle): a.jcl, b.jcl" in out

    def test_unknown_format(self, library, capsys):
        assert main([str(library), "lineage", "png"]) == 1
        assert "unknown lineage format" in capsys.readouterr().err

    def test_job_query_on_directory(self, library, capsys):
        assert main([str(library), "steps"]) == 1
        assert "only 'lineage'" in capsys.readouterr().err

    def test_directory_without_jobs(self, tmp_path, capsys):
        (tmp_path / "junk.txt").write_text("nope\n")
        assert main([str(tmp_path)]) == 1
        err = capsys.readouterr().err
        assert err.startswith("Error: no JCL jobs found")
        assert "junk.txt" in err


# --- PDS members (issue #145) ----------------------------------------------

COMPILE = """\
//{name}  JOB (ACCT),'PGMR'
//PRECOMP  EXEC PGM=DSNHPC
//DBRMLIB  DD DSN=BANK.DBRMLIB({prog}),DISP=(NEW,CATLG)
//BIND     EXEC PGM=IKJEFT01
//DBRMLIB  DD DSN=BANK.DBRMLIB,DISP=SHR
"""


def _job(text: str):
    return parse_jcl(text)


@pytest.mark.unit
class TestPdsMembers:
    def test_library_of(self):
        assert library_of("P.L(M)") == "P.L"
        assert library_of("P.L") == "P.L"

    def test_compile_jobs_sharing_a_library_do_not_form_a_cycle(self):
        jobs = {
            f"{n}.jcl": _job(COMPILE.format(name=n.ljust(8), prog=p))
            for n, p in (("JOBA", "PROGA"), ("JOBB", "PROGB"))
        }
        report = build_lineage(jobs)
        assert report.dependencies == []
        assert report.cycles == []
        assert report.run_order == ["JOBA.jcl", "JOBB.jcl"]

    def test_library_reader_that_writes_no_member_still_depends(self):
        compile_job = _job(COMPILE.format(name="JOBA    ", prog="PROGA"))
        runner = _job(
            "//RUN JOB\n//S EXEC PGM=X\n//STEPLIB DD DSN=BANK.DBRMLIB,DISP=SHR\n"
        )
        report = build_lineage({"a": compile_job, "run": runner})
        assert [(d.producer, d.consumer, d.datasets) for d in report.dependencies] == [
            ("a", "run", ("BANK.DBRMLIB(PROGA)",))
        ]

    def test_member_write_feeds_only_that_member(self):
        writer = _job("//W JOB\n//S EXEC PGM=X\n//O DD DSN=P.L(M1),DISP=(NEW,CATLG)\n")
        reader1 = _job("//R1 JOB\n//S EXEC PGM=X\n//I DD DSN=P.L(M1),DISP=SHR\n")
        reader2 = _job("//R2 JOB\n//S EXEC PGM=X\n//I DD DSN=P.L(M2),DISP=SHR\n")
        report = build_lineage({"w": writer, "r1": reader1, "r2": reader2})
        assert [(d.producer, d.consumer, d.datasets) for d in report.dependencies] == [
            ("w", "r1", ("P.L(M1)",))
        ]
        assert report.external_inputs == ["P.L(M2)"]
        assert report.final_outputs == []
        assert report.cycles == []

    def test_whole_library_write_feeds_member_reads(self):
        writer = _job("//W JOB\n//S EXEC PGM=X\n//O DD DSN=P.L,DISP=(NEW,CATLG)\n")
        reader = _job("//R JOB\n//S EXEC PGM=X\n//I DD DSN=P.L(M2),DISP=SHR\n")
        report = build_lineage({"w": writer, "r": reader})
        assert [(d.producer, d.consumer, d.datasets) for d in report.dependencies] == [
            ("w", "r", ("P.L(M2)",))
        ]
        assert report.external_inputs == []
        assert report.final_outputs == []

    def test_member_write_feeds_whole_library_read(self):
        writer = _job("//W JOB\n//S EXEC PGM=X\n//O DD DSN=P.L(M1),DISP=(NEW,CATLG)\n")
        reader = _job("//R JOB\n//S EXEC PGM=X\n//STEPLIB DD DSN=P.L,DISP=SHR\n")
        report = build_lineage({"w": writer, "r": reader})
        assert [(d.producer, d.consumer) for d in report.dependencies] == [("w", "r")]
        assert report.run_order == ["w", "r"]

    def test_independent_member_compiles_are_ordered(self):
        # Each job writes and then reads back only its own member.
        text = (
            "//{n} JOB\n//S1 EXEC PGM=X\n"
            "//O DD DSN=BANK.LOAD({n}),DISP=(NEW,CATLG)\n"
            "//S2 EXEC PGM=Y\n//I DD DSN=BANK.LOAD({n}),DISP=SHR\n"
        )
        jobs = {n: _job(text.format(n=n)) for n in ("JA", "JB", "JC")}
        report = build_lineage(jobs)
        assert report.dependencies == []
        assert report.cycles == []
        assert report.run_order == ["JA", "JB", "JC"]


# --- PROC members in the directory (issue #144) ------------------------------

CALLER = """\
//CALLER   JOB (ACCT),'PGMR'
//S1       EXEC COMPILE,PROG=PAY
"""

COMPILE_PROC = """\
//COMPILE  PROC PROG=X
//C        EXEC PGM=IGYCRCTL
//SYSLIN   DD DSN=BANK.OBJ(&PROG),DISP=(NEW,CATLG)
"""

READER = """\
//READER   JOB (ACCT),'PGMR'
//S1       EXEC PGM=IEWL
//OBJ      DD DSN=BANK.OBJ(PAY),DISP=SHR
"""


@pytest.mark.unit
class TestDirectoryProcMembers:
    @pytest.mark.parametrize("member", ["compile.prc", "COMPILE.proc", "COMPILE"])
    def test_jobs_are_exploded_with_directory_members(self, tmp_path, member):
        (tmp_path / "caller.jcl").write_text(CALLER)
        (tmp_path / "reader.jcl").write_text(READER)
        (tmp_path / member).write_text(COMPILE_PROC)
        stream = load_job_stream(tmp_path)
        assert stream.procedures == [member]
        assert stream.warnings == {}
        assert [s.name for s in stream.jobs["caller.jcl"].steps] == ["S1.C"]
        report = stream.lineage()
        assert [(d.producer, d.consumer) for d in report.dependencies] == [
            ("caller.jcl", "reader.jcl")
        ]

    def test_member_found_by_member_name_not_proc_label(self, tmp_path):
        (tmp_path / "caller.jcl").write_text(CALLER)
        (tmp_path / "compile.prc").write_text(
            COMPILE_PROC.replace("//COMPILE  PROC", "//OTHER    PROC")
        )
        stream = load_job_stream(tmp_path)
        assert stream.warnings == {}
        assert [s.name for s in stream.jobs["caller.jcl"].steps] == ["S1.C"]

    def test_in_stream_proc_wins_over_member(self, tmp_path):
        inline = (
            "//CALLER   JOB (ACCT),'PGMR'\n"
            "//COMPILE  PROC\n//INL      EXEC PGM=IEFBR14\n//         PEND\n"
            "//S1       EXEC COMPILE\n"
        )
        (tmp_path / "caller.jcl").write_text(inline)
        (tmp_path / "compile.prc").write_text(COMPILE_PROC)
        job = load_job_stream(tmp_path).jobs["caller.jcl"]
        assert [s.name for s in job.steps] == ["S1.INL"]
