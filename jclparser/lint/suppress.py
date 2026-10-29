"""Inline lint suppression comments.

A JCL comment record can switch lint rules off:

``//* jcl-lint: disable=JCL-LINT-001,JCL-LINT-002``
    Suppresses those codes on the next statement (the next ``//`` record
    that is not a comment), so it goes on the line before the statement.
``//* jcl-lint: disable-file=JCL-LINT-004``
    Suppresses those codes everywhere in the file.

``all`` stands for every code.  Codes are matched case-insensitively, and
unknown codes are ignored.  A finding is matched by its line number, so a
directive only sees the records of the source it is read from (not those of
an INCLUDE member or an external PROC).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..errors import ValidationError
from ..utils import split_source_lines

_DIRECTIVE = re.compile(
    r"^//\*\s*jcl-lint:\s*(?P<kind>disable-file|disable)\s*=\s*(?P<codes>\S+)",
    re.IGNORECASE,
)

#: The code that stands for every code in a directive.
ALL = "ALL"


@dataclass
class Suppressions:
    """The suppression directives of one source.

    Attributes:
        file_codes: Codes suppressed in the whole file.
        line_codes: Statement line number -> codes suppressed on it.
    """

    file_codes: set[str] = field(default_factory=set)
    line_codes: dict[int, set[str]] = field(default_factory=dict)

    def suppresses(self, finding: ValidationError) -> bool:
        """True if a directive switches *finding* off."""
        code = (finding.error_code or "").upper()
        codes = self.file_codes | self.line_codes.get(finding.line_number or 0, set())
        return ALL in codes or (bool(code) and code in codes)

    def filter(self, findings: Iterable[ValidationError]) -> list[ValidationError]:
        """*findings* without the suppressed ones."""
        return [f for f in findings if not self.suppresses(f)]


def _is_statement(line: str) -> bool:
    return line.startswith("//") and not line.startswith("//*")


def parse_suppressions(source: str | Iterable[str]) -> Suppressions:
    """The suppression directives in *source* (JCL text or its lines)."""
    lines = split_source_lines(source) if isinstance(source, str) else list(source)
    result = Suppressions()
    pending: set[str] = set()
    for number, line in enumerate(lines, start=1):
        match = _DIRECTIVE.match(line)
        if match:
            codes = {c.upper() for c in match.group("codes").split(",") if c}
            if match.group("kind").lower() == "disable-file":
                result.file_codes |= codes
            else:
                pending |= codes
        elif pending and _is_statement(line):
            result.line_codes.setdefault(number, set()).update(pending)
            pending = set()
    return result


__all__ = ["ALL", "Suppressions", "parse_suppressions"]
