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

# DSN subcommand: RUN PROGRAM(PROGA) PLAN(PLANA) ...
_RE_RUN_PROGRAM = re.compile(
    r"\bRUN\s+PROGRAM\s*\(\s*([A-Za-z0-9@#$]+)\s*\)", re.IGNORECASE
)

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
    """
    raw = raw.strip()
    # Only the first comma-delimited operand is the program; the rest are parms.
    member = _RE_MEMBER.search(raw)
    if member:
        return member.group(1).upper()

    token = raw.split(",", 1)[0].strip().strip("'").strip()
    if _RE_SIMPLE_NAME.match(token):
        return token.upper()
    return None


def extract_invoked_programs(text: str | None) -> list[InvokedProgram]:
    """Return the programs named in *text* via RUN PROGRAM / CALL, de-duplicated.

    Order is preserved (first occurrence wins). Returns an empty list when
    *text* is falsy or contains no recognised invocation.
    """
    if not text:
        return []

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


__all__ = ["InvokedProgram", "extract_invoked_programs"]
