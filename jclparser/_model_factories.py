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
from collections.abc import Callable
from typing import Any

from .errors import JCLSyntaxError
from .model import DDStatement, Job, Statement, Step
from .utils import (
    MAX_SYMBOL_VALUE_LENGTH,
    POSITIONAL_PARAM_PREFIX,
    is_positional_key,
    jcl_value_text,
)

_SET_SYMBOL_PATTERN = re.compile(r"&&|&([A-Z0-9@#$]+)\.?")


def _resolve_set_value(
    value: str,
    known_symbols: dict[str, str],
    *,
    symbol: str = "",
    line_number: int = 0,
    strict: bool = False,
    warnings: list[str] | None = None,
) -> str:
    """Resolve &SYMBOL references in a SET value using already-accumulated SET symbols.

    Mirrors the mainframe rule: SET values are evaluated left-to-right so a
    symbol can reference any earlier SET in the same job. A literal "&&" is
    left untouched here -- collapsing it would corrupt a SET value that
    itself holds a "&&NAME" temporary-dataset marker (e.g. ``SET
    MYTEMP=&&WORK``) before it ever reaches a DD statement. That collapse is
    explode_job()'s job (Tier 2), not this Tier-1 SET-value resolution.

    A resolved value longer than :data:`~jclparser.utils.MAX_SYMBOL_VALUE_LENGTH`
    is never built (#70): its length is computed first, and the value is
    returned unresolved with a message on *warnings* -- or, when *strict*,
    :class:`~jclparser.errors.JCLSyntaxError` is raised. *symbol* and
    *line_number* only label that message.
    """
    matches = list(_SET_SYMBOL_PATTERN.finditer(value))
    if not matches:
        return value

    def _replacement(m: re.Match[str]) -> str:
        if m.group(0) == "&&":
            return "&&"
        return known_symbols.get(m.group(1).upper(), m.group(0))

    replacements = [_replacement(m) for m in matches]
    length = len(value) + sum(
        len(r) - len(m.group(0)) for m, r in zip(matches, replacements)
    )
    if length > MAX_SYMBOL_VALUE_LENGTH:
        _report_set_overflow(symbol, length, line_number, strict, warnings)
        return value
    parts: list[str] = []
    pos = 0
    for m, r in zip(matches, replacements):
        parts.append(value[pos : m.start()])
        parts.append(r)
        pos = m.end()
    parts.append(value[pos:])
    return "".join(parts)


def _report_set_overflow(
    symbol: str,
    length: int,
    line_number: int,
    strict: bool,
    warnings: list[str] | None,
) -> None:
    """Raise (strict) or warn that SET *symbol* would resolve to *length* chars."""
    message = (
        f"SET symbol &{symbol or '?'} would resolve to {length:,} characters, "
        f"more than the {MAX_SYMBOL_VALUE_LENGTH:,}-character limit"
    )
    if strict:
        raise JCLSyntaxError(message, line_number)
    if warnings is not None:
        prefix = f"Line {line_number}: " if line_number else ""
        warnings.append(f"{prefix}{message}; value left unresolved")


def _resolve_jcllib_library(library: str, known_symbols: dict[str, str]) -> str | None:
    """Substitute SET symbols into one ``JCLLIB ORDER`` library name.

    z/OS resolves the SET symbols defined before the JCLLIB statement, so
    *known_symbols* must be the SET table in effect at that statement. Returns
    ``None`` when a ``&symbol`` is still unresolved afterwards (a system symbol
    such as ``&SYSUID``, or a SET coded later); the caller keeps the library as
    written then.
    """
    if "&" not in library:
        return library
    resolved = _resolve_set_value(library, known_symbols)
    if _has_unresolved_symbol_ref(resolved):
        return None
    return resolved


def _has_unresolved_symbol_ref(
    value: str, ignore: Callable[[str], bool] | None = None
) -> bool:
    """True if *value* still contains a genuine (unescaped) &SYMBOL reference,
    as opposed to only escaped literal "&&" pairs.

    Used to decide whether a resolved SET value is safe to propagate into DD
    dataset names/EXEC parameters. A value that legitimately contains "&&"
    (e.g. from ``SET MYTEMP=&&WORK``) must not be excluded the same way a
    value with a genuinely unresolved reference (e.g. "&B." left over from an
    unresolvable SET cycle) is -- both contain an "&" character, but only the
    latter is actually unresolved.

    *ignore*, when given, names references that do not count as unresolved
    (system symbols, which ``explode_job()`` resolves later).
    """
    return any(
        m.group(0) != "&&" and not (ignore is not None and ignore(m.group(1)))
        for m in _SET_SYMBOL_PATTERN.finditer(value)
    )


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


def _strip_enclosing_parens(value: str) -> str:
    """Remove one pair of parentheses that encloses the whole of *value*.

    ``(1234,(A,B))`` becomes ``1234,(A,B)``; ``(A,B),(C)`` is returned as is
    because its first ``(`` closes before the end. Apostrophe-quoted text is
    skipped so a paren inside quotes does not count.
    """
    if len(value) < 2 or value[0] != "(" or value[-1] != ")":
        return value
    depth = 0
    in_quote = False
    for i, ch in enumerate(value):
        if ch == "'":
            in_quote = not in_quote
        elif in_quote:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and i != len(value) - 1:
                return value
    return value[1:-1]


def _create_job_from_statement(stmt: Statement) -> Job:
    """Create Job object from JOB statement"""
    accounting_info = None

    # Extract accounting information (first positional parameter). Any
    # further positional (e.g. the programmer-name operand in
    # ``JOB (acct),'programmer-name',...``) is left in job.parameters
    # rather than discarded -- mirrors _create_step_from_statement, which
    # only pops _pos_0 and leaves the rest of stmt.parameters intact.
    job_params = dict(stmt.parameters)
    if f"{POSITIONAL_PARAM_PREFIX}0" in job_params:
        accounting_info = _strip_enclosing_parens(
            job_params.pop(f"{POSITIONAL_PARAM_PREFIX}0")
        )

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
        if not isinstance(proc_or_pgm, str) or (
            "." not in proc_or_pgm and "/" not in proc_or_pgm
        ):
            procedure = proc_or_pgm
        else:
            program = proc_or_pgm

    for keyword, value in (("PGM", program), ("PROC", procedure)):
        if value is not None and (not isinstance(value, str) or value.startswith("(")):
            # PGM=(A,B): Step.program / Step.procedure are names, and every
            # consumer reads them as text.
            raise JCLSyntaxError(
                f"EXEC {keyword}= must name one "
                f"{'program' if keyword == 'PGM' else 'procedure'}, got "
                f"{jcl_value_text(value)}",
                stmt.line_number,
            )

    return Step(
        name=stmt.name,
        program=program,
        procedure=procedure,
        parameters=stmt.parameters,
        line_number=stmt.line_number,
    )


def _create_dd_from_statement(stmt: Statement) -> DDStatement:
    """Create DDStatement object from DD statement"""
    # DSNAME= is the long form of DSN=; either one names the dataset.
    dataset_name = stmt.parameters.get("DSN")
    if dataset_name is None:
        dataset_name = stmt.parameters.get("DSNAME")
    if isinstance(dataset_name, list):
        # ``DSN=(A.B)`` tokenizes to a list; dataset_name is always text, so
        # keep it as coded ("(A.B)") for validate_jcl() to report as an
        # invalid dataset name instead of crashing on it (#121).
        dataset_name = jcl_value_text(dataset_name)
    disposition = stmt.parameters.get("DISP")

    return DDStatement(
        name=stmt.name,
        dataset_name=dataset_name,
        disposition=disposition,
        parameters=stmt.parameters,
        line_number=stmt.line_number,
    )
