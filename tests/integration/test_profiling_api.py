"""Integration tests: parse_jcl() with enable_profiling=True."""

from jclparser import parse_jcl
from jclparser.profiling import ProfilingResult
from jclparser.model import Job

_HELLO = """\
//HELLO    JOB (ACCT),'Test',CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD   SYSOUT=*
"""


def test_parse_jcl_no_profiling_returns_job():
    result = parse_jcl(_HELLO)
    assert isinstance(result, Job)


def test_parse_jcl_profiling_returns_tuple():
    result = parse_jcl(_HELLO, enable_profiling=True)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_parse_jcl_profiling_result_type():
    _, prof = parse_jcl(_HELLO, enable_profiling=True)
    assert isinstance(prof, ProfilingResult)


def test_parse_jcl_profiling_metrics_positive():
    _, prof = parse_jcl(_HELLO, enable_profiling=True)
    assert prof.wall_clock_s > 0.0
    assert prof.peak_memory_mb >= 0.0


def test_parse_jcl_profiling_top_functions_non_empty():
    _, prof = parse_jcl(_HELLO, enable_profiling=True)
    assert len(prof.top_functions) > 0


def test_parse_jcl_profiling_top_n_respected():
    _, prof = parse_jcl(_HELLO, enable_profiling=True, top_n=3)
    assert 0 < len(prof.top_functions) <= 3


def test_parse_jcl_profiling_prof_file(tmp_path):
    import os

    prof_path = str(tmp_path / "parse.prof")
    parse_jcl(_HELLO, enable_profiling=True, prof_output=prof_path)
    assert os.path.exists(prof_path)


def test_parse_jcl_profiling_job_still_valid():
    job, _ = parse_jcl(_HELLO, enable_profiling=True)
    assert isinstance(job, Job)
    assert job.name == "HELLO"
