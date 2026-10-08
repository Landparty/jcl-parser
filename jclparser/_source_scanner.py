"""Source pre-scan: classify records, then merge continuation lines.

Before the parse loop sees a single statement, the source is read record by
record to find the records that are *not* JCL — in-stream data (``DD *`` /
``DD DATA`` / ``DLM=``, and the implicit ``//SYSIN DD *`` JES assumes for data
with no DD) and the program control records of a ``CNTL``/``ENDCNTL`` block.
Only the remaining JCL records go through continuation merging; the data
records are then woven back in, in source order.

:func:`_merge_source_lines` is the entry point, used by
:func:`jclparser.parser.parse_jcl` and by
:func:`jclparser.include_loader.resolve_includes` (so an ``// INCLUDE`` inside
in-stream data is left alone). Both are re-exported from
:mod:`jclparser.parser` for backward compatibility.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from ._statement_parser import (
    _STATEMENT_TYPES,
    _operand_field,
    _parse_parameters,
    split_comment_field,
    statement_operation,
)
from .continuation_handler import ContinuationLineHandler
from .errors import JCLSyntaxError
from .utils import (
    instream_delimiter,
    is_continued_card_image,
    normalize_jcl_line,
    split_source_lines,
)


class ScannedSource(NamedTuple):
    """Result of :func:`_merge_source_lines` (unpacks like the old 4-tuple)."""

    #: ``(line, 1-based line number)`` pairs ready for the parse loop.
    merged_lines: list[tuple[str, int]]
    #: 0-based indices of in-stream (``DD *`` / ``DD DATA``) data records,
    #: delimiter records included.
    inline_data_indices: set[int]
    #: 0-based indices of the control records inside a ``CNTL`` block.
    control_data_indices: set[int]
    #: Findings about records that were discarded or repaired.
    warnings: list[str]


def _merge_source_lines(content: str) -> ScannedSource:
    """Normalize, mark in-stream data, and merge continuation lines.

    Neither in-stream data nor CNTL control records may be parsed as JCL
    statements; the parse loop uses the returned index sets to route them.
    The warnings report an unterminated CNTL block and comment fields that
    were stripped off statements but still looked like operands (truncated
    or garbled records).
    """
    raw_lines = split_source_lines(content)
    lines = [normalize_jcl_line(line) for line in raw_lines]

    classifier = _RecordClassifier(lines)
    jcl_indices = classifier.run()

    handler = ContinuationLineHandler()
    merged_jcl = merge_continuations(raw_lines, lines, jcl_indices, handler)

    # Map each merged statement back to the original index of its first
    # record. Continuation records folded into a statement are absent from
    # this map and are skipped when weaving the lines back together.
    merged_start = {
        jcl_indices[jcl_line_num - 1]: merged_line
        for merged_line, jcl_line_num in merged_jcl
    }
    merged_lines = _weave_lines(
        lines,
        merged_start,
        classifier.inline_data_indices | classifier.control_data_indices,
    )

    # Map the handler's suspect comment fields back to original line numbers.
    warnings = classifier.warnings + [
        f"Line {jcl_indices[jcl_line_num - 1] + 1}: text after the "
        f"operand field ignored as a comment, but it looks like operands: "
        f"{comment!r}"
        for jcl_line_num, comment in handler.suspect_comments
    ]

    return ScannedSource(
        merged_lines,
        classifier.inline_data_indices,
        classifier.control_data_indices,
        warnings,
    )


def merge_continuations(
    raw_lines: Sequence[str],
    lines: Sequence[str],
    indices: Sequence[int],
    handler: ContinuationLineHandler | None = None,
) -> list[tuple[str, int]]:
    """Merge the continuation records among ``lines[i] for i in indices``.

    *raw_lines* are the records before :func:`normalize_jcl_line`; they decide
    which records are column-72 card images. Returns the handler's
    ``(merged_line, 1-based position in indices)`` pairs.
    """
    if handler is None:
        handler = ContinuationLineHandler()
    return handler.merge_continuation_lines(
        [lines[i] for i in indices],
        card_images={
            n
            for n, orig in enumerate(indices)
            if is_continued_card_image(raw_lines[orig])
        },
    )


def _weave_lines(
    lines: list[str], merged_start: dict[int, str], data_indices: set[int]
) -> list[tuple[str, int]]:
    """Recombine merged statements with the data records, in source order.

    A comment (or blank) record met inside a continued statement is its own
    entry, but it must come *before* that merged statement: a DD that opens
    in-stream data (``DD *,`` / ``//* c`` / ``//  DLM=$$``) would otherwise
    read the comment as its first data record, or end its data at it
    (issue #58). ``stmt_pos`` is the entry of the last statement still open
    to continuation records.
    """
    merged_lines: list[tuple[str, int]] = []
    stmt_pos: int | None = None
    for i, line in enumerate(lines):
        if i in data_indices:
            merged_lines.append((line, i + 1))
            stmt_pos = None
        elif i in merged_start:
            merged_lines.append((merged_start[i], i + 1))
            if line.strip() and not line.startswith("//*"):
                stmt_pos = len(merged_lines) - 1
        elif stmt_pos is not None and stmt_pos < len(merged_lines) - 1:
            # A continuation record folded into the statement at stmt_pos,
            # with comment records in between: move the statement after them.
            merged_lines.append(merged_lines.pop(stmt_pos))
            stmt_pos = len(merged_lines) - 1
    return merged_lines


class _RecordClassifier:
    """Single pass over normalized records that separates data from JCL.

    :meth:`run` returns the indices of the JCL records (to be merged and
    parsed) and fills :attr:`inline_data_indices`,
    :attr:`control_data_indices` and :attr:`warnings`.
    """

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.inline_data_indices: set[int] = set()
        self.control_data_indices: set[int] = set()
        self.warnings: list[str] = []

        self.in_inline_data = False
        self.delimiter = "/*"
        # When the current in-stream dataset was opened with ``DD *`` (and
        # *no* custom ``DLM=``), z/OS terminates the data at the next record
        # beginning with ``//`` as well as at ``/*``. ``DD DATA`` deliberately
        # does not do this so that records containing ``//`` can be supplied
        # as data; for ``DD DATA`` (or any dataset with an explicit ``DLM=``)
        # only the delimiter ends the data.
        self.terminates_on_slash = False

        self.in_cntl_block = False
        self.cntl_start_line = 0

        # Once a step exists, a record that is not JCL (no ``//`` or ``/*``)
        # starts in-stream data with no DD statement, which JES reads as an
        # implicit ``//SYSIN DD *`` (see JobBuilder.start_implicit_sysin).
        self.seen_exec = False
        # Operands of a DD statement whose continuation records are still
        # coming.
        self.pending_dd: str | None = None

    def run(self) -> list[int]:
        return [i for i, line in enumerate(self.lines) if self._is_jcl(i, line)]

    def _is_jcl(self, i: int, line: str) -> bool:
        """Classify record *i*; return True if it is a JCL record."""
        if self.in_inline_data and self._consume_inline_data(i, line):
            return False
        if self.in_cntl_block and self._consume_control_data(i, line):
            return False
        if self._opens_implicit_sysin(i, line):
            return False
        if (
            line.strip()
            and line.startswith("//")
            and not line.strip().startswith("//*")
        ):
            self._note_statement(i, line)
        return True

    def _open_instream(self, delimiter: str, terminates_on_slash: bool) -> None:
        self.in_inline_data = True
        self.delimiter = delimiter
        self.terminates_on_slash = terminates_on_slash

    def _consume_inline_data(self, i: int, line: str) -> bool:
        """Handle a record inside in-stream data; True if it was data."""
        # The delimiter only counts in columns 1-2: an indented ``/*`` is
        # data (a C, REXX or SQL comment in SYSIN).
        if line.startswith(self.delimiter):
            # The delimiter record belongs to the in-stream data block (it
            # is not a JCL statement) — mark it and stop collecting.
            self.inline_data_indices.add(i)
            self.in_inline_data = False
            return True
        if self.terminates_on_slash and line.startswith("//"):
            # Unterminated ``DD *`` data: the next JCL statement ends it, and
            # this record is treated as a normal statement.
            self.in_inline_data = False
            return False
        self.inline_data_indices.add(i)
        return True

    def _consume_control_data(self, i: int, line: str) -> bool:
        """Handle a record inside a CNTL block; True if it was control data.

        Records between CNTL and ENDCNTL are program control statements handed
        to the program, not JCL: they must not be merged as continuations nor
        parsed. ENDCNTL closes the block; so does any record that is
        unmistakably a JCL statement, so an unterminated CNTL cannot swallow
        the rest of the job (that gets a warning).
        """
        operation = statement_operation(line)
        if operation == "ENDCNTL":
            self.in_cntl_block = False
            return False
        if operation in _STATEMENT_TYPES:
            self.in_cntl_block = False
            self.warnings.append(
                f"Line {self.cntl_start_line}: CNTL block has no matching ENDCNTL; "
                f"ended at the {operation} statement on line {i + 1}"
            )
            return False
        self.control_data_indices.add(i)
        return True

    def _opens_implicit_sysin(self, i: int, line: str) -> bool:
        """Start implicit ``SYSIN`` data at a non-JCL record after an EXEC."""
        if (
            line.startswith(("//", "/*"))
            or not self.seen_exec
            or not line.strip()
            or _expects_continuation(self.lines, i)
        ):
            return False
        self.inline_data_indices.add(i)
        self._open_instream("/*", True)
        return True

    def _note_statement(self, i: int, line: str) -> None:
        """Track the statements that change how later records are read."""
        upper_line = line.upper()
        if (
            not self.seen_exec
            and "EXEC" in upper_line
            and statement_operation(line) == "EXEC"
        ):
            self.seen_exec = True
        if "CNTL" in upper_line and statement_operation(line) == "CNTL":
            self.in_cntl_block = True
            self.cntl_start_line = i + 1
        dd_operands = self._complete_dd_operands(line, upper_line)
        if dd_operands is not None:
            instream = _instream_delimiter(dd_operands)
            if instream is not None:
                self._open_instream(*instream)

    def _complete_dd_operands(self, line: str, upper_line: str) -> str | None:
        """Return a DD's whole operand field once its last record is read.

        In-stream data starts at ``DD *`` / ``DD DATA`` / any DD with an
        explicit DLM=. The operand field is located by tokenizing the record —
        the same way the JobBuilder reads it — so that spacing
        ("//SYSIN    DD    *") can never make the two disagree and leave data
        records to be parsed as JCL. A DD statement continued onto further
        records (``DD DATA,`` / ``//   DLM=$$``) is only judged once its last
        record is read: those records are JCL, and DLM= may sit on any of them.
        """
        if self.pending_dd is not None:
            if statement_operation(line) in _STATEMENT_TYPES:
                self.pending_dd = None  # continuation never came
                return None
            continuation = split_comment_field(line, "DD")[0][2:].strip()
            self.pending_dd += continuation
            if continuation.endswith(","):
                return None
            operands, self.pending_dd = self.pending_dd, None
            return operands
        if "DD" not in upper_line:
            return None
        dd_field = _operand_field(line)
        if dd_field is None or dd_field[1] != "DD":
            return None
        statement = split_comment_field(line, "DD")[0]
        operands = statement[dd_field[0] :].strip()
        if operands.endswith(","):
            self.pending_dd = operands
            return None
        return operands


def _instream_delimiter(operands: str) -> tuple[str, bool] | None:
    """Return ``(delimiter, ends_at_slash)`` if a DD's operands open in-stream data.

    *operands* is the DD's whole operand field (continuations joined, comment
    field removed). They are tokenized exactly as the JobBuilder tokenizes
    them and judged by the same :func:`~jclparser.utils.instream_delimiter`
    rule, so the pre-scan can never mark records as data that the builder
    then has no DD to attach to (the old substring test did, for any DD
    mentioning ``DLM=``, silently dropping the rest of the job).
    """
    try:
        parameters = _parse_parameters(operands)
    except JCLSyntaxError:
        # Unbalanced operands: the statement parser reports them; no data.
        return None
    instream = instream_delimiter(parameters)
    if instream is None:
        return None
    delimiter, ends_at_slash = instream
    if not isinstance(delimiter, str):
        # A malformed DLM= is rejected by the JobBuilder; keep the default
        # delimiter here so the pre-scan stays in step until then.
        delimiter = "/*"
    return delimiter, ends_at_slash


def _expects_continuation(lines: list[str], index: int) -> bool:
    """Return True if the JCL record before *index* awaits a continuation.

    A statement whose operand field ends in a comma expects a ``//``
    continuation record; a non-JCL record there is a broken continuation,
    not in-stream data, and is left for parse_statement() to reject.
    Only called for the rare non-JCL record, so the backward scan is cheap.
    """
    prev = index - 1
    while prev >= 0 and (not lines[prev].strip() or lines[prev].startswith("//*")):
        prev -= 1
    if prev < 0 or not lines[prev].startswith("//"):
        return False
    # The operation of the statement that record belongs to decides where
    # its comment field starts.
    group_operation = ""
    for k in range(prev, -1, -1):
        operation = statement_operation(lines[k])
        if operation in _STATEMENT_TYPES:
            group_operation = operation
            break
    statement_part = split_comment_field(lines[prev], group_operation)[0]
    return statement_part.rstrip().endswith(",")
