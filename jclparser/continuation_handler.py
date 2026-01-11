"""
Enhanced continuation line handling for JCL parsing.

Handles complex multi-line statements with proper context awareness.
"""

from typing import List, Tuple
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
    - Standard continuation (15+ spaces after //)
    - Continuation within quoted strings
    - Continuation within parentheses
    - Comments on continuation lines
    """
    
    # Standard JCL continuation: // followed by 15+ spaces
    CONTINUATION_PATTERN = re.compile(r'^//\s{15,}')
    
    # Alternative continuation: // followed by spaces and comma
    ALT_CONTINUATION_PATTERN = re.compile(r'^//\s+,')
    
    def __init__(self):
        self.context = ContinuationContext()
    
    def is_continuation_line(self, line: str, previous_line: str = "") -> bool:
        """
        Determine if a line is a continuation of the previous line.
        
        Args:
            line: Current line to check
            previous_line: Previous line for context
            
        Returns:
            True if line is a continuation
        """
        # Skip empty lines and comments
        if not line.strip() or line.strip().startswith("//*"):
            return False
        
        # Check for standard continuation pattern
        if self.CONTINUATION_PATTERN.match(line):
            return True
        
        # Check for alternative continuation (// ,param=value)
        if self.ALT_CONTINUATION_PATTERN.match(line):
            return True
        
        # Check if previous line ends with comma (implicit continuation)
        if previous_line.rstrip().endswith(','):
            # But only if current line starts with //
            if line.strip().startswith('//'):
                return True
        
        # Check if we're inside unclosed parentheses or quotes
        if previous_line:
            ctx = self._analyze_line_context(previous_line)
            if ctx.paren_depth > 0 or ctx.in_quotes:
                return True
        
        return False
    
    def merge_continuation_lines(
        self, 
        lines: List[str]
    ) -> List[Tuple[str, int]]:
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
            j = i + 1
            
            # Look ahead for continuation lines
            while j < len(lines):
                next_line = lines[j]
                
                # Stop merging if we hit a comment or empty line
                # (Comments break continuation chains)
                if not next_line.strip() or next_line.strip().startswith("//*"):
                    break
                
                # Check if next line is a continuation
                if self.is_continuation_line(next_line, merged_line):
                    # Extract continuation content
                    cont_content = self._extract_continuation_content(next_line)
                    
                    # Merge with proper separator
                    if merged_line.rstrip().endswith(','):
                        # Already has comma separator
                        merged_line = merged_line.rstrip() + cont_content
                    else:
                        # Add comma separator if needed
                        if cont_content and not cont_content.startswith(','):
                            merged_line = merged_line.rstrip() + ',' + cont_content
                        else:
                            merged_line = merged_line.rstrip() + cont_content
                    
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
        if content.startswith(','):
            content = content[1:].lstrip()
        
        return content
    
    def _analyze_line_context(self, line: str) -> ContinuationContext:
        """
        Analyze a line to determine if it has unclosed quotes/parens.
        
        Args:
            line: Line to analyze
            
        Returns:
            ContinuationContext with state information
        """
        ctx = ContinuationContext()
        
        i = 0
        while i < len(line):
            char = line[i]
            
            if char == "'" and ctx.last_char != '\\':
                # Handle escaped quotes
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 2  # Skip escaped quote
                    continue
                ctx.in_quotes = not ctx.in_quotes
            
            elif not ctx.in_quotes:
                if char == '(':
                    ctx.paren_depth += 1
                elif char == ')':
                    ctx.paren_depth -= 1
                elif char == '[':
                    ctx.bracket_depth += 1
                elif char == ']':
                    ctx.bracket_depth -= 1
            
            ctx.last_char = char
            i += 1
        
        ctx.is_complete = (
            not ctx.in_quotes and 
            ctx.paren_depth == 0 and 
            ctx.bracket_depth == 0
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
