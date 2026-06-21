"""Default synthetic PROC skeletons for common homemade-PROC equivalences.

Mainframe shops frequently define their own JCL procedures that are thin
wrappers around a standard IBM program.  The canonical example is ``IMSBATCH``,
a site PROC that simply runs ``EXEC PGM=DFSRRC00`` (the IMS batch region
controller).  When such a PROC is invoked but its source is unavailable, the
parser cannot tell that the step is really an IMS batch run, so program-profile
analysis, SQL detection, and relationship extraction all miss it.

This module ships a small catalog of *synthetic* PROC definitions — real JCL
skeletons whose symbolic parameters forward the caller's operands into the
underlying ``PGM=`` step.  Fed to the proc-loader chain as a lowest-priority
fallback, they let the existing explosion → profile → analysis pipeline treat a
homemade PROC exactly as if its real source were present, with no special-case
analysis code.  New equivalences are added by extending the catalog (here) or,
for site-specific PROCs, by passing overrides to :func:`build_alias_loader`.

Symbols are declared on the ``PROC`` card with empty defaults so that the
caller's operands (e.g. ``MBR=``, ``PSB=``) substitute in during explosion.
"""

from __future__ import annotations

from .proc_loader import DictProcedureLoader

# Mapping of PROC name (case-insensitive) -> synthetic PROC JCL.  The skeletons
# are intentionally minimal: just enough structure for the explosion engine to
# substitute the caller's operands and produce a real ``PGM=`` step.
DEFAULT_PROC_ALIASES: dict[str, str] = {
    # IMS batch message processing region (BMP).
    "IMSBATCH": (
        "//IMSBATCH PROC MBR=,PSB=\n"
        "//G  EXEC PGM=DFSRRC00,PARM='BMP,&MBR,&PSB'\n"
        "//   PEND\n"
    ),
    # IMS DL/I batch region.
    "DLIBATCH": (
        "//DLIBATCH PROC MBR=,PSB=\n"
        "//G  EXEC PGM=DFSRRC00,PARM='DLI,&MBR,&PSB'\n"
        "//   PEND\n"
    ),
}


def build_alias_loader(extra: dict[str, str] | None = None) -> DictProcedureLoader:
    """Build a :class:`DictProcedureLoader` from the default aliases.

    Args:
        extra: Additional or overriding ``proc_name -> synthetic PROC JCL``
            entries.  Entries here take precedence over :data:`DEFAULT_PROC_ALIASES`
            with the same (case-insensitive) name, allowing sites to override a
            shipped default or register their own homemade PROCs.

    Returns:
        A loader resolving each catalog name to a parsed ``Procedure``.  Intended
        to be placed *last* in a :class:`CompositeProcedureLoader` chain so that
        inline PROCs and real external source always win.
    """
    merged = {**DEFAULT_PROC_ALIASES, **(extra or {})}
    return DictProcedureLoader(merged)
