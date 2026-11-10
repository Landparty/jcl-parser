"""Report INCLUDE-expanded line numbers against the main source (issue #118).

``// INCLUDE MEMBER=`` statements are expanded before the source is scanned,
so every line number the parser computes counts the inlined member lines.
:class:`IncludeLineMap` translates such a number back: a main-source line to
its own line, a member line to the line of the ``// INCLUDE`` statement in
the main source (the outermost one, for a nested INCLUDE).  Messages about a
member line also name the member and the line within it::

    Line 2 (INCLUDE member COMMON, line 3): EXEC statement missing ...

The parse runs on the expanded text unchanged; :func:`_parse_jcl_core
<jclparser.parser._parse_jcl_core>` applies the translation once, at the end
(:meth:`IncludeLineMap.relabel_job`) or to the exception that ends the parse
(:meth:`IncludeLineMap.relabel_error`).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable
from typing import Any

from .errors import JCLParseError
from .include_loader import LineOrigin
from .model import Job, Procedure

_LEADING_LINE = re.compile(r"^Line (\d+)")
_INNER_LINE = re.compile(r"\bon line (\d+)\b")


class IncludeLineMap:
    """Line number translation for one INCLUDE-expanded source."""

    def __init__(self, origins: list[LineOrigin]) -> None:
        self._origins = origins

    def origin(self, line_number: int) -> LineOrigin | None:
        """Where expanded line *line_number* came from (None if unknown)."""
        if 1 <= line_number <= len(self._origins):
            return self._origins[line_number - 1]
        return None

    def translate(self, line_number: int) -> int:
        """The main-source line of expanded line *line_number*."""
        origin = self.origin(line_number)
        return origin.line if origin is not None else line_number

    def note(self, line_number: int) -> str:
        """``"INCLUDE member M, line k"`` for a member line, else ``""``."""
        origin = self.origin(line_number)
        if origin is None or origin.member is None:
            return ""
        return f"INCLUDE member {origin.member}, line {origin.member_line}"

    def label(self, line_number: int) -> str:
        """``"Line N"``, plus the member note for a member line."""
        note = self.note(line_number)
        main_line = self.translate(line_number)
        return f"Line {main_line} ({note})" if note else f"Line {main_line}"

    def relabel_text(self, text: str) -> str:
        """Translate the ``Line N`` prefix (and ``on line N``) of a message."""
        text = _LEADING_LINE.sub(lambda m: self.label(int(m.group(1))), text, 1)
        return _INNER_LINE.sub(
            lambda m: f"on line {self.translate(int(m.group(1)))}", text
        )

    def relabel_error(self, exc: JCLParseError) -> None:
        """Translate the line number of the exception that ended the parse."""
        if exc.line_number <= 0:
            return
        exc.include_note = self.note(exc.line_number)
        exc.line_number = self.translate(exc.line_number)
        exc.args = (exc._format_message(),)

    def relabel_job(self, job: Job, own_procedures: Iterable[Procedure]) -> None:
        """Translate every line number on *job* and in its warnings.

        Only the procedures in *own_procedures* -- the in-stream ones, read
        from this source -- are relabelled: an external or built-in PROC
        carries line numbers of its own library member.
        """
        own = {id(proc) for proc in own_procedures}
        skip = {id(p) for p in job.procedures if id(p) not in own}
        self._relabel_object(job, skip)
        job.warnings[:] = [self.relabel_text(w) for w in job.warnings]
        job.unresolved_output_refs[:] = [
            (step_name, ref, self.translate(line))
            for step_name, ref, line in job.unresolved_output_refs
        ]
        job.conditional_errors[:] = [
            (self.translate(line), message) for line, message in job.conditional_errors
        ]
        job.statement_findings[:] = [
            (self.translate(line), message, severity)
            for line, message, severity in job.statement_findings
        ]

    def _relabel_object(self, obj: Any, seen: set[int]) -> None:
        """Translate ``line_number`` on *obj* and every model object under it."""
        if id(obj) in seen:
            return
        seen.add(id(obj))
        if isinstance(obj, (list, tuple)):
            for item in obj:
                self._relabel_object(item, seen)
        elif isinstance(obj, dict):
            for item in obj.values():
                self._relabel_object(item, seen)
        elif _is_model_object(obj):
            self._relabel_fields(obj, seen)

    def _relabel_fields(self, obj: Any, seen: set[int]) -> None:
        line_number = getattr(obj, "line_number", None)
        if isinstance(line_number, int) and line_number > 0:
            try:
                obj.line_number = self.translate(line_number)
            except dataclasses.FrozenInstanceError:
                pass
        for field in dataclasses.fields(obj):
            if not field.name.startswith("_") and field.name != "line_number":
                self._relabel_object(getattr(obj, field.name), seen)


def _is_model_object(obj: Any) -> bool:
    """A jclparser dataclass instance (not a class, not a foreign type)."""
    return (
        dataclasses.is_dataclass(obj)
        and not isinstance(obj, type)
        and type(obj).__module__.startswith("jclparser")
    )
