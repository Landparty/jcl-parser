"""Unit tests for the bundled IBM-supplied utility procedures."""

import pytest

from jclparser import (
    BUILTIN_UTILITY_PROCS,
    create_builtin_proc_loader,
    parse_jcl,
)
from jclparser.model import Procedure
from jclparser.proc_loader import (
    CompositeProcedureLoader,
    DictProcedureLoader,
    create_default_loader,
)

pytestmark = pytest.mark.unit


class TestBuiltinProcDefinitions:
    """Every bundled definition must parse into a usable Procedure."""

    def test_registry_is_non_empty(self):
        assert BUILTIN_UTILITY_PROCS
        # The user-named example must be present.
        assert "IMSBATCH" in BUILTIN_UTILITY_PROCS

    @pytest.mark.parametrize("name", sorted(BUILTIN_UTILITY_PROCS))
    def test_each_builtin_proc_parses(self, name):
        loader = create_builtin_proc_loader()
        proc = loader.load_procedure(name)
        assert isinstance(proc, Procedure)
        assert proc.is_external is True
        assert proc.steps, f"{name} produced no steps"

    def test_unknown_proc_returns_none(self):
        loader = create_builtin_proc_loader()
        assert loader.load_procedure("NOSUCHPROC") is None

    def test_lookup_is_case_insensitive(self):
        loader = create_builtin_proc_loader()
        assert loader.load_procedure("imsbatch") is not None


class TestBuiltinExplosion:
    """The bundled procs must resolve through the explosion engine."""

    def test_exec_imsbatch_resolves_to_region_controller(self):
        job = parse_jcl(
            "//J JOB\n//S EXEC IMSBATCH,MBR=MYPGM,PSB=MYPSB\n",
            strict_mode=False,
        )
        exploded = job.explode(loader=create_builtin_proc_loader())
        programs = [s.program for s in exploded.steps]
        assert "DFSRRC00" in programs
        assert any(r.proc_name == "IMSBATCH" for r in exploded.explosion_audit)

    def test_exec_dsnuproc_resolves(self):
        job = parse_jcl(
            "//J JOB\n//U EXEC DSNUPROC,UID=MYUID\n",
            strict_mode=False,
        )
        exploded = job.explode(loader=create_builtin_proc_loader())
        assert any(s.program == "DSNUTILB" for s in exploded.steps)


class TestPrecedence:
    """Inline / site PROCs must override the bundled defaults."""

    def test_inline_proc_overrides_builtin(self):
        # An inline IMSBATCH that runs a different program must win over the
        # bundled IMS region controller when ordered first in the chain.
        jcl = (
            "//J JOB\n"
            "//IMSBATCH PROC\n"
            "//RUN EXEC PGM=MYCUSTOM\n"
            "// PEND\n"
            "//S EXEC IMSBATCH\n"
        )
        job = parse_jcl(jcl, strict_mode=False)
        from jclparser.proc_loader import InlineProcedureLoader

        loader = CompositeProcedureLoader(
            [InlineProcedureLoader(job.procedures), create_builtin_proc_loader()]
        )
        exploded = job.explode(loader=loader)
        programs = [s.program for s in exploded.steps]
        assert "MYCUSTOM" in programs
        assert "DFSRRC00" not in programs

    def test_site_dict_loader_overrides_builtin(self):
        site = DictProcedureLoader(
            {"IMSBATCH": "//IMSBATCH PROC\n//RUN EXEC PGM=SITEPGM\n// PEND\n"}
        )
        loader = CompositeProcedureLoader([site, create_builtin_proc_loader()])
        proc = loader.load_procedure("IMSBATCH")
        assert proc.steps[0].program == "SITEPGM"


class TestDefaultLoaderIntegration:
    """create_default_loader should include builtins by default but allow opt-out."""

    def test_default_loader_includes_builtins(self):
        loader = create_default_loader([], include_jcllib=False)
        assert loader.load_procedure("IMSBATCH") is not None

    def test_default_loader_can_exclude_builtins(self):
        loader = create_default_loader([], include_jcllib=False, include_builtins=False)
        assert loader.load_procedure("IMSBATCH") is None
