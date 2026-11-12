"""Symbol substitution in in-stream data coded with ``SYMBOLS=``.

``//SYSIN DD *,SYMBOLS=JCLONLY`` (or ``EXECSYS`` / ``CNVTSYS``) asks JES to
substitute the job's *exported* JCL symbols (``// EXPORT SYMLIST=``) in the
in-stream records, so ``NAME(&H..KSDS)`` reaches the program as
``NAME(PROD.KSDS)``. Lineage, IDCAMS analysis and SQL detection read the
in-stream data, so they must see it substituted. A symbol with no exported
value (a system symbol, resolved on the execution system) is left as coded.
"""

from __future__ import annotations

from typing import Any

from .model import Job, iter_execution_steps

#: ``SYMBOLS=`` values that turn substitution on.
_SUBSTITUTING_MODES = frozenset({"JCLONLY", "EXECSYS", "CNVTSYS"})


def _symbols_mode(value: Any) -> str | None:
    """The substitution mode of a ``SYMBOLS=`` value, or None."""
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, str):
        return None
    mode = value.strip("()").split(",")[0].strip().upper()
    return mode if mode in _SUBSTITUTING_MODES else None


def _exported_table(job: Job, values: dict[str, str] | None = None) -> dict[str, str]:
    """The SET symbols *job* exports (``SYMLIST=*`` exports them all), taken
    from *values* (default: the job's final SET table)."""
    table = job.set_statements if values is None else values
    exported = {name.upper() for name in job.exported_symbols}
    if "*" in exported:
        return dict(table)
    return {k: v for k, v in table.items() if k.upper() in exported}


def substitute_instream_symbols(job: Job, at_each_step: bool = False) -> None:
    """Substitute exported symbols into every ``SYMBOLS=`` in-stream DD of *job*.

    With *at_each_step* (``parse_jcl``, whose steps carry the SET values in
    effect where each was coded), a DD gets the values in effect at its step,
    as its step's DD operands do; a symbol first set after it is left as
    coded (#197). Otherwise the job's final SET table is used.
    """
    if not _exported_table(job):
        return
    from ._post_parse import _scope_for_table
    from .explosion import substitute_symbols

    scopes: dict[tuple[tuple[str, str], ...], Any] = {}
    for step in iter_execution_steps(job.steps):
        snapshot = step.set_symbols if at_each_step else None
        table = _exported_table(job, snapshot)
        for dd in step.dd_statements:
            if not dd.inline_data or "&" not in dd.inline_data:
                continue
            if _symbols_mode(dd.parameters.get("SYMBOLS")) is None:
                continue
            key = tuple(sorted(table.items()))
            if key not in scopes:
                scopes[key] = _scope_for_table(table, job.warnings)
            dd.inline_data = substitute_symbols(
                dd.inline_data,
                scopes[key],
                allow_undefined=True,
                collapse_double_amp=False,
            )
