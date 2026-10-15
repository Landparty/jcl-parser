"""Regression tests for issue #116.

With no ``JCLLIB ORDER`` the parser never built a PROC loader: the built-in
PROCs and ``<proc_base_path>/SYS1.PROCLIB`` were not consulted, so
``validate_jcl`` and a strict parse rejected every cataloged-PROC call, and
``explode_job`` could not find a PROC in the configured base path.
"""

from __future__ import annotations

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl
from jclparser.errors import ErrorSeverity, JCLSyntaxError
from jclparser.proc_loader import DEFAULT_SYSTEM_PROCLIBS, JCLLIBProcedureLoader

pytestmark = pytest.mark.unit


@pytest.fixture
def base(tmp_path):
    lib = tmp_path / "SYS1.PROCLIB"
    lib.mkdir()
    (lib / "MYPROC.jcl").write_text("//MYPROC PROC\n//PS1 EXEC PGM=MYPGM\n// PEND\n")
    user = tmp_path / "USER.PROCLIB"
    user.mkdir()
    (user / "MYPROC.jcl").write_text("//MYPROC PROC\n//PS1 EXEC PGM=USERPGM\n")
    return tmp_path


def test_builtin_proc_without_jcllib_validates():
    jcl = "//J1 JOB (A),'X'\n//S2 EXEC IGYWCL\n"
    assert validate_jcl(jcl) == []
    job = parse_jcl(jcl, strict_mode=True)
    assert job.get_procedure("IGYWCL") is not None
    assert {s.name for s in explode_job(job).steps} >= {"S2.COBOL", "S2.LKED"}


def test_system_proclib_searched_without_jcllib(base):
    job = parse_jcl("//J JOB\n//R EXEC MYPROC\n", proc_base_path=base)
    (step,) = explode_job(job).steps
    assert step.program == "MYPGM"
    parse_jcl("//J JOB\n//R EXEC MYPROC\n", proc_base_path=base, strict_mode=True)


def test_jcllib_searched_before_system_proclib(base):
    jcl = "//J JOB\n// JCLLIB ORDER=USER.PROCLIB\n//R EXEC MYPROC\n"
    (step,) = explode_job(parse_jcl(jcl, proc_base_path=base)).steps
    assert step.program == "USERPGM"


def test_system_proclib_searched_after_jcllib(base):
    jcl = "//J JOB\n// JCLLIB ORDER=OTHER.PROCLIB\n//R EXEC MYPROC\n"
    (step,) = explode_job(parse_jcl(jcl, proc_base_path=base)).steps
    assert step.program == "MYPGM"


def test_loader_does_not_search_system_proclib_twice(base, monkeypatch):
    loader = JCLLIBProcedureLoader(base)
    searched: list[str] = []
    original = loader._load_from_library

    def spy(name, library):
        searched.append(library)
        return original(name, library)

    monkeypatch.setattr(loader, "_load_from_library", spy)
    assert loader.load_procedure("NOSUCH", ["sys1.proclib"]) is None
    assert searched == ["sys1.proclib"]
    assert DEFAULT_SYSTEM_PROCLIBS == ("SYS1.PROCLIB",)


def test_unknown_proc_without_jcllib_is_a_warning():
    jcl = "//J JOB\n//R EXEC NOSUCH\n"
    job = parse_jcl(jcl, strict_mode=True)
    assert any("'NOSUCH' not found" in w for w in job.warnings)
    assert validate_jcl(jcl) == []
    (finding,) = validate_jcl(jcl, level="structure")
    assert finding.severity == ErrorSeverity.WARNING


def test_unknown_proc_with_jcllib_is_still_an_error(base):
    jcl = "//J JOB\n// JCLLIB ORDER=USER.PROCLIB\n//R EXEC NOSUCH\n"
    with pytest.raises(JCLSyntaxError, match="'NOSUCH' not found"):
        parse_jcl(jcl, strict_mode=True, proc_base_path=base)
    assert validate_jcl(jcl)


def test_external_loading_disabled_still_strict():
    with pytest.raises(JCLSyntaxError, match="external PROC loading is disabled"):
        parse_jcl(
            "//J JOB\n//R EXEC IGYWCL\n",
            strict_mode=True,
            enable_external_procs=False,
        )
