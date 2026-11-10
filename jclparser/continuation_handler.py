"""
Enhanced continuation line handling for JCL parsing.

Handles complex multi-line statements with proper context awareness.
"""

import logging
import re
from collections.abc import Collection
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

#: Statements whose operands are blank-delimited (IF ... THEN); a trailing
#: comma there is not a continuation request.
_BLANK_DELIMITED = frozenset({"IF", "THEN", "ELSE", "ENDIF"})


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

    def __init__(self) -> None:
        self.context = ContinuationContext()
        #: ``(index_in_input_list, comment_text)`` for every stripped comment
        #: field that still looks like it holds operands (it contains an
        #: ``=``).  Populated by :meth:`merge_continuation_lines`; the parser
        #: turns these into job warnings so a truncated or garbled statement
        #: is never dropped without a trace.
        self.suspect_comments: list[tuple[int, str]] = []
        #: ``(index_in_input_list, record_text)`` for every continuation-like
        #: record that followed a complete statement (no trailing comma) and
        #: so was not merged into it.  Populated by
        #: :meth:`merge_continuation_lines`; the parser reports them as job
        #: warnings, since the record's operands are otherwise ignored.
        self.stray_continuations: list[tuple[int, str]] = []
        #: ``(index_in_input_list, column)`` for every continuation record
        #: whose text starts after column 16; z/OS requires columns 4-16.
        self.late_continuations: list[tuple[int, int]] = []
        #: ``(index_in_input_list, statement_text)`` for every statement
        #: whose operand field ends with a comma but is followed by no
        #: continuation record (z/OS: expected continuation not received).
        self.missing_continuations: list[tuple[int, str]] = []

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

    def is_stray_continuation_record(self, line: str) -> bool:
        """Return True if *line* looks like a continuation record but starts a
        statement group of its own.

        A continuation record (blank name field, first token not an operation)
        only continues a statement whose operand field ended with a comma or
        is inside an open quoted string or parenthesised list.  When the
        statement before it was complete -- a missing comma, the classic
        ``DSN=PROD.MASTER`` / ``DISP=SHR`` slip -- the record is not merged
        (that silently corrupted the last value) and the caller reports it.
        """
        if self.ALT_CONTINUATION_PATTERN.match(line):
            return True
        if not self.CONTINUATION_PATTERN.match(line):
            return False
        if self._looks_like_new_statement(line):
            return False
        first_keyword = self._get_first_keyword(line)
        return bool(first_keyword) and first_keyword not in self.JCL_KEYWORDS

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

        # Without a trailing comma (or an open quote/paren) the previous
        # statement is complete: a record that is not a statement of its own
        # is a stray continuation, never merged (issue #123) -- see
        # is_stray_continuation_record().
        if not (has_implicit_continuation or has_unclosed_context):
            return False

        if self.CONTINUATION_PATTERN.match(line):
            return True

        stripped_line = line.strip()
        return (
            stripped_line.startswith("//")
            and not stripped_line.startswith("//*")
            and not self._looks_like_new_statement(line)
        )

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
        self._record_suspect_comment(line_num, comment)
        return statement

    def _record_suspect_comment(self, line_num: int, comment: str) -> None:
        if "=" in comment:
            self.suspect_comments.append((line_num, comment))

    def merge_continuation_lines(
        self, lines: list[str], card_images: Collection[int] = ()
    ) -> list[tuple[str, int]]:
        """
        Merge continuation lines into complete statements.

        Args:
            lines: List of raw JCL lines
            card_images: 0-based indices of *lines* that were card images
                continued in column 72 (see
                :func:`~jclparser.utils.is_continued_card_image`). A quoted
                string continued from such a record keeps its blanks through
                column 71 and resumes in column 16 of the next record.

        Returns:
            List of (merged_line, original_line_number) tuples
        """
        merged: list[tuple[str, int]] = []
        self.suspect_comments = []
        self.stray_continuations = []
        self.late_continuations = []
        self.missing_continuations = []
        i = 0
        # Whether the statement just merged ended on a card image continued
        # in column 72: a complete statement coded that way continues its
        # *comment field* on the next record.
        comment_continued = False

        while i < len(lines):
            line = lines[i]

            # Skip comments and empty lines
            if not line.strip() or line.strip().startswith("//*"):
                merged.append((line, i + 1))
                i += 1
                comment_continued = False
                continue

            # Check if this is a JCL statement
            if not line.startswith("//"):
                merged.append((line, i + 1))
                i += 1
                comment_continued = False
                continue

            i = self._merge_statement(lines, i, card_images, merged, comment_continued)
            comment_continued = i - 1 in card_images

        return merged

    def _merge_statement(
        self,
        lines: list[str],
        i: int,
        card_images: Collection[int],
        merged: list[tuple[str, int]],
        comment_continued: bool = False,
    ) -> int:
        """Merge the JCL statement starting at ``lines[i]`` with its continuations.

        Appends the merged statement (followed by any comments interspersed
        within it) to *merged* and returns the index of the first record
        after the statement.  *comment_continued* says the statement before
        ended on a card image continued in column 72; a continuation-like
        record after it continues that statement's comment field, so it is
        not reported as a stray continuation.
        """
        original_line_num = i + 1
        # Strip the statement's comment field before anything else: a
        # comment after a trailing comma otherwise hides the comma and the
        # continued operands are lost (see split_comment_field).
        group_operation = statement_operation(lines[i])
        line = self._strip_comment(lines[i], group_operation, original_line_num)
        # A complete statement whose card is continued in column 72 continues
        # its comment field on the next record (IBM: "Continuing the comment
        # field"), so that record is a comment, not a missing comma.
        if not comment_continued and self.is_stray_continuation_record(line):
            self.stray_continuations.append((original_line_num, line.strip()))

        # Start building merged line
        merged_line = line.rstrip()
        # Compute initial context for this statement line once.
        cached_ctx = self._analyze_line_context(merged_line)
        j = i + 1
        # The record whose text currently ends merged_line.
        last_record = i
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

            # A continuation record has no comment field of its own while
            # a quoted string is being continued (the blank would be inside
            # it). Inside a parenthesised list it may have one after a
            # subparameter's comma, so the open depth is passed along.
            # The comment is only recorded once the record is known to be
            # merged: a record that starts the next statement is stripped
            # (and recorded) again as that statement, which would report
            # the same comment twice.
            next_comment = ""
            if not cached_ctx.in_quotes:
                next_line, next_comment = split_comment_field(
                    next_line, group_operation, cached_ctx.paren_depth
                )

            # Check if next line is a continuation, passing cached context
            # to avoid re-scanning the full (growing) merged_line.
            continues_if = self._continues_if(merged_line, group_operation, next_line)
            if not (
                continues_if
                or self.is_continuation_line(next_line, merged_line, ctx=cached_ctx)
            ):
                # Not a continuation, stop merging
                break

            self._record_suspect_comment(j + 1, next_comment)
            if not continues_if:
                self._check_continuation_column(next_line, j + 1)
            # A quoted string continued from a column-72 card image keeps its
            # blanks through column 71 (see _join_continuation).
            card_image_pad = (
                71 - len(lines[last_record].rstrip())
                if cached_ctx.in_quotes and last_record in card_images
                else None
            )
            merged_line, cont_content = self._join_continuation(
                merged_line, next_line, continues_if, card_image_pad
            )

            # Incrementally update context: scan only the new content
            # starting from the prior cached state (not the full merged line).
            cached_ctx = self._analyze_line_context(
                cont_content, starting_ctx=cached_ctx
            )
            last_record = j
            j += 1

        if group_operation not in _BLANK_DELIMITED and merged_line.endswith(","):
            self.missing_continuations.append((original_line_num, merged_line))
        continued = j - i - 1
        if continued:
            logger.debug(
                "merged %d continuation line(s) into statement at line %d",
                continued,
                original_line_num,
            )

        merged.append((merged_line, original_line_num))
        merged.extend(interspersed_comments)
        return j

    def _check_continuation_column(self, line: str, line_num: int) -> None:
        """Record continuation *line* if its text starts after column 16."""
        column = len(line) - len(line[2:].lstrip()) + 1
        if column > 16:
            self.late_continuations.append((line_num, column))

    def _join_continuation(
        self,
        merged_line: str,
        next_line: str,
        continues_if: bool,
        card_image_pad: int | None,
    ) -> tuple[str, str]:
        """Append continuation record *next_line* to *merged_line*.

        *card_image_pad* is ``71 - len(previous record)`` when the statement
        is inside a quoted string and the record that currently ends
        *merged_line* was a card image continued in column 72, else ``None``.

        Returns ``(new_merged_line, continuation_content)``; the content is
        what the caller feeds into the incremental context scan.
        """
        raw_after_slashes = (next_line.removeprefix("//")).lstrip()
        had_leading_comma = raw_after_slashes.startswith(",")

        # Extract continuation content
        cont_content = self._extract_continuation_content(next_line)

        # Merge with proper separator
        stripped = merged_line.rstrip()
        if card_image_pad is not None and not next_line[2:15].strip():
            # IBM: a quoted string is coded through column 71
            # and continues in column 16 of the next record, so
            # blanks on either side of the break are part of it.
            cont_content = next_line[15:]
            padding = " " * max(card_image_pad, 0)
            return merged_line + padding + cont_content, cont_content
        if stripped.endswith(","):
            return stripped + cont_content, cont_content
        if had_leading_comma:
            return stripped + "," + cont_content, cont_content
        if continues_if:
            # IF operands are blank-delimited: keep a blank.
            return stripped + " " + cont_content, cont_content
        return stripped + cont_content, cont_content

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

            if char == "'":
                # JCL has no backslash escape: ``'C:\'`` is a complete
                # string.  The only escape is a doubled apostrophe.
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
