"""
JCL IF condition expression parser.

Parses the condition string from ``// IF condition THEN`` statements into a
structured AST.  The AST nodes can be inspected programmatically and evaluated
against known step return-code results.

Grammar (simplified)::

    condition  := or_expr
    or_expr    := and_expr ( ('OR' | '|') and_expr )*
    and_expr   := not_expr ( ('AND' | '&') not_expr )*
    not_expr   := ('NOT' | '¬' | '^' | '~') not_expr | primary
    primary    := '(' condition ')' | atom
    atom       := step_ref 'RC' op integer
               |  step_ref 'ABEND' [ ('=' | '¬=') ('TRUE' | 'FALSE') ]
               |  step_ref 'RUN'   [ ('=' | '¬=') ('TRUE' | 'FALSE') ]
    step_ref   := IDENTIFIER '.'                  (optional — omitted means "all steps so far")
               |  IDENTIFIER '.' IDENTIFIER '.'   (qualified after PROC explosion)
    op         := EQ | NE | LT | GT | LE | GE | = | ¬= | ^= | ~= | != | <> | < | > | <= | >=

Usage::

    from jclparser.condition_parser import parse_condition
    ast = parse_condition("STEP1.RC EQ 0 AND NOT STEP2.ABEND")
    result = ast.evaluate({"STEP1": (0, False), "STEP2": (4, False)})
    # result is True

Without a step name, ``RC`` is the highest return code of the steps run so far
and ``ABEND`` is true if any of them abended (IBM semantics).

Unparseable conditions — including any trailing text the grammar does not
cover, such as ``ABENDCC`` tests — return ``None`` from :func:`parse_condition` so the raw
string stored on :attr:`~jclparser.model.ConditionalBlock.condition` always
remains authoritative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# AST node types
# ---------------------------------------------------------------------------


class ConditionNode:
    """Base class for all condition expression nodes."""

    def evaluate(self, step_results: dict[str, tuple[int, bool]]) -> bool | None:
        """
        Evaluate the condition against known step results.

        Args:
            step_results: Mapping of *uppercase* step name to
                ``(return_code, abended)`` tuples.

        Returns:
            ``True`` or ``False`` when all referenced steps are present,
            ``None`` when a referenced step has not yet run.
        """
        raise NotImplementedError


@dataclass
class ReturnCodeCondition(ConditionNode):
    """``[STEPNAME.]RC op value``"""

    step_name: str | None  # None means "highest RC of the steps run so far"
    operator: str  # EQ NE LT GT LE GE
    value: int

    def evaluate(self, step_results: dict[str, tuple[int, bool]]) -> bool | None:
        if self.step_name:
            result = step_results.get(self.step_name.upper())
            if result is None:
                return None
            rc = result[0]
        else:
            if not step_results:
                return None
            rc = max(result[0] for result in step_results.values())

        op, v = self.operator, self.value
        if op == "EQ":
            return rc == v
        if op == "NE":
            return rc != v
        if op == "LT":
            return rc < v
        if op == "GT":
            return rc > v
        if op == "LE":
            return rc <= v
        if op == "GE":
            return rc >= v
        return None


@dataclass
class AbendCondition(ConditionNode):
    """``[STEPNAME.]ABEND``"""

    step_name: str | None

    def evaluate(self, step_results: dict[str, tuple[int, bool]]) -> bool | None:
        if self.step_name:
            result = step_results.get(self.step_name.upper())
            if result is None:
                return None
            return result[1]
        if not step_results:
            return None
        return any(result[1] for result in step_results.values())


@dataclass
class RunCondition(ConditionNode):
    """``[STEPNAME.]RUN`` — true if the step was executed."""

    step_name: str | None

    def evaluate(self, step_results: dict[str, tuple[int, bool]]) -> bool | None:
        if self.step_name:
            return self.step_name.upper() in step_results
        return bool(step_results)


@dataclass
class NotCondition(ConditionNode):
    """``NOT condition``"""

    operand: ConditionNode

    def evaluate(self, step_results: dict[str, tuple[int, bool]]) -> bool | None:
        inner = self.operand.evaluate(step_results)
        return None if inner is None else not inner


@dataclass
class AndCondition(ConditionNode):
    """``condition AND condition``"""

    left: ConditionNode
    right: ConditionNode

    def evaluate(self, step_results: dict[str, tuple[int, bool]]) -> bool | None:
        lv = self.left.evaluate(step_results)
        rv = self.right.evaluate(step_results)
        if lv is False or rv is False:
            return False  # short-circuit: one False makes the AND False
        if lv is None or rv is None:
            return None
        return True


@dataclass
class OrCondition(ConditionNode):
    """``condition OR condition``"""

    left: ConditionNode
    right: ConditionNode

    def evaluate(self, step_results: dict[str, tuple[int, bool]]) -> bool | None:
        lv = self.left.evaluate(step_results)
        rv = self.right.evaluate(step_results)
        if lv is True or rv is True:
            return True  # short-circuit: one True makes the OR True
        if lv is None or rv is None:
            return None
        return False


# ---------------------------------------------------------------------------
# Operator mapping
# ---------------------------------------------------------------------------

_OP_MAP: dict[str, str] = {
    "EQ": "EQ",
    "NE": "NE",
    "LT": "LT",
    "GT": "GT",
    "LE": "LE",
    "GE": "GE",
    # Symbol forms
    "=": "EQ",
    "¬=": "NE",
    "^=": "NE",
    "~=": "NE",
    "!=": "NE",
    "<>": "NE",
    "<": "LT",
    ">": "GT",
    "<=": "LE",
    ">=": "GE",
    # NOT-less-than / NOT-greater-than  (equivalent to GE / LE)
    "¬<": "GE",
    "^<": "GE",
    "~<": "GE",
    "!<": "GE",
    "¬>": "LE",
    "^>": "LE",
    "~>": "LE",
    "!>": "LE",
}

# Symbolic Boolean operators (IBM: & is AND, | is OR, ¬ is NOT; ^ and ~ stand in
# for ¬ on code pages without it).
_SYMBOL_KEYWORDS: dict[str, str] = {
    "&": "AND",
    "|": "OR",
    "¬": "NOT",
    "^": "NOT",
    "~": "NOT",
}

# The operator that keeps a comparison true with its operands swapped:
# ``4 LT RC`` is ``RC GT 4``.
_MIRRORED_OP: dict[str, str] = {
    "EQ": "EQ",
    "NE": "NE",
    "LT": "GT",
    "GT": "LT",
    "LE": "GE",
    "GE": "LE",
}

# Two-character operator prefixes (characters that combine with = / < / >)
_TWO_CHAR_OP_STARTS = frozenset("¬^~!<>")

# Precompiled regex pattern for numeric token matching
_RE_DIGITS = re.compile(r"\d+$")


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Split a condition string into tokens."""
    tokens: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # Whitespace
        if ch.isspace():
            i += 1
            continue

        # Parentheses
        if ch in "()":
            tokens.append(ch)
            i += 1
            continue

        # Two-character symbolic operators (¬=  ^=  ~=  !=  <=  >=  <>  ¬<  etc.)
        if ch in _TWO_CHAR_OP_STARTS and i + 1 < n:
            two = text[i : i + 2]
            if two in _OP_MAP:
                tokens.append(two)
                i += 2
                continue

        # Standalone Boolean symbols (after the two-character check, so that
        # "¬=" stays a comparison operator)
        if ch in _SYMBOL_KEYWORDS:
            tokens.append(_SYMBOL_KEYWORDS[ch])
            i += 1
            continue

        # Single-character symbolic operators
        if ch in "=<>":
            # Check for <= / >=
            if i + 1 < n and text[i : i + 2] in _OP_MAP:
                tokens.append(text[i : i + 2])
                i += 2
            else:
                tokens.append(ch)
                i += 1
            continue

        # Quoted string literal (e.g. values like 'PRODUCTION')
        if ch == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    j += 2  # escaped apostrophe
                elif text[j] == "'":
                    j += 1
                    break
                else:
                    j += 1
            tokens.append(text[i:j])
            i = j
            continue

        # Word: identifier, keyword, number, or step.attr reference
        if ch.isalnum() or ch in "@#$_":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "@#$_.-"):
                j += 1
            tokens.append(text[i:j])
            i = j
            continue

        # Anything else — skip (handles stray characters gracefully)
        i += 1

    return tokens


# ---------------------------------------------------------------------------
# Recursive descent parser
# ---------------------------------------------------------------------------


class _Parser:
    """Internal recursive-descent parser for condition expressions."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> str | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self) -> str:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _peek_upper(self) -> str | None:
        t = self._peek()
        return t.upper() if t else None

    # -- grammar rules -------------------------------------------------------

    def parse(self) -> ConditionNode:
        node = self._parse_or()
        # A stray trailing ')' changes nothing and is tolerated.
        while self._peek() == ")":
            self._consume()
        if self._peek() is not None:
            # Leftover tokens mean the grammar did not cover the whole
            # expression; returning the prefix would silently change it.
            raise ValueError(f"Unexpected token in condition: {self._peek()!r}")
        return node

    def _parse_or(self) -> ConditionNode:
        left = self._parse_and()
        while self._peek_upper() == "OR":
            self._consume()
            right = self._parse_and()
            left = OrCondition(left, right)
        return left

    def _parse_and(self) -> ConditionNode:
        left = self._parse_not()
        while self._peek_upper() == "AND":
            self._consume()
            right = self._parse_not()
            left = AndCondition(left, right)
        return left

    def _parse_not(self) -> ConditionNode:
        if self._peek_upper() == "NOT":
            self._consume()
            return NotCondition(self._parse_not())
        return self._parse_primary()

    def _parse_primary(self) -> ConditionNode:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of condition expression")

        if tok == "(":
            self._consume()
            node = self._parse_or()
            if self._peek() == ")":
                self._consume()
            elif self._peek() is not None:
                # Only a ')' missing at the very end is tolerated.
                raise ValueError("Unbalanced parentheses in condition")
            return node

        # Atom: [STEPNAME.]RC op value | [STEPNAME.]ABEND | [STEPNAME.]RUN
        # Three-level form: PROCSTEP.INNERSTEP.RC  (qualified step reference
        # produced after PROC explosion; "PROCSTEP.INNERSTEP" is used as the
        # step-name key in step_results).
        token = self._consume()
        step_name: str | None = None
        attr: str

        if "." in token:
            parts = token.split(".", 2)  # at most 3 parts
            if len(parts) == 3:
                # Three-level: OUTERST.INNERST.ATTR
                step_name = f"{parts[0]}.{parts[1]}".upper()
                attr = parts[2].upper()
            else:
                step_name = parts[0].upper()
                attr = parts[1].upper()
        else:
            attr = token.upper()

        if attr == "ABEND":
            return self._boolean_test(AbendCondition(step_name=step_name))

        if attr == "RUN":
            return self._boolean_test(RunCondition(step_name=step_name))

        if attr == "RC":
            op_tok = self._peek()
            if op_tok is None:
                return ReturnCodeCondition(step_name=step_name, operator="EQ", value=0)

            op = _OP_MAP.get(op_tok.upper())
            if op is None:
                # No recognisable operator after RC — treat as RC EQ 0
                return ReturnCodeCondition(step_name=step_name, operator="EQ", value=0)

            self._consume()  # consume operator

            val_tok = self._peek()
            if val_tok is not None and _RE_DIGITS.match(val_tok):
                self._consume()
                return ReturnCodeCondition(
                    step_name=step_name, operator=op, value=int(val_tok)
                )

            # A non-numeric value (e.g. an unresolved &SYMBOL) cannot be
            # compared; reading it as 0 would invent a different condition.
            raise ValueError(f"Expected a numeric RC value, got {val_tok!r}")

        # Bare number first: ``value op [STEP.]RC`` (rare).  The operands are
        # the other way round, so the operator is mirrored -- ``4 LT RC``
        # holds when RC is greater than 4, i.e. ``RC GT 4``.
        if _RE_DIGITS.match(attr):
            op_tok = self._peek()
            op = _OP_MAP.get(op_tok.upper()) if op_tok else None
            if op:
                self._consume()
                # After the operator the user may have written "RC" or a step ref
                next_tok = self._peek()
                ref = next_tok.upper() if next_tok else ""
                if ref == "RC" or ref.endswith(".RC"):
                    self._consume()
                    ref_step = ref[: -len(".RC")] if ref != "RC" else None
                    return ReturnCodeCondition(
                        step_name=ref_step or None,
                        operator=_MIRRORED_OP[op],
                        value=int(attr),
                    )
                raise ValueError(f"Expected RC after {attr} {op_tok}, got {next_tok!r}")
            # Fallback: single number, treat as RC EQ value
            return ReturnCodeCondition(
                step_name=step_name, operator="EQ", value=int(attr)
            )

        raise ValueError(f"Unrecognised condition atom: {token!r}")

    def _boolean_test(self, node: ConditionNode) -> ConditionNode:
        """Consume an optional ``= TRUE`` / ``= FALSE`` after ABEND or RUN."""
        op_tok = self._peek()
        op = _OP_MAP.get(op_tok.upper()) if op_tok else None
        if op not in ("EQ", "NE"):
            return node
        self._consume()
        value_tok = self._peek_upper()
        if value_tok not in ("TRUE", "FALSE"):
            raise ValueError(f"Expected TRUE or FALSE, got {value_tok!r}")
        self._consume()
        if (value_tok == "TRUE") == (op == "EQ"):
            return node
        return NotCondition(node)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_condition(condition_str: str) -> ConditionNode | None:
    """
    Parse a JCL IF condition string into a structured AST.

    The raw condition string (from ``// IF condition THEN``) must have
    the trailing ``THEN`` keyword already stripped.

    Args:
        condition_str: Raw condition text, e.g.
            ``"STEP1.RC EQ 0 AND NOT STEP2.ABEND"``

    Returns:
        A :class:`ConditionNode` subclass instance, or ``None`` if the
        condition could not be parsed (the caller should fall back to the
        raw string in that case).
    """
    if not condition_str or not condition_str.strip():
        return None
    try:
        tokens = _tokenize(condition_str.strip())
        if not tokens:
            return None
        parser = _Parser(tokens)
        return parser.parse()
    except (ValueError, TypeError, IndexError, AttributeError, RecursionError):
        # RecursionError: nesting (parentheses, NOT chains) deeper than the
        # recursive-descent parser can follow; fall back to the raw string.
        return None
