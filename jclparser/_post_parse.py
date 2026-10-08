"""Post-parse passes run by ``parse_jcl()`` after the core loop.

Internal module split out of :mod:`jclparser._job_builder`. It contains the
whole-``Job`` passes that run once the :class:`~jclparser._job_builder.JobBuilder`
state machine has assembled the model:

* external PROC loading (:func:`load_external_procedures`),
* ``OUTPUT=*.name`` back-reference resolution (:func:`_resolve_output_refs`),
* SET-symbol substitution into DD/EXEC parameters
  (:func:`resolve_set_symbols`),
* the strict-mode orphaned-DD structure check
  (:func:`enforce_strict_dd_structure`).

Behavior is identical to the pre-split ``_job_builder.py``; only the code
layout changed. Nothing here is public API — import
:func:`~jclparser.parse_jcl` from the package instead.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._model_factories import _has_unresolved_symbol_ref
from .errors import JCLStructureError, JCLSyntaxError
from .model import Job, Step, iter_execution_steps
from .utils import split_source_lines

if TYPE_CHECKING:
    from .explosion import SymbolScope
    from .model import DDStatement

logger = logging.getLogger(__name__)


def _extract_output_ref_names(value: Any) -> list[str]:
    """Return OUTPUT reference names from a DD ``OUTPUT=`` parameter value.

    Supports only the ``*.`` prefix forms — the standard way JCL references
    an OUTPUT statement from a DD::

        OUTPUT=*.NAME                -> ["NAME"]
        OUTPUT=(*.NAME)              -> ["NAME"]
        OUTPUT=(*.N1,*.N2)           -> ["N1", "N2"]
        OUTPUT=*.STEP.NAME           -> ["NAME"]   (qualified — take tail)

    Values that do not start with ``*.`` (e.g. a bare nodename, a qualified
    ``STEP.PROCSTEP.N`` form without the leading ``*.``, or ``None``) yield
    an empty list.  Callers rely on this to distinguish output-statement
    references from other uses of the OUTPUT= parameter.
    """
    names: list[str] = []
    items: list[str]
    if isinstance(value, list):
        items = [str(v) for v in value]
    elif isinstance(value, str):
        items = [value]
    else:
        return names

    for item in items:
        token = item.strip().strip("()")
        if not token.startswith("*."):
            # Qualified form step.procstep.name uses ".name" — last segment after *
            if ".*" in token:
                # Not a back-reference either
                continue
            continue
        ref = token[2:].strip()
        if not ref:
            continue
        # If qualified like STEP.PROCSTEP.NAME, take the final segment.
        if "." in ref:
            ref = ref.split(".")[-1]
        names.append(ref.upper())
    return names


def _resolve_output_refs(job: Job) -> None:
    """Populate ``DDStatement.output_refs`` for every DD that uses ``OUTPUT=*.X``.

    Unresolved references (no matching :class:`OutputStatement`) are recorded
    on ``job.unresolved_output_refs`` as ``(step_name, ref_name, line_number)``
    tuples so :func:`jclparser.validators.validate_job_structure` can emit
    warnings without re-scanning the parameter string.
    """
    if not job:
        return
    # Index OUTPUT statements by uppercased name (last wins if duplicated).
    output_by_name: dict[str, Any] = {
        out.name.upper(): out for out in job.output_statements if out.name
    }

    from .model import iter_execution_steps

    for step in iter_execution_steps(job.steps):
        for dd in step.dd_statements:
            value = dd.parameters.get("OUTPUT")
            if value is None:
                continue
            for ref in _extract_output_ref_names(value):
                target = output_by_name.get(ref)
                if target is not None:
                    dd.output_refs.append(target)
                else:
                    job.unresolved_output_refs.append(
                        (step.name or "", ref, dd.line_number)
                    )


def load_external_procedures(
    job: Job,
    strict_mode: bool,
    proc_base_path: str | Path | None,
    enable_external_procs: bool,
) -> None:
    """Attach a PROC loader and resolve external PROC references on *job*.

    In strict mode a referenced-but-unresolvable procedure raises
    :class:`JCLSyntaxError`; otherwise unresolved references are left as-is.
    """
    if enable_external_procs and job.jcllib_order:
        logger.debug("loading external PROCs via JCLLIB order: %s", job.jcllib_order)
        from .proc_loader import create_default_loader

        proc_loader = create_default_loader(
            inline_procedures=job.procedures,
            base_path=Path(proc_base_path)
            if isinstance(proc_base_path, str)
            else proc_base_path,
            include_jcllib=True,
        )
        # Store loader on job for later use (e.g., in explosion)
        job._proc_loader = proc_loader

        # Try to load any external PROCs that were referenced but not found inline
        # This happens when EXEC PROC is used but PROC is not defined inline.
        # A call inside an IF/THEN/ELSE block is a call all the same.
        for step in iter_execution_steps(job.steps):
            if step.procedure and not job.get_procedure(step.procedure):
                # Try to load external PROC
                libraries_list = list(job.jcllib_order) if job.jcllib_order else None
                proc = proc_loader.load_procedure(step.procedure, libraries_list)
                if proc:
                    job.add_procedure(proc)
                elif strict_mode:
                    raise JCLSyntaxError(
                        f"Procedure '{step.procedure}' not found. "
                        f"Searched in: inline={len(job.procedures)} procedures, "
                        f"libraries={job.jcllib_order}",
                        step.line_number,
                    )
    else:
        # External loading disabled or no JCLLIB - check for missing PROCs in strict mode
        if strict_mode:
            for step in iter_execution_steps(job.steps):
                if step.procedure and not job.get_procedure(step.procedure):
                    reason = (
                        "external PROC loading is disabled"
                        if not enable_external_procs
                        else "no JCLLIB ORDER specified"
                    )
                    raise JCLSyntaxError(
                        f"Procedure '{step.procedure}' not found ({reason}). "
                        f"Searched in: inline={len(job.procedures)} procedures",
                        step.line_number,
                    )


def enforce_strict_dd_structure(content: str) -> None:
    """Strict mode: a DD statement with no EXEC anywhere is a structural error.

    Called only when the parsed job ended up with no steps; re-scans the raw
    *content* for any DD statement and raises :class:`JCLStructureError` when
    one is found.
    """
    for line in split_source_lines(content):
        stripped = line.strip()
        if stripped.startswith("//") and not stripped.startswith("//*"):
            parts = stripped.split()
            if len(parts) >= 2 and parts[1].upper() == "DD":
                raise JCLStructureError(
                    "DD statement found before any EXEC step. "
                    "Each DD must belong to a step."
                )


def resolve_set_symbols(job: Job) -> None:
    """Substitute fully-resolved SET symbols into DD and EXEC-step parameters.

    SET statements may appear before or after the DD statements that reference
    them, so this substitution pass runs *after* the main parse loop once all
    SET symbols are fully known.

    Chained SET symbols are handled too, e.g.::

        // SET HLQ=CORP
        // SET LIB=&HLQ..DATA        <- value contains a symbol reference
        //DD1 DD DSN=&LIB..FILE      <- should resolve to CORP.DATA.FILE

    ``_resolve_set_value`` (called during parsing) already handles backward
    references (symbol defined before it is used in a SET value).  Forward
    references — where ``SET B=&A.`` appears before ``SET A=VALUE`` — are
    stored as the literal string ``"&A."`` and are left unresolved after the
    parse loop.  We fix those here by iteratively pre-resolving the symbol
    table until it stabilises (up to 10 passes, which also bounds any
    accidental cycle).

    This pass must never collapse ``&&`` to a literal ``&``:
    ``DDStatement.is_temporary()`` detects temporary datasets by their raw
    ``&&NAME`` prefix, and ``parse_jcl()`` output must keep that detectable —
    ``&&`` collapsing is ``explode_job()``'s job (Tier 2), not this Tier-1
    pass.  It also covers EXEC step parameters (e.g. ``PARM=&SYM``), not just
    DD dataset names/dispositions, so a job-level SET symbol resolves the same
    way regardless of which kind of statement references it.
    """
    from .explosion import substitute_dd_statement
    from .system_symbols import is_system_symbol_name

    _set_scope = _scope_for_table(job.set_statements)
    # A step read before a SET redefined a symbol sees the value in effect at
    # that point (Step.set_symbols); symbols it has no snapshot for (forward
    # references) still fall back to the job's final table.
    _step_scopes: dict[int, SymbolScope] = {}

    from .model import iter_execution_steps

    _flat_steps = list(iter_execution_steps(job.steps))
    for _owner, _dd in _dds_with_owners(_flat_steps):
        substitute_dd_statement(
            _dd,
            _scope_for_step(_owner, job, _set_scope, _step_scopes),
            strict=False,
            warnings=job.warnings,
            collapse_double_amp=False,
            keep_undefined=is_system_symbol_name,
        )

    for _step in _flat_steps:
        _step_scope = _scope_for_step(_step, job, _set_scope, _step_scopes)
        _substitute_step_parameters(_step, _step_scope, job.warnings)
        _substitute_step_names(_step, _step_scope)


def _preresolve_set_table(table: dict[str, str]) -> dict[str, str]:
    """Return a copy of SET *table* with symbol references between values expanded."""
    from .explosion import SymbolScope, substitute_symbols

    # Pre-resolve the symbol table so every value is fully expanded before
    # we apply it to DD dataset names.  On each pass we substitute symbols
    # within each SET value using the *other* symbols in the table
    # (excluding the symbol itself prevents direct self-reference loops).
    # We repeat until no value changes or we reach the pass limit.
    _raw: dict[str, str] = dict(table)
    for _pass in range(10):
        _changed = False
        for _name, _val in list(_raw.items()):
            if "&" not in _val:
                continue
            # Build a temporary scope that excludes this symbol's own name
            # so "&A." inside SET A's value does not expand to itself.
            _scope_for_val = SymbolScope(
                set_symbols={k: v for k, v in _raw.items() if k != _name}
            )
            _new_val = substitute_symbols(
                _val,
                _scope_for_val,
                allow_undefined=True,
                collapse_double_amp=False,
            )
            if _new_val != _val:
                _raw[_name] = _new_val
                _changed = True
        if not _changed:
            break  # table has stabilised – no need for more passes
    return _raw


def _scope_for_table(table: dict[str, str]) -> SymbolScope:
    """Build the substitution scope for SET symbol *table* (see resolve_set_symbols)."""
    from .explosion import SymbolScope
    from .system_symbols import is_system_symbol_name

    _raw = _preresolve_set_table(table)

    # Symbols whose values still contain a genuinely unresolved
    # &-reference after all passes are excluded from the final scope.
    # Propagating a raw "&B." value into a DD dataset_name would leave a
    # literal token in the output; instead, strict=False below will
    # silently elide those unresolvable references (they become empty
    # string) and warn. System symbols (&SYSUID, &LYYMMDD, ...) are the
    # exception: no SET defines them, but explode_job() resolves them from
    # its SystemSymbolProvider, so blanking them here would destroy
    # ``DSN=&SYSUID..WORK`` before that pass runs (keep_undefined below). A value that legitimately contains "&&" (e.g.
    # SET MYTEMP=&&WORK) is NOT excluded -- it has nothing left to
    # resolve, it just happens to contain an escaped literal ampersand.
    _resolved_symbols = {
        k: v
        for k, v in _raw.items()
        if not _has_unresolved_symbol_ref(v, ignore=is_system_symbol_name)
    }
    return SymbolScope(set_symbols=_resolved_symbols)


def _scope_for_step(
    step: Step,
    job: Job,
    set_scope: SymbolScope,
    step_scopes: dict[int, SymbolScope],
) -> SymbolScope:
    """Return the SET scope in effect for *step*, memoised in *step_scopes*.

    *set_scope* is the scope of the job's final SET table, used for steps
    with no ``set_symbols`` snapshot.
    """
    if step.set_symbols is None:
        return set_scope
    if id(step) not in step_scopes:
        step_scopes[id(step)] = _scope_for_table(
            {**job.set_statements, **step.set_symbols}
        )
    return step_scopes[id(step)]


def _dds_with_owners(steps: list[Step]) -> list[tuple[Step, DDStatement]]:
    """Return every ``(step, dd)`` pair SET substitution must visit.

    Step DD statements come first, then PROCSTEP.DDNAME overrides.
    """
    # PROCSTEP.DDNAME overrides (and their concatenation members) are job-level
    # JCL too; they live outside ``dd_statements``, so get_dd_statements()
    # alone left ``&HLQ`` unresolved in them even after explosion.
    _override_dds = [
        (_step, _dd)
        for _step in steps
        for _dd in [
            *_step.dd_overrides.values(),
            *(m for ms in _step.dd_override_concatenations.values() for m in ms),
        ]
    ]
    _step_dds = [(_step, _dd) for _step in steps for _dd in _step.dd_statements]
    return [*_step_dds, *_override_dds]


def _substitute_step_parameters(
    step: Step, scope: SymbolScope, job_warnings: list[str]
) -> None:
    """Substitute SET symbols into *step*'s EXEC parameters, warning on *job_warnings*."""
    from .explosion import substitute_parameters_dict
    from .system_symbols import is_system_symbol_name

    _step_warnings: list[str] = []
    step.parameters = substitute_parameters_dict(
        step.parameters,
        scope,
        strict=False,
        warnings=_step_warnings,
        collapse_double_amp=False,
        keep_undefined=is_system_symbol_name,
    )
    for _msg in _step_warnings:
        job_warnings.append(
            f"Line {step.line_number}: Step {step.name or '(unnamed)'}: {_msg}"
        )


def _substitute_step_names(step: Step, scope: SymbolScope) -> None:
    """Substitute SET symbols into *step*'s program and PROC names."""
    from .explosion import substitute_symbols

    # PGM= and the PROC name are lifted out of ``parameters`` into their
    # own attributes, so the parameter pass never reached them: ``SET
    # PGMNAME=X`` + ``EXEC PGM=&PGMNAME`` left the program as the literal
    # "&PGMNAME". A symbol that stays unresolved is left as written.
    for _attr in ("program", "procedure"):
        _name_val = getattr(step, _attr, None)
        if isinstance(_name_val, str) and "&" in _name_val:
            _substituted = substitute_symbols(
                _name_val,
                scope,
                allow_undefined=True,
                collapse_double_amp=False,
            )
            if not _has_unresolved_symbol_ref(_substituted):
                setattr(step, _attr, _substituted)
