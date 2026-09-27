"""Shared extraction of *invoked program names* from TSO/DSN control text.

TSO batch wrappers (``IKJEFT01`` and friends) and the DB2 ``DSN`` command
processor read their control statements from ``SYSTSIN`` / ``SYSIN`` in-stream
data.  Those statements frequently name the application program that is
*actually* run — most commonly via the DSN ``RUN PROGRAM(...)`` subcommand or
the TSO ``CALL`` command.  When dependency analysis looks only at
``EXEC PGM=`` it sees the wrapper (e.g. IKJEFT01) and misses the real program.

This module provides the small, self-contained regex layer that recovers those
program names so profiles can surface them as structured output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..sql_detector import detect_sql_in_text

# DSN subcommand: RUN PROGRAM(PROGA) PLAN(PLANA) ...  TSO accepts the keyword
# abbreviated (``PROG``), the name quoted (``PROGRAM('PROGA')``), and the
# operands in any order (``RUN PLAN(P) PROGRAM(PROGA)``).
_RE_RUN_PROGRAM = re.compile(
    r"\bRUN\b[^\n]*?\bPROG(?:R|RA|RAM)?\s*\(\s*'?([A-Za-z0-9@#$]+)'?\s*\)",
    re.IGNORECASE,
)

# TSO comment: ``/* ... */``, or ``/*`` to the end of the line.
_RE_TSO_COMMENT = re.compile(r"/\*.*?(?:\*/|$)", re.MULTILINE)
# TSO continuation: a trailing ``-`` or ``+`` joins the next line.
_RE_TSO_CONTINUATION = re.compile(r"[-+][ \t]*\r?\n")

# TSO command: CALL 'HLQ.LOADLIB(MEMBER)' / CALL MEMBER / CALL *(MEMBER)
_RE_CALL = re.compile(r"\bCALL\s+(?:'([^']*)'|(\S+))", re.IGNORECASE)

# A bare load-module / member name (no qualifiers).
_RE_SIMPLE_NAME = re.compile(r"^[A-Za-z0-9@#$]+$")
# A member name inside parentheses, e.g. dsname(MEMBER) or *(MEMBER).
_RE_MEMBER = re.compile(r"\(([A-Za-z0-9@#$]+)\)")


@dataclass(frozen=True)
class InvokedProgram:
    """A program named inside SYSTSIN/SYSIN control text.

    Attributes:
        name: Upper-cased program / load-module name.
        via: The construct it was recovered from ("RUN PROGRAM" or "CALL").
    """

    name: str
    via: str


def _resolve_call_target(raw: str) -> str | None:
    """Resolve a TSO ``CALL`` operand to a load-module name, or None.

    Handles ``'HLQ.LOADLIB(MEMBER)'``, ``*(MEMBER)``, ``MEMBER`` and
    ``'MEMBER'``.  A dotted dataset name without an explicit member is
    ambiguous (no extractable module name) and yields None.

    Only the first comma-delimited operand names the program; the rest are
    run-time parameters.  Parentheses are interpreted as a dataset member only
    for dataset/member forms (``*(MEM)`` or ``HLQ.LIB(MEM)``); otherwise
    ``NAME(PARMS)`` is treated as the program ``NAME`` — so ``PGM,'PARM(MEM)'``
    resolves to ``PGM`` and ``PROC(1)`` resolves to ``PROC``.
    """
    operand = raw.strip().split(",", 1)[0].strip().strip("'").strip()
    if not operand:
        return None

    member = _RE_MEMBER.search(operand)
    if member:
        prefix = operand[: member.start()]
        if prefix == "*" or "." in prefix:
            # *(MEM) / HLQ.LIB(MEM) — the program is the member.
            return member.group(1).upper()
        if _RE_SIMPLE_NAME.match(prefix):
            # NAME(PARMS) — the parentheses hold parameters, not a member.
            return prefix.upper()
        return None

    if _RE_SIMPLE_NAME.match(operand):
        return operand.upper()
    return None


def _normalize_control_text(text: str) -> str:
    """Drop TSO comments and join continued lines, so each command is whole.

    Comments go first: a comment line ending in ``-`` is not a continuation.
    """
    text = _RE_TSO_COMMENT.sub(" ", text)
    return _RE_TSO_CONTINUATION.sub(" ", text)


def extract_invoked_programs(text: str | None) -> list[InvokedProgram]:
    """Return the programs named in *text* via RUN PROGRAM / CALL, de-duplicated.

    Order is preserved (first occurrence wins). Returns an empty list when
    *text* is falsy or contains no recognised invocation.
    """
    if not text:
        return []
    text = _normalize_control_text(text)

    found: list[InvokedProgram] = []
    seen: set[str] = set()

    def _add(name: str | None, via: str) -> None:
        if not name:
            return
        upper = name.upper()
        if upper in seen:
            return
        seen.add(upper)
        found.append(InvokedProgram(name=upper, via=via))

    for m in _RE_RUN_PROGRAM.finditer(text):
        _add(m.group(1), "RUN PROGRAM")

    for m in _RE_CALL.finditer(text):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        _add(_resolve_call_target(raw or ""), "CALL")

    return found


def collect_control_text(step) -> str:
    """Join the control text of a TSO/DB2 driver *step*.

    That is the in-stream data of its SYSTSIN/SYSIN DD -- and its ``PARM``,
    which carries exactly the same TSO command stream when the caller has
    nothing else to put in it::

        //RUNIT EXEC PGM=IKJEFT01,
        //      PARM='DSN SYSTEM(DB2P) RUN PROGRAM(MYPROG) PLAN(MYPLAN)'
        //SYSTSIN DD DUMMY

    Reading only the DD misses the real program in that shape entirely, and
    ``SYSTSIN DD DUMMY`` alongside a PARM-borne command is common enough on
    a real site to leave a visible hole in the dependency graph.
    """
    texts: list[str] = []
    parm = _parm_text(step)
    if parm:
        texts.append(parm)
    for dd_name in ("SYSTSIN", "SYSIN"):
        dd = step.get_dd(dd_name)
        if dd and dd.inline_data:
            texts.append(dd.inline_data)
    return "\n".join(texts)


def _parm_text(step) -> str:
    """The step's ``PARM`` as one string, whatever shape the parser left it in.

    ``PARM=(sub,parm)`` arrives as a list and ``PARM='text'`` as a plain
    string; both are joined to a single line so the command scanners above
    see the same text either way.
    """
    raw = step.parameters.get("PARM")
    if isinstance(raw, list):
        return " ".join(str(part) for part in raw)
    return str(raw) if raw else ""


def invoked_and_sql_notes(combined: str) -> tuple[list[InvokedProgram], list[str]]:
    """Recover invoked programs and embedded SQL from *combined* control text.

    Returns ``(invoked_programs, notes)`` where *notes* lists each invoked
    program (``VIA(NAME)``) followed by a single embedded-SQL summary line when
    SQL is present.
    """
    invoked = extract_invoked_programs(combined)
    notes = [f"{prog.via}({prog.name})" for prog in invoked]
    sql_hits = detect_sql_in_text(combined) if combined else []
    if sql_hits:
        categories = sorted({cat for _, cat in sql_hits})
        notes.append(f"embedded SQL: {', '.join(categories)}")
    return invoked, notes


__all__ = [
    "InvokedProgram",
    "collect_control_text",
    "extract_invoked_programs",
    "invoked_and_sql_notes",
]
