"""Unit tests for the bundled utility PROC templates."""

import pytest

from jclparser import (
    BUILTIN_UTILITY_PROCS,
    clear_registered_utility_procs,
    create_builtin_proc_loader,
    get_registered_utility_procs,
    parse_jcl,
    register_utility_proc,
    unregister_utility_proc,
)
from jclparser.model import Procedure
from jclparser.proc_loader import (
    CompositeProcedureLoader,
    DictProcedureLoader,
    create_default_loader,
)

pytestmark = pytest.mark.unit


_CUSTOM_PROC = (
    "//MYUTIL   PROC\n//RUN     EXEC PGM=MYHOMEPGM\n//SYSPRINT DD SYSOUT=*\n// PEND\n"
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Keep the global custom-proc registry clean across tests."""
    clear_registered_utility_procs()
    yield
    clear_registered_utility_procs()


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


class TestCustomUtilityProcRegistry:
    """Home-made utility PROCs must resolve just like the bundled IBM ones."""

    def test_register_makes_proc_resolvable(self):
        register_utility_proc("MYUTIL", _CUSTOM_PROC)
        loader = create_builtin_proc_loader()
        proc = loader.load_procedure("MYUTIL")
        assert isinstance(proc, Procedure)
        assert proc.steps[0].program == "MYHOMEPGM"

    def test_registration_is_case_insensitive(self):
        register_utility_proc("myutil", _CUSTOM_PROC)
        assert "MYUTIL" in get_registered_utility_procs()
        loader = create_builtin_proc_loader()
        assert loader.load_procedure("MyUtil") is not None

    def test_custom_proc_explodes_like_a_builtin(self):
        register_utility_proc("MYUTIL", _CUSTOM_PROC)
        job = parse_jcl(
            "//J JOB\n//S EXEC MYUTIL\n",
            strict_mode=False,
        )
        exploded = job.explode(loader=create_builtin_proc_loader())
        assert "MYHOMEPGM" in [s.program for s in exploded.steps]
        assert any(r.proc_name == "MYUTIL" for r in exploded.explosion_audit)

    def test_register_overrides_bundled_proc(self):
        override = "//IMSBATCH PROC\n//RUN EXEC PGM=SITEIMS\n// PEND\n"
        register_utility_proc("IMSBATCH", override)
        loader = create_builtin_proc_loader()
        assert loader.load_procedure("IMSBATCH").steps[0].program == "SITEIMS"

    def test_unregister_removes_proc(self):
        register_utility_proc("MYUTIL", _CUSTOM_PROC)
        assert unregister_utility_proc("myutil") is True
        assert create_builtin_proc_loader().load_procedure("MYUTIL") is None
        # Removing again reports nothing was removed.
        assert unregister_utility_proc("MYUTIL") is False

    def test_clear_empties_registry(self):
        register_utility_proc("MYUTIL", _CUSTOM_PROC)
        clear_registered_utility_procs()
        assert get_registered_utility_procs() == {}

    def test_blank_name_or_content_rejected(self):
        with pytest.raises(ValueError):
            register_utility_proc("", _CUSTOM_PROC)
        with pytest.raises(ValueError):
            register_utility_proc("MYUTIL", "   ")

    def test_get_registered_returns_copy(self):
        register_utility_proc("MYUTIL", _CUSTOM_PROC)
        snapshot = get_registered_utility_procs()
        snapshot["INJECTED"] = "x"
        assert "INJECTED" not in get_registered_utility_procs()


class TestExtraProcsParameter:
    """Per-call extra_procs let a host inject one tenant's procs without globals."""

    def test_extra_procs_resolve(self):
        loader = create_builtin_proc_loader(extra_procs={"MYUTIL": _CUSTOM_PROC})
        assert loader.load_procedure("MYUTIL").steps[0].program == "MYHOMEPGM"
        # Bundled procs are still served alongside the extras.
        assert loader.load_procedure("IMSBATCH") is not None

    def test_extra_procs_override_registered(self):
        register_utility_proc("MYUTIL", _CUSTOM_PROC)
        other = "//MYUTIL PROC\n//RUN EXEC PGM=PERCALL\n// PEND\n"
        loader = create_builtin_proc_loader(extra_procs={"MYUTIL": other})
        assert loader.load_procedure("MYUTIL").steps[0].program == "PERCALL"

    def test_extra_procs_keys_case_insensitive(self):
        loader = create_builtin_proc_loader(extra_procs={"myutil": _CUSTOM_PROC})
        assert loader.load_procedure("MYUTIL") is not None
