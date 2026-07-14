"""Statement-line parsing for JCL.

Internal module split out of :mod:`jclparser.parser`. It contains everything
needed to turn a single (continuation-merged) JCL line into a
:class:`~jclparser.model.Statement`: the statement-type keyword table,
parameter-string tokenization, and the small pre-scan helpers used before the
main parse loop (INCLUDE detection, JCLLIB ORDER extraction).

The public entry point :func:`parse_statement` is re-exported unchanged from
both :mod:`jclparser` and :mod:`jclparser.parser`; import it from there.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .errors import JCLSyntaxError
from .model import Statement
from .plugins import get_plugin_registry
from .utils import POSITIONAL_PARAM_PREFIX

logger = logging.getLogger(__name__)

#: All recognised JCL statement type keywords (single canonical definition).
_STATEMENT_TYPES: frozenset = frozenset(
    {
        "JOB",
        "EXEC",
        "DD",
        "PROC",
        "PEND",
        "JCLLIB",
        "INCLUDE",
        "SET",
        "EXPORT",
        "IF",
        "THEN",
        "ELSE",
        "ENDIF",
        "XMIT",
        "OUTPUT",
        "SCHEDULE",
        "NULL",
        "COMMAND",
        "CNTL",
        "ENDCNTL",
    }
)

#: Lazily-initialised ParameterParser instance shared across calls (same pattern as utils.py).
_PARAMETER_PARSER = None

#: Characters that can precede '=' to form a relational operator (¬=, ^=, ~=, !=, <=, >=).
#: Defined at module level so the frozenset is built exactly once.
_OPERATOR_PREFIXES: frozenset = frozenset("¬^~!<>")


def parse_statement(line: str, line_number: int = 0) -> Statement | None:
    """
    Parse individual JCL statement for syntax analysis.

    Args:
        line: Single line of JCL text
        line_number: Line number for error context

    Returns:
        Parsed statement object or None if comment/empty

    Raises:
        JCLSyntaxError: If line cannot be parsed
    """
    # Check for plugin that can handle this line
    registry = get_plugin_registry()
    plugin = registry.get_parser_for_line(line)
    if plugin:
        return plugin.parse_statement(line, line_number)

    # Standard JCL parsing
    line = line.strip()

    # Skip comments and empty lines
    if not line or line.startswith("//*"):
        return None

    # JCL statements must start with //
    if line.startswith("/*"):
        if len(line) <= 2 or not line[2].strip():
            # Just '/*' or '/* ' is an EOF delimiter, ignore if treating as stmt
            return None

        # Parse JES statement
        # Format: /*COMMAND options
        parts = line[2:].split(None, 1)
        command = parts[0]
        params = parts[1] if len(parts) > 1 else ""

        return Statement(
            type="JES",
            name=command,
            parameters={"_raw": params},
            line_number=line_number,
        )

    if not line.startswith("//"):
        raise JCLSyntaxError(
            f"Invalid JCL statement (must start with //): {line}", line_number
        )

    # Remove // prefix
    content = line[2:]

    # Handle continuation lines - these start with spaces after // BUT check if it's actually a statement without name
    if content.startswith(" ") and content.strip():
        # Check if this might be a statement without a name field (like // SET, // IF, // EXEC, // DD, etc.)
        content_stripped = content.strip()
        _cs_parts = content_stripped.split()
        first_token = _cs_parts[0].upper() if _cs_parts else ""
        # All valid JCL statement types that can appear without a name field
        if first_token not in _STATEMENT_TYPES:
            # This is a true continuation line - return None
            return None

    content = content.strip()

    # Handle empty lines after // (NULL statement)
    if not content:
        # This is a NULL statement (//)
        return Statement(type="NULL", name="", parameters={}, line_number=line_number)

    # Parse statement name and type
    # Handle cases like "//         IF ..." where there's no name
    content_stripped = content.lstrip()

    if not content_stripped:
        return None

    # Check if first token is a statement type (no name field)
    _cs_parts2 = content_stripped.split()
    first_token = _cs_parts2[0] if _cs_parts2 else ""

    if first_token.upper() in _STATEMENT_TYPES:
        # No name field - statement starts directly with type
        name_part = ""
        rest = content_stripped
    elif " " not in content_stripped:
        # Only one token - could be name without operation
        name_part = content_stripped
        rest = ""
    else:
        # Has name field
        name_part, rest = content_stripped.split(" ", 1)
        rest = rest.strip()

    # Determine statement type
    if " " not in rest:
        statement_type = rest.upper()
        parameters_part = ""
    else:
        rest_upper = rest.upper()
        if rest_upper.startswith("SET "):
            statement_type = "SET"
            parameters_part = rest[4:].strip()  # Everything after "SET "
        else:
            statement_type, parameters_part = rest.split(" ", 1)
            statement_type = statement_type.upper()

    # Validate statement type
    if statement_type not in _STATEMENT_TYPES:
        # Don't crash on unknown statement types - create UNKNOWN type for graceful degradation
        return Statement(
            type="UNKNOWN",
            name=name_part,
            parameters={"_raw": parameters_part, "_statement_type": statement_type},
            line_number=line_number,
        )

    # Parse parameters
    stmt_warnings: list[str] = []
    parameters = (
        _parse_parameters(parameters_part, line_number, warnings=stmt_warnings)
        if parameters_part
        else {}
    )

    return Statement(
        type=statement_type,
        name=name_part,
        parameters=parameters,
        line_number=line_number,
        warnings=stmt_warnings,
    )


def _find_keyword_eq(part: str, operator_prefixes: frozenset) -> int | None:
    """Find the position of '=' that acts as a keyword parameter delimiter.

    Returns None if no keyword '=' is found (i.e., all '=' signs are part of
    relational operators like ¬=, ^=, ~=, !=, <=, >=).
    """
    pos = 0
    while pos < len(part):
        eq_pos = part.find("=", pos)
        if eq_pos == -1:
            return None
        # An '=' is a keyword delimiter if it's at position 0 or the preceding
        # character is NOT an operator prefix (¬, ^, ~, !, <, >)
        if eq_pos == 0 or part[eq_pos - 1] not in operator_prefixes:
            return eq_pos
        pos = eq_pos + 1
    return None


def _check_param_balance(param_string: str, line_number: int) -> None:
    """Validate that *param_string* has balanced quotes and parentheses.

    Raises JCLSyntaxError with a descriptive message on the first imbalance
    detected, including the 1-based column position of the offending character.
    """
    in_quotes = False
    paren_depth = 0
    quote_open_col: int = 0  # 1-based column of the unclosed opening quote
    paren_open_cols: list = []  # stack of 1-based columns for open parens
    i = 0
    while i < len(param_string):
        c = param_string[i]
        if c == "'":
            if in_quotes and i + 1 < len(param_string) and param_string[i + 1] == "'":
                i += 2
                continue
            if not in_quotes:
                quote_open_col = i + 1  # record where this quote was opened
            in_quotes = not in_quotes
        elif c == "(" and not in_quotes:
            paren_open_cols.append(i + 1)
            paren_depth += 1
        elif c == ")" and not in_quotes:
            paren_depth -= 1
            if paren_depth < 0:
                raise JCLSyntaxError(
                    f"Unmatched parentheses in parameter: {param_string}",
                    line_number,
                    column_number=i + 1,
                )
            if paren_open_cols:
                paren_open_cols.pop()
        i += 1
    if in_quotes:
        raise JCLSyntaxError(
            f"Unclosed quote in parameter: {param_string}",
            line_number,
            column_number=quote_open_col,
        )
    if paren_depth != 0:
        hint = (
            " (statement may have been truncated at column 71 —"
            " use JCL continuation lines to break long statements"
            " across multiple records)"
        )
        col = paren_open_cols[0] if paren_open_cols else 0
        raise JCLSyntaxError(
            f"Unmatched parentheses in parameter: {param_string}{hint}",
            line_number,
            column_number=col,
        )


def _parse_parameters(
    param_string: str, line_number: int = 0, warnings: list[str] | None = None
) -> dict[str, Any]:
    """Parse JCL parameters from parameter string.

    Args:
        param_string: Raw parameter text (everything after the statement type).
        line_number: Source line, used to annotate any warnings.
        warnings: Optional list to receive non-fatal diagnostics, e.g. a
            repeated keyword silently overwriting its earlier value.
    """
    parameters: dict[str, Any] = {}

    if not param_string.strip():
        return parameters

    # Handle special cases like DD * or DD DATA (only if standalone)
    param_upper = param_string.strip().upper()
    if param_upper == "*":
        parameters["*"] = True
        return parameters
    elif param_upper == "DATA" or param_upper.startswith("DATA,"):
        parameters["DATA"] = True
        # Continue parsing if there are additional parameters after DATA,
        if "," in param_string:
            # Parse remaining parameters
            remaining = param_string[param_string.index(",") + 1 :]
            # Continue to normal parameter parsing
            param_string = remaining
        else:
            return parameters

    # Validate balance then split using the canonical ParameterParser implementation
    _check_param_balance(param_string, line_number)
    global _PARAMETER_PARSER
    if _PARAMETER_PARSER is None:
        from .parameter_ast import ParameterParser

        _PARAMETER_PARSER = ParameterParser()
    parts = _PARAMETER_PARSER._split_parameters(param_string)

    # Parse individual parameters
    for i, part in enumerate(parts):
        # Find the first '=' that acts as a keyword parameter delimiter
        # (not part of a relational operator like ¬=, ^=, ~=, !=, <=, >=)
        keyword_eq_pos = _find_keyword_eq(part, _OPERATOR_PREFIXES)
        if keyword_eq_pos is not None and not part.startswith("("):
            # Keyword parameter
            eq_pos = keyword_eq_pos
            key = part[:eq_pos].strip().upper()  # Uppercase key
            value = part[eq_pos + 1 :].strip()

            if key in parameters and warnings is not None:
                warnings.append(
                    f"Line {line_number}: duplicate parameter '{key}' "
                    f"(previous value {parameters[key]!r} overwritten by '{value}')"
                )

            # Handle parameter lists like DSN=(A,B,C)
            if value.startswith("(") and value.endswith(")"):
                # Parse list value
                list_content = value[1:-1]
                list_items = _parse_list_parameter(list_content)
                parameters[key] = list_items
            else:
                # Remove quotes from quoted values
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1].replace("''", "'")
                parameters[key] = value
        else:
            # Positional parameter
            value = part
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            parameters[f"{POSITIONAL_PARAM_PREFIX}{i}"] = value

    logger.debug("parsed %d parameter(s) at line %d", len(parameters), line_number)
    return parameters


def _parse_list_parameter(list_content: str) -> list[str]:
    """Parse parameter list like A,B,C or 'A','B','C'.

    Empty positional subfields are preserved so that omitted DISP subfields
    such as ``DISP=(,CATLG,DELETE)`` retain their positional meaning.
    Trailing empty elements are stripped (from trailing commas).
    """
    items = []
    in_quotes = False
    paren_depth = 0
    start = 0

    i = 0
    while i < len(list_content):
        char = list_content[i]
        if char == "'":
            # Handle escaped quotes
            if in_quotes and i + 1 < len(list_content) and list_content[i + 1] == "'":
                i += 2
                continue
            in_quotes = not in_quotes
        elif char == "(" and not in_quotes:
            paren_depth += 1
        elif char == ")" and not in_quotes:
            paren_depth -= 1
        elif char == "," and not in_quotes and paren_depth == 0:
            item = list_content[start:i].strip()
            if item.startswith("'") and item.endswith("'"):
                item = item[1:-1].replace("''", "'")
            items.append(
                item
            )  # preserve empty strings for omitted positional subfields
            start = i + 1
        i += 1

    # Append final element
    item = list_content[start:].strip()
    if item.startswith("'") and item.endswith("'"):
        item = item[1:-1].replace("''", "'")
    items.append(item)

    # Strip trailing empty elements (from trailing commas) but keep internal ones
    while items and items[-1] == "":
        items.pop()

    return items


# Matches any of:
#   // INCLUDE ...      (no label, spaces before INCLUDE)
#   //INCLUDE ...       (no label, no space — INCLUDE starts right after //)
#   //LABEL INCLUDE ... (label present, INCLUDE is the operation token)
# The word boundary \b ensures we don't match partial tokens like INCLUDES.
_RE_HAS_INCLUDE = re.compile(
    r"^\s*//(?:[^\s*/][^\s]*\s+|\s+)?INCLUDE\b",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_jcllib_order(content: str) -> list[str]:
    """Quick pre-scan that extracts JCLLIB ORDER library names from raw JCL.

    Returns an ordered list of library names found in any ``JCLLIB ORDER=``
    statement in *content*.  Recognises the same syntactic forms as the main
    parser (no label, ``//JCLLIB``, and ``//LABEL JCLLIB``).

    This is a best-effort single-line scan — ORDER values split across JCL
    continuation lines are not resolved here.  The result is used to pass a
    library list to :func:`~jclparser.include_loader.resolve_includes` before
    the full parse begins.
    """
    libraries: list[str] = []
    for line in content.splitlines():
        line = line.lstrip()
        if not line.startswith("//") or line.startswith("//*"):
            continue
        # Detect JCLLIB operation token (same token-match approach as INCLUDE)
        statement = line[2:]
        stripped = statement.lstrip()
        parts = stripped.split(None, 1)
        if not parts:
            continue
        first_upper = parts[0].upper()
        if first_upper == "JCLLIB":
            params_part = parts[1] if len(parts) > 1 else ""
        else:
            # Try label + JCLLIB
            if len(parts) < 2:
                continue
            rest_parts = parts[1].split(None, 1)
            if not rest_parts or rest_parts[0].upper() != "JCLLIB":
                continue
            params_part = rest_parts[1] if len(rest_parts) > 1 else ""

        # Extract ORDER= value
        upper_params = params_part.upper()
        order_idx = upper_params.find("ORDER=")
        if order_idx == -1:
            continue
        rest = params_part[order_idx + 6 :].strip()
        # Strip surrounding parentheses if present
        if rest.startswith("("):
            end = rest.find(")")
            rest = rest[1:end] if end != -1 else rest[1:]
        for lib in rest.split(","):
            lib = lib.strip()
            if lib:
                libraries.append(lib)
    return libraries


def _has_include_statement(content: str) -> bool:
    """Return True if *content* contains at least one INCLUDE statement.

    Fast pre-check so the overhead of the include-resolution pass is avoided
    for the vast majority of JCL that contains no INCLUDEs.  Handles all
    syntactic forms accepted by :func:`parse_statement`:

    * ``// INCLUDE MEMBER=name``   — no label, space(s) before INCLUDE
    * ``//INCLUDE MEMBER=name``    — no label, no leading space
    * ``//LABEL INCLUDE MEMBER=name`` — explicit label
    """
    return bool(_RE_HAS_INCLUDE.search(content))
