"""
Dynamic procedure explosion engine for JCL parsing.

Implements symbolic parameter substitution and procedure expansion with
support for nested procedures, circular dependency detection, and audit logging.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from copy import deepcopy

from .model import Job, Step, DDStatement, Procedure, ConditionalBlock
from .errors import (
    UndefinedSymbolError,
    ExplosionDepthError,
    CircularProcedureError,
    ProcedureNotFoundError,
)
from .proc_loader import ProcedureLoader, create_default_loader
from .system_symbols import SystemSymbolProvider, get_default_provider


# Single-pass pattern: matches && (escaped ampersand) OR &SYMBOL with optional trailing period
_SYMBOL_SUB_PATTERN = re.compile(r"&&|&([A-Z0-9@#$]+)\.?")


@dataclass
class SymbolScope:
    """
    Symbol resolution scope for parameter substitution.

    Manages symbol precedence: EXEC overrides > PROC defaults > SET statements > System symbols
    """

    set_symbols: Dict[str, str] = field(default_factory=dict)
    proc_params: Dict[str, Any] = field(default_factory=dict)
    exec_overrides: Dict[str, Any] = field(default_factory=dict)
    system_provider: Optional[SystemSymbolProvider] = None

    def resolve(self, symbol_name: str, strict: bool = False) -> Optional[str]:
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
            return str(value) if value is not None else None

        # 2. PROC parameters (default values)
        if symbol_upper in self.proc_params:
            value = self.proc_params[symbol_upper]
            return str(value) if value is not None else None

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
    parameters: Dict[str, Any]
    depth: int
    timestamp: datetime
    expanded_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
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
    resolved_parameters: Dict[str, Any]
    source_line_numbers: List[int]
    expanded_step_names: List[str]


def _make_replacer(scope: "SymbolScope", strict: bool, allow_undefined: bool):
    """Create a regex replacer function for symbol substitution."""

    def _replacer(m: re.Match) -> str:
        if m.group(0) == "&&":
            return "&"
        symbol_name = m.group(1)
        value = scope.resolve(symbol_name, strict=strict)
        if value is None:
            if allow_undefined:
                return m.group(0)  # leave as-is
            if strict:
                raise UndefinedSymbolError(symbol_name)
            return ""
        return value

    return _replacer


def substitute_symbols(
    text: str, scope: "SymbolScope", strict: bool = False, allow_undefined: bool = False
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

    Returns:
        Text with symbols substituted

    Raises:
        UndefinedSymbolError: If strict=True and symbol undefined
    """
    if not text or not isinstance(text, str):
        return text
    return _SYMBOL_SUB_PATTERN.sub(_make_replacer(scope, strict, allow_undefined), text)


def detect_circular_refs(
    proc_name: str,
    call_chain: List[str],
    call_chain_upper: Optional[frozenset] = None,
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
        raise CircularProcedureError(proc_name, call_chain + [proc_name])


def expand_proc_invocation(
    step: Step,
    procedure: Procedure,
    overrides: Dict[str, Any],
    scope: SymbolScope,
    step_prefix: Optional[str] = None,
) -> List[Step]:
    """
    Expand a single procedure invocation into steps.

    Args:
        step: Original EXEC step calling the procedure
        procedure: Procedure definition to expand
        overrides: Parameter overrides from EXEC statement
        scope: Symbol resolution scope
        step_prefix: Optional prefix for qualified step names

    Returns:
        List of expanded steps with substituted parameters
    """
    # Create new scope with overrides
    expansion_scope = SymbolScope(
        set_symbols=scope.set_symbols.copy(),
        proc_params=procedure.parameters.copy(),
        exec_overrides=overrides.copy(),
        system_provider=scope.system_provider,
    )

    expanded_steps = []

    # Generate step name prefix
    prefix = step_prefix or step.name or "PROC"

    def _process_proc_steps(steps_list):
        result = []
        for proc_step in steps_list:
            if isinstance(proc_step, ConditionalBlock):
                new_cond = ConditionalBlock(
                    condition=proc_step.condition, line_number=proc_step.line_number
                )
                new_cond.then_steps = _process_proc_steps(proc_step.then_steps)
                new_cond.else_steps = _process_proc_steps(proc_step.else_steps)
                result.append(new_cond)
            else:
                # Clone the step
                new_step = deepcopy(proc_step)

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
                        new_step.program, expansion_scope, strict=False
                    )

                # Substitute symbols in step parameters
                new_step.parameters = substitute_parameters_dict(
                    new_step.parameters, expansion_scope
                )

                # Substitute symbols in DD statements
                for dd in new_step.dd_statements:
                    substitute_dd_statement(dd, expansion_scope, strict=False)

                result.append(new_step)
        return result

    expanded_steps = _process_proc_steps(procedure.steps)

    return expanded_steps


def substitute_parameters_dict(
    parameters: Dict[str, Any], scope: SymbolScope
) -> Dict[str, Any]:
    """
    Substitute symbols in parameter dictionary.

    Args:
        parameters: Parameter dictionary
        scope: Symbol resolution scope

    Returns:
        Dictionary with substituted values
    """
    result = {}

    for key, value in parameters.items():
        if isinstance(value, str):
            result[key] = substitute_symbols(value, scope, strict=False)
        elif isinstance(value, (list, tuple)):
            result[key] = [
                substitute_symbols(str(v), scope, strict=False)
                if isinstance(v, str)
                else v
                for v in value
            ]
        elif isinstance(value, dict):
            result[key] = substitute_parameters_dict(value, scope)
        else:
            result[key] = value

    return result


def substitute_dd_statement(
    dd: DDStatement, scope: SymbolScope, strict: bool = False
) -> None:
    """
    Substitute symbols in DD statement (in-place).

    Args:
        dd: DD statement to process
        scope: Symbol resolution scope
    """
    # Substitute dataset name
    if dd.dataset_name:
        dd.dataset_name = substitute_symbols(dd.dataset_name, scope, strict=strict)

    # Substitute disposition
    if dd.disposition:
        dd.disposition = substitute_symbols(dd.disposition, scope, strict=strict)

    # Substitute all parameters
    dd.parameters = substitute_parameters_dict(dd.parameters, scope)

    # Note: inline_data intentionally NOT substituted (data content preserved)


def apply_dd_overrides(
    expanded_steps: List[Step],
    dd_overrides: Dict[str, DDStatement],
    step_name_prefix: str,
) -> None:
    """
    Apply DD overrides to expanded steps.

    Args:
        expanded_steps: List of expanded steps
        dd_overrides: Dictionary of qualified DD name -> override DDStatement
        step_name_prefix: Prefix used for step names
    """
    for override_key, override_dd in dd_overrides.items():
        # Parse qualified DD name.
        # Two-part  "PROCSTEP.DDNAME"              -> step prefix.PROCSTEP  / DD DDNAME
        # Three-part "PROCSTEP.INNERST.DDNAME"     -> step prefix.PROCSTEP.INNERST / DD DDNAME
        #   (used for nested PROC invocations where the outer PROC step itself
        #   calls another PROC whose internal step name is needed)
        parts = override_key.split(".")

        if len(parts) == 2:
            target_step, target_dd = parts
            qualified_step = f"{step_name_prefix}.{target_step}"

            for step in expanded_steps:
                if step.name == qualified_step:
                    for i, dd in enumerate(step.dd_statements):
                        if dd.name == target_dd:
                            step.dd_statements[i] = deepcopy(override_dd)
                            break

        elif len(parts) == 3:
            # Three-part override: OUTERSTEP.INNERSTEP.DDNAME
            # The outer expansion has not yet expanded the inner PROC, so the
            # fully-qualified step "prefix.OUTERSTEP.INNERSTEP" does not exist
            # in `expanded_steps` at this point.  Instead we locate the
            # intermediate step "prefix.OUTERSTEP" (which is still a proc
            # invocation) and inject a two-part override "INNERSTEP.DDNAME"
            # into it so the override is applied when the inner PROC is later
            # expanded by the recursive _explode_step call.
            outer_step, inner_step, target_dd = parts
            qualified_outer = f"{step_name_prefix}.{outer_step}"
            two_part_key = f"{inner_step}.{target_dd}"

            for step in expanded_steps:
                if step.name == qualified_outer:
                    step.dd_overrides[two_part_key] = deepcopy(override_dd)
                    break


def explode_job(
    job: Job,
    proc_loader: Optional[ProcedureLoader] = None,
    max_depth: int = 10,
    audit: bool = True,
    system_provider: Optional[SystemSymbolProvider] = None,
    strict_symbols: bool = False,
) -> Job:
    """
    Explode all procedure invocations in a job.

    Creates a new Job instance with all PROC invocations expanded into
    their constituent steps with symbolic parameters fully resolved.

    Args:
        job: Original job with procedure invocations
        proc_loader: Procedure loader (defaults to inline + JCLLIB)
        max_depth: Maximum procedure nesting depth
        audit: Whether to generate audit logs
        system_provider: System symbol provider (defaults to mock provider)
        strict_symbols: If True, raise errors for undefined symbols

    Returns:
        New Job instance with exploded procedures

    Raises:
        ExplosionDepthError: If nesting exceeds max_depth
        CircularProcedureError: If circular references detected
        ProcedureNotFoundError: If referenced procedure not found
        UndefinedSymbolError: If strict_symbols=True and symbol undefined
    """
    # Create default loader if not provided
    if proc_loader is None:
        proc_loader = create_default_loader(job.procedures)

    # Get system provider
    if system_provider is None:
        system_provider = get_default_provider()

    # Create base symbol scope
    base_scope = SymbolScope(
        set_symbols=job.set_statements.copy(), system_provider=system_provider
    )

    # Track explosion metadata
    explosion_audit: List[ExplosionRecord] = []
    explosion_map: Dict[str, ProcExpansionInfo] = {}

    # Process steps
    def _process_steps(steps_list):
        result = []
        for step in steps_list:
            if isinstance(step, ConditionalBlock):
                new_cond = ConditionalBlock(
                    condition=step.condition, line_number=step.line_number
                )
                new_cond.then_steps = _process_steps(step.then_steps)
                new_cond.else_steps = _process_steps(step.else_steps)
                result.append(new_cond)
            elif step.is_procedure:
                # Expand procedure
                expanded = _explode_step(
                    step=step,
                    proc_loader=proc_loader,
                    base_scope=base_scope,
                    call_chain=[],
                    call_chain_upper=frozenset(),
                    depth=0,
                    max_depth=max_depth,
                    audit_records=explosion_audit if audit else None,
                    expansion_map=explosion_map,
                    strict_symbols=strict_symbols,
                    jcllib_order=job.jcllib_order or None,
                )
                result.extend(expanded)
            else:
                # Regular step - just substitute symbols
                substituted_step = deepcopy(step)

                if substituted_step.program:
                    substituted_step.program = substitute_symbols(
                        substituted_step.program, base_scope, strict=strict_symbols
                    )

                substituted_step.parameters = substitute_parameters_dict(
                    substituted_step.parameters, base_scope
                )

                for dd in substituted_step.dd_statements:
                    substitute_dd_statement(dd, base_scope, strict=strict_symbols)

                result.append(substituted_step)
        return result

    exploded_steps = _process_steps(job.steps)

    # Create new job with exploded steps
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
    )

    # Attach audit metadata
    if audit:
        exploded_job.explosion_audit = explosion_audit
    exploded_job.explosion_map = explosion_map

    return exploded_job


def _explode_step(
    step: Step,
    proc_loader: ProcedureLoader,
    base_scope: SymbolScope,
    call_chain: List[str],
    depth: int,
    max_depth: int,
    audit_records: Optional[List[ExplosionRecord]],
    expansion_map: Dict[str, ProcExpansionInfo],
    strict_symbols: bool,
    jcllib_order: Optional[List[str]] = None,
    call_chain_upper: Optional[frozenset] = None,
) -> List[Step]:
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

    Returns:
        List of exploded steps
    """
    # Backfill call_chain_upper if not provided (backward-compatible callers)
    if call_chain_upper is None:
        call_chain_upper = frozenset(p.upper() for p in call_chain)

    # Check depth limit
    if depth > max_depth:
        raise ExplosionDepthError(depth, max_depth, call_chain)

    proc_name = step.procedure
    if not proc_name:
        return [step]

    # Check for circular references (O(1) with frozenset)
    detect_circular_refs(proc_name, call_chain, call_chain_upper)

    # Load procedure definition
    # CompositeProcedureLoader requires a tuple (hashable) for its LRU cache;
    # other loaders accept both.  Always pass a tuple or None.
    _libs = tuple(jcllib_order) if jcllib_order else None
    procedure = proc_loader.load_procedure(proc_name, _libs)

    if procedure is None:
        raise ProcedureNotFoundError(proc_name, step.line_number)

    # Extract parameter overrides from step
    overrides = step.parameters.copy()

    # Expand this procedure
    expanded = expand_proc_invocation(
        step=step,
        procedure=procedure,
        overrides=overrides,
        scope=base_scope,
        step_prefix=step.name,
    )

    # Apply DD overrides if present
    if hasattr(step, "dd_overrides") and step.dd_overrides:
        apply_dd_overrides(expanded, step.dd_overrides, step.name or "PROC")

    # Record audit information
    if audit_records is not None:
        record = ExplosionRecord(
            step_name=step.name or "UNNAMED",
            proc_name=proc_name,
            parameters=overrides,
            depth=depth,
            timestamp=datetime.now(),
            expanded_steps=[s.name for s in expanded if hasattr(s, "name") and s.name],
        )
        audit_records.append(record)

    # Record expansion info — resolved_parameters is PROC defaults merged with
    # EXEC overrides (overrides win), giving the full effective parameter set.
    if step.name:
        expansion_map[step.name] = ProcExpansionInfo(
            original_statement=f"EXEC {proc_name}",
            proc_definition=procedure.name,
            resolved_parameters={**procedure.parameters, **overrides},
            source_line_numbers=[step.line_number],
            expanded_step_names=[
                s.name for s in expanded if hasattr(s, "name") and s.name
            ],
        )

    # Recursively explode any nested procedure calls
    new_call_chain = call_chain + [proc_name]
    new_call_chain_upper = call_chain_upper | {proc_name.upper()}

    def _explode_nested(steps_list):
        result = []
        for s in steps_list:
            if isinstance(s, ConditionalBlock):
                new_cond = ConditionalBlock(
                    condition=s.condition, line_number=s.line_number
                )
                new_cond.then_steps = _explode_nested(s.then_steps)
                new_cond.else_steps = _explode_nested(s.else_steps)
                result.append(new_cond)
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
                )
                result.extend(nested)
            else:
                result.append(s)
        return result

    return _explode_nested(expanded)
