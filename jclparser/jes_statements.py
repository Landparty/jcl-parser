"""
Typed JES2/JES3 control statement models.

JES (Job Entry Subsystem) statements begin with ``/*`` (JES2) or ``//*`` (JES3
operator commands like ``//*ROUTE XEQ``).  The core parser used to capture every
``/*COMMAND`` as an opaque :class:`~jclparser.model.Statement` with ``type="JES"``
and a ``_raw`` parameter.  This module promotes the common commands to typed
dataclasses with parsed fields, while leaving unknown commands as the legacy
generic Statement (backwards compatible).

See :func:`parse_jes_control` for the dispatcher used by ``parse_jcl``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JESControlStatement:
    """Base class for typed JES control statements.

    Provides common fields (command name, raw parameter text, line number)
    and a ``type`` tag of ``"JES"`` so existing consumers that key off
    ``stmt.type`` continue to work.
    """

    name: str
    raw: str = ""
    line_number: int = 0
    type: str = field(default="JES", init=False, repr=False)

    def to_source(self) -> str:
        """Return an approximate source representation (``/*CMD raw``)."""
        if self.raw:
            return f"/*{self.name} {self.raw}".rstrip()
        return f"/*{self.name}"


@dataclass
class JobParmStatement(JESControlStatement):
    """``/*JOBPARM`` — JES2 job parameters (CLASS, LINES, TIME, etc.)."""

    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class RouteStatement(JESControlStatement):
    """``/*ROUTE`` — route SYSOUT / job output.

    ``subcommand`` is ``"XEQ"``, ``"PRINT"``, or ``"PUNCH"`` when recognised.
    """

    subcommand: str | None = None
    destination: str | None = None


@dataclass
class XmitStatement(JESControlStatement):
    """``/*XMIT`` — transmit a job (NJE) to another node."""

    destination: str | None = None
    dlm: str | None = None


@dataclass
class SignonStatement(JESControlStatement):
    """``/*SIGNON`` — operator signon (JES2 RJE)."""


@dataclass
class MessageStatement(JESControlStatement):
    """``/*MESSAGE`` — operator message from the job."""

    text: str = ""


@dataclass
class NetacctStatement(JESControlStatement):
    """``/*NETACCT`` — network accounting number."""

    account: str | None = None


@dataclass
class NotifyStatement(JESControlStatement):
    """``/*NOTIFY`` — alternate notify destination."""

    destination: str | None = None


@dataclass
class PriorityStatement(JESControlStatement):
    """``/*PRIORITY`` — job selection priority."""

    value: int | None = None


@dataclass
class Jes3RouteXeqStatement(JESControlStatement):
    """``//*ROUTE XEQ nodename`` — JES3 execution routing.

    Unlike JES2 commands, JES3 control statements start with ``//*`` and are
    otherwise indistinguishable from comments, so the caller has to route
    them in explicitly.
    """

    node: str | None = None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _split_keyword_params(params: str) -> dict[str, str]:
    """Split a simple ``K=V,K=V`` parameter string.

    JES control parameters are much simpler than DD/EXEC parameters — no
    nested parentheses, no continuation quirks — so a minimal split is
    sufficient.  Unparseable segments are stored under positional keys
    ``_pos0``, ``_pos1`` to preserve information without crashing.
    """
    out: dict[str, str] = {}
    if not params:
        return out
    # Respect parens so ROUTE=(LOCAL,NODE2) is left intact.
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in params:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())

    pos = 0
    for p in parts:
        if not p:
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().upper()] = v.strip()
        else:
            out[f"_pos{pos}"] = p
            pos += 1
    return out


def parse_jes_control(command: str, params: str, line_number: int = 0) -> Any:
    """Dispatch on *command* and return the appropriate typed statement.

    Args:
        command: Command token after ``/*`` (e.g. ``"JOBPARM"``, ``"ROUTE"``).
        params: Raw parameter text after the command (may be empty).
        line_number: Source line number.

    Returns:
        A :class:`JESControlStatement` subclass instance, or a generic
        :class:`~jclparser.model.Statement` for unknown commands (handled by
        the caller — this function only covers the typed cases).
    """
    cmd_upper = command.upper()
    raw = params.strip()

    if cmd_upper == "JOBPARM":
        return JobParmStatement(
            name=command,
            raw=raw,
            line_number=line_number,
            parameters=_split_keyword_params(raw),
        )

    if cmd_upper == "ROUTE":
        parts = raw.split(None, 1)
        sub = parts[0].upper() if parts else None
        dest = parts[1].strip() if len(parts) > 1 else None
        return RouteStatement(
            name=command,
            raw=raw,
            line_number=line_number,
            subcommand=sub,
            destination=dest,
        )

    if cmd_upper == "XMIT":
        parts = raw.split(None, 1)
        dest = parts[0] if parts else None
        kv = _split_keyword_params(parts[1]) if len(parts) > 1 else {}
        return XmitStatement(
            name=command,
            raw=raw,
            line_number=line_number,
            destination=dest,
            dlm=kv.get("DLM"),
        )

    if cmd_upper == "SIGNON":
        return SignonStatement(name=command, raw=raw, line_number=line_number)

    if cmd_upper == "MESSAGE":
        return MessageStatement(
            name=command, raw=raw, line_number=line_number, text=raw
        )

    if cmd_upper == "NETACCT":
        return NetacctStatement(
            name=command,
            raw=raw,
            line_number=line_number,
            account=raw or None,
        )

    if cmd_upper == "NOTIFY":
        return NotifyStatement(
            name=command,
            raw=raw,
            line_number=line_number,
            destination=raw or None,
        )

    if cmd_upper == "PRIORITY":
        try:
            value = int(raw) if raw else None
        except ValueError:
            value = None
        return PriorityStatement(
            name=command, raw=raw, line_number=line_number, value=value
        )

    # Unknown JES command — let the caller fall back to the generic Statement.
    return None


def parse_jes3_route_xeq(
    comment_line: str, line_number: int = 0
) -> Jes3RouteXeqStatement | None:
    """Recognise ``//*ROUTE XEQ nodename`` from a JES3 comment line.

    Returns ``None`` if *comment_line* is not a recognised JES3 routing
    statement.  Callers pass the line verbatim (including the ``//*`` prefix).
    """
    stripped = comment_line.strip()
    if not stripped.startswith("//*"):
        return None
    body = stripped[3:].strip()
    parts = body.split()
    if len(parts) < 2 or parts[0].upper() != "ROUTE" or parts[1].upper() != "XEQ":
        return None
    node = parts[2] if len(parts) > 2 else None
    return Jes3RouteXeqStatement(
        name="ROUTE",
        raw=body,
        line_number=line_number,
        node=node,
    )


__all__ = [
    "JESControlStatement",
    "JobParmStatement",
    "RouteStatement",
    "XmitStatement",
    "SignonStatement",
    "MessageStatement",
    "NetacctStatement",
    "NotifyStatement",
    "PriorityStatement",
    "Jes3RouteXeqStatement",
    "parse_jes_control",
    "parse_jes3_route_xeq",
]
