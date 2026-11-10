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
from .errors import ErrorSeverity, JCLSyntaxError
from .utils import (
    instream_delimiter,
    is_card_image,
    is_continued_card_image,
    is_jes_xmit,
    jes_xmit_delimiter,
    normalize_jcl_lines,
    split_source_lines,
    xmit_delimiter,
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
    #: 0-based indices of the records of a JES3 ``//*DATASET`` input data
    #: set (between ``//*DATASET`` and ``//*ENDDATASET`` or its ``END=``
    #: terminator, the terminator included when it is not ENDDATASET).
    jes3_data_indices: frozenset[int] = frozenset()
    #: ``(1-based line, message, severity)`` for records z/OS rejects that
    #: the merge recovered from (a continuation past column 16, a trailing
    #: comma with no continuation record); see :attr:`Job.statement_findings`.
    errors: tuple[tuple[int, str, ErrorSeverity], ...] = ()


def _merge_source_lines(content: str, dialect: str = "standard") -> ScannedSource:
    """Normalize, mark in-stream data, and merge continuation lines.

    Under every dialect but ``jes2`` (where ``//*`` is only ever a comment),
    the records of a JES3 ``//*DATASET`` ... ``//*ENDDATASET`` input data set
    are data too (issue #162).

    Neither in-stream data nor CNTL control records may be parsed as JCL
    statements; the parse loop uses the returned index sets to route them.
    The warnings report an unterminated CNTL block and comment fields that
    were stripped off statements but still looked like operands (truncated
    or garbled records).
    """
    raw_lines = split_source_lines(content)
    lines = normalize_jcl_lines(raw_lines)

    classifier = _RecordClassifier(lines, jes3_datasets=dialect != "jes2")
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
    # In-stream data records reach the program as coded: columns 72-80 and
    # tabs are data, not a continuation indicator and sequence field, so the
    # raw record is woven in (trailing blanks aside) rather than the
    # normalized one (issue #115).  CNTL control records are statements
    # with JCL's column rules and stay normalized.
    data_lines = {
        i: _data_record(raw_lines[i])
        for i in classifier.inline_data_indices | classifier.jes3_data_indices
    }
    merged_lines = _weave_lines(
        lines,
        merged_start,
        classifier.inline_data_indices
        | classifier.control_data_indices
        | classifier.jes3_data_indices,
        data_lines,
    )

    # Map the handler's suspect comment fields back to original line numbers.
    warnings = classifier.warnings + [
        f"Line {jcl_indices[jcl_line_num - 1] + 1}: text after the "
        f"operand field ignored as a comment, but it looks like operands: "
        f"{comment!r}"
        for jcl_line_num, comment in handler.suspect_comments
    ]
    # A continuation-like record after a complete statement (missing comma)
    # is not merged into it; say so instead of dropping its operands (#123).
    warnings += [
        f"Line {jcl_indices[jcl_line_num - 1] + 1}: continuation record "
        f"ignored because the statement before it does not end with a comma "
        f"(missing comma?): {record!r}"
        for jcl_line_num, record in handler.stray_continuations
    ]

    errors = _continuation_errors(handler, jcl_indices)
    warnings += [f"Line {line}: {message}" for line, message, _ in errors]

    return ScannedSource(
        merged_lines,
        classifier.inline_data_indices,
        classifier.control_data_indices,
        warnings,
        frozenset(classifier.jes3_data_indices),
        errors,
    )


def _continuation_errors(
    handler: ContinuationLineHandler, jcl_indices: Sequence[int]
) -> tuple[tuple[int, str, ErrorSeverity], ...]:
    """The continuation records z/OS rejects, by source line number."""
    errors = [
        (
            jcl_indices[jcl_line_num - 1] + 1,
            (
                f"continuation record starts in column {column}; a "
                "continuation must start in columns 4-16"
            ),
            ErrorSeverity.WARNING,
        )
        for jcl_line_num, column in handler.late_continuations
    ]
    errors += [
        (
            jcl_indices[jcl_line_num - 1] + 1,
            (
                "statement ends with a comma but no continuation record "
                f"follows (expected continuation not received): {text!r}"
            ),
            ErrorSeverity.ERROR,
        )
        for jcl_line_num, text in handler.missing_continuations
    ]
    return tuple(sorted(errors))


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
            if is_continued_card_image(
                raw_lines[orig],
                raw_lines[orig + 1] if orig + 1 < len(raw_lines) else None,
            )
        },
    )


def _data_record(record: str) -> str:
    """An in-stream data record as woven into the parse (issue #115).

    A card image (exactly 80 columns, :func:`utils.is_card_image`) is kept
    whole, so readers of control statements can still tell its columns
    72-80 from text (:func:`utils.control_card_text`); any other record only
    loses its trailing blanks.
    """
    return record if is_card_image(record) else record.rstrip(" ")


def _weave_lines(
    lines: list[str],
    merged_start: dict[int, str],
    data_indices: set[int],
    data_lines: dict[int, str] | None = None,
) -> list[tuple[str, int]]:
    """Recombine merged statements with the data records, in source order.

    *data_lines* overrides the text woven in for a data record (the raw
    in-stream record instead of its normalized form).

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
            merged_lines.append(
                (data_lines.get(i, line) if data_lines else line, i + 1)
            )
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

    def __init__(self, lines: list[str], *, jes3_datasets: bool = True) -> None:
        self.lines = lines
        self.inline_data_indices: set[int] = set()
        self.control_data_indices: set[int] = set()
        self.jes3_data_indices: set[int] = set()
        self.warnings: list[str] = []

        # JES3 ``//*DATASET``: the records up to ``//*ENDDATASET`` (or the
        # ``END=`` terminator) are the content of an input data set.
        self.jes3_datasets = jes3_datasets
        self.jes3_terminator: str | None = None
        self.jes3_start_line = 0

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
        # ``(operation, operands)`` of a DD / XMIT statement whose
        # continuation records are still coming.
        self.pending: tuple[str, str] | None = None

    def run(self) -> list[int]:
        jcl = [i for i, line in enumerate(self.lines) if self._is_jcl(i, line)]
        if self.jes3_terminator is not None:
            self.warnings.append(
                f"Line {self.jes3_start_line}: //*DATASET has no matching "
                f"{self._jes3_terminator_name()}; its data runs to the end "
                f"of the source"
            )
        return jcl

    def _jes3_terminator_name(self) -> str:
        return (
            "//*ENDDATASET"
            if self.jes3_terminator == _ENDDATASET
            else f"END={self.jes3_terminator} terminator"
        )

    def _consume_jes3_data(self, i: int, line: str) -> bool:
        """Handle a record inside a JES3 ``//*DATASET``; True if it was data.

        The ``//*ENDDATASET`` record itself stays a JCL (JES3 control)
        record; an ``END=`` terminator record is part of the data block.
        """
        if _jes3_command(line) == "ENDDATASET":
            self.jes3_terminator = None
            return False
        if self.jes3_terminator != _ENDDATASET and line.startswith(
            str(self.jes3_terminator)
        ):
            self.jes3_terminator = None
        self.jes3_data_indices.add(i)
        return True

    def _opens_jes3_dataset(self, i: int, line: str) -> None:
        """Note a ``//*DATASET`` record: data follows until its terminator.

        A JES3 ``//*DATASET`` statement always codes ``DDNAME=``; without it
        the record is an ordinary comment that happens to start with that
        word (``//*DATASET DEFINITIONS FOR ...``) and opens no data (#164).
        """
        if not self.jes3_datasets or _jes3_command(line) != "DATASET":
            return
        terminator = _ENDDATASET
        has_ddname = False
        for param in line.strip()[3:].split(None, 1)[1:2]:
            for item in param.split(None, 1)[0].split(","):
                key, _, value = item.partition("=")
                if key.upper() == "DDNAME" and value:
                    has_ddname = True
                if key.upper() == "END" and value.strip("'"):
                    terminator = value.strip("'")
        if not has_ddname:
            return
        self.jes3_terminator = terminator
        self.jes3_start_line = i + 1

    def _is_jcl(self, i: int, line: str) -> bool:
        """Classify record *i*; return True if it is a JCL record."""
        if self.jes3_terminator is not None and self._consume_jes3_data(i, line):
            return False
        if line.startswith("//*") and not self.in_inline_data:
            self._opens_jes3_dataset(i, line)
        if self.in_inline_data and self._consume_inline_data(i, line):
            return False
        if self.in_cntl_block and self._consume_control_data(i, line):
            return False
        if self._opens_implicit_sysin(i, line):
            return False
        if is_jes_xmit(line):
            # JES2 ``/*XMIT``: the records after it are a job stream for
            # another node, ended only by ``/*`` or its DLM= (issue #117).
            self._open_instream(jes_xmit_delimiter(line[6:]), False)
            return True
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
        completed = self._complete_data_operands(line, upper_line)
        if completed is None:
            return
        operation, operands = completed
        if operation == "XMIT":
            self._open_instream(*_xmit_data_delimiter(operands))
            return
        instream = _instream_delimiter(operands)
        if instream is not None:
            self._open_instream(*instream)

    def _complete_data_operands(
        self, line: str, upper_line: str
    ) -> tuple[str, str] | None:
        """Return ``(operation, operands)`` of a DD / XMIT once its last record
        is read.

        In-stream data starts at ``DD *`` / ``DD DATA`` (DLM= may change its
        delimiter); transmitted data starts at ``XMIT``. The operand field is
        located by tokenizing the record — the same way the JobBuilder reads
        it — so that spacing ("//SYSIN    DD    *") can never make the two
        disagree and leave data records to be parsed as JCL. A statement
        continued onto further records (``DD DATA,`` / ``//   DLM=$$``) is
        only judged once its last record is read: those records are JCL, and
        DLM= may sit on any of them. A new statement while one is pending
        means its continuation never came.
        """
        if (
            self.pending is not None
            and statement_operation(line) not in _STATEMENT_TYPES
        ):
            operation, operands = self.pending
            operands += split_comment_field(line, operation)[0][2:].strip()
        else:
            self.pending = None
            if "DD" not in upper_line and "XMIT" not in upper_line:
                return None
            field = _operand_field(line)
            if field is None or field[1] not in _DATA_OPENING_OPERATIONS:
                return None
            operation = field[1]
            operands = split_comment_field(line, operation)[0][field[0] :].strip()
        if operands.endswith(","):
            self.pending = (operation, operands)
            return None
        self.pending = None
        return operation, operands


#: Marks a ``//*DATASET`` whose data ends at ``//*ENDDATASET``.
_ENDDATASET = "\0ENDDATASET"


def _jes3_command(line: str) -> str | None:
    """The command of a JES3 ``//*COMMAND`` record (no blank after ``//*``)."""
    if not line.startswith("//*") or len(line) < 4 or line[3].isspace():
        return None
    return line[3:].split(None, 1)[0].upper()


#: Statements whose operands can open a data block in the pre-scan.
_DATA_OPENING_OPERATIONS = frozenset({"DD", "XMIT"})


def _xmit_data_delimiter(operands: str) -> tuple[str, bool]:
    """Return ``(delimiter, False)`` for the data after a ``//X XMIT``.

    Transmitted records are a job stream, so ``//`` never ends them; a
    malformed or unbalanced DLM= keeps the default ``/*`` here and is
    reported by the JobBuilder.
    """
    try:
        parameters = _parse_parameters(operands) if operands else {}
    except JCLSyntaxError:
        parameters = {}
    delimiter = xmit_delimiter(parameters)
    return (delimiter if isinstance(delimiter, str) else "/*"), False


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
