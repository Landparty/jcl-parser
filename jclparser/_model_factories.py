"""``Statement`` -> model factory helpers for the JCL parse loop.

Internal module split out of :mod:`jclparser._job_builder`. It contains the
pure, stateless helpers used while assembling the :class:`~jclparser.model.Job`
model from parsed :class:`~jclparser.model.Statement` objects:

* the ``Statement -> Job/Step/DDStatement`` factory functions,
* SET-symbol value resolution helpers (shared by
  :class:`~jclparser._job_builder.JobBuilder` and the post-parse SET
  substitution pass in :mod:`jclparser._post_parse`),
* the EXEC program/procedure-spec syntax check.

Behavior is identical to the pre-split ``_job_builder.py``; only the code
layout changed. Nothing here is public API — import
:func:`~jclparser.parse_jcl` from the package instead.
"""

from __future__ import annotations

import re
from typing import Any

from .model import DDStatement, Job, Statement, Step
from .utils import POSITIONAL_PARAM_PREFIX, is_positional_key

_SET_SYMBOL_PATTERN = re.compile(r"&&|&([A-Z0-9@#$]+)\.?")


def _resolve_set_value(value: str, known_symbols: dict[str, str]) -> str:
    """Resolve &SYMBOL references in a SET value using already-accumulated SET symbols.

    Mirrors the mainframe rule: SET values are evaluated left-to-right so a
    symbol can reference any earlier SET in the same job. A literal "&&" is
    left untouched here -- collapsing it would corrupt a SET value that
    itself holds a "&&NAME" temporary-dataset marker (e.g. ``SET
    MYTEMP=&&WORK``) before it ever reaches a DD statement. That collapse is
    explode_job()'s job (Tier 2), not this Tier-1 SET-value resolution.
    """

    def _replacer(m: re.Match[str]) -> str:
        if m.group(0) == "&&":
            return "&&"
        sym = m.group(1).upper()
        return known_symbols.get(sym, m.group(0))

    return _SET_SYMBOL_PATTERN.sub(_replacer, value)


def _has_unresolved_symbol_ref(value: str) -> bool:
    """True if *value* still contains a genuine (unescaped) &SYMBOL reference,
    as opposed to only escaped literal "&&" pairs.

    Used to decide whether a resolved SET value is safe to propagate into DD
    dataset names/EXEC parameters. A value that legitimately contains "&&"
    (e.g. from ``SET MYTEMP=&&WORK``) must not be excluded the same way a
    value with a genuinely unresolved reference (e.g. "&B." left over from an
    unresolvable SET cycle) is -- both contain an "&" character, but only the
    latter is actually unresolved.
    """
    return any(m.group(0) != "&&" for m in _SET_SYMBOL_PATTERN.finditer(value))


def _exec_has_program_spec(parameters: dict[str, Any]) -> bool:
    """Return True if *parameters* specifies a program, procedure, or positional arg.

    An EXEC statement is valid when it names a program (``PGM=``), an explicit
    procedure (``PROC=``), or uses a bare positional token (no keyword, treated
    as a proc name by the parser).
    """
    return (
        "PGM" in parameters
        or "PROC" in parameters
        or any(is_positional_key(k) for k in parameters)
    )


def _create_job_from_statement(stmt: Statement) -> Job:
    """Create Job object from JOB statement"""
    accounting_info = None

    # Extract accounting information (first positional parameter)
    if f"{POSITIONAL_PARAM_PREFIX}0" in stmt.parameters:
        accounting_info = stmt.parameters[f"{POSITIONAL_PARAM_PREFIX}0"].strip("()")

    # Extract other parameters
    job_params = {k: v for k, v in stmt.parameters.items() if not is_positional_key(k)}

    return Job(
        name=stmt.name,
        parameters=job_params,
        accounting_info=accounting_info,
        line_number=stmt.line_number,
    )


def _create_step_from_statement(stmt: Statement) -> Step:
    """Create Step object from EXEC statement"""
    program = None
    procedure = None

    # Check if it's a program or procedure call
    if "PGM" in stmt.parameters:
        program = stmt.parameters.pop("PGM")
    elif "PROC" in stmt.parameters:
        procedure = stmt.parameters.pop("PROC")
    elif f"{POSITIONAL_PARAM_PREFIX}0" in stmt.parameters:
        # Might be a procedure call without keyword
        proc_or_pgm = stmt.parameters.pop(f"{POSITIONAL_PARAM_PREFIX}0")
        # If it looks like a procedure name (no path separators), treat as procedure
        if "." not in proc_or_pgm and "/" not in proc_or_pgm:
            procedure = proc_or_pgm
        else:
            program = proc_or_pgm

    return Step(
        name=stmt.name,
        program=program,
        procedure=procedure,
        parameters=stmt.parameters,
        line_number=stmt.line_number,
    )


def _create_dd_from_statement(stmt: Statement) -> DDStatement:
    """Create DDStatement object from DD statement"""
    dataset_name = stmt.parameters.get("DSN")
    disposition = stmt.parameters.get("DISP")

    return DDStatement(
        name=stmt.name,
        dataset_name=dataset_name,
        disposition=disposition,
        parameters=stmt.parameters,
        line_number=stmt.line_number,
    )
