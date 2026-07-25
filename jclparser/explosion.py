"""
Dynamic procedure explosion engine for JCL parsing.

Implements symbolic parameter substitution and procedure expansion with
support for nested procedures, circular dependency detection, and audit logging.
"""

import logging
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
    JCLStructureError,
)
from .proc_loader import ProcedureLoader, create_default_loader
from .system_symbols import SystemSymbolProvider, get_default_provider

logger = logging.getLogger(__name__)


# Single-pass pattern: matches && (escaped ampersand) OR &SYMBOL with optional trailing period
_SYMBOL_SUB_PATTERN = re.compile(r"&&|&([A-Z0-9@#$]+)\.?")


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
    return new_dd


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
    )


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


def _make_replacer(
    scope: "SymbolScope",
    strict: bool,
    allow_undefined: bool,
    source_text: str = "",
    warnings: Optional[List[str]] = None,
    collapse_double_amp: bool = True,
):
    """Create a regex replacer function for symbol substitution."""

    def _replacer(m: re.Match) -> str:
        if m.group(0) == "&&":
            return "&" if collapse_double_amp else "&&"
        symbol_name = m.group(1)
        # Always resolve with strict=False so that UndefinedSymbolError is raised
        # here (with full source context) rather than inside scope.resolve().
        value = scope.resolve(symbol_name, strict=False)
        if value is None:
            if allow_undefined:
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
        return value

    return _replacer


def substitute_symbols(
    text: str,
    scope: "SymbolScope",
    strict: bool = False,
    allow_undefined: bool = False,
    warnings: Optional[List[str]] = None,
    collapse_double_amp: bool = True,
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

    Returns:
        Text with symbols substituted

    Raises:
        UndefinedSymbolError: If strict=True and symbol undefined
    """
    if not text or not isinstance(text, str):
        return text
    return _SYMBOL_SUB_PATTERN.sub(
        _make_replacer(
            scope,
            strict,
            allow_undefined,
            source_text=text,
            warnings=warnings,
            collapse_double_amp=collapse_double_amp,
        ),
        text,
    )


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
    strict: bool = False,
    warnings: Optional[List[str]] = None,
) -> List[Step]:
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

    # Generate step name prefix
    prefix = step_prefix or step.name or "PROC"

    def _process_proc_steps(steps_list):
        result = []
        for proc_step in steps_list:
            if isinstance(proc_step, ConditionalBlock):
                result.append(_clone_conditional(proc_step, _process_proc_steps))
            else:
                # Clone the step
                new_step = _clone_step_for_explosion(proc_step)

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
                        expansion_scope,
                        strict=strict,
                        warnings=warnings,
                    )

                # Substitute symbols in step parameters
                new_step.parameters = substitute_parameters_dict(
                    new_step.parameters,
                    expansion_scope,
                    strict=strict,
                    warnings=warnings,
                )

                # Substitute symbols in DD statements
                for dd in new_step.dd_statements:
                    substitute_dd_statement(
                        dd, expansion_scope, strict=strict, warnings=warnings
                    )

                result.append(new_step)
        return result

    expanded_steps = _process_proc_steps(procedure.steps)

    return expanded_steps


def substitute_parameters_dict(
    parameters: Dict[str, Any],
    scope: SymbolScope,
    strict: bool = False,
    allow_undefined: bool = False,
    warnings: Optional[List[str]] = None,
    collapse_double_amp: bool = True,
) -> Dict[str, Any]:
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
    result: Dict[str, Any] = {}

    for key, value in parameters.items():
        if isinstance(value, str):
            result[key] = substitute_symbols(
                value,
                scope,
                strict=strict,
                allow_undefined=allow_undefined,
                warnings=warnings,
                collapse_double_amp=collapse_double_amp,
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


def substitute_dd_statement(
    dd: DDStatement,
    scope: SymbolScope,
    strict: bool = False,
    allow_undefined: bool = False,
    warnings: Optional[List[str]] = None,
    collapse_double_amp: bool = True,
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
            of collapsing it to "&". Callers that must preserve the
            "&&NAME" temporary-dataset idiom (see
            ``DDStatement.is_temporary()``) ahead of full PROC explosion
            should pass False here.
    """
    local_warnings: Optional[List[str]] = [] if warnings is not None else None

    # Substitute dataset name
    if dd.dataset_name:
        dd.dataset_name = substitute_symbols(
            dd.dataset_name,
            scope,
            strict=strict,
            allow_undefined=allow_undefined,
            warnings=local_warnings,
            collapse_double_amp=collapse_double_amp,
        )
        dd.dataset_name = _strip_empty_member(dd.dataset_name)

    # Substitute disposition. DISP=(&STATUS,CATLG,DELETE) parses to a list,
    # not a plain string, so each element needs its own substitution pass —
    # substitute_symbols() is a no-op for non-str input and would otherwise
    # silently skip symbols in list-valued dispositions.
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
            )

    # Substitute all parameters
    dd.parameters = substitute_parameters_dict(
        dd.parameters,
        scope,
        strict=strict,
        allow_undefined=allow_undefined,
        collapse_double_amp=collapse_double_amp,
    )

    # Note: inline_data intentionally NOT substituted (data content preserved)

    if warnings is not None and local_warnings:
        for msg in local_warnings:
            warnings.append(
                f"Line {dd.line_number}: DD {dd.name or '(unnamed)'}: {msg}"
            )


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
                    # override_dd.name is the raw statement name field, i.e.
                    # the *qualified* key ("PROCSTEP.DDNAME") -- normalize it
                    # to the plain DD name so the resulting DD looks the same
                    # as one coded directly on the step.
                    clone = deepcopy(override_dd)
                    clone.name = target_dd
                    for i, dd in enumerate(step.dd_statements):
                        if dd.name == target_dd:
                            step.dd_statements[i] = clone
                            break
                    else:
                        # No DD named target_dd on this step -- per z/OS
                        # semantics a PROCSTEP.DDNAME override with no
                        # matching DD *adds* one, same as the unqualified
                        # form (apply_unqualified_dd_overrides). Without
                        # this, a fully-parsed override DD was silently
                        # discarded.
                        step.dd_statements.append(clone)
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


def apply_unqualified_dd_overrides(
    expanded_steps: List[Step],
    override_dds: List[DDStatement],
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

    first_step = next((s for s in expanded_steps if isinstance(s, Step)), None)
    if first_step is None:
        return

    index_by_name = {
        dd.name: i for i, dd in enumerate(first_step.dd_statements) if dd.name
    }
    for override_dd in override_dds:
        clone = deepcopy(override_dd)
        existing = index_by_name.get(override_dd.name) if override_dd.name else None
        if existing is not None:
            first_step.dd_statements[existing] = clone
        else:
            first_step.dd_statements.append(clone)
            if override_dd.name:
                index_by_name[override_dd.name] = len(first_step.dd_statements) - 1


def explode_job(
    job: Job,
    proc_loader: Optional[ProcedureLoader] = None,
    max_depth: int = 10,
    max_steps: int = 0,
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
        max_steps: Maximum total expanded steps (0 = unlimited). Protects against
                   runaway step proliferation when a PROC is called many times.
        audit: Whether to generate audit logs
        system_provider: System symbol provider (defaults to mock provider)
        strict_symbols: If True, raise errors for undefined symbols

    Returns:
        New Job instance with exploded procedures

    Raises:
        ExplosionDepthError: If nesting exceeds max_depth
        JCLStructureError: If max_steps > 0 and the expanded step count exceeds it
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
    # Symbol-substitution diagnostics accumulated during explosion (e.g. an
    # undefined &SYMBOL only resolvable inside a PROC body, against PROC
    # defaults/EXEC overrides/system symbols -- parse_jcl() never sees these,
    # since it doesn't expand PROCs). Merged onto exploded_job.warnings below.
    explosion_warnings: List[str] = []

    # Mutable step counter shared across all _process_steps recursions.
    # Using a list (not int) so the nested closure can mutate it.
    _step_count: List[int] = [0]

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

    # Process steps
    def _process_steps(steps_list):
        result = []
        for step in steps_list:
            if isinstance(step, ConditionalBlock):
                result.append(_clone_conditional(step, _process_steps))
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
                    warnings=explosion_warnings,
                )
                _check_step_limit(len(expanded))
                result.extend(expanded)
            else:
                # Regular step - just substitute symbols
                substituted_step = _clone_step_for_explosion(step)

                if substituted_step.program:
                    substituted_step.program = substitute_symbols(
                        substituted_step.program,
                        base_scope,
                        strict=strict_symbols,
                        warnings=explosion_warnings,
                    )

                substituted_step.parameters = substitute_parameters_dict(
                    substituted_step.parameters,
                    base_scope,
                    warnings=explosion_warnings,
                )

                for dd in substituted_step.dd_statements:
                    substitute_dd_statement(
                        dd,
                        base_scope,
                        strict=strict_symbols,
                        warnings=explosion_warnings,
                    )

                _check_step_limit(1)
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
        exported_symbols=set(job.exported_symbols),
    )

    # Preserve post-parse analysis metadata so consumers of the exploded job
    # see the same derived state as on the original parsed job.  We copy
    # rather than share so downstream mutation of one doesn't surprise the
    # other.
    for _attr in (
        "unresolved_output_refs",
        "sql_detections",
        "jes_typed_statements",
        "jes_statements",
        "output_statements",
        "joblib_dds",
        "warnings",
    ):
        src_val = getattr(job, _attr, None)
        if src_val is not None:
            setattr(exploded_job, _attr, deepcopy(src_val))

    # Diagnostics raised while substituting symbols during explosion itself
    # (as opposed to during parse_jcl(), already covered by the warnings
    # copy above) -- e.g. an undefined &SYMBOL only resolvable inside a
    # PROC body.
    exploded_job.warnings.extend(explosion_warnings)

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
    warnings: Optional[List[str]] = None,
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
        warnings: List to append symbol-substitution diagnostics to (e.g. an
                  undefined &SYMBOL referenced inside the PROC body). None
                  means diagnostics are discarded, matching audit_records.

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
        return [step]

    logger.debug("expanding PROC %s at depth %d", proc_name, depth)

    # Check for circular references (O(1) with frozenset)
    if proc_name.upper() in call_chain_upper:
        logger.debug(
            "circular PROC reference detected: %s already in chain %s",
            proc_name,
            call_chain,
        )
    detect_circular_refs(proc_name, call_chain, call_chain_upper)

    # Load procedure definition. The same JCLLIB ORDER is threaded through every
    # nesting level so an external PROC invoked from inside another PROC is found
    # against the job's library order. Pass an immutable tuple: loaders key their
    # caches on the library list, so a hashable value keeps that contract safe.
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
        strict=strict_symbols,
        warnings=warnings,
    )

    # Apply qualified DD overrides (PROCSTEP.DDNAME) if present
    if step.dd_overrides:
        apply_dd_overrides(expanded, step.dd_overrides, step.name or "PROC")

    # Merge unqualified DD overrides/additions (coded directly under EXEC PROC=,
    # stored on the step's own dd_statements) onto the procedure's first step.
    if step.dd_statements:
        apply_unqualified_dd_overrides(expanded, step.dd_statements)

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
                )
                result.extend(nested)
            else:
                result.append(s)
        return result

    return _explode_nested(expanded)
