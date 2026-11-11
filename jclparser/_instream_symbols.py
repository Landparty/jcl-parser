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


def _exported_table(job: Job) -> dict[str, str]:
    """The SET symbols *job* exports (``SYMLIST=*`` exports them all)."""
    exported = {name.upper() for name in job.exported_symbols}
    if "*" in exported:
        return dict(job.set_statements)
    return {k: v for k, v in job.set_statements.items() if k.upper() in exported}


def substitute_instream_symbols(job: Job) -> None:
    """Substitute exported symbols into every ``SYMBOLS=`` in-stream DD of *job*."""
    table = _exported_table(job)
    if not table:
        return
    from ._post_parse import _scope_for_table
    from .explosion import substitute_symbols

    scope = None
    for step in iter_execution_steps(job.steps):
        for dd in step.dd_statements:
            if not dd.inline_data or "&" not in dd.inline_data:
                continue
            if _symbols_mode(dd.parameters.get("SYMBOLS")) is None:
                continue
            if scope is None:
                scope = _scope_for_table(table, job.warnings)
            dd.inline_data = substitute_symbols(
                dd.inline_data, scope, allow_undefined=True, collapse_double_amp=False
            )
