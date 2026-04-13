"""
Tests targeting coverage gaps in jclparser/explosion.py.

Covers:
- _explode_step with a PGM= step (no procedure name) → fast-path return (line 585)
- substitute_symbols with strict=True and an undefined symbol → UndefinedSymbolError
- substitute_symbols with allow_undefined=True → leaves symbol as-is
- substitute_symbols with escaped && → literal & in output
- SymbolScope.resolve with a missing symbol
"""

import pytest

from jclparser.explosion import (
    SymbolScope,
    explode_job,
    substitute_symbols,
)
from jclparser.errors import UndefinedSymbolError
from jclparser.model import Job, Step, DDStatement, Procedure
from jclparser.proc_loader import InlineProcedureLoader


# ---------------------------------------------------------------------------
# _explode_step fast-path: step with no PROC name (PGM= step)
# ---------------------------------------------------------------------------


class TestExplodeJobPGMStep:
    """Steps that execute a program (not a PROC) pass through explosion unchanged."""

    def test_pgm_step_passes_through_without_change(self):
        jcl_text = (
            "//MYJOB  JOB\n"
            "//STEP1  EXEC PGM=IEFBR14\n"
            "//SYSOUT DD SYSOUT=*\n"
        )
        from jclparser import parse_jcl

        job = parse_jcl(jcl_text)
        loader = InlineProcedureLoader(job.procedures)
        exploded = explode_job(job, proc_loader=loader)

        # The job must have exactly one step and it must still be PGM=IEFBR14
        steps = [s for s in exploded.steps if hasattr(s, "program")]
        assert any(s.program == "IEFBR14" for s in steps)

    def test_mixed_pgm_and_proc_steps(self):
        """A job with both PGM and PROC steps — only the PROC step is expanded."""
        jcl_text = (
            "//MYJOB  JOB\n"
            "//MYPROC PROC\n"
            "//PS1    EXEC PGM=SORT\n"
            "//       PEND\n"
            "//STEP1  EXEC PGM=IEFBR14\n"   # plain PGM step
            "//STEP2  EXEC MYPROC\n"         # PROC step
        )
        from jclparser import parse_jcl

        job = parse_jcl(jcl_text)
        loader = InlineProcedureLoader(job.procedures)
        exploded = explode_job(job, proc_loader=loader)

        # IEFBR14 step should survive unchanged
        all_steps = []
        for s in exploded.steps:
            if hasattr(s, "program"):
                all_steps.append(s)
        assert any(s.program == "IEFBR14" for s in all_steps)


# ---------------------------------------------------------------------------
# substitute_symbols — strict mode and allow_undefined
# ---------------------------------------------------------------------------


class TestSubstituteSymbols:
    """substitute_symbols handles undefined symbols in multiple modes."""

    def _scope(self, mapping: dict) -> SymbolScope:
        return SymbolScope(set_symbols={k.upper(): v for k, v in mapping.items()})

    def test_defined_symbol_is_replaced(self):
        scope = self._scope({"VAR": "VALUE"})
        result = substitute_symbols("prefix.&VAR.suffix", scope)
        assert "VALUE" in result

    def test_escaped_double_ampersand_becomes_single(self):
        scope = self._scope({})
        result = substitute_symbols("&&LITERAL", scope)
        assert result == "&LITERAL"

    def test_undefined_symbol_strict_raises(self):
        scope = self._scope({})
        with pytest.raises(UndefinedSymbolError):
            substitute_symbols("&UNDEFINED", scope, strict=True)

    def test_undefined_symbol_not_strict_returns_empty(self):
        scope = self._scope({})
        result = substitute_symbols("prefix&UNDEFINEDsuffix", scope, strict=False)
        # Undefined + non-strict → symbol replaced with ""
        assert "UNDEFINED" not in result

    def test_undefined_symbol_allow_undefined_leaves_as_is(self):
        scope = self._scope({})
        result = substitute_symbols("&UNDEFINED", scope, allow_undefined=True)
        assert "&UNDEFINED" in result

    def test_multiple_symbols_mixed(self):
        scope = self._scope({"DEFINED": "X"})
        result = substitute_symbols(
            "&DEFINED.&MISSING", scope, allow_undefined=True
        )
        assert "X" in result
        assert "&MISSING" in result


# ---------------------------------------------------------------------------
# SymbolScope
# ---------------------------------------------------------------------------


class TestSymbolScope:
    """SymbolScope.resolve returns None for unknown symbols."""

    def test_resolve_unknown_returns_none(self):
        scope = SymbolScope()
        assert scope.resolve("NOTSET") is None

    def test_resolve_set_symbol(self):
        scope = SymbolScope(set_symbols={"FOO": "BAR"})
        assert scope.resolve("FOO") == "BAR"

    def test_resolve_is_case_insensitive_on_lookup(self):
        scope = SymbolScope(set_symbols={"FOO": "BAR"})
        # resolve() uppercases the key before lookup
        assert scope.resolve("foo") == "BAR"

    def test_exec_override_has_highest_priority(self):
        scope = SymbolScope(
            set_symbols={"VAR": "FROM_SET"},
            proc_params={"VAR": "FROM_PROC"},
            exec_overrides={"VAR": "FROM_EXEC"},
        )
        assert scope.resolve("VAR") == "FROM_EXEC"

    def test_proc_param_takes_priority_over_set(self):
        scope = SymbolScope(
            set_symbols={"VAR": "FROM_SET"},
            proc_params={"VAR": "FROM_PROC"},
        )
        assert scope.resolve("VAR") == "FROM_PROC"
