"""Shared tokeniser for utility control statements (DFSORT, IEBCOPY).

Both programs read 80-column control statements laid out like JCL:

* an optional *label* starting in column 1,
* the *operation* (``SORT``, ``COPY``, ...),
* the *operands*, which end at the first blank outside quotes and
  parentheses,
* anything after that is a *remark* and is ignored.

A line whose operands end with a comma, or that has a non-blank in column 72,
is continued on the next line.  A ``*`` as the first non-blank character makes
a comment statement.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ControlStatement:
    """One logical control statement.

    Attributes:
        operation: Upper-cased operation name, or ``""`` for a statement made
            of operands only (an IEBCOPY ``INDD=`` statement following a
            ``COPY``).
        operands: The operand field, continuations joined.
        label: The label, or ``""``.
    """

    operation: str
    operands: str
    label: str = ""


def _next_field(text: str, start: int = 0) -> tuple[str, int]:
    """The field of *text* starting at the first non-blank at or after
    *start*: up to the first blank outside quotes and parentheses.  Returns
    the field and the position just after it."""
    pos = start
    while pos < len(text) and text[pos] in " \t":
        pos += 1
    begin = pos
    depth = 0
    quoted = False
    while pos < len(text):
        char = text[pos]
        if char == "'":
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth = max(depth - 1, 0)
        elif not quoted and depth == 0 and char in " \t":
            break
        pos += 1
    return text[begin:pos], pos


def split_operands(operands: str) -> list[str]:
    """Split *operands* at the commas outside quotes and parentheses."""
    parts: list[str] = []
    depth = 0
    quoted = False
    current: list[str] = []
    for char in operands:
        if char == "'":
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth = max(depth - 1, 0)
        elif not quoted and depth == 0 and char == ",":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _card_body(line: str) -> tuple[str, bool]:
    """The statement columns of *line* and whether column 72 continues it.

    Columns 73-80 are a sequence field on an 80-column card; a longer line
    is free-form text and is taken whole.
    """
    line = line.rstrip("\r\n")
    if 72 <= len(line) <= 80:
        return line[:71].rstrip(), line[71] not in " \t"
    return line.rstrip(), False


def _new_statement(body: str, operations: frozenset[str]) -> ControlStatement:
    """Split the first line of a statement into label, operation, operands."""
    first, pos = _next_field(body)
    if first.upper() in operations:
        operands, _ = _next_field(body, pos)
        return ControlStatement(first.upper(), operands)
    if body[:1] not in (" ", "\t") and "=" not in first:
        # A label in column 1, then the operation.
        operation, pos = _next_field(body, pos)
        operands, _ = _next_field(body, pos)
        return ControlStatement(operation.upper(), operands, label=first)
    return ControlStatement("", first)


def parse_control_statements(
    text: str, operations: frozenset[str]
) -> list[ControlStatement]:
    """The logical control statements in *text*.

    *operations* are the operation names the program knows: one coded in
    column 1 is read as the operation rather than as a label (a common, if
    strictly invalid, layout).  Remarks and comment statements are dropped.
    """
    statements: list[ControlStatement] = []
    continued = False
    for line in text.splitlines():
        body, col72 = _card_body(line)
        if not body.strip():
            continue
        if body.lstrip().startswith("*") and not continued:
            continue
        if continued:
            more, _ = _next_field(body)
            statements[-1].operands += more
        else:
            statements.append(_new_statement(body, operations))
        continued = col72 or statements[-1].operands.endswith(",")
    return statements


__all__ = ["ControlStatement", "parse_control_statements", "split_operands"]
