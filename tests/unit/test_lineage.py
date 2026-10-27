"""Tests for cross-job dataset lineage (jclparser.lineage) and `jcl-parser DIR`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jclparser import build_lineage, load_job_stream, parse_jcl
from jclparser.cli import main
from jclparser.lineage import _first_line, dataset_key

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
            ("PROD.LIB(MEM)", "PROD.LIB"),
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
        assert report.external_inputs == ["EXT.MASTER", "PROD.PARMLIB"]
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
        assert "PROC members skipped: libproc.jcl" in out
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
