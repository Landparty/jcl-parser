"""
Tests targeting uncovered lines in explosion.py.

Covers: nested dict substitution, ConditionalBlock during explosion,
strict-mode symbol resolution, unnamed step expansion, and
call_chain_upper backward-compat path.
"""

import pytest

from jclparser.model import Job, Step, DDStatement, Procedure, ConditionalBlock
from jclparser.explosion import (
    SymbolScope,
    substitute_symbols,
    substitute_parameters_dict,
    expand_proc_invocation,
    explode_job,
    _explode_step,
)
from jclparser.proc_loader import InlineProcedureLoader
from jclparser.errors import UndefinedSymbolError


# ---------------------------------------------------------------------------
# substitute_parameters_dict with nested dict — lines 305-308
# ---------------------------------------------------------------------------


class TestSubstituteNestedDict:
    """Test substitute_parameters_dict() with dict-valued parameters."""

    def test_nested_dict_substitution(self):
        """Dict values are recursively substituted (lines 305-306)."""
        scope = SymbolScope(set_symbols={"DSN": "MY.DATASET"})
        params = {
            "OUTER": {
                "INNER_KEY": "&DSN",
                "STATIC": "UNCHANGED",
            }
        }
        result = substitute_parameters_dict(params, scope)
        assert result["OUTER"]["INNER_KEY"] == "MY.DATASET"
        assert result["OUTER"]["STATIC"] == "UNCHANGED"

    def test_non_string_non_list_non_dict_passthrough(self):
        """Non-string/list/dict values are passed through unchanged (line 308)."""
        scope = SymbolScope()
        params = {"COUNT": 42, "FLAG": True, "EMPTY": None}
        result = substitute_parameters_dict(params, scope)
        assert result["COUNT"] == 42
        assert result["FLAG"] is True
        assert result["EMPTY"] is None

    def test_list_with_mixed_types(self):
        """List with mixed string/non-string items (lines 299-304)."""
        scope = SymbolScope(set_symbols={"VAR": "HELLO"})
        params = {"ITEMS": ["&VAR", 123, "STATIC"]}
        result = substitute_parameters_dict(params, scope)
        assert result["ITEMS"] == ["HELLO", 123, "STATIC"]


# ---------------------------------------------------------------------------
# _make_replacer modes — lines 131-140
# ---------------------------------------------------------------------------


class TestMakeReplacerStrict:
    """Test _make_replacer in strict / allow_undefined / default modes."""

    def test_strict_undefined_raises(self):
        """Strict mode raises UndefinedSymbolError from scope.resolve (line 80).

        Note: With a standard SymbolScope, the error is raised by
        scope.resolve(strict=True) before the _replacer's own strict check
        at line 139 is reached.
        """
        scope = SymbolScope()
        with pytest.raises(UndefinedSymbolError):
            substitute_symbols("&UNDEFINED", scope, strict=True, allow_undefined=False)

    def test_make_replacer_strict_fallback(self):
        """_replacer's own strict check (line 139) raises when resolve returns None.

        With a standard SymbolScope, resolve(strict=True) raises first, making
        line 139 unreachable.  A custom scope that returns None without raising
        exercises the defensive check.
        """

        class LenientScope(SymbolScope):
            def resolve(self, symbol_name, strict=False):
                return None  # Never raises, even when strict=True

        scope = LenientScope()
        with pytest.raises(UndefinedSymbolError):
            substitute_symbols("&MISSING", scope, strict=True, allow_undefined=False)

    def test_allow_undefined_leaves_as_is(self):
        """allow_undefined=True leaves unresolved symbols in place (line 137)."""
        scope = SymbolScope()
        result = substitute_symbols(
            "&MISSING", scope, strict=False, allow_undefined=True
        )
        assert result == "&MISSING"

    def test_undefined_non_strict_returns_empty(self):
        """Non-strict, non-allow_undefined replaces undefined symbol with '' (line 140)."""
        scope = SymbolScope()
        result = substitute_symbols(
            "&MISSING", scope, strict=False, allow_undefined=False
        )
        assert result == ""

    def test_escaped_ampersand(self):
        """'&&' is replaced with '&' (line 131-132)."""
        scope = SymbolScope()
        result = substitute_symbols("&&TEMP", scope)
        assert result == "&TEMP"

    def test_non_string_input_passthrough(self):
        """Non-string input is returned unchanged (line 167-168)."""
        scope = SymbolScope()
        assert substitute_symbols("", scope) == ""
        assert substitute_symbols(None, scope) is None


# ---------------------------------------------------------------------------
# ConditionalBlock in explode_job — lines 441-446
# ---------------------------------------------------------------------------


class TestExplosionWithConditionals:
    """Test explosion of jobs containing ConditionalBlocks."""

    def test_conditional_block_in_top_level_steps(self):
        """ConditionalBlock within job.steps is handled during explosion (lines 441-446)."""
        # Build a job with an IF/THEN conditional containing a regular step
        inner_step = Step(name="S1", program="IEFBR14", line_number=3)
        cond = ConditionalBlock(condition="RC EQ 0", line_number=2)
        cond.then_steps.append(inner_step)

        job = Job(
            name="TESTJOB",
            steps=[cond],
            line_number=1,
        )

        exploded = explode_job(job)
        # The conditional should be preserved in the exploded job
        assert len(exploded.steps) == 1
        assert isinstance(exploded.steps[0], ConditionalBlock)
        assert len(exploded.steps[0].then_steps) == 1
        assert exploded.steps[0].then_steps[0].program == "IEFBR14"

    def test_conditional_block_with_else(self):
        """ConditionalBlock with else_steps is also processed."""
        then_step = Step(name="S1", program="PGM1", line_number=3)
        else_step = Step(name="S2", program="PGM2", line_number=5)
        cond = ConditionalBlock(condition="RC GT 4", line_number=2)
        cond.then_steps.append(then_step)
        cond.else_steps.append(else_step)

        job = Job(name="TESTJOB", steps=[cond], line_number=1)
        exploded = explode_job(job)

        assert isinstance(exploded.steps[0], ConditionalBlock)
        assert len(exploded.steps[0].then_steps) == 1
        assert len(exploded.steps[0].else_steps) == 1


# ---------------------------------------------------------------------------
# expand_proc_invocation with unnamed step — line 251
# ---------------------------------------------------------------------------


class TestExpandUnnamedStep:
    """Test expand_proc_invocation when the calling step has no name."""

    def test_unnamed_step_uses_proc_prefix(self):
        """Unnamed step defaults prefix to 'PROC' (line 231)."""
        proc = Procedure(
            name="MYPROC",
            steps=[Step(name="INNER", program="IEFBR14", line_number=2)],
            line_number=1,
        )
        step = Step(name=None, procedure="MYPROC", line_number=5)
        scope = SymbolScope()

        expanded = expand_proc_invocation(step, proc, {}, scope)
        # Should use "PROC" as prefix
        assert expanded[0].name == "PROC.INNER"

    def test_unnamed_inner_step(self):
        """Inner step with no name gets just the prefix (line 251)."""
        proc = Procedure(
            name="MYPROC",
            steps=[Step(name=None, program="IEFBR14", line_number=2)],
            line_number=1,
        )
        step = Step(name="CALLER", procedure="MYPROC", line_number=5)
        scope = SymbolScope()

        expanded = expand_proc_invocation(step, proc, {}, scope)
        assert expanded[0].name == "CALLER"


# ---------------------------------------------------------------------------
# _explode_step backward compat — line 550
# ---------------------------------------------------------------------------


class TestExplodeStepBackwardCompat:
    """Test _explode_step when call_chain_upper is not provided."""

    def test_call_chain_upper_none_fallback(self):
        """When call_chain_upper=None, it is computed from call_chain (line 541-542)."""
        proc = Procedure(
            name="MYPROC",
            steps=[Step(name="S1", program="IEFBR14", line_number=2)],
            line_number=1,
        )
        job = Job(name="TESTJOB", procedures=[proc], line_number=1)
        step = Step(name="CALL", procedure="MYPROC", line_number=5)

        loader = InlineProcedureLoader(job.procedures)
        scope = SymbolScope()

        # Explicitly pass call_chain_upper=None to exercise the fallback
        result = _explode_step(
            step=step,
            proc_loader=loader,
            base_scope=scope,
            call_chain=[],
            depth=0,
            max_depth=10,
            audit_records=[],
            expansion_map={},
            strict_symbols=False,
            call_chain_upper=None,
        )
        assert len(result) == 1
        assert result[0].name == "CALL.S1"


# ---------------------------------------------------------------------------
# Symbol substitution in expanded steps
# ---------------------------------------------------------------------------


class TestSymbolSubstitutionInExpansion:
    """Test that symbols are properly resolved during proc expansion."""

    def test_program_name_substituted(self):
        """Program name with symbol is resolved during expansion."""
        proc = Procedure(
            name="MYPROC",
            parameters={"PGM": "IEFBR14"},
            steps=[Step(name="S1", program="&PGM", line_number=2)],
            line_number=1,
        )
        step = Step(name="CALL", procedure="MYPROC", line_number=5)
        scope = SymbolScope()

        expanded = expand_proc_invocation(step, proc, {}, scope)
        assert expanded[0].program == "IEFBR14"

    def test_dd_dataset_name_substituted(self):
        """DD dataset names with symbols are resolved."""
        dd = DDStatement(name="DD1", dataset_name="&DSN", line_number=3)
        proc = Procedure(
            name="MYPROC",
            parameters={"DSN": "MY.DATA"},
            steps=[
                Step(name="S1", program="IEFBR14", dd_statements=[dd], line_number=2)
            ],
            line_number=1,
        )
        step = Step(name="CALL", procedure="MYPROC", line_number=5)
        scope = SymbolScope()

        expanded = expand_proc_invocation(step, proc, {}, scope)
        assert expanded[0].dd_statements[0].dataset_name == "MY.DATA"
