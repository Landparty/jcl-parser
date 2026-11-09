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


@dataclass
class JobParmStatement(JESControlStatement):
    """``/*JOBPARM`` — JES2 job parameters (CLASS, LINES, TIME, etc.)."""

    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class Jes3ControlStatement(JESControlStatement):
    """A JES3 ``//*COMMAND`` control statement (``//*MAIN``, ``//*FORMAT``, ...).

    ``parameters`` holds the keyword operands that could be split out; ``raw``
    always carries the statement text after ``//*``.
    """

    parameters: dict[str, str] = field(default_factory=dict)
    #: For ``//*DATASET``: the records of the input data set, as coded, up
    #: to ``//*ENDDATASET`` (or the ``END=`` terminator, which is not kept).
    data: list[str] = field(default_factory=list)


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


def _operand_field(params: str) -> str:
    """Return *params* up to its first blank outside quotes and parentheses.

    Like a JCL statement, a JES2 ``/*JOBPARM`` or JES3 ``//*MAIN`` statement's
    operand field ends at the first blank; what follows is a comment and must
    not be absorbed into the last parameter value.
    """
    depth = 0
    in_quotes = False
    for i, ch in enumerate(params):
        if ch == "'":
            in_quotes = not in_quotes
        elif in_quotes:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch.isspace() and depth == 0:
            return params[:i]
    return params


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
            parameters=_split_keyword_params(_operand_field(raw)),
        )

    if cmd_upper == "ROUTE":
        # ``/*ROUTE PRINT RMT5  comment``: subcommand, then the destination's
        # operand field -- the text after it is a comment.
        parts = raw.split(None, 1)
        sub = parts[0].upper() if parts else None
        dest = (_operand_field(parts[1].strip()) or None) if len(parts) > 1 else None
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
        kv = (
            _split_keyword_params(_operand_field(parts[1].strip()))
            if len(parts) > 1
            else {}
        )
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
            account=_operand_field(raw) or None,
        )

    if cmd_upper == "NOTIFY":
        return NotifyStatement(
            name=command,
            raw=raw,
            line_number=line_number,
            destination=_operand_field(raw) or None,
        )

    if cmd_upper == "PRIORITY":
        operand = _operand_field(raw)
        try:
            value = int(operand) if operand else None
        except ValueError:
            value = None
        return PriorityStatement(
            name=command, raw=raw, line_number=line_number, value=value
        )

    # Unknown JES command — let the caller fall back to the generic Statement.
    return None


#: JES3 control statements, written ``//*COMMAND ...`` with the command
#: starting immediately after ``//*`` (a blank there makes it an ordinary
#: comment).  ``//*ROUTE XEQ`` has its own typed model; the rest are captured
#: generically so they are not mistaken for comments and dropped.
JES3_COMMANDS: frozenset[str] = frozenset(
    {
        "MAIN",
        "FORMAT",
        "NET",
        "NETACCT",
        "OPERATOR",
        "PAUSE",
        "PROCESS",
        "ENDPROCESS",
        "DATASET",
        "ENDDATASET",
        "ROUTE",
        "SIGNOFF",
        "SIGNON",
    }
)


#: JES3 statements whose operand is free text (a message), not keywords.
_JES3_FREE_TEXT_COMMANDS: frozenset[str] = frozenset({"OPERATOR"})


def parse_jes3_control(comment_line: str, line_number: int = 0) -> Any:
    """Recognise a JES3 ``//*COMMAND`` control statement.

    JES3 control statements share the ``//*`` prefix with ordinary comments,
    so they are told apart by the command token starting in column 4 with no
    intervening blank (``//*MAIN CLASS=A``, not ``//* MAIN PROCESSING``).

    Returns a typed statement, or ``None`` when *comment_line* is an ordinary
    comment.
    """
    stripped = comment_line.strip()
    if not stripped.startswith("//*"):
        return None
    body = stripped[3:]
    if not body or body[0].isspace():
        return None
    parts = body.split(None, 1)
    command = parts[0].upper()
    if command not in JES3_COMMANDS:
        return None
    params = parts[1].strip() if len(parts) > 1 else ""
    if command == "ROUTE":
        route = parse_jes3_route_xeq(comment_line, line_number)
        if route is not None:
            return route
    return Jes3ControlStatement(
        name=parts[0],
        raw=body.strip(),
        line_number=line_number,
        parameters=_split_keyword_params(
            params if command in _JES3_FREE_TEXT_COMMANDS else _operand_field(params)
        ),
    )


def jes3_continued(statement: Any) -> bool:
    """True when a JES3 control statement's operand field ends with a comma,
    so the next ``//*`` record continues it (z/OS MVS JCL Reference, JES3
    control statements). JES2 ``/*`` statements are never continued (#185)."""
    if not isinstance(statement, Jes3ControlStatement):
        return False
    if statement.name.upper() in _JES3_FREE_TEXT_COMMANDS:
        return False
    parts = statement.raw.split(None, 1)
    if len(parts) < 2:
        return False
    return _operand_field(parts[1].strip()).rstrip().endswith(",")


def jes3_continuation_text(statement: Any, continuation_line: str) -> str:
    """The ``//*COMMAND operands`` text of *statement* with a continuation
    record's operand (from column 4, leading blanks dropped) appended."""
    parts = statement.raw.split(None, 1)
    operand = _operand_field(parts[1].strip()) if len(parts) > 1 else ""
    more = continuation_line.strip()[3:].strip()
    return f"//*{parts[0]} {operand}{more}"


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
    "JES3_COMMANDS",
    "JESControlStatement",
    "Jes3ControlStatement",
    "Jes3RouteXeqStatement",
    "JobParmStatement",
    "MessageStatement",
    "NetacctStatement",
    "NotifyStatement",
    "PriorityStatement",
    "RouteStatement",
    "SignonStatement",
    "XmitStatement",
    "parse_jes3_control",
    "parse_jes3_route_xeq",
    "parse_jes_control",
]
