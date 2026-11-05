"""
Dynamic procedure explosion engine for JCL parsing.

Implements symbolic parameter substitution and procedure expansion with
support for nested procedures, circular dependency detection, and audit logging.
"""

import logging
import re
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from datetime import datetime
from typing import Any

from .errors import (
    CircularProcedureError,
    ExplosionDepthError,
    JCLStructureError,
    ProcedureNotFoundError,
    UndefinedSymbolError,
)
from .include_loader import IncludeMemberLoader
from .model import (
    ConditionalBlock,
    DDStatement,
    Job,
    Procedure,
    Step,
    iter_execution_steps,
)
from .proc_loader import (
    CompositeProcedureLoader,
    InlineProcedureLoader,
    ProcedureLoader,
    create_default_loader,
)
from .system_symbols import SystemSymbolProvider, get_default_provider
from .utils import MAX_SYMBOL_VALUE_LENGTH, jcl_value_text

logger = logging.getLogger(__name__)

#: Default ``max_steps`` for :func:`explode_job`. z/OS itself allows at most
#: 255 steps in a job, PROC steps included, so a real job stays far below this;
#: the limit only exists to stop a runaway PROC fan-out early.
DEFAULT_MAX_STEPS: int = 10_000


# Single-pass pattern: matches && (escaped ampersand) OR &SYMBOL with optional trailing period
_SYMBOL_SUB_PATTERN = re.compile(r"&&|&([A-Z0-9@#$]+)\.?")

# A symbol value may itself reference symbols (``HLQ=&SYSUID``); this bounds
# how deep those nested references are followed.
_MAX_NESTED_SUBSTITUTION = 8

# Total characters the symbol values spliced in by one substitution may add
# up to (``utils.MAX_SYMBOL_VALUE_LENGTH``). Fan-out over distinct symbols
# (``A='&B&B&B'``, ``B='&C&C&C'`` ...) grows exponentially with depth even
# without a cycle, so depth alone is no bound (#70).
_MAX_NESTED_EXPANSION_CHARS = MAX_SYMBOL_VALUE_LENGTH


class _SymbolOverflow(Exception):
    """Internal: a substitution would splice in more than the character budget."""


def _overflow_message(source_text: str) -> str:
    return (
        f"Symbols in '{source_text[:80]}' expand to more than "
        f"{_MAX_NESTED_EXPANSION_CHARS:,} characters"
    )


# A value ending in a bare ``&NAME`` reference (not the ``&&NAME`` literal).
_TRAILING_SYMBOL_REF = re.compile(r"(?<!&)&[A-Z0-9@#$]+$")


def _clone_conditional(
    block: ConditionalBlock,
    process_steps_fn,
) -> ConditionalBlock:
    """Clone *block*, recursively processing each branch with *process_steps_fn*.

    *process_steps_fn* must accept a list of ``Step | ConditionalBlock`` and
    return a new list.  This centralises the repeated ConditionalBlock-cloning
    boilerplate that appears in every step-processing loop in this module.
    """
    new_cond = ConditionalBlock(
        condition=block.condition,
        line_number=block.line_number,
        condition_ast=block.condition_ast,
    )
    new_cond.then_steps = process_steps_fn(block.then_steps)
    new_cond.else_steps = process_steps_fn(block.else_steps)
    return new_cond


def _qualify_step_ref(
    name: str | None, proc_steps: frozenset[str], prefix: str
) -> str | None:
    """Qualify a step reference made inside a procedure with the call's prefix.

    Inside a procedure, ``PS1`` (or ``PS1.INNER`` for a nested call) names the
    procedure's own step; after explosion that step is ``PREFIX.PS1``.
    References to anything else (job steps) are returned unchanged.
    """
    if name and name.split(".", 1)[0].upper() in proc_steps:
        return f"{prefix}.{name}"
    return name


def _qualify_condition_ast(node: Any, proc_steps: frozenset[str], prefix: str) -> Any:
    """Return a copy of an IF condition AST with procedure step refs qualified.

    The procedure's AST is shared by every expansion, so it is never mutated.
    """
    if node is None:
        return None
    changes: dict[str, Any] = {}
    if hasattr(node, "step_name"):
        changes["step_name"] = _qualify_step_ref(node.step_name, proc_steps, prefix)
    for child in ("operand", "left", "right"):
        if hasattr(node, child):
            changes[child] = _qualify_condition_ast(
                getattr(node, child), proc_steps, prefix
            )
    return dataclass_replace(node, **changes) if changes else node


#: A step reference in IF condition text: ``NAME`` of ``NAME.RC``,
#: ``NAME.PROCSTEP.ABEND``, ... (not a later segment of a qualified name).
_RE_CONDITION_STEP_REF = re.compile(
    r"(?<![A-Z0-9@#$.&])([A-Z@#$][A-Z0-9@#$]*)"
    r"(?=\.(?:[A-Z@#$][A-Z0-9@#$]*\.)?(?:RC|ABENDCC|ABEND|RUN)(?![A-Z0-9@#$.]))",
    re.IGNORECASE,
)


def _qualify_condition_text(text: str, proc_steps: frozenset[str], prefix: str) -> str:
    """IF condition *text* with procedure step refs qualified, as in its AST."""
    return _RE_CONDITION_STEP_REF.sub(
        lambda m: _qualify_step_ref(m.group(1), proc_steps, prefix) or m.group(1),
        text,
    )


def _qualify_cond_parameter(value: Any, proc_steps: frozenset[str], prefix: str) -> Any:
    """Qualify the step of each ``(code,operator,stepname)`` test in COND=."""
    if isinstance(value, list):
        if (
            len(value) == 3
            and all(isinstance(v, str) for v in value)
            and not value[0].startswith("(")
        ):
            # COND=(4,LT,PS1): a single test stored as its three tokens.
            return [
                value[0],
                value[1],
                _qualify_step_ref(value[2], proc_steps, prefix),
            ]
        return [_qualify_cond_parameter(v, proc_steps, prefix) for v in value]
    if isinstance(value, str) and value.startswith("(") and value.endswith(")"):
        # COND=((4,LT,PS1),...): each test stored as "(4,LT,PS1)".
        parts = value[1:-1].split(",")
        if len(parts) == 3:
            parts[2] = _qualify_step_ref(parts[2], proc_steps, prefix) or parts[2]
            return "(" + ",".join(parts) + ")"
    return value


def _clone_dd_statement(dd: DDStatement) -> DDStatement:
    # substitute_dd_statement mutates dataset_name, disposition, parameters
    # in-place, so each exploded step needs its own DDStatement instance.
    # Inner parameter values (strings, lists, dicts) are replaced wholesale
    # by substitute_parameters_dict — never mutated — so a shallow dict
    # copy is sufficient. output_refs is populated post-parse and not
    # touched by explosion; sharing the list by reference is safe.
    new_dd = DDStatement(
        name=dd.name,
        dataset_name=dd.dataset_name,
        disposition=dd.disposition,
        parameters=dict(dd.parameters),
        inline_data=dd.inline_data,
        comments=list(dd.comments),
        line_number=dd.line_number,
    )
    new_dd.output_refs = dd.output_refs
    new_dd.coded_dataset_name = dd.coded_dataset_name
    return new_dd


def _step_dds_and_overrides(step: Step) -> list[DDStatement]:
    """Every DD coded under *step*: its own, its PROCSTEP.DDNAME overrides and
    their concatenation members."""
    return [
        *step.dd_statements,
        *step.dd_overrides.values(),
        *(dd for dds in step.dd_override_concatenations.values() for dd in dds),
    ]


def _clone_step_for_explosion(step: Step) -> Step:
    # Performance-tuned alternative to deepcopy(step) on the PROC explosion
    # hot path. Clones only what downstream substitution actually mutates:
    # dd_statements (in-place mutation by substitute_dd_statement) and the
    # outer parameters / dd_overrides / comments containers. Strings and
    # scalars are shared safely.
    return Step(
        name=step.name,
        program=step.program,
        procedure=step.procedure,
        parameters=dict(step.parameters),
        dd_statements=[_clone_dd_statement(dd) for dd in step.dd_statements],
        comments=list(step.comments),
        line_number=step.line_number,
        is_exploded=step.is_exploded,
        original_proc_call=step.original_proc_call,
        dd_overrides={k: _clone_dd_statement(v) for k, v in step.dd_overrides.items()},
        dd_override_concatenations={
            k: [_clone_dd_statement(dd) for dd in v]
            for k, v in step.dd_override_concatenations.items()
        },
    )


@dataclass
class SymbolScope:
    """
    Symbol resolution scope for parameter substitution.

    Manages symbol precedence: EXEC overrides > PROC defaults > SET statements > System symbols
    """

    set_symbols: dict[str, str] = field(default_factory=dict)
    proc_params: dict[str, Any] = field(default_factory=dict)
    exec_overrides: dict[str, Any] = field(default_factory=dict)
    system_provider: SystemSymbolProvider | None = None

    def raw_value(self, symbol_name: str) -> Any:
        """Return an EXEC-override / PROC-default value as tokenized.

        A parenthesised value such as ``DISP=(NEW,CATLG)`` comes back as the
        list the tokenizer built; ``None`` when neither defines the symbol.
        """
        symbol_upper = symbol_name.upper()
        if symbol_upper in self.exec_overrides:
            return self.exec_overrides[symbol_upper]
        return self.proc_params.get(symbol_upper)

    def resolve(self, symbol_name: str, strict: bool = False) -> str | None:
        """
        Resolve a symbol using precedence rules.

        Args:
            symbol_name: Symbol name (without leading &)
            strict: If True, raise error for undefined symbols

        Returns:
            Resolved value or None if not found

        Raises:
            UndefinedSymbolError: If strict=True and symbol undefined
        """
        symbol_upper = symbol_name.upper()

        # 1. EXEC overrides (highest priority)
        if symbol_upper in self.exec_overrides:
            value = self.exec_overrides[symbol_upper]
            return jcl_value_text(value) if value is not None else None

        # 2. PROC parameters (default values)
        if symbol_upper in self.proc_params:
            value = self.proc_params[symbol_upper]
            return jcl_value_text(value) if value is not None else None

        # 3. SET statements (job-level)
        if symbol_upper in self.set_symbols:
            return self.set_symbols[symbol_upper]

        # 4. System symbols (lowest priority)
        if self.system_provider:
            value = self.system_provider.get_symbol(symbol_upper)
            if value is not None:
                return value

        # Symbol not found
        if strict:
            raise UndefinedSymbolError(symbol_name)

        return None


@dataclass
class ExplosionRecord:
    """
    Audit record for a procedure explosion.

    Captures metadata about procedure expansion for debugging and compliance.
    """

    step_name: str
    proc_name: str
    parameters: dict[str, Any]
    depth: int
    timestamp: datetime
    expanded_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "step_name": self.step_name,
            "proc_name": self.proc_name,
            "parameters": self.parameters,
            "depth": self.depth,
            "timestamp": self.timestamp.isoformat(),
            "expanded_steps": self.expanded_steps,
        }


@dataclass
class ProcExpansionInfo:
    """
    Cross-reference information for expanded procedure.

    Maps expanded steps back to their original PROC definition.
    """

    original_statement: str
    proc_definition: str
    resolved_parameters: dict[str, Any]
    source_line_numbers: list[int]
    expanded_step_names: list[str]


def _make_replacer(
    scope: "SymbolScope",
    strict: bool,
    allow_undefined: bool,
    source_text: str = "",
    warnings: list[str] | None = None,
    collapse_double_amp: bool = True,
    keep_undefined: Callable[[str], bool] | None = None,
    _depth: int = 0,
    _resolving: frozenset[str] = frozenset(),
    _budget: list[int] | None = None,
):
    """Create a regex replacer function for symbol substitution.

    *_resolving* holds the symbols whose values are being expanded above this
    level; a reference back to one of them is a cycle and is left as written.
    *_budget* is a one-element list shared by every nested level, counting
    down the characters the substitution may still splice in; running out
    raises :class:`_SymbolOverflow`, so no level builds a string much longer
    than the budget.
    """
    if _budget is None:
        _budget = [_MAX_NESTED_EXPANSION_CHARS]
    budget = _budget

    def _replacer(m: re.Match[str]) -> str:
        if m.group(0) == "&&":
            return "&" if collapse_double_amp else "&&"
        symbol_name = m.group(1)
        if symbol_name in _resolving:
            # ``A='&A'`` (directly or via other symbols): no value to splice.
            return m.group(0)
        # Always resolve with strict=False so that UndefinedSymbolError is raised
        # here (with full source context) rather than inside scope.resolve().
        value = scope.resolve(symbol_name, strict=False)
        if value is None:
            if allow_undefined or (
                keep_undefined is not None and keep_undefined(symbol_name)
            ):
                return m.group(0)  # leave as-is
            if strict:
                raise UndefinedSymbolError(symbol_name, source_text=source_text)
            if warnings is not None:
                warnings.append(
                    f"unresolved symbol &{symbol_name} in '{source_text}' "
                    "resolved to empty string"
                )
            return ""
        logger.debug("resolved &%s -> %s", symbol_name, value)
        if "&" in value and _depth < _MAX_NESTED_SUBSTITUTION:
            # The value references other symbols (``HLQ=&SYSUID``): resolve
            # those too. One still undefined is left as written for a later
            # pass (e.g. explode_job() resolving system symbols).
            value = _SYMBOL_SUB_PATTERN.sub(
                _make_replacer(
                    scope,
                    strict=False,
                    allow_undefined=True,
                    source_text=value,
                    collapse_double_amp=False,
                    _depth=_depth + 1,
                    _resolving=_resolving | {symbol_name},
                    _budget=budget,
                ),
                value,
            )
        budget[0] -= len(value)
        if budget[0] < 0:
            raise _SymbolOverflow
        return _splice_ready_value(value, collapse_double_amp)

    return _replacer


def _splice_ready_value(value: str, collapse_double_amp: bool) -> str:
    """Finish a resolved symbol *value* for splicing into the text."""
    if _TRAILING_SYMBOL_REF.search(value):
        # Splicing a bare ``&SYSUID`` in front of ``.DATA`` would make that
        # period the reference's delimiter; give it its own.
        value += "."
    if collapse_double_amp:
        # The nested pass keeps ``&&`` so a value's escaped ampersand is not
        # read as a symbol reference; collapse it now, exactly once, as a
        # literal ``&&`` in the text itself is (invariant 4, #127).
        value = value.replace("&&", "&")
    return value


def _substitute_symbols_bounded(
    text: str,
    scope: "SymbolScope",
    strict: bool = False,
    allow_undefined: bool = False,
    warnings: list[str] | None = None,
    collapse_double_amp: bool = True,
    keep_undefined: Callable[[str], bool] | None = None,
) -> str:
    """:func:`substitute_symbols` that raises :class:`_SymbolOverflow` on overflow."""
    return _SYMBOL_SUB_PATTERN.sub(
        _make_replacer(
            scope,
            strict,
            allow_undefined,
            source_text=text,
            warnings=warnings,
            collapse_double_amp=collapse_double_amp,
            keep_undefined=keep_undefined,
        ),
        text,
    )


def substitute_symbols(
    text: str,
    scope: "SymbolScope",
    strict: bool = False,
    allow_undefined: bool = False,
    warnings: list[str] | None = None,
    collapse_double_amp: bool = True,
    keep_undefined: Callable[[str], bool] | None = None,
) -> str:
    """
    Substitute symbolic parameters in text.

    Replaces &SYMBOL references with resolved values from scope.
    Handles escaped symbols (&&) and trailing-period concatenation (&VAR.SUFFIX).

    Args:
        text: Text containing symbolic parameters
        scope: Symbol resolution scope
        strict: If True, raise error for undefined symbols
        allow_undefined: If True, leave undefined symbols as-is
        warnings: Optional list to receive a message whenever an undefined
            symbol is silently resolved to an empty string (only relevant
            when strict=False and allow_undefined=False, the default).
        collapse_double_amp: If False, leave a literal "&&" untouched instead
            of collapsing it to "&". Callers that only want to resolve named
            symbols without touching temporary-dataset names (which use the
            "&&NAME" idiom, detected via ``DDStatement.is_temporary()``) should
            pass False here.
        keep_undefined: Optional predicate on a symbol name; an undefined
            symbol it accepts is left as written instead of being blanked,
            so a later pass (e.g. ``explode_job()`` resolving system
            symbols) can still resolve it.

    Returns:
        Text with symbols substituted. When the substituted values would add
        up to more than ``utils.MAX_SYMBOL_VALUE_LENGTH`` characters (chained
        symbols that double at each step), *text* is returned unchanged and a
        message goes to *warnings* (#70).

    Raises:
        UndefinedSymbolError: If strict=True and symbol undefined
        JCLStructureError: If strict=True and the substitution would exceed
            ``utils.MAX_SYMBOL_VALUE_LENGTH`` characters
    """
    if not text or not isinstance(text, str):
        return text
    try:
        return _substitute_symbols_bounded(
            text,
            scope,
            strict=strict,
            allow_undefined=allow_undefined,
            warnings=warnings,
            collapse_double_amp=collapse_double_amp,
            keep_undefined=keep_undefined,
        )
    except _SymbolOverflow:
        message = _overflow_message(text)
        if strict:
            raise JCLStructureError(message) from None
        if warnings is not None:
            warnings.append(f"{message}; left unresolved")
        return text


def detect_circular_refs(
    proc_name: str,
    call_chain: list[str],
    call_chain_upper: frozenset | None = None,
) -> None:
    """
    Detect circular procedure references.

    Args:
        proc_name: Procedure being called
        call_chain: Current call chain
        call_chain_upper: Optional pre-built frozenset of uppercased chain names
                          for O(1) membership testing.

    Raises:
        CircularProcedureError: If circular reference detected
    """
    proc_upper = proc_name.upper()

    chain_set = (
        call_chain_upper
        if call_chain_upper is not None
        else frozenset(p.upper() for p in call_chain)
    )
    if proc_upper in chain_set:
        logger.debug(
            "circular PROC reference detected: %s already in chain %s",
            proc_name,
            call_chain,
        )
        raise CircularProcedureError(proc_name, call_chain + [proc_name])


def expand_proc_invocation(
    step: Step,
    procedure: Procedure,
    overrides: dict[str, Any],
    scope: SymbolScope,
    step_prefix: str | None = None,
    strict: bool = False,
    warnings: list[str] | None = None,
    nested_call_scopes: dict[int, SymbolScope] | None = None,
) -> list[Step]:
    """
    Expand a single procedure invocation into steps.

    Args:
        step: Original EXEC step calling the procedure
        procedure: Procedure definition to expand
        overrides: Parameter overrides from EXEC statement
        scope: Symbol resolution scope
        step_prefix: Optional prefix for qualified step names
        strict: Whether to raise on undefined symbols inside the PROC body
        warnings: List to append symbol-substitution diagnostics to (e.g. an
                  undefined &SYMBOL only resolvable against PROC defaults /
                  EXEC overrides / system symbols, inside the PROC body).
                  None means diagnostics are discarded.
        nested_call_scopes: When given, an ``EXEC procname`` inside the
                  procedure only has its symbolic values substituted; its
                  keyword overrides and DDs are left for the called PROC's
                  scope (:func:`_resolve_call_in_proc_scope`) and the scope
                  in effect at it is recorded here, keyed by ``id()`` of the
                  expanded step.

    Returns:
        List of expanded steps with substituted parameters
    """
    expansion_scope = _expansion_scope(procedure, overrides, scope)

    # Generate step name prefix
    prefix = step_prefix or step.name or "PROC"

    # Step references made inside the procedure (IF PS1.RC, COND=(4,LT,PS1))
    # name its own steps, which are renamed PREFIX.PS1 below.
    proc_steps = frozenset(
        s.name.upper() for s in iter_execution_steps(procedure.steps) if s.name
    )

    def _process_proc_steps(steps_list):
        result = []
        for proc_step in steps_list:
            if isinstance(proc_step, ConditionalBlock):
                new_block = _clone_conditional(proc_step, _process_proc_steps)
                new_block.condition = _qualify_condition_text(
                    new_block.condition, proc_steps, prefix
                )
                new_block.condition_ast = _qualify_condition_ast(
                    new_block.condition_ast, proc_steps, prefix
                )
                result.append(new_block)
            else:
                # Clone the step
                new_step = _clone_step_for_explosion(proc_step)
                step_scope = _proc_step_scope(expansion_scope, proc_step)
                new_step.set_symbols = None

                # Generate qualified step name
                if new_step.name:
                    new_step.name = f"{prefix}.{new_step.name}"
                else:
                    new_step.name = prefix

                # Mark as exploded
                new_step.is_exploded = True
                new_step.original_proc_call = step.name

                # Substitute symbols in program name
                if new_step.program:
                    new_step.program = substitute_symbols(
                        new_step.program,
                        step_scope,
                        strict=strict,
                        warnings=warnings,
                    )

                _substitute_proc_body_step(
                    new_step, step_scope, strict, warnings, nested_call_scopes
                )
                if "COND" in new_step.parameters:
                    new_step.parameters["COND"] = _qualify_cond_parameter(
                        new_step.parameters["COND"], proc_steps, prefix
                    )

                result.append(new_step)
        return result

    expanded_steps = _process_proc_steps(procedure.steps)

    return expanded_steps


def _substitute_proc_body_step(
    step: Step,
    scope: SymbolScope,
    strict: bool,
    warnings: list[str] | None,
    nested_call_scopes: dict[int, SymbolScope] | None,
) -> None:
    """Substitute *scope*'s symbols into the expanded PROC step *step*.

    A nested ``EXEC procname`` keeps "&&" in its symbolic values, as a
    job-level one does (``TMP='&&WORK'`` is a temporary dataset).  With
    *nested_call_scopes*, its keyword overrides and DDs are left for the
    called PROC's scope and *scope* is recorded for them (issue #126).
    """
    if step.is_procedure and nested_call_scopes is not None:
        _resolve_symbolic_values(
            step, scope, allow_undefined=False, strict=strict, warnings=warnings
        )
        nested_call_scopes[id(step)] = scope
        return
    if step.is_procedure:
        step.parameters = _substitute_proc_call_parameters(
            step.parameters, scope, strict=strict, warnings=warnings
        )
    else:
        step.parameters = substitute_parameters_dict(
            step.parameters, scope, strict=strict, warnings=warnings
        )
    # The step's own DDs and, for a nested ``EXEC procname``, its
    # PROCSTEP.DDNAME overrides.
    for dd in _step_dds_and_overrides(step):
        substitute_dd_statement(dd, scope, strict=strict, warnings=warnings)


def _flattened_caller_scope(scope: SymbolScope) -> SymbolScope:
    """*scope* of a PROC step as the fallback for a call coded in it.

    The overrides of an ``EXEC procname`` coded inside a procedure are that
    procedure's text, so the calling procedure's symbols (EXEC values, PROC
    defaults, SETs) back up the called PROC's own, ranked below them.
    """

    def _texts(values: dict[str, Any]) -> dict[str, str]:
        return {
            k: jcl_value_text(v)
            for k, v in values.items()
            if v is not None and not is_exec_override_keyword(k)
        }

    return SymbolScope(
        set_symbols={
            **scope.set_symbols,
            **_texts(scope.proc_params),
            **_texts(scope.exec_overrides),
        },
        system_provider=scope.system_provider,
    )


def _expansion_scope(
    procedure: Procedure, overrides: dict[str, Any], scope: SymbolScope
) -> SymbolScope:
    """The symbol scope of one expansion of *procedure* called from *scope*.

    SETs coded inside the procedure body apply to this expansion only,
    overriding same-named job-level SETs; they rank as SET symbols, so -- as
    for job-level SETs -- EXEC-statement overrides and PROC-statement
    defaults still take precedence over them.
    """
    return SymbolScope(
        set_symbols={**scope.set_symbols, **procedure.set_statements},
        proc_params=procedure.parameters.copy(),
        exec_overrides=overrides.copy(),
        system_provider=scope.system_provider,
    )


def _resolve_call_in_proc_scope(
    step: Step,
    procedure: Procedure,
    caller_scope: SymbolScope,
    strict: bool,
    warnings: list[str] | None,
) -> None:
    """Resolve the keyword overrides and DDs of a PROC call in its scope.

    ``PARM.PS1='&HLQ'`` and ``//PS1.IN DD DSN=&HLQ..X`` coded under
    ``EXEC procname,HLQ=TEST`` are merged into the procedure, so their
    symbols resolve in its scope -- EXEC values, PROC defaults, the PROC's
    SETs in effect at the procstep they override (``Step.set_symbols``),
    then *caller_scope* -- like that procstep's own statements (issue
    #126).  An unqualified override and an added DD go to the first
    procstep.  A symbol undefined there raises with *strict*; otherwise it
    is left as written, with a warning, rather than blanked: an emptied
    ``PARM.PS1=`` would nullify the procedure's PARM.
    """
    expansion = _expansion_scope(procedure, step.parameters, caller_scope)
    proc_steps = list(iter_execution_steps(procedure.steps))
    by_name = {s.name.upper(): s for s in proc_steps if s.name}

    def _scope_for(procstep: str) -> SymbolScope:
        target = by_name.get(procstep.upper()) or (
            proc_steps[0] if proc_steps else None
        )
        return _proc_step_scope(expansion, target) if target else expansion

    undefined: list[str] = []

    def _keep(name: str) -> bool:
        if name not in undefined:
            undefined.append(name)
        return True

    keep = None if strict else _keep
    for key, dd in _qualified_call_dds(step):
        substitute_dd_statement(
            dd, _scope_for(key.partition(".")[0]), strict=strict, keep_undefined=keep
        )
    for key, value in list(step.parameters.items()):
        if is_exec_override_keyword(key):
            step.parameters[key] = substitute_parameters_dict(
                {key: value},
                _scope_for(key.partition(".")[2]),
                strict=strict,
                keep_undefined=keep,
            )[key]
    if undefined and warnings is not None:
        names = ", ".join(f"&{name}" for name in undefined)
        warnings.append(
            f"EXEC {step.name or 'PROC'}: undefined symbol(s) {names} in its "
            f"overrides of PROC {procedure.name} left as written"
        )


def _qualified_call_dds(step: Step) -> list[tuple[str, DDStatement]]:
    """Every DD coded under PROC call *step*, keyed ``PROCSTEP.DDNAME``.

    Unqualified DDs (added to the first procstep) get an empty procstep.
    """
    return [
        *((f".{dd.name or ''}", dd) for dd in step.dd_statements),
        *step.dd_overrides.items(),
        *(
            (key, dd)
            for key, dds in step.dd_override_concatenations.items()
            for dd in dds
        ),
    ]


def _proc_step_scope(expansion_scope: SymbolScope, proc_step: Step) -> SymbolScope:
    """Return *expansion_scope* with the PROC SETs in effect at *proc_step*.

    A SET inside a procedure is in effect from where it is coded: a step read
    before a later SET redefined a symbol keeps the earlier value
    (``Step.set_symbols``). Symbols it has no snapshot for still resolve
    against the procedure's final SET table.
    """
    if proc_step.set_symbols is None:
        return expansion_scope
    return SymbolScope(
        set_symbols={**expansion_scope.set_symbols, **proc_step.set_symbols},
        proc_params=expansion_scope.proc_params,
        exec_overrides=expansion_scope.exec_overrides,
        system_provider=expansion_scope.system_provider,
    )


_WHOLE_SYMBOL_RE = re.compile(r"&([A-Z0-9@#$]+)\.?")


def _whole_symbol_list(value: Any, scope: SymbolScope) -> list[Any] | None:
    """If *value* is exactly one symbol whose value is a list, return a copy.

    ``DISP=&DP`` with ``DP=(NEW,CATLG)`` must become the same
    ``["NEW", "CATLG"]`` list that coding ``DISP=(NEW,CATLG)`` produces.
    """
    if not isinstance(value, str):
        return None
    match = _WHOLE_SYMBOL_RE.fullmatch(value)
    if match is None:
        return None
    raw = scope.raw_value(match.group(1))
    if isinstance(raw, (list, tuple)):
        return deepcopy(list(raw))
    return None


def substitute_parameters_dict(
    parameters: dict[str, Any],
    scope: SymbolScope,
    strict: bool = False,
    allow_undefined: bool = False,
    warnings: list[str] | None = None,
    collapse_double_amp: bool = True,
    keep_undefined: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """
    Substitute symbols in parameter dictionary.

    Args:
        parameters: Parameter dictionary
        scope: Symbol resolution scope
        strict: Whether to raise on undefined symbols
        allow_undefined: If True, leave undefined symbols as-is instead of
            blanking them to an empty string
        warnings: Optional list to receive a message whenever an undefined
            symbol is silently resolved to an empty string (ignored when
            allow_undefined=True, since nothing is blanked in that mode)
        collapse_double_amp: If False, leave a literal "&&" untouched instead
            of collapsing it to "&" (see substitute_symbols()).

    Returns:
        Dictionary with substituted values
    """
    result: dict[str, Any] = {}

    for key, value in parameters.items():
        whole = _whole_symbol_list(value, scope)
        if whole is not None:
            # DISP=&DP with DP=(NEW,CATLG): keep the list, exactly as if
            # DISP=(NEW,CATLG) had been coded, substituting inside it.
            value = whole
        if isinstance(value, str):
            result[key] = substitute_symbols(
                value,
                scope,
                strict=strict,
                allow_undefined=allow_undefined,
                warnings=warnings,
                collapse_double_amp=collapse_double_amp,
                keep_undefined=keep_undefined,
            )
        elif isinstance(value, (list, tuple)):
            result[key] = [
                substitute_symbols(
                    str(v),
                    scope,
                    strict=strict,
                    allow_undefined=allow_undefined,
                    warnings=warnings,
                    collapse_double_amp=collapse_double_amp,
                    keep_undefined=keep_undefined,
                )
                if isinstance(v, str)
                else v
                for v in value
            ]
        elif isinstance(value, dict):
            result[key] = substitute_parameters_dict(
                value,
                scope,
                strict=strict,
                allow_undefined=allow_undefined,
                warnings=warnings,
                collapse_double_amp=collapse_double_amp,
                keep_undefined=keep_undefined,
            )
        else:
            result[key] = value

    return result


def _strip_empty_member(dataset_name: str) -> str:
    """Drop a trailing empty member reference left by an elided symbol.

    ``DSN=LIB(&MEM)`` with ``&MEM`` undefined elides to ``LIB()`` after
    substitution. An empty member is meaningless and pollutes downstream
    dataset inventories, so collapse it to the bare PDS name. Non-empty
    members (``LIB(MEMBER)``) and generations (``GDG(+1)``) are left intact.
    """
    if dataset_name.endswith(")"):
        open_idx = dataset_name.rfind("(")
        if open_idx != -1 and not dataset_name[open_idx + 1 : -1].strip():
            return dataset_name[:open_idx]
    return dataset_name


_DSN_KEYS = ("DSN", "DSNAME")

# A dataset name that is one bare ``&NAME`` reference, optionally with a member
# or generation (``&TEMP``, ``&TEMP(MEM)``). With no symbol NAME defined it is
# the single-ampersand spelling of a temporary dataset name, not a symbol to
# blank out. Strict symbol mode still reports it as undefined.
_BARE_SYMBOL_DSN_RE = re.compile(r"&([A-Z0-9@#$]+)(?:\([^()]*\))?")


def _dsn_keep_undefined(
    dataset_name: str, keep_undefined: Callable[[str], bool] | None, strict: bool
) -> Callable[[str], bool] | None:
    """Extend *keep_undefined* to keep an undefined bare-``&NAME`` dataset name."""
    if strict or not isinstance(dataset_name, str):
        return keep_undefined
    match = _BARE_SYMBOL_DSN_RE.fullmatch(dataset_name)
    if match is None:
        return keep_undefined
    temp_name = match.group(1)

    def _keep(name: str) -> bool:
        return name == temp_name or (
            keep_undefined is not None and keep_undefined(name)
        )

    return _keep


def substitute_dd_statement(
    dd: DDStatement,
    scope: SymbolScope,
    strict: bool = False,
    allow_undefined: bool = False,
    warnings: list[str] | None = None,
    collapse_double_amp: bool = True,
    keep_undefined: Callable[[str], bool] | None = None,
) -> None:
    """
    Substitute symbols in DD statement (in-place).

    Args:
        dd: DD statement to process
        scope: Symbol resolution scope
        strict: Whether to raise on undefined symbols
        allow_undefined: If True, leave undefined symbols as-is instead of
            blanking them to an empty string.
        warnings: Optional list to receive a message (with DD name/line
            context) whenever an undefined symbol silently resolves to an
            empty string in this DD's dataset name or disposition. Ignored
            when allow_undefined=True, since nothing is blanked in that mode.
        collapse_double_amp: If False, leave a literal "&&" untouched instead
            of collapsing it to "&". The dataset name (``dataset_name`` and
            the ``DSN`` / ``DSNAME`` parameters) never collapses: there
            ``&&NAME`` is the temporary-dataset idiom (see
            ``DDStatement.is_temporary()``), not an escaped ampersand.
    """
    local_warnings: list[str] | None = [] if warnings is not None else None

    # Substitute dataset name, remembering the name as first coded. A
    # non-text name (a DDStatement built directly with a list) is left alone.
    if dd.dataset_name and isinstance(dd.dataset_name, str):
        if dd.coded_dataset_name is None and "&" in dd.dataset_name:
            dd.coded_dataset_name = dd.dataset_name
        dd.dataset_name = substitute_symbols(
            dd.dataset_name,
            scope,
            strict=strict,
            allow_undefined=allow_undefined,
            warnings=local_warnings,
            collapse_double_amp=False,
            keep_undefined=_dsn_keep_undefined(dd.dataset_name, keep_undefined, strict),
        )
        dd.dataset_name = _strip_empty_member(dd.dataset_name)

    # Substitute disposition. DISP=(&STATUS,CATLG,DELETE) parses to a list,
    # not a plain string, so each element needs its own substitution pass —
    # substitute_symbols() is a no-op for non-str input and would otherwise
    # silently skip symbols in list-valued dispositions.
    whole_disposition = _whole_symbol_list(dd.disposition, scope)
    if whole_disposition is not None:
        dd.disposition = whole_disposition
    if dd.disposition:
        if isinstance(dd.disposition, list):
            dd.disposition = [
                substitute_symbols(
                    v,
                    scope,
                    strict=strict,
                    allow_undefined=allow_undefined,
                    warnings=local_warnings,
                    collapse_double_amp=collapse_double_amp,
                    keep_undefined=keep_undefined,
                )
                if isinstance(v, str)
                else v
                for v in dd.disposition
            ]
        else:
            dd.disposition = substitute_symbols(
                dd.disposition,
                scope,
                strict=strict,
                allow_undefined=allow_undefined,
                warnings=local_warnings,
                collapse_double_amp=collapse_double_amp,
                keep_undefined=keep_undefined,
            )

    # Substitute all parameters. DSN= / DISP= usually repeat dataset_name /
    # disposition above, so a message already recorded there is not repeated.
    original_parameters = dd.parameters
    param_warnings: list[str] | None = [] if local_warnings is not None else None
    dd.parameters = substitute_parameters_dict(
        {k: v for k, v in original_parameters.items() if k not in _DSN_KEYS},
        scope,
        strict=strict,
        allow_undefined=allow_undefined,
        warnings=param_warnings,
        collapse_double_amp=collapse_double_amp,
        keep_undefined=keep_undefined,
    )
    # The dataset-name parameters keep "&&" (temporary dataset), matching
    # dataset_name above.
    for key in _DSN_KEYS:
        if key not in original_parameters:
            continue
        value = original_parameters[key]
        if isinstance(value, str):
            value = _strip_empty_member(
                substitute_symbols(
                    value,
                    scope,
                    strict=strict,
                    allow_undefined=allow_undefined,
                    warnings=param_warnings,
                    collapse_double_amp=False,
                    keep_undefined=_dsn_keep_undefined(value, keep_undefined, strict),
                )
            )
        else:
            value = substitute_parameters_dict(
                {key: value},
                scope,
                strict=strict,
                allow_undefined=allow_undefined,
                warnings=param_warnings,
                collapse_double_amp=False,
                keep_undefined=keep_undefined,
            )[key]
        dd.parameters[key] = value
    # Restore coded key order (DSN keys were substituted separately).
    dd.parameters = {k: dd.parameters[k] for k in original_parameters}
    if local_warnings is not None and param_warnings:
        local_warnings.extend(m for m in param_warnings if m not in local_warnings)

    # Note: inline_data intentionally NOT substituted (data content preserved)

    if warnings is not None and local_warnings:
        for msg in local_warnings:
            warnings.append(
                f"Line {dd.line_number}: DD {dd.name or '(unnamed)'}: {msg}"
            )


# DD parameters that each name the DD's data source. They are mutually
# exclusive, so an override that codes any of them displaces all of them on the
# overridden DD (e.g. DSN= on the override nullifies a PROC DD's DUMMY).
# ``_pos_0`` is the positional DUMMY / * / DATA operand; a bare ``DD *`` or
# ``DD DATA`` is stored as a ``{"*": True}`` / ``{"DATA": True}`` flag instead.
_DD_INSTREAM_MARKERS = frozenset({"*", "DATA"})
_DD_SOURCE_KEYS = frozenset({"DSN", "DSNAME", "SYSOUT", "PATH", "_pos_0"}).union(
    _DD_INSTREAM_MARKERS
)


def _is_instream_dd(params: dict[str, Any]) -> bool:
    """Return True if *params* describe an in-stream (``DD *`` / ``DATA``) DD."""
    if _DD_INSTREAM_MARKERS.intersection(params):
        return True
    return str(params.get("_pos_0", "")).upper() in _DD_INSTREAM_MARKERS


def _dcb_subparameters(value: Any) -> list[str]:
    """Return a DCB value as its list of subparameters (``RECFM=FB``, ...)."""
    if isinstance(value, list):
        return [jcl_value_text(v) for v in value]
    return [jcl_value_text(value)]


def _merge_dcb_override(base_value: Any, override_value: Any) -> Any:
    """Merge an overriding ``DCB=`` onto the PROC DD's ``DCB=``.

    z/OS keeps every DCB subparameter the override does not code: overriding
    ``DCB=(RECFM=FB,LRECL=80,BLKSIZE=800)`` with ``DCB=BLKSIZE=0`` yields
    ``DCB=(RECFM=FB,LRECL=80,BLKSIZE=0)``. A subparameter coded with no value
    (``BLKSIZE=``) is nullified. A positional model / referback
    (``DCB=(A.B,...)`` / ``DCB=*.STEP.DD``) coded on the override replaces the
    PROC DD's one.
    """
    base_items = _dcb_subparameters(base_value)
    override_items = _dcb_subparameters(override_value)

    override_positionals = [item for item in override_items if "=" not in item]
    positionals = override_positionals or [
        item for item in base_items if "=" not in item
    ]
    keywords: dict[str, str] = {}
    for item in base_items + override_items:
        if "=" not in item:
            continue
        name, _, sub_value = item.partition("=")
        name = name.strip().upper()
        if sub_value == "":
            keywords.pop(name, None)
        else:
            keywords[name] = sub_value

    merged = positionals + [f"{name}={sub}" for name, sub in keywords.items()]
    if len(merged) == 1 and not isinstance(override_value, list):
        return merged[0]
    return merged


def _merge_dd_override(base: DDStatement, override: DDStatement) -> DDStatement:
    """Return *base* modified by *override* per z/OS DD-override semantics.

    An overriding DD statement changes only the parameters it codes: every
    other parameter of the PROC's DD is kept, and a parameter coded with no
    value (``UNIT=``) is nullified. An in-stream override (``DD *`` /
    ``DD DATA``) supplies its own data and replaces the DD outright.
    """
    clone = deepcopy(override)
    if _is_instream_dd(override.parameters):
        return clone

    params = deepcopy(base.parameters)
    if _DD_SOURCE_KEYS.intersection(override.parameters):
        for key in _DD_SOURCE_KEYS:
            params.pop(key, None)
    else:
        # The data source (and so the coded dataset name) is the PROC DD's.
        clone.coded_dataset_name = base.coded_dataset_name
    for key, value in clone.parameters.items():
        if value == "":
            params.pop(key, None)
        elif key == "DCB" and "DCB" in params:
            params[key] = _merge_dcb_override(params["DCB"], value)
        else:
            params[key] = value

    dataset_name = params.get("DSN")
    if dataset_name is None:
        dataset_name = params.get("DSNAME")
    clone.parameters = params
    clone.dataset_name = dataset_name
    clone.disposition = params.get("DISP")
    if _is_instream_dd(params):
        clone.inline_data = base.inline_data
    return clone


# EXEC keyword parameters that an ``EXEC procname`` statement can override on
# the procedure's steps, as ``KEYWORD.procstep=value`` or plain
# ``KEYWORD=value``. Symbolic parameter names can never collide with these.
_EXEC_OVERRIDE_KEYWORDS = frozenset(
    {
        "ACCT",
        "ADDRSPC",
        "CCSID",
        "COND",
        "DPRTY",
        "DYNAMNBR",
        "MEMLIMIT",
        "PARM",
        "PARMDD",
        "PERFORM",
        "RD",
        "REGION",
        "REGIONX",
        "RLSTMOUT",
        "TIME",
        "TVSMSG",
        "TVSAMCOM",
    }
)
# PARM and PARMDD are mutually exclusive: coding one on a step displaces the
# other.
_PARM_KEYWORDS = frozenset({"PARM", "PARMDD"})


def is_exec_override_keyword(key: str) -> bool:
    """Whether *key* of an ``EXEC procname`` statement is a keyword override.

    ``PARM``, ``PARM.PS1``, ``COND.PS2``, ... override the procedure's steps;
    any other key (``HLQ``) assigns a symbolic parameter.
    """
    return key.upper().partition(".")[0] in _EXEC_OVERRIDE_KEYWORDS


_SYMBOL_REFERENCE = re.compile(r"&&|&([A-Z@#$][A-Z0-9@#$]{0,7})", re.IGNORECASE)
_INCLUDE_STATEMENT = re.compile(r"^//\S*\s+INCLUDE\s", re.IGNORECASE | re.MULTILINE)


def _referenced_symbols(value: Any, found: set[str], seen: set[int]) -> None:
    """Add every ``&NAME`` written anywhere in *value* to *found*.

    Walks strings, dicts, lists and the model dataclasses (steps, DDs,
    conditional blocks) a procedure body is made of. ``&&`` is an escaped
    ampersand, not a reference.
    """
    if isinstance(value, str):
        for match in _SYMBOL_REFERENCE.finditer(value):
            if match.group(1):
                found.add(match.group(1).upper())
        return
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, dict):
        for item in value.values():
            _referenced_symbols(item, found, seen)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _referenced_symbols(item, found, seen)
    elif isinstance(value, (Step, DDStatement, ConditionalBlock)):
        for name, item in vars(value).items():
            if name not in ("comments", "inline_data", "original_proc_call"):
                _referenced_symbols(item, found, seen)


def call_override_symbols(call: Step) -> set[str]:
    """Every ``&NAME`` in the overrides coded with PROC call *call*.

    The overriding and added DDs after the call (and their concatenations)
    and the values of its keyword overrides (``PARM.PS1='&X'``) are merged
    into the procedure, so the call's symbolics are substituted there too
    (issue #176).
    """
    found: set[str] = set()
    _referenced_symbols(
        [
            call.dd_statements,
            list(call.dd_overrides.values()),
            list(call.dd_override_concatenations.values()),
            [
                value
                for key, value in call.parameters.items()
                if is_exec_override_keyword(key)
            ],
        ],
        found,
        set(),
    )
    return found


def unused_proc_symbols(
    call: Step, procedure: Procedure, call_references: set[str] | None = None
) -> list[str]:
    """The symbolics PROC call *call* assigns that *procedure* never uses.

    A symbolic coded on ``EXEC procname`` that is neither declared on the
    PROC statement nor referenced as ``&NAME`` in the procedure body is a
    JCL error on z/OS (``IEFC657I THE SYMBOL x WAS NOT USED``), and the
    expansion silently runs with the PROC's defaults (issue #172). EXEC
    keyword overrides (``PARM``, ``COND.PS1``, ...) are not symbolics. A
    reference in the call's overriding or added DDs, or in a keyword
    override's value, counts as a use (issue #176); *call_references* gives
    those references when the call's overrides were already substituted
    (default: :func:`call_override_symbols` of *call*).

    Returns an empty list when the body cannot be fully checked: a procedure
    with no steps (unloaded), or one whose text has an ``INCLUDE`` (its
    members' references are not known before explosion).
    """
    if not procedure.steps:
        return []
    if procedure.source_text and _INCLUDE_STATEMENT.search(procedure.source_text):
        return []
    known = {name.upper() for name in procedure.parameters}
    _referenced_symbols(
        [procedure.steps, procedure.set_statements, procedure.parameters],
        known,
        set(),
    )
    if procedure.source_text:
        _referenced_symbols(procedure.source_text, known, set())
    known |= call_override_symbols(call) if call_references is None else call_references
    return [
        key
        for key in call.parameters
        if not is_exec_override_keyword(key)
        and key.upper() != "PROC"
        and key.upper() not in known
    ]


def _substitute_proc_call_parameters(
    parameters: dict[str, Any],
    scope: SymbolScope,
    strict: bool = False,
    allow_undefined: bool = False,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Substitute symbols in the parameters of an ``EXEC procname`` statement.

    EXEC keyword overrides (``PARM.PS1='A&&B'``) collapse "&&" to "&" like any
    other step parameter; a symbolic value keeps it, because it may carry a
    temporary dataset name (``TMP='&&WORK'``) into the procedure's DDs.
    """
    return {
        key: substitute_parameters_dict(
            {key: value},
            scope,
            strict=strict,
            allow_undefined=allow_undefined,
            warnings=warnings,
            collapse_double_amp=key.upper().partition(".")[0]
            in _EXEC_OVERRIDE_KEYWORDS,
        )[key]
        for key, value in parameters.items()
    }


def _set_exec_keyword(step: Step, keyword: str, value: Any) -> None:
    """Override (or, for an empty value, nullify) *keyword* on *step*."""
    if keyword in _PARM_KEYWORDS:
        for key in _PARM_KEYWORDS:
            step.parameters.pop(key, None)
    if value == "":
        step.parameters.pop(keyword, None)
    else:
        step.parameters[keyword] = deepcopy(value)


def apply_exec_parameter_overrides(
    expanded_steps: Sequence[Step | ConditionalBlock],
    exec_parameters: dict[str, Any],
    step_name_prefix: str,
    warnings: list[str] | None = None,
) -> None:
    """Apply EXEC keyword overrides from an ``EXEC procname`` statement.

    z/OS semantics for an EXEC statement that calls a procedure:

    * ``KEYWORD.procstep=value`` overrides (or adds) the keyword on that step
      only; ``KEYWORD.procstep=`` nullifies it.
    * ``PARM=`` / ``PARMDD=`` without a procstep applies to the procedure's
      first step and nullifies PARM/PARMDD on every other step.
    * Every other keyword without a procstep overrides it on every step.
      (``TIME=`` really limits the procedure as a whole; applying it to each
      step is the closest per-step model.)

    Unqualified overrides are applied before qualified ones.
    """
    steps = list(iter_execution_steps(list(expanded_steps)))
    if not steps:
        return
    by_name = {s.name: s for s in steps if s.name}

    qualified: list[tuple[str, str, Any]] = []
    for key, value in exec_parameters.items():
        keyword, _, procstep = key.upper().partition(".")
        if keyword not in _EXEC_OVERRIDE_KEYWORDS:
            continue
        if procstep:
            qualified.append((keyword, procstep, value))
        elif keyword in _PARM_KEYWORDS:
            _set_exec_keyword(steps[0], keyword, value)
            for other in steps[1:]:
                for parm_key in _PARM_KEYWORDS:
                    other.parameters.pop(parm_key, None)
        else:
            for target in steps:
                _set_exec_keyword(target, keyword, value)

    for keyword, procstep, value in qualified:
        target = by_name.get(f"{step_name_prefix}.{procstep}")
        if target is None:
            if warnings is not None:
                warnings.append(
                    f"EXEC {step_name_prefix}: {keyword}.{procstep} names no step "
                    "of the procedure; override ignored"
                )
            continue
        _set_exec_keyword(target, keyword, value)


def _override_concatenation_members(
    dd_statements: list[DDStatement],
    index: int,
    member_overrides: Sequence[DDStatement],
) -> None:
    """Apply *member_overrides* to the concatenation whose named DD is at *index*.

    The first override applies to the 2nd member of the concatenation (the
    first unnamed DD after the named one), and so on. An override with no
    operands (``//  DD``) leaves its member unchanged; overrides beyond the
    last member add new members to the end of the concatenation.
    """
    position = index + 1
    for member_override in member_overrides:
        is_member = position < len(dd_statements) and not dd_statements[position].name
        if not is_member:
            dd_statements.insert(position, deepcopy(member_override))
        elif member_override.parameters:
            dd_statements[position] = _merge_dd_override(
                dd_statements[position], member_override
            )
        position += 1


def apply_dd_overrides(
    expanded_steps: Sequence[Step | ConditionalBlock],
    dd_overrides: dict[str, DDStatement],
    step_name_prefix: str,
    concatenations: dict[str, list[DDStatement]] | None = None,
    proc_name: str | None = None,
    warnings: list[str] | None = None,
) -> None:
    """
    Apply DD overrides to expanded steps.

    Args:
        expanded_steps: List of expanded steps; steps nested in a PROC's
            ``IF``/``ELSE`` blocks are overridden too
        dd_overrides: Dictionary of qualified DD name -> override DDStatement
        step_name_prefix: Prefix used for step names
        concatenations: Qualified DD name -> the unnamed DDs coded after that
            override, overriding the later members of its concatenation
            (``Step.dd_override_concatenations``)
        proc_name: Name of the procedure that was expanded, for warnings
        warnings: Optional list to receive ``DD override X.D names no step
            in PROC P`` when an override's qualifier matches no step of the
            procedure (or has more than three parts); the override is
            ignored (#64)
    """
    concatenations = concatenations or {}
    # A PROC step inside an IF/THEN/ELSE block is still a PROCSTEP an override
    # can name; walking only the top level crashed on the ConditionalBlock.
    steps = list(iter_execution_steps(list(expanded_steps)))
    for override_key, override_dd in dd_overrides.items():
        # Two-part  "PROCSTEP.DDNAME"          -> step prefix.PROCSTEP / DD DDNAME
        # Three-part "PROCSTEP.INNERST.DDNAME" -> forwarded to prefix.PROCSTEP
        #   (a nested PROC invocation whose internal step name is needed)
        parts = override_key.split(".")
        members = concatenations.get(override_key)
        if len(parts) == 2:
            applied = _apply_two_part_override(
                steps,
                f"{step_name_prefix}.{parts[0]}",
                parts[1],
                override_dd,
                members or [],
            )
        elif len(parts) == 3:
            applied = _forward_three_part_override(
                steps, f"{step_name_prefix}.{parts[0]}", parts, override_dd, members
            )
        else:
            # Four or more parts: deeper than this model resolves.
            applied = False
        if not applied and warnings is not None:
            warnings.append(
                f"DD override {override_key} names no step in PROC "
                f"{proc_name or step_name_prefix}"
            )


def _apply_two_part_override(
    steps: list[Step],
    qualified_step: str,
    target_dd: str,
    override_dd: DDStatement,
    members: list[DDStatement],
) -> bool:
    """Merge a ``PROCSTEP.DDNAME`` override into *qualified_step*.

    Returns ``False`` when no step has that name.
    """
    step = next((s for s in steps if s.name == qualified_step), None)
    if step is None:
        return False
    # override_dd.name is the raw statement name field, i.e. the *qualified*
    # key ("PROCSTEP.DDNAME") -- normalize it to the plain DD name so the
    # resulting DD looks the same as one coded directly on the step.
    for i, dd in enumerate(step.dd_statements):
        if dd.name == target_dd:
            merged = _merge_dd_override(dd, override_dd)
            merged.name = target_dd
            step.dd_statements[i] = merged
            _override_concatenation_members(step.dd_statements, i, members)
            return True
    # No DD named target_dd on this step -- per z/OS semantics a
    # PROCSTEP.DDNAME override with no matching DD *adds* one, same as the
    # unqualified form (apply_unqualified_dd_overrides).
    clone = deepcopy(override_dd)
    clone.name = target_dd
    step.dd_statements.append(clone)
    step.dd_statements.extend(deepcopy(members))
    return True


def _forward_three_part_override(
    steps: list[Step],
    qualified_outer: str,
    parts: list[str],
    override_dd: DDStatement,
    members: list[DDStatement] | None,
) -> bool:
    """Hand an ``OUTERSTEP.INNERSTEP.DDNAME`` override to the nested PROC call.

    The outer expansion has not yet expanded the inner PROC, so the step
    ``prefix.OUTERSTEP.INNERSTEP`` does not exist yet. The override is stored
    on ``prefix.OUTERSTEP`` (still a PROC invocation) as the two-part key
    ``INNERSTEP.DDNAME``, and applied when the recursive ``_explode_step``
    expands the inner PROC. Returns ``False`` when no step has that name or
    it runs a program (there is no inner PROC step to name).
    """
    step = next((s for s in steps if s.name == qualified_outer), None)
    if step is None or not step.is_procedure:
        return False
    two_part_key = f"{parts[1]}.{parts[2]}"
    step.dd_overrides[two_part_key] = deepcopy(override_dd)
    if members is not None:
        step.dd_override_concatenations[two_part_key] = deepcopy(members)
    return True


def apply_unqualified_dd_overrides(
    expanded_steps: Sequence[Step | ConditionalBlock],
    override_dds: list[DDStatement],
) -> None:
    """Merge unqualified DD overrides onto the procedure's first step.

    A DD coded directly under an ``EXEC PROC=`` statement *without* a
    ``PROCSTEP.`` qualifier is, per z/OS semantics, an override/addition to the
    **first step** of the invoked procedure: a DD whose name matches one already
    on that step replaces it; a DD with a new name is appended. The parser stores
    these on the ``EXEC PROC=`` step's own ``dd_statements`` (qualified overrides
    go to ``dd_overrides`` instead), so without this merge they are silently
    dropped during explosion.

    Args:
        expanded_steps: Steps produced by expanding the procedure invocation.
        override_dds: The ``EXEC PROC=`` step's own (unqualified) DD statements.
    """
    if not override_dds:
        return

    # The first step in source order, even when it sits inside an IF block.
    first_step = next(iter_execution_steps(list(expanded_steps)), None)
    if first_step is None:
        return

    # Group each named override with the unnamed DDs coded right after it:
    # those override members 2..n of the named DD's concatenation, exactly
    # like the members of a qualified PROCSTEP.DDNAME override.
    groups: list[tuple[DDStatement, list[DDStatement]]] = []
    for override_dd in override_dds:
        if not override_dd.name and groups:
            groups[-1][1].append(override_dd)
        else:
            groups.append((override_dd, []))

    dd_statements = first_step.dd_statements
    for override_dd, members in groups:
        existing = next(
            (
                i
                for i, dd in enumerate(dd_statements)
                if override_dd.name and dd.name == override_dd.name
            ),
            None,
        )
        if existing is not None:
            dd_statements[existing] = _merge_dd_override(
                dd_statements[existing], override_dd
            )
            _override_concatenation_members(dd_statements, existing, members)
        else:
            dd_statements.append(deepcopy(override_dd))
            dd_statements.extend(deepcopy(members))


def explode_job(
    job: Job,
    proc_loader: ProcedureLoader | None = None,
    max_depth: int = 10,
    max_steps: int = DEFAULT_MAX_STEPS,
    audit: bool = True,
    system_provider: SystemSymbolProvider | None = None,
    strict_symbols: bool = False,
    include_loader: IncludeMemberLoader | None = None,
) -> Job:
    """
    Explode all procedure invocations in a job.

    Creates a new Job instance with all PROC invocations expanded into
    their constituent steps with symbolic parameters fully resolved.

    Args:
        job: Original job with procedure invocations
        proc_loader: Procedure loader (defaults to inline + JCLLIB)
        max_depth: Maximum procedure nesting depth
        max_steps: Maximum total expanded steps (0 = unlimited; default
                   :data:`DEFAULT_MAX_STEPS`). Checked as each step is
                   produced, so a PROC fan-out stops at the limit instead of
                   being built in full first.
        audit: Whether to generate audit logs
        system_provider: System symbol provider (defaults to mock provider)
        strict_symbols: If True, raise errors for undefined symbols
        include_loader: Loader for the ``// INCLUDE MEMBER=`` statements of
                   a cataloged (external) PROC, searched in the job's JCLLIB
                   order; defaults to the loader :func:`parse_jcl` read the
                   job's own INCLUDEs with.  A member it cannot find is a
                   job warning.

    Returns:
        New Job instance with exploded procedures

    Raises:
        ExplosionDepthError: If nesting exceeds max_depth
        JCLStructureError: If max_steps > 0 and the expanded step count exceeds it
        CircularProcedureError: If circular references detected
        ProcedureNotFoundError: If referenced procedure not found
        UndefinedSymbolError: If strict_symbols=True and symbol undefined
    """
    # Loader precedence: the caller's, else the one parse_jcl() attached for
    # the job's JCLLIB / proc_base_path (so an external PROC called from inside
    # another PROC or an IF block is found where the top-level ones were),
    # else the default chain. Inline procedures always win.
    include_expander = _IncludeExpandingLoader(
        proc_loader if proc_loader is not None else _job_proc_loader(job),
        include_loader or _job_include_loader(job),
    )
    proc_loader = include_expander

    # Get system provider
    system_provider = system_provider or get_default_provider()

    # Create base symbol scope
    base_scope = SymbolScope(
        set_symbols=job.set_statements.copy(), system_provider=system_provider
    )

    # Track explosion metadata
    explosion_audit: list[ExplosionRecord] = []
    explosion_map: dict[str, ProcExpansionInfo] = {}
    # Symbol-substitution diagnostics accumulated during explosion (e.g. an
    # undefined &SYMBOL only resolvable inside a PROC body, against PROC
    # defaults/EXEC overrides/system symbols -- parse_jcl() never sees these,
    # since it doesn't expand PROCs). Merged onto exploded_job.warnings below.
    explosion_warnings: list[str] = []

    # Mutable step counter shared across all _process_steps recursions.
    # Using a list (not int) so the nested closure can mutate it.
    _step_count: list[int] = [0]

    def _check_step_limit(new_steps: int) -> None:
        """Raise JCLStructureError if adding new_steps would exceed max_steps."""
        if max_steps > 0:
            _step_count[0] += new_steps
            if _step_count[0] > max_steps:
                raise JCLStructureError(
                    f"Procedure explosion produced more than {max_steps} steps "
                    f"(currently {_step_count[0]}). Use max_steps= to raise the "
                    f"limit or check for runaway PROC expansion."
                )

    def _count_one_step() -> None:
        _check_step_limit(1)

    # Process steps
    def _process_steps(steps_list):
        result = []
        for step in steps_list:
            if isinstance(step, ConditionalBlock):
                result.append(_clone_conditional(step, _process_steps))
                continue
            step_scope = _job_step_scope(job, step, base_scope)
            if step.is_procedure:
                # The symbolic values of an ``EXEC procname`` (HLQ=&SYSUID)
                # belong to the job: resolve the job's SET and system symbols
                # in them, leaving any other symbol as written. A symbolic
                # value keeps "&&": it may carry a temporary dataset name
                # (TMP='&&WORK'). Its keyword overrides (PARM.PS1='&HLQ') and
                # DDs are merged into the procedure and resolved in its scope
                # by _explode_step (issue #126).
                step = _clone_step_for_explosion(step)
                _resolve_symbolic_values(step, step_scope)
                # Expand procedure
                expanded = _explode_step(
                    step=step,
                    proc_loader=proc_loader,
                    base_scope=step_scope,
                    call_chain=[],
                    call_chain_upper=frozenset(),
                    depth=0,
                    max_depth=max_depth,
                    audit_records=explosion_audit if audit else None,
                    expansion_map=explosion_map,
                    strict_symbols=strict_symbols,
                    jcllib_order=job.jcllib_order or None,
                    warnings=explosion_warnings,
                    on_step=_count_one_step,
                    call_scope=step_scope,
                )
                result.extend(expanded)
            else:
                # Regular step - just substitute symbols
                _check_step_limit(1)
                result.append(
                    _substituted_plain_step(
                        step, step_scope, strict_symbols, explosion_warnings
                    )
                )
        return result

    exploded_steps = _process_steps(job.steps)

    exploded_job = _exploded_job(job, exploded_steps)

    # Diagnostics raised while substituting symbols during explosion itself
    # (as opposed to during parse_jcl(), already covered by the warnings
    # copy in _exploded_job) -- e.g. an undefined &SYMBOL only resolvable
    # inside a PROC body.
    exploded_job.warnings.extend(explosion_warnings)
    include_expander.record_on(exploded_job)

    # Attach audit metadata
    if audit:
        exploded_job.explosion_audit = explosion_audit
    exploded_job.explosion_map = explosion_map

    logger.info(
        "exploded job %s: %d steps expanded from %d PROC invocation(s)",
        exploded_job.name or "(unnamed)",
        len(exploded_steps),
        len(explosion_map),
    )

    return exploded_job


def _job_step_scope(job: Job, step: Step, base_scope: SymbolScope) -> SymbolScope:
    """The scope of job-level *step*: *base_scope* or the SETs in effect at it.

    A step read before a later SET redefined a symbol resolves it to the
    value in effect at that step (``Step.set_symbols``).
    """
    if step.set_symbols is None:
        return base_scope
    return SymbolScope(
        set_symbols={**job.set_statements, **step.set_symbols},
        system_provider=base_scope.system_provider,
    )


def _job_include_loader(job: Job) -> IncludeMemberLoader:
    """The INCLUDE loader :func:`parse_jcl` attached to *job*, else the
    default filesystem one."""
    from .include_loader import JCLLIBMemberLoader

    loader: IncludeMemberLoader | None = getattr(job, "_include_loader", None)
    return loader if loader is not None else JCLLIBMemberLoader()


class _IncludeExpandingLoader(ProcedureLoader):
    """*inner*, with the INCLUDEs of each external PROC it returns expanded.

    ``parse_jcl`` expands INCLUDEs in the job text, in-stream PROCs
    included, before parsing; a cataloged PROC is read later, so its
    INCLUDEs are expanded here, against the job's JCLLIB order (issue #153).
    :meth:`record_on` adds the members expanded to the exploded job's
    ``includes`` and a warning for each member not found.
    """

    def __init__(
        self, inner: ProcedureLoader, include_loader: IncludeMemberLoader
    ) -> None:
        self._inner = inner
        self._include_loader = include_loader
        self._included: list[str] = []
        self._warnings: list[str] = []
        self._cache: dict[tuple[str, tuple[str, ...] | None], Procedure | None] = {}
        self._call_cache: dict[
            tuple[str, tuple[str, ...] | None, tuple[tuple[str, str], ...]], Procedure
        ] = {}

    def load_procedure(
        self, name: str, libraries: Sequence[str] | None = None
    ) -> Procedure | None:
        key = (name.upper(), tuple(libraries) if libraries else None)
        if key not in self._cache:
            proc = self._inner.load_procedure(name, libraries)
            self._cache[key] = (
                self._expanded(proc, libraries) if proc is not None else None
            )
        return self._cache[key]

    def for_call(
        self,
        proc: Procedure,
        libraries: Sequence[str] | None,
        scope: SymbolScope,
    ) -> Procedure:
        """*proc* as one call of it sees it: INCLUDE member names written as
        symbols (``MEMBER=&MEM``) resolved in that call's *scope* -- EXEC
        values, PROC defaults, SETs (issue #160).

        *proc* is returned as is when no INCLUDE of its text names a symbol.
        """
        text = proc.source_text
        if not text or not _has_symbolic_include(text):
            return proc
        symbols = _flattened_caller_scope(scope).set_symbols
        key = (
            (proc.name or "").upper(),
            tuple(libraries) if libraries else None,
            tuple(sorted(symbols.items())),
        )
        if key not in self._call_cache:
            self._call_cache[key] = self._expanded(proc, libraries, symbols)
        return self._call_cache[key]

    def record_on(self, job: Job) -> None:
        job.warnings.extend(self._warnings)
        job.includes.extend(m for m in self._included if m not in job.includes)

    def _expanded(
        self,
        proc: Procedure,
        libraries: Sequence[str] | None,
        symbols: dict[str, str] | None = None,
    ) -> Procedure:
        """*proc* with the INCLUDEs of its text expanded.

        Without *symbols* (the expansion at load time), an INCLUDE whose
        member is a symbol is left for :meth:`for_call`, without a warning.
        """
        from ._statement_parser import _has_include_statement
        from .include_loader import resolve_includes
        from .proc_loader import _build_procedure_from_content

        text = proc.source_text
        if not proc.is_external or not text or not _has_include_statement(text):
            return proc
        members: list[str] = []
        expanded_text = resolve_includes(
            text,
            self._include_loader,
            list(libraries) if libraries else None,
            _collected=members,
            _symbols=dict(symbols) if symbols is not None else None,
        )
        self._warn_missing(proc, expanded_text, symbols)
        self._included.extend(m for m in members if m not in self._included)
        if not members:
            return proc
        rebuilt = _build_procedure_from_content(expanded_text, proc.name)
        if rebuilt is None:
            return proc
        rebuilt.source_text = text
        return rebuilt

    def _warn_missing(
        self, proc: Procedure, expanded_text: str, symbols: dict[str, str] | None
    ) -> None:
        """Warn once for each INCLUDE left in *expanded_text* (not found)."""
        from .include_loader import (
            _extract_include_member,
            _record_set_symbols,
            _substitute_member_symbols,
        )
        from .utils import split_source_lines

        seen = dict(symbols) if symbols is not None else {}
        for line in split_source_lines(expanded_text):
            _record_set_symbols(line.rstrip(), seen)
            missing = _extract_include_member(line.rstrip())
            if not missing:
                continue
            if "&" in missing:
                if symbols is None:
                    continue
                missing = _substitute_member_symbols(missing, seen)
            warning = (
                f"INCLUDE member {missing} in PROC {proc.name} not found; "
                "its statements are missing from the exploded job"
            )
            if warning not in self._warnings:
                self._warnings.append(warning)


def _has_symbolic_include(text: str) -> bool:
    """Whether an ``// INCLUDE`` statement of *text* names its member by symbol."""
    from .include_loader import _extract_include_member
    from .utils import split_source_lines

    return any(
        "&" in (_extract_include_member(line.rstrip()) or "")
        for line in split_source_lines(text)
    )


def _job_proc_loader(job: Job) -> ProcedureLoader:
    """The loader :func:`explode_job` uses when the caller passes none."""
    job_loader: ProcedureLoader | None = getattr(job, "_proc_loader", None)
    if job_loader is None:
        return create_default_loader(job.procedures)
    return CompositeProcedureLoader([InlineProcedureLoader(job.procedures), job_loader])


def _resolve_symbolic_values(
    step: Step,
    scope: SymbolScope,
    allow_undefined: bool = True,
    strict: bool = False,
    warnings: list[str] | None = None,
) -> None:
    """Resolve the caller's symbols in the symbolic values of PROC call *step*.

    ``HLQ=&SYSUID`` belongs to the caller (the job, or the procedure the
    call is coded in): its symbols resolve against *scope*.  With
    *allow_undefined* an undefined symbol is left as written (a job-level
    call: it may be resolved later); without, it is blanked and reported on
    *warnings*, or raises with *strict* (a call inside a procedure, like the
    rest of that procedure's text).  A symbolic value keeps "&&": it may
    carry a temporary dataset name (``TMP='&&WORK'``).  Keyword overrides
    are left for :func:`_resolve_call_in_proc_scope`.
    """
    symbolic = _substitute_proc_call_parameters(
        {k: v for k, v in step.parameters.items() if not is_exec_override_keyword(k)},
        scope,
        strict=strict,
        allow_undefined=allow_undefined,
        warnings=warnings,
    )
    step.parameters = {k: symbolic.get(k, v) for k, v in step.parameters.items()}


def _substituted_plain_step(
    step: Step, scope: SymbolScope, strict: bool, warnings: list[str]
) -> Step:
    """A copy of the ``EXEC PGM=`` *step* with its symbols substituted."""
    substituted_step = _clone_step_for_explosion(step)
    if substituted_step.program:
        substituted_step.program = substitute_symbols(
            substituted_step.program, scope, strict=strict, warnings=warnings
        )
    substituted_step.parameters = substitute_parameters_dict(
        substituted_step.parameters, scope, strict=strict, warnings=warnings
    )
    for dd in substituted_step.dd_statements:
        substitute_dd_statement(dd, scope, strict=strict, warnings=warnings)
    return substituted_step


def _exploded_job(job: Job, exploded_steps: list[Step | ConditionalBlock]) -> Job:
    """A copy of *job* with *exploded_steps*, keeping its post-parse metadata."""
    exploded_job = Job(
        name=job.name,
        parameters=job.parameters,
        accounting_info=job.accounting_info,
        steps=exploded_steps,
        procedures=job.procedures,  # Keep original procedures
        conditionals=job.conditionals,
        set_statements=job.set_statements,
        jcllib_order=job.jcllib_order,
        includes=job.includes,
        comments=job.comments,
        line_number=job.line_number,
        exported_symbols=set(job.exported_symbols),
        is_procedure_member=job.is_procedure_member,
    )

    # Preserve post-parse analysis metadata so consumers of the exploded job
    # see the same derived state as on the original parsed job.  We copy
    # rather than share so downstream mutation of one doesn't surprise the
    # other.
    for _attr in (
        "unresolved_output_refs",
        "conditional_errors",
        "sql_detections",
        "jes_typed_statements",
        "jes_statements",
        "output_statements",
        "joblib_dds",
        "custom_statements",
        "warnings",
    ):
        src_val = getattr(job, _attr, None)
        if src_val is not None:
            setattr(exploded_job, _attr, deepcopy(src_val))
    return exploded_job


def _apply_call_overrides(
    expanded: list[Step],
    step: Step,
    proc_name: str,
    warnings: list[str] | None,
) -> None:
    """Apply what the ``EXEC procname`` *step* overrides to its *expanded* steps."""
    # EXEC keyword overrides (PARM.PROCSTEP=, COND=, ...).
    apply_exec_parameter_overrides(
        expanded, step.parameters, step.name or "PROC", warnings
    )

    # Qualified DD overrides (PROCSTEP.DDNAME).
    if step.dd_overrides:
        apply_dd_overrides(
            expanded,
            step.dd_overrides,
            step.name or "PROC",
            step.dd_override_concatenations,
            proc_name=proc_name,
            warnings=warnings,
        )

    # Unqualified DD overrides/additions (coded directly under EXEC PROC=,
    # stored on the step's own dd_statements) go onto the procedure's first
    # step.
    if step.dd_statements:
        apply_unqualified_dd_overrides(expanded, step.dd_statements)


def _record_expansion(
    step: Step,
    procedure: Procedure,
    overrides: dict[str, Any],
    expanded: list[Step],
    depth: int,
    audit_records: list[ExplosionRecord] | None,
    expansion_map: dict[str, ProcExpansionInfo],
) -> None:
    """Record the audit entry and expansion-map entry of one PROC expansion."""
    proc_name = step.procedure or procedure.name
    expanded_names = [s.name for s in expanded if hasattr(s, "name") and s.name]
    if audit_records is not None:
        audit_records.append(
            ExplosionRecord(
                step_name=step.name or "UNNAMED",
                proc_name=proc_name,
                parameters=overrides,
                depth=depth,
                timestamp=datetime.now(),  # local time, matches SYSTIME
                expanded_steps=list(expanded_names),
            )
        )

    # resolved_parameters is PROC defaults merged with EXEC overrides
    # (overrides win), giving the full effective parameter set.
    if step.name:
        expansion_map[step.name] = ProcExpansionInfo(
            original_statement=f"EXEC {proc_name}",
            proc_definition=procedure.name,
            resolved_parameters={**procedure.parameters, **overrides},
            source_line_numbers=[step.line_number],
            expanded_step_names=list(expanded_names),
        )


def _load_called_procedure(
    step: Step,
    proc_loader: ProcedureLoader,
    libraries: tuple[str, ...] | None,
    base_scope: SymbolScope,
    call_scope: SymbolScope | None,
    strict_symbols: bool,
    warnings: list[str] | None,
) -> Procedure:
    """The procedure PROC call *step* names, as that call sees it.

    The call's still-unresolved overrides are resolved in the procedure's
    scope when *call_scope* is given (see :func:`_explode_step`), then the
    INCLUDEs naming their member by symbol are expanded in the call's scope.

    Raises:
        ProcedureNotFoundError: If *proc_loader* cannot find the procedure.
    """
    proc_name = step.procedure or ""
    procedure = proc_loader.load_procedure(proc_name, libraries)
    if procedure is None:
        raise ProcedureNotFoundError(proc_name, step.line_number)
    if call_scope is not None:
        _resolve_call_in_proc_scope(
            step, procedure, call_scope, strict_symbols, warnings
        )
    if isinstance(proc_loader, _IncludeExpandingLoader):
        procedure = proc_loader.for_call(
            procedure,
            libraries,
            _expansion_scope(procedure, step.parameters, base_scope),
        )
    return procedure


def _explode_step(
    step: Step,
    proc_loader: ProcedureLoader,
    base_scope: SymbolScope,
    call_chain: list[str],
    depth: int,
    max_depth: int,
    audit_records: list[ExplosionRecord] | None,
    expansion_map: dict[str, ProcExpansionInfo],
    strict_symbols: bool,
    jcllib_order: list[str] | None = None,
    call_chain_upper: frozenset | None = None,
    warnings: list[str] | None = None,
    on_step: Callable[[], None] | None = None,
    call_scope: SymbolScope | None = None,
) -> list[Step]:
    """
    Recursively explode a single step.

    Args:
        step: Step to explode
        proc_loader: Procedure loader
        base_scope: Base symbol scope
        call_chain: Current procedure call chain (list, for audit purposes)
        depth: Current nesting depth
        max_depth: Maximum allowed depth
        audit_records: List to append audit records (if auditing)
        expansion_map: Dictionary to populate with expansion info
        strict_symbols: Whether to enforce strict symbol resolution
        jcllib_order: JCLLIB library order for external PROC loading
        call_chain_upper: Frozenset of uppercased call chain names (O(1) membership);
                          computed from call_chain if not provided (backward-compat).
        warnings: List to append symbol-substitution diagnostics to (e.g. an
                  undefined &SYMBOL referenced inside the PROC body). None
                  means diagnostics are discarded, matching audit_records.
        on_step: Called once for every plain (non-PROC) step this produces,
                 before it is added, at every nesting level -- the hook
                 ``explode_job`` enforces ``max_steps`` through, so a fan-out
                 is stopped while it is being built.
        call_scope: When given, *step*'s keyword overrides and DDs are
                 still unresolved: resolve them in the called procedure's
                 scope first, with *call_scope* -- the scope of the code
                 that calls it -- as the fallback
                 (:func:`_resolve_call_in_proc_scope`).

    Returns:
        List of exploded steps
    """
    # Backfill call_chain_upper if not provided (backward-compatible callers)
    if call_chain_upper is None:
        call_chain_upper = frozenset(p.upper() for p in call_chain)

    # Check depth limit
    if depth > max_depth:
        logger.debug(
            "explosion depth limit exceeded: depth %d > max %d (chain=%s)",
            depth,
            max_depth,
            call_chain,
        )
        raise ExplosionDepthError(depth, max_depth, call_chain)

    proc_name = step.procedure
    if not proc_name:
        if on_step is not None:
            on_step()
        return [step]

    logger.debug("expanding PROC %s at depth %d", proc_name, depth)

    # Check for circular references (O(1) with frozenset)
    detect_circular_refs(proc_name, call_chain, call_chain_upper)

    # Load procedure definition. The same JCLLIB ORDER is threaded through every
    # nesting level so an external PROC invoked from inside another PROC is found
    # against the job's library order. Pass an immutable tuple: loaders key their
    # caches on the library list, so a hashable value keeps that contract safe.
    _libs = tuple(jcllib_order) if jcllib_order else None
    # Read before loading resolves the call's overrides (issue #176).
    call_references = call_override_symbols(step)
    procedure = _load_called_procedure(
        step, proc_loader, _libs, base_scope, call_scope, strict_symbols, warnings
    )

    # Extract parameter overrides from step
    overrides = step.parameters.copy()

    # Expand this procedure. The overrides of a call nested in it are
    # resolved below, in the PROC that call names (nested_call_scopes).
    nested_call_scopes: dict[int, SymbolScope] = {}
    expanded = expand_proc_invocation(
        step=step,
        procedure=procedure,
        overrides=overrides,
        scope=base_scope,
        step_prefix=step.name,
        strict=strict_symbols,
        warnings=warnings,
        nested_call_scopes=nested_call_scopes,
    )

    _apply_call_overrides(expanded, step, procedure.name or proc_name, warnings)
    unused = unused_proc_symbols(step, procedure, call_references)
    if unused and warnings is not None:
        warnings.append(
            f"EXEC {step.name or 'PROC'}: symbol(s) {', '.join(unused)} not used "
            f"by PROC {procedure.name or proc_name} (IEFC657I); its defaults apply"
        )
    _record_expansion(
        step, procedure, overrides, expanded, depth, audit_records, expansion_map
    )

    # Recursively explode any nested procedure calls
    new_call_chain = call_chain + [proc_name]
    new_call_chain_upper = call_chain_upper | {proc_name.upper()}

    def _explode_nested(steps_list):
        result = []
        for s in steps_list:
            if isinstance(s, ConditionalBlock):
                result.append(_clone_conditional(s, _explode_nested))
            elif s.is_procedure:
                # Nested procedure - recurse
                nested = _explode_step(
                    step=s,
                    proc_loader=proc_loader,
                    base_scope=base_scope,
                    call_chain=new_call_chain,
                    call_chain_upper=new_call_chain_upper,
                    depth=depth + 1,
                    max_depth=max_depth,
                    audit_records=audit_records,
                    expansion_map=expansion_map,
                    strict_symbols=strict_symbols,
                    jcllib_order=jcllib_order,
                    warnings=warnings,
                    on_step=on_step,
                    call_scope=_flattened_caller_scope(nested_call_scopes[id(s)]),
                )
                result.extend(nested)
            else:
                if on_step is not None:
                    on_step()
                result.append(s)
        return result

    return _explode_nested(expanded)
