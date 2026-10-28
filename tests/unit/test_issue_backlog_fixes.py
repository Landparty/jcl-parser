"""Regression tests for the 2026-10-28 issue backlog sweep.

#104 exception pickling, #105 omitted DISP, #112 binder INCLUDE members,
#113 IEHPROGM continuations, #114 UNIT=(SYSDA,...), #125 binary sources,
#131 --profile output, #132 sources read once / stdin, #133 query words vs
step and DD names.
"""

from __future__ import annotations

import copy
import io
import json
import pickle
import sys
import tracemalloc
from pathlib import Path

import pytest

from jclparser import parse_jcl, validate_jcl
from jclparser.cli import main
from jclparser.errors import (
    CircularProcedureError,
    ExplosionDepthError,
    JCLParseError,
    JCLSyntaxError,
    ProcedureNotFoundError,
    UndefinedSymbolError,
)
from jclparser.lint import lint_job
from jclparser.profiling import ProfilerContext
from jclparser.program_profiles import analyze_step

pytestmark = pytest.mark.unit


# --- #104 -----------------------------------------------------------------


ERRORS = [
    JCLParseError("boom", line_number=3, context="ctx", column_number=4),
    JCLSyntaxError("bad", 7),
    CircularProcedureError("A", ["A", "B", "A"]),
    ExplosionDepthError(11, 10, ["A", "B"]),
    UndefinedSymbolError("HLQ", line_number=3, source_text="&HLQ..X"),
    ProcedureNotFoundError("NOPROC", line_number=4),
]


@pytest.mark.parametrize("error", ERRORS, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize(
    "roundtrip",
    [copy.deepcopy, lambda e: pickle.loads(pickle.dumps(e))],
    ids=["deepcopy", "pickle"],
)
def test_errors_round_trip(error, roundtrip):
    clone = roundtrip(error)
    assert type(clone) is type(error)
    assert str(clone) == str(error)
    assert clone.args == error.args
    assert clone.__dict__ == error.__dict__


def test_include_note_survives_pickle():
    error = JCLSyntaxError("bad", 7)
    error.include_note = "INCLUDE member M, line 2"
    clone = pickle.loads(pickle.dumps(error))
    assert clone.include_note == "INCLUDE member M, line 2"


# --- #105 -----------------------------------------------------------------


def _dds(text: str):
    return parse_jcl("//J JOB\n//S1 EXEC PGM=SORT\n" + text).steps[0].dd_statements


def test_omitted_disp_is_new():
    (dd,) = _dds("//SORTOUT DD DSN=&&SORTED,UNIT=SYSDA,SPACE=(CYL,5)\n")
    assert dd.is_output()
    assert not dd.is_input()


def test_omitted_disp_step_outputs():
    job = parse_jcl("//J JOB\n//S1 EXEC PGM=X\n//O DD DSN=A.B,SPACE=(CYL,5)\n")
    assert job.steps[0].get_output_datasets() == ["A.B"]


@pytest.mark.parametrize(
    "dd",
    [
        "//A DD DUMMY\n",
        "//A DD DUMMY,DSN=A.B\n",
        "//A DD SYSOUT=*\n",
        "//A DD DSN=NULLFILE\n",
        "//A DD DSN=*.S0.DD\n",
        "//A DD *\nDATA\n/*\n",
    ],
)
def test_omitted_disp_without_new_data(dd):
    (parsed,) = _dds(dd)
    assert not parsed.is_output()


# --- #112 / #113 ------------------------------------------------------------


def _analyze(program: str, sysin: str):
    job = parse_jcl(f"//J JOB\n//S EXEC PGM={program}\n//SYSIN DD *\n{sysin}/*\n")
    return analyze_step(job.steps[0])


def test_binder_counts_include_members():
    result = _analyze("IEWL", " INCLUDE OBJLIB(PAYROLL,PAYCALC,PAYTAX)\n")
    assert result.summary == "IEWL: link-edits 3 object module(s)"
    assert result.notes == ["INCLUDE OBJLIB(PAYROLL,PAYCALC,PAYTAX)"]


def test_binder_counts_mixed_includes():
    result = _analyze("IEWL", " INCLUDE SYSLIB(A),OBJ\n INCLUDE OBJ2\n")
    assert result.summary == "IEWL: link-edits 3 object module(s)"


def test_iehprogm_scratch_continued_on_next_card():
    sysin = (
        "  SCRATCH VOL=3390=VOL001,".ljust(71)
        + "X".ljust(9)
        + "\n"
        + "               DSNAME=PROD.OLD.FILE\n"
        + "  UNCATLG DSNAME=PROD.OLD.FILE\n"
    )
    result = _analyze("IEHPROGM", sysin)
    assert result.notes == ["SCRATCH PROD.OLD.FILE", "UNCATLG PROD.OLD.FILE"]
    assert [e.action for e in result.dataset_events] == ["DELETE", "UNCATALOG"]


def test_iehprogm_trailing_comma_continuation_and_catlg():
    sysin = (
        "  CATLG VOL=3390=V1,\n"
        "        DSNAME=NEW.FILE\n"
        "  RENAME DSNAME=A.B,VOL=3390=V1,NEWNAME=A.C\n"
        "  BLDG INDEX=G.H,ENTRIES=5\n"
        "  CONNECT HIGHQUAL=X,VOL=3390=V1\n"
    )
    result = _analyze("IEHPROGM", sysin)
    assert result.notes == [
        "CATLG NEW.FILE",
        "RENAME A.B",
        "BLDG (build generation data group index)",
        "CONNECT (add user catalog connection)",
    ]
    assert [e.action for e in result.dataset_events] == ["ALLOCATE"]


# --- #114 -------------------------------------------------------------------


@pytest.mark.parametrize("unit", ["SYSDA", "(SYSDA,2)", "(SYSDA,,DEFER)", "sysda"])
def test_lint_002_flags_sysda_with_subparameters(unit):
    job = parse_jcl(f"//J JOB\n//S EXEC PGM=X\n//A DD DSN=A.B,UNIT={unit},DISP=SHR\n")
    assert any(e.error_code == "JCL-LINT-002" for e in lint_job(job))


def test_lint_002_ignores_other_units():
    job = parse_jcl("//J JOB\n//S EXEC PGM=X\n//A DD DSN=A.B,UNIT=(3390,2),DISP=SHR\n")
    assert not any(e.error_code == "JCL-LINT-002" for e in lint_job(job))


# --- #125 -------------------------------------------------------------------

JCL = b"//J1 JOB\n//S1 EXEC PGM=A\n"


def test_parse_binary_file_object():
    job = parse_jcl(io.BytesIO(JCL))
    assert job.name == "J1"
    assert [s.name for s in job.steps] == ["S1"]


def test_validate_binary_file_object():
    assert validate_jcl(io.BytesIO(JCL)) == []


def test_binary_source_decoding_fallbacks(tmp_path):
    bom_crlf = io.BytesIO(b"\xef\xbb\xbf//J1 JOB\r\n//S1 EXEC PGM=A\r\n")
    assert [s.name for s in parse_jcl(bom_crlf).steps] == ["S1"]
    cp1252 = io.BytesIO(b"//J1 JOB 'CAF\xc9'\n//S1 EXEC PGM=A\n")  # not UTF-8
    assert parse_jcl(cp1252).name == "J1"
    path = tmp_path / "x.jcl"
    path.write_bytes(JCL)
    with open(path, "rb") as fh:
        assert parse_jcl(fh).name == "J1"


# --- #132 -------------------------------------------------------------------

BAD = "//J1 JOB (A),'X'\nJUNK ONE\nJUNK TWO\n"


def test_validate_reads_a_path_once(tmp_path, monkeypatch):
    path = tmp_path / "x.jcl"
    path.write_text(BAD)
    from jclparser import utils

    calls = []
    real = utils._read_file_with_fallback

    def counting(p, *a, **kw):
        calls.append(p)
        return real(p, *a, **kw)

    monkeypatch.setattr(utils, "_read_file_with_fallback", counting)
    errors = validate_jcl(path)
    assert len(calls) == 1
    assert {e.line_number for e in errors} >= {2, 3}


class _Stdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


def test_cli_reads_stdin_dash(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Stdin(b"//J1 JOB\n//S1 EXEC PGM=A\n"))
    assert main(["-", "steps"]) == 0
    assert "S1" in capsys.readouterr().out


def test_cli_validate_stdin_reports_every_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Stdin(BAD.encode()))
    assert main(["-", "--validate", "--json"]) == 1
    lines = {e["line"] for e in json.loads(capsys.readouterr().out)["errors"]}
    assert {2, 3} <= lines


def test_cli_detect_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Stdin(b"//P PROC\n//S EXEC PGM=A\n"))
    assert main(["-", "detect", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"file_type": "PROC", "path": "-"}


# --- #131 -------------------------------------------------------------------


@pytest.fixture
def job_file(tmp_path: Path) -> str:
    path = tmp_path / "a.jcl"
    path.write_text("//J1 JOB\n//S1 EXEC PGM=A\n//DD1 DD DSN=A.B,DISP=SHR\n")
    return str(path)


def test_profile_text_output(job_file, capsys):
    assert main([job_file, "--profile", "--profile-top-n", "2"]) == 0
    out = capsys.readouterr().out
    assert "J1" in out
    assert "Profiling:" in out
    assert "Peak memory:" in out
    assert "Top functions" in out


@pytest.mark.parametrize("query", [[], ["metrics"], ["S1"]])
def test_profile_json_dict_views(job_file, capsys, query):
    assert main([job_file, *query, "--json", "--profile"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert "wall_clock_s" in doc["profiling"]


def test_profile_json_list_view_is_wrapped(job_file, capsys):
    assert main([job_file, "steps", "--json", "--profile"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["result"][0]["name"] == "S1"
    assert "profiling" in doc


def test_profile_output_written(job_file, tmp_path, capsys):
    prof = tmp_path / "x.prof"
    assert main([job_file, "--profile", "--profile-output", str(prof)]) == 0
    assert prof.exists()
    assert f"cProfile:    {prof}" in capsys.readouterr().out


def test_profile_output_requires_profile(job_file, capsys):
    with pytest.raises(SystemExit) as exc:
        main([job_file, "--profile-output", "x.prof"])
    assert exc.value.code == 2
    assert "--profile-output requires --profile" in capsys.readouterr().err


def test_profiler_peak_is_reset_under_outer_tracer():
    tracemalloc.start()
    try:
        big = bytearray(8 * 1024 * 1024)
        del big
        with ProfilerContext(top_n=0) as ctx:
            pass
        assert ctx.result is not None
        assert ctx.result.peak_memory_mb < 4
        assert tracemalloc.is_tracing()
    finally:
        tracemalloc.stop()


# --- #133 -------------------------------------------------------------------

NAMES = """\
//J JOB (A),B
//SQL EXEC PGM=X
//LINT DD DSN=A.B,DISP=SHR
//STEPS EXEC PGM=Y
//DETECT DD DSN=C.D,DISP=SHR
"""


@pytest.fixture
def names_file(tmp_path: Path) -> str:
    path = tmp_path / "e.jcl"
    path.write_text(NAMES)
    return str(path)


def test_uppercase_step_name_wins_over_query_word(names_file, capsys):
    assert main([names_file, "SQL", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "SQL"


def test_uppercase_dd_name_wins_over_query_word(names_file, capsys):
    assert main([names_file, "LINT", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["step"] == "SQL"


def test_steps_step_name(names_file, capsys):
    assert main([names_file, "STEPS", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["program"] == "Y"


def test_detect_dd_name(names_file, capsys):
    assert main([names_file, "DETECT", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["step"] == "STEPS"


def test_lowercase_words_stay_queries(names_file, capsys):
    assert main([names_file, "steps"]) == 0
    out = capsys.readouterr().out
    assert "SQL" in out and "STEPS" in out
    assert main([names_file, "detect"]) == 0
    assert capsys.readouterr().out.strip() == "JCL"


def test_uppercase_word_with_no_such_name_is_a_query(job_file, capsys):
    assert main([job_file, "STEPS"]) == 0
    assert "S1" in capsys.readouterr().out
    assert main([job_file, "DETECT"]) == 0
    assert capsys.readouterr().out.strip() == "JCL"


def test_uppercase_detect_on_unparseable_file(tmp_path, capsys):
    path = tmp_path / "junk.txt"
    path.write_text("not jcl\n")
    assert main([str(path), "DETECT"]) == 0
    assert capsys.readouterr().out.strip() == "UNKNOWN"
