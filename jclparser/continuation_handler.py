"""
Enhanced continuation line handling for JCL parsing.

Handles complex multi-line statements with proper context awareness.
"""

from typing import ClassVar, List, Optional, Set, Tuple
from dataclasses import dataclass
import re


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
    # Only include primary JCL statement types, not parameter keywords
    JCL_KEYWORDS: ClassVar[Set[str]] = {
        "JOB",
        "EXEC",
        "DD",
        "PROC",
        "PEND",
        "SET",
        "IF",
        "ELSE",
        "ENDIF",
        "GOTO",
        "OUTPUT",
        "JCLLIB",
        "INCLUDE",
        "SCHED",
        "CNTL",
        "ENDCNTL",
    }

    def __init__(self):
        self.context = ContinuationContext()

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

    def is_continuation_line(
        self, line: str, previous_line: str = "", ctx: Optional[ContinuationContext] = None
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

            first_keyword = self._get_first_keyword(line)
            if first_keyword and first_keyword not in self.JCL_KEYWORDS:
                return True

        if has_implicit_continuation or has_unclosed_context:
            if line.strip().startswith("//") and not line.strip().startswith("//*"):
                return True

        return False

    def merge_continuation_lines(self, lines: List[str]) -> List[Tuple[str, int]]:
        """
        Merge continuation lines into complete statements.

        Args:
            lines: List of raw JCL lines

        Returns:
            List of (merged_line, original_line_number) tuples
        """
        merged = []
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

            # Start building merged line
            merged_line = line.rstrip()
            # Compute initial context for this statement line once.
            cached_ctx = self._analyze_line_context(merged_line)
            j = i + 1

            # Look ahead for continuation lines
            while j < len(lines):
                next_line = lines[j]

                # Stop merging if we hit a comment or empty line
                # (Comments break continuation chains)
                if not next_line.strip() or next_line.strip().startswith("//*"):
                    break

                # Check if next line is a continuation, passing cached context
                # to avoid re-scanning the full (growing) merged_line.
                if self.is_continuation_line(next_line, merged_line, ctx=cached_ctx):
                    raw_after_slashes = (next_line[2:] if next_line.startswith("//") else next_line).lstrip()
                    had_leading_comma = raw_after_slashes.startswith(",")

                    # Extract continuation content
                    cont_content = self._extract_continuation_content(next_line)

                    # Merge with proper separator
                    stripped = merged_line.rstrip()
                    if stripped.endswith(","):
                        merged_line = stripped + cont_content
                    elif had_leading_comma:
                        merged_line = stripped + "," + cont_content
                    else:
                        merged_line = stripped + cont_content

                    # Incrementally update context: scan only the new content
                    # starting from the prior cached state (not the full merged line).
                    cached_ctx = self._analyze_line_context(cont_content, starting_ctx=cached_ctx)
                    j += 1
                else:
                    # Not a continuation, stop merging
                    break

            merged.append((merged_line, original_line_num))
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
        self, line: str, starting_ctx: Optional[ContinuationContext] = None
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


def merge_continuation_lines(lines: List[str]) -> List[Tuple[str, int]]:
    """
    Convenience function to merge continuation lines.

    Args:
        lines: List of JCL lines

    Returns:
        List of (merged_line, line_number) tuples
    """
    handler = ContinuationLineHandler()
    return handler.merge_continuation_lines(lines)
