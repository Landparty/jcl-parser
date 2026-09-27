"""
Enhanced continuation line handling for JCL parsing.

Handles complex multi-line statements with proper context awareness.
"""

import logging
import re
from dataclasses import dataclass
from typing import ClassVar

from ._statement_parser import (
    _STATEMENT_TYPES,
    _find_then_end,
    _is_named_statement,
    split_comment_field,
    statement_operation,
)

logger = logging.getLogger(__name__)


@dataclass
class ContinuationContext:
    """Track context for continuation line processing."""

    in_quotes: bool = False
    paren_depth: int = 0
    bracket_depth: int = 0
    last_char: str = ""
    is_complete: bool = False


class ContinuationLineHandler:
    """
    Advanced continuation line handler for JCL.

    Handles:
    - Standard continuation (2-14 spaces after //, i.e., columns 4-16)
    - Continuation within quoted strings
    - Continuation within parentheses
    - Comments on continuation lines
    """

    # Standard JCL continuation: // followed by 2-14 spaces (columns 4-16)
    # Must be followed by content or end of line
    CONTINUATION_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^//\s{2,14}(\S|$)")

    # Alternative continuation: // followed by spaces and comma
    ALT_CONTINUATION_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^//\s+,")

    # Standard JCL statement keywords that start new statements (not continuations)
    # Only include primary JCL statement types, not parameter keywords.
    #
    # Derived from jclparser._statement_parser._STATEMENT_TYPES -- the
    # parser's own recognized-type allowlist -- so the two can never drift
    # again. They used to be two independently-maintained copies; a type
    # recognized by the parser but missing here got misclassified as a
    # continuation and silently merged into the previous statement,
    # corrupting it (see test_silent_drop_fixes.py
    # TestContinuationHandlerKeywordDrift). GOTO/SCHED are unioned in on top
    # even though they are not real _STATEMENT_TYPES entries -- untested,
    # likely vestigial, but left alone to avoid changing their existing
    # behavior.
    JCL_KEYWORDS: ClassVar[set[str]] = _STATEMENT_TYPES | {"GOTO", "SCHED"}

    def __init__(self):
        self.context = ContinuationContext()
        #: ``(index_in_input_list, comment_text)`` for every stripped comment
        #: field that still looks like it holds operands (it contains an
        #: ``=``).  Populated by :meth:`merge_continuation_lines`; the parser
        #: turns these into job warnings so a truncated or garbled statement
        #: is never dropped without a trace.
        self.suspect_comments: list[tuple[int, str]] = []

    def _has_implicit_continuation(self, previous_line: str) -> bool:
        """Check if previous line ends with comma (implicit continuation)."""
        return bool(previous_line.rstrip().endswith(","))

    def _has_unclosed_context(self, previous_line: str) -> bool:
        """Check if previous line has unclosed parentheses or quotes."""
        if not previous_line:
            return False
        ctx = self._analyze_line_context(previous_line)
        return ctx.paren_depth > 0 or ctx.in_quotes

    def _get_first_keyword(self, line: str) -> str:
        """Extract the first keyword from a line after // prefix."""
        content_after_slashes = line[2:]
        stripped = content_after_slashes.lstrip()
        if stripped:
            first_word = stripped.split()[0].upper()
            first_keyword = first_word.split("=")[0].split("(")[0]
            return first_keyword
        return ""

    def _looks_like_new_statement(self, line: str) -> bool:
        """Return True if *line* has a non-blank name field (e.g. ``//S2
        EXEC PGM=Y`` or even ``//S2 UNKNOWNOP FOO=BAR``).

        Per z/OS syntax, a true continuation record's name field (columns
        3-10) is always blank, so a line whose content starts immediately
        after ``//`` with no leading space is always a fresh statement —
        never a continuation — regardless of whether its operation keyword
        is one this parser recognizes, and even if the previous line ended
        with a dangling comma.
        """
        if not line.startswith("//"):
            return False
        content = line[2:]
        if bool(content) and not content[0].isspace():
            return True
        # ``//   STEP2 EXEC PGM=X`` — a statement whose name field starts late.
        # Its second token being an operation keyword gives it away.
        return _is_named_statement(content.split(), False)

    def is_continuation_line(
        self,
        line: str,
        previous_line: str = "",
        ctx: ContinuationContext | None = None,
    ) -> bool:
        """
        Determine if a line is a continuation of the previous line.

        Args:
            line: Current line to check
            previous_line: Previous line for context

        Returns:
            True if line is a continuation
        """
        if not line.strip() or line.strip().startswith("//*"):
            return False

        if self.ALT_CONTINUATION_PATTERN.match(line):
            return True

        has_implicit_continuation = self._has_implicit_continuation(previous_line)
        # Use provided context if available (avoids re-scanning the full merged line).
        # ctx replaces only the _has_unclosed_context check; implicit continuation
        # still uses previous_line directly (trivial endswith check, no growing-string cost).
        if ctx is not None:
            has_unclosed_context = ctx.paren_depth > 0 or ctx.in_quotes
        else:
            has_unclosed_context = self._has_unclosed_context(previous_line)

        if self.CONTINUATION_PATTERN.match(line):
            if has_implicit_continuation or has_unclosed_context:
                return True

            if self._looks_like_new_statement(line):
                return False

            first_keyword = self._get_first_keyword(line)
            if first_keyword and first_keyword not in self.JCL_KEYWORDS:
                return True

        if has_implicit_continuation or has_unclosed_context:
            stripped_line = line.strip()
            if (
                stripped_line.startswith("//")
                and not stripped_line.startswith("//*")
                and not self._looks_like_new_statement(line)
            ):
                return True

        return False

    @staticmethod
    def _continues_if(merged_line: str, group_operation: str, line: str) -> bool:
        """Return True if *line* continues an IF statement still missing THEN.

        An IF's relational expression may be broken at a blank and resumed on
        the next record (``//CHK IF S1.RC = 0 |`` / ``//   S1.ABEND THEN``).
        There is no trailing comma to signal it, and ``S1.ABEND THEN`` even
        looks like a statement named ``S1.ABEND``; what gives it away is that
        the IF has not reached its ``THEN`` yet.
        """
        return (
            group_operation == "IF"
            and line.startswith("// ")
            and not line.strip().startswith("//*")
            and _find_then_end(merged_line) is None
        )

    def _strip_comment(self, line: str, group_operation: str, line_num: int) -> str:
        """Strip *line*'s comment field, recording suspicious ones.

        A comment field containing an ``=`` is more likely to be truncated or
        garbled operands than prose, so it is remembered in
        :attr:`suspect_comments` for the caller to report.
        """
        statement, comment = split_comment_field(line, group_operation)
        if "=" in comment:
            self.suspect_comments.append((line_num, comment))
        return statement

    def merge_continuation_lines(self, lines: list[str]) -> list[tuple[str, int]]:
        """
        Merge continuation lines into complete statements.

        Args:
            lines: List of raw JCL lines

        Returns:
            List of (merged_line, original_line_number) tuples
        """
        merged = []
        self.suspect_comments = []
        i = 0

        while i < len(lines):
            line = lines[i]
            original_line_num = i + 1

            # Skip comments and empty lines
            if not line.strip() or line.strip().startswith("//*"):
                merged.append((line, original_line_num))
                i += 1
                continue

            # Check if this is a JCL statement
            if not line.startswith("//"):
                merged.append((line, original_line_num))
                i += 1
                continue

            # Strip the statement's comment field before anything else: a
            # comment after a trailing comma otherwise hides the comma and the
            # continued operands are lost (see split_comment_field).
            group_operation = statement_operation(line)
            line = self._strip_comment(line, group_operation, original_line_num)

            # Start building merged line
            merged_line = line.rstrip()
            # Compute initial context for this statement line once.
            cached_ctx = self._analyze_line_context(merged_line)
            j = i + 1
            # Comments encountered mid-continuation are buffered and emitted
            # right after the statement they interrupted (see below) instead
            # of immediately, so the statement itself keeps its place in the
            # output relative to source order.
            interspersed_comments: list[tuple[str, int]] = []

            # Look ahead for continuation lines
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()

                if next_stripped.startswith("//*"):
                    # A comment does not terminate a statement that has an
                    # explicit pending continuation (trailing comma, or an
                    # unclosed paren/quote) — per z/OS, comments may be
                    # interspersed within a continued statement. Preserve the
                    # comment in the output and keep looking for the actual
                    # continuation line so its operands aren't lost.
                    pending_continuation = (
                        merged_line.rstrip().endswith(",")
                        or cached_ctx.paren_depth > 0
                        or cached_ctx.in_quotes
                    )
                    if pending_continuation:
                        interspersed_comments.append((next_line, j + 1))
                        j += 1
                        continue
                    break

                # Stop merging if we hit an empty line
                if not next_stripped:
                    break

                # A continuation record only has a comment field of its own
                # when the statement so far is syntactically closed (the
                # blank that starts a comment would otherwise be inside the
                # quoted string or parenthesised list being continued).
                if not cached_ctx.in_quotes and cached_ctx.paren_depth == 0:
                    next_line = self._strip_comment(next_line, group_operation, j + 1)

                # Check if next line is a continuation, passing cached context
                # to avoid re-scanning the full (growing) merged_line.
                continues_if = self._continues_if(
                    merged_line, group_operation, next_line
                )
                if continues_if or self.is_continuation_line(
                    next_line, merged_line, ctx=cached_ctx
                ):
                    raw_after_slashes = (next_line.removeprefix("//")).lstrip()
                    had_leading_comma = raw_after_slashes.startswith(",")

                    # Extract continuation content
                    cont_content = self._extract_continuation_content(next_line)

                    # Merge with proper separator
                    stripped = merged_line.rstrip()
                    if stripped.endswith(","):
                        merged_line = stripped + cont_content
                    elif had_leading_comma:
                        merged_line = stripped + "," + cont_content
                    elif continues_if:
                        # IF operands are blank-delimited: keep a blank.
                        merged_line = stripped + " " + cont_content
                    else:
                        merged_line = stripped + cont_content

                    # Incrementally update context: scan only the new content
                    # starting from the prior cached state (not the full merged line).
                    cached_ctx = self._analyze_line_context(
                        cont_content, starting_ctx=cached_ctx
                    )
                    j += 1
                else:
                    # Not a continuation, stop merging
                    break

            continued = j - i - 1
            if continued:
                logger.debug(
                    "merged %d continuation line(s) into statement at line %d",
                    continued,
                    original_line_num,
                )

            merged.append((merged_line, original_line_num))
            merged.extend(interspersed_comments)
            i = j

        return merged

    def _extract_continuation_content(self, line: str) -> str:
        """
        Extract the content from a continuation line.

        Args:
            line: Continuation line

        Returns:
            Content without continuation markers
        """
        # Remove // prefix
        if line.startswith("//"):
            content = line[2:]
        else:
            content = line

        # Remove leading spaces (continuation marker)
        content = content.lstrip()

        # Remove leading comma if present (alternative continuation)
        if content.startswith(","):
            content = content[1:].lstrip()

        return content

    def _analyze_line_context(
        self, line: str, starting_ctx: ContinuationContext | None = None
    ) -> ContinuationContext:
        """
        Analyze a line to determine if it has unclosed quotes/parens.

        Args:
            line: Line to analyze
            starting_ctx: Optional starting state. When provided the scan
                continues from this context rather than from a blank state.
                Used for incremental updates in merge_continuation_lines().

        Returns:
            ContinuationContext with state information
        """
        if starting_ctx is not None:
            ctx = ContinuationContext(
                in_quotes=starting_ctx.in_quotes,
                paren_depth=starting_ctx.paren_depth,
                bracket_depth=starting_ctx.bracket_depth,
                last_char=starting_ctx.last_char,
                is_complete=False,
            )
        else:
            ctx = ContinuationContext()

        i = 0
        while i < len(line):
            char = line[i]

            if char == "'" and ctx.last_char != "\\":
                # Handle escaped quotes
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 2  # Skip escaped quote
                    continue
                ctx.in_quotes = not ctx.in_quotes

            elif not ctx.in_quotes:
                if char == "(":
                    ctx.paren_depth += 1
                elif char == ")":
                    ctx.paren_depth -= 1
                elif char == "[":
                    ctx.bracket_depth += 1
                elif char == "]":
                    ctx.bracket_depth -= 1

            ctx.last_char = char
            i += 1

        ctx.is_complete = (
            not ctx.in_quotes and ctx.paren_depth == 0 and ctx.bracket_depth == 0
        )

        return ctx
