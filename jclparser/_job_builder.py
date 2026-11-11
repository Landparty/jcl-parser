"""Job model assembly for the JCL parse loop.

Internal module split out of :mod:`jclparser.parser`. It contains
:class:`JobBuilder` — the per-statement state machine driven by the
``parse_jcl()`` core loop (one ``_on_<type>`` handler per statement type).

Its former helpers now live in two sibling modules (behavior unchanged,
layout only):

* :mod:`jclparser._model_factories` — the ``Statement -> Job/Step/DDStatement``
  factory helpers and SET-symbol value resolution helpers,
* :mod:`jclparser._post_parse` — the post-parse passes (external PROC
  loading, ``OUTPUT=*.name`` back-reference resolution, SET-symbol
  substitution, strict DD structure).

Everything that historically lived here is still importable from this module
via the re-export block below. Nothing here is public API — import
:func:`~jclparser.parse_jcl` from the package instead.
"""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

# Backward-compatible re-exports: these helpers historically lived in this
# module (and before that in ``jclparser.parser``) and are imported from here
# by ``parser.py`` and downstream code. Keep them importable from this path.
from ._model_factories import (
    _SET_SYMBOL_PATTERN,
    _create_dd_from_statement,
    _create_job_from_statement,
    _create_step_from_statement,
    _exec_has_program_spec,
    _has_unresolved_symbol_ref,
    _resolve_jcllib_library,
    _resolve_set_value,
)
from ._post_parse import (
    _extract_output_ref_names,
    _resolve_output_refs,
    enforce_strict_dd_structure,
    load_external_procedures,
    resolve_set_symbols,
)
from .condition_parser import parse_condition
from .errors import ErrorSeverity, JCLSyntaxError
from .model import (
    ConditionalBlock,
    DDStatement,
    Job,
    OutputStatement,
    Procedure,
    Statement,
    Step,
)
from .utils import (
    POSITIONAL_PARAM_PREFIX,
    instream_delimiter,
    is_positional_key,
    jcl_value_text,
    jes_xmit_delimiter,
    xmit_delimiter,
)

logger = logging.getLogger(__name__)

#: A record that looks like a JCL ``EXEC`` statement (``//name EXEC ...``).
_RE_EXEC_RECORD = re.compile(r"^//\S+\s+EXEC(\s|$)")
#: A JOB statement record (named; ``//*`` comments never reach the check).
_RE_JOB_RECORD = re.compile(r"^//\S+\s+JOB(\s|$)")

#: ``/*`` statements JES3 itself processes (RJP workstation sign-on/off); every
#: other ``/*`` control statement is JES2-only.
_JES3_SLASH_STAR = frozenset({"SIGNON", "SIGNOFF"})

#: Explicit re-export list: mypy strict (``no_implicit_reexport``) would
#: otherwise reject the historical ``from ._job_builder import ...`` imports
#: in ``parser.py`` for the helpers that moved to the sibling modules.
__all__ = [  # noqa: RUF022 — grouped by the module each name comes from
    "JobBuilder",
    # _model_factories re-exports
    "_SET_SYMBOL_PATTERN",
    "_create_dd_from_statement",
    "_create_job_from_statement",
    "_create_step_from_statement",
    "_exec_has_program_spec",
    "_has_unresolved_symbol_ref",
    "_resolve_set_value",
    # _post_parse re-exports
    "_extract_output_ref_names",
    "_resolve_output_refs",
    "enforce_strict_dd_structure",
    "load_external_procedures",
    "resolve_set_symbols",
]


#: Deepest IF nesting z/OS allows (JCL Reference, IF/THEN/ELSE/ENDIF).
MAX_IF_NESTING = 15
#: Deepest IF nesting the parse builds before it gives up (far past the
#: z/OS limit, well short of overflowing a recursive walk of the model).
_MAX_IF_NESTING_PARSED = 100

#: The ``THEN`` that ends an IF statement's operands.
_RE_ENDS_WITH_THEN = re.compile(r"(^|[\s)])THEN$", re.IGNORECASE)

#: Statements that belong to a job: coded before its JOB statement they are
#: reported (EXEC already raises; PROC/PEND make a JOB-less member).
_JOB_SCOPE_TYPES = frozenset(
    {
        "DD",
        "SET",
        "JCLLIB",
        "OUTPUT",
        "EXPORT",
        "INCLUDE",
        "IF",
        "ELSE",
        "ENDIF",
        "CNTL",
        "ENDCNTL",
        "COMMAND",
        "SCHEDULE",
        "NOTIFY",
        "XMIT",
    }
)

#: Statements on which a keyword may be coded only once.
_KEYWORD_STATEMENTS = frozenset({"JOB", "EXEC", "DD", "OUTPUT"})
#: Keywords with two spellings: coding both is coding one twice.
_KEYWORD_ALIASES = (("DSN", "DSNAME"), ("VOL", "VOLUME"))
#: The statement parser's warning for a repeated keyword.
_RE_DUPLICATE_WARNING = re.compile(r"duplicate parameter '([^']+)'")

#: DDs z/OS allows before a job's first EXEC.
_JOB_LEVEL_DDS = frozenset({"JOBLIB", "JOBCAT", "SYSCHK"})


class JobBuilder:
    """Accumulates parse-loop state and assembles the :class:`Job` model.

    The ``parse_jcl()`` core loop feeds it one merged line / parsed
    :class:`Statement` at a time; each JCL statement type has its own
    ``_on_<type>`` handler. Call :meth:`finish` after the last line to obtain
    the assembled :class:`Job`.
    """

    # Statement type -> name of its ``_on_<type>`` handler.  Every type in
    # ``_STATEMENT_TYPES`` must appear here, even when its handler is a
    # deliberate no-op (NULL, ENDCNTL).  Any other type -- a custom type
    # returned by a StatementPlugin -- is kept in ``Job.custom_statements``.
    _HANDLERS: ClassVar[dict[str, str]] = {
        "JOB": "_on_job",
        "EXEC": "_on_exec",
        "DD": "_on_dd",
        "PROC": "_on_proc",
        "PEND": "_on_pend",
        "SET": "_on_set",
        "EXPORT": "_on_export",
        "JCLLIB": "_on_jcllib",
        "INCLUDE": "_on_include",
        "IF": "_on_conditional",
        "THEN": "_on_conditional",
        "ELSE": "_on_conditional",
        "ENDIF": "_on_conditional",
        "JES": "_on_jes",
        "OUTPUT": "_on_output",
        "NULL": "_on_null",
        # No richer model representation for COMMAND / SCHEDULE / CNTL /
        # NOTIFY (z/OS 2.3).
        "COMMAND": "_on_control",
        "SCHEDULE": "_on_control",
        "CNTL": "_on_control",
        "NOTIFY": "_on_control",
        "ENDCNTL": "_on_endcntl",
        "UNKNOWN": "_on_unknown",
        "XMIT": "_on_xmit",
    }

    def __init__(self, dialect: str = "standard", strict: bool = False) -> None:
        #: ``ParserConfig.dialect``: decides which JES control statements are
        #: interpreted (see ``jclparser.plugins.SUPPORTED_DIALECTS``).
        self.dialect = dialect
        #: Strict parsing: a SET value over ``MAX_SYMBOL_VALUE_LENGTH`` raises
        #: instead of being left unresolved with a warning.
        self.strict = strict
        self.job: Job | None = None
        #: tuples: (ConditionalBlock, active_branch)
        self.conditional_stack: list[tuple[ConditionalBlock, str]] = []
        self.current_step: Step | None = None
        self.current_dd: DDStatement | None = None
        self.inline_data_lines: list[str] = []
        self.in_inline_data = False
        #: Track when we're inside a PROC/PEND block
        self.current_procedure: Procedure | None = None
        #: Procedures collected before any JOB statement (PROC-only files)
        self.pending_procedures: list[Procedure] = []
        self.current_delimiter = "/*"
        self.current_terminates_on_slash = False
        #: Job-level DDs that appear before the first job-level EXEC (e.g.
        #: ``SYSCHK``/``JOBCAT``); attached to that step, never to a step of an
        #: in-stream PROC defined in between (#103).
        self.orphaned_dds: list[DDStatement] = []
        #: DDs inside a PROC/PEND body before the procedure's first EXEC.
        self.proc_orphaned_dds: list[DDStatement] = []
        #: ``len(conditional_stack)`` when the open PROC began: IF blocks at
        #: or below it belong to the enclosing job, not to the procedure.
        self.proc_cond_depth = 0
        #: True while accumulating JOBLIB concatenation lines
        self.in_joblib_concat = False
        #: Qualified name (``PROCSTEP.DDNAME``) of the override DD the current
        #: step's unnamed DDs concatenate onto, or None
        self.concat_override_key: str | None = None
        #: Warnings collected before the JOB statement is seen (no job.warnings
        #: yet to append to); flushed onto job.warnings once the Job object exists.
        self.pending_warnings: list[str] = []
        #: JES2/JES3 control statements (e.g. /*JOBPARM) seen before the JOB
        #: statement, which is legal per z/OS; flushed once job exists.
        self.pending_jes_statements: list[str] = []
        self.pending_jes_typed: list[Any] = []
        #: Line number of the last JES3 control record when its operand ends
        #: with a comma: the next ``//*`` record continues it (#185).
        self._jes3_continues_after: int | None = None
        #: Statements that carry job-level information but were seen before the
        #: JOB statement — or in a JOB-less member such as a cataloged
        #: procedure, where no JOB statement ever arrives.  They used to be
        #: dropped on the floor; they are flushed onto the Job in finish().
        self.pending_sets: dict[str, str] = {}
        #: Job-level steps, whose ``set_symbols`` snapshot finish() keeps
        #: only if some SET symbol is redefined after it was first set.
        self.job_level_steps: list[Step] = []
        self.set_redefined = False
        #: Steps of in-stream / cataloged procedures with the procedure they
        #: belong to; finish() prunes their ``set_symbols`` snapshot the same
        #: way (against the procedure's own final SET table).
        self.procedure_steps: list[tuple[Procedure, Step]] = []
        self.pending_exported: set[str] = set()
        self.pending_jcllib: list[str] = []
        self.pending_includes: list[str] = []
        self.pending_outputs: list[OutputStatement] = []
        self.pending_conditionals: list[ConditionalBlock] = []
        self.pending_steps: list[Step | ConditionalBlock] = []
        self.pending_control: list[Statement] = []
        #: Statements of a type the builder has no handler for (e.g. a custom
        #: type returned by a StatementPlugin) seen before the JOB statement.
        self.pending_custom: list[Statement] = []
        #: The open ``CNTL`` block, whose program control records are collected
        #: verbatim until its ``ENDCNTL``.
        self.current_cntl: Statement | None = None
        #: Line of the null statement (``//``) that ended the job, or None.
        self.null_line: int | None = None
        #: Line numbers of the records after it, which are not part of the job.
        self.after_null_lines: list[int] = []
        #: Misplaced ``IF``/``THEN``/``ELSE``/``ENDIF`` statements as
        #: ``(line, message)``; finish() copies them to
        #: :attr:`Job.conditional_errors`.
        self.conditional_errors: list[tuple[int, str]] = []
        #: Misplaced DD statements as ``(line, message)``; finish() copies
        #: them to :attr:`Job.statement_findings`.
        self.statement_findings: list[tuple[int, str, ErrorSeverity]] = []
        #: INCLUDE members left unexpanded because they include themselves.
        self.recursive_includes: set[str] | frozenset[str] = frozenset()
        #: INCLUDE members left unexpanded because they are nested deeper
        #: than the 15 levels z/OS allows.
        self.too_deep_includes: set[str] | frozenset[str] = frozenset()
        #: ``(line, message)`` for each misplaced DD in :attr:`orphaned_dds`;
        #: reported once the first job-level EXEC picks the DDs up (with no
        #: EXEC at all they are discarded, and reported as such, instead).
        self.misplaced_dds: list[tuple[int, str]] = []
        #: ``(line, type)`` of the job statements seen before the JOB
        #: statement; reported once it arrives (a JOB-less member has none).
        self.before_job: list[tuple[int, str]] = []
        #: Line of the job's JCLLIB statement, once one is seen.
        self.jcllib_line: int | None = None
        #: Name of the last job-level DD before the first EXEC (JOBLIB,
        #: JOBCAT, ...): an unnamed DD after it concatenates onto it.
        self.last_job_dd: str | None = None

    # ------------------------------------------------------------------ #
    # Line-level handling (before statement parsing)
    # ------------------------------------------------------------------ #

    def _warnings_sink(self) -> list[str]:
        """The active warning list: job.warnings once a Job exists."""
        return self.job.warnings if self.job is not None else self.pending_warnings

    def _flush_inline_data(self) -> None:
        if self.current_dd:
            self.current_dd.inline_data = "\n".join(self.inline_data_lines)
        self.inline_data_lines = []
        self.in_inline_data = False

    def consume_inline_data(self, line: str) -> bool:
        """Handle *line* while inside an in-stream data block.

        Returns True when the line was consumed (data record or closing
        delimiter). Returns False when the line ends the block by starting a
        new JCL statement (unterminated ``DD *`` data) or when no in-stream
        block is open — in both cases the caller must parse the line normally.
        """
        if not self.in_inline_data:
            return False
        # Only a delimiter in columns 1-2 ends the data (see _merge_source_lines).
        if line.startswith(self.current_delimiter):
            # End of inline data
            self._flush_inline_data()
            return True
        if self.current_terminates_on_slash and line.startswith("//"):
            # Unterminated ``DD *`` data: the next JCL statement ends the
            # in-stream block.  Flush what we collected and fall through
            # so this record is parsed as a normal statement.
            self._flush_inline_data()
            return False
        # Collect inline data
        self.inline_data_lines.append(line)
        return True

    def start_implicit_sysin(self, line: str, line_num: int) -> None:
        """Open an implicit ``//SYSIN DD *`` for in-stream data with no DD.

        JES treats data records that follow a step without a ``DD *`` /
        ``DD DATA`` statement as ``//SYSIN DD *``. *line* is the first data
        record; the block ends at ``/*`` or the next ``//`` record.
        """
        if self.current_step is None:
            self._warnings_sink().append(
                f"Line {line_num}: in-stream data outside any step ignored"
            )
            return
        self.current_dd = DDStatement(
            name="SYSIN", parameters={"*": True}, line_number=line_num
        )
        self.current_step.add_dd(self.current_dd)
        self._warnings_sink().append(
            f"Line {line_num}: in-stream data with no DD statement; "
            "treated as //SYSIN DD * (JES default)"
        )
        self.in_inline_data = True
        self.inline_data_lines = [line]
        self.current_delimiter = "/*"
        self.current_terminates_on_slash = True

    def handle_comment_line(self, line: str, line_num: int) -> None:
        """Recognise JES3 ``//*COMMAND`` control statements (``//*MAIN``,
        ``//*ROUTE XEQ``, ...) before dropping the comment line.

        They share the ``//*`` prefix with comments, so without this they would
        be discarded along with them.  Statements seen before the JOB card are
        buffered and flushed by :meth:`finish`.
        """
        if not line.strip().startswith("//*"):
            return
        if self.dialect == "jes2":
            # Under JES2 a ``//*`` record is only ever a comment.
            return
        from .jes_statements import jes3_continued, parse_jes3_control

        jes3 = parse_jes3_control(line, line_num)
        if jes3 is None:
            self._continue_jes3(line, line_num)
            return
        raw_text = line.strip()
        if self.job is not None:
            self.job.jes_typed_statements.append(jes3)
            self.job.jes_statements.append(raw_text)
        else:
            self.pending_jes_typed.append(jes3)
            self.pending_jes_statements.append(raw_text)
        self._jes3_continues_after = line_num if jes3_continued(jes3) else None

    def _continue_jes3(self, line: str, line_num: int) -> None:
        """Append a ``//*`` continuation record to the JES3 control statement
        on the record before it, whose operand ended with a comma (#185)."""
        from .jes_statements import (
            jes3_continuation_text,
            jes3_continued,
            parse_jes3_control,
        )

        previous = self._jes3_continues_after
        self._jes3_continues_after = None
        if previous is None or line_num != previous + 1:
            return
        typed = self.job.jes_typed_statements if self.job else self.pending_jes_typed
        texts = self.job.jes_statements if self.job else self.pending_jes_statements
        if not typed or not texts:
            return
        if not line.strip()[3:].strip():
            return
        merged_text = jes3_continuation_text(typed[-1], line)
        merged = parse_jes3_control(merged_text, typed[-1].line_number)
        if merged is None:
            return
        typed[-1] = merged
        texts[-1] = merged_text
        if jes3_continued(merged):
            self._jes3_continues_after = line_num

    def handle_jes3_data(self, line: str) -> None:
        """Keep a record of a JES3 ``//*DATASET`` with that statement.

        The ``END=`` terminator record ends the data and is not kept.
        """
        from .jes_statements import Jes3ControlStatement

        typed = self.job.jes_typed_statements if self.job else self.pending_jes_typed
        for stmt in reversed(typed):
            if (
                isinstance(stmt, Jes3ControlStatement)
                and stmt.name.upper() == "DATASET"
            ):
                terminator = stmt.parameters.get("END", "").strip("'")
                if not (terminator and line.startswith(terminator)):
                    stmt.data.append(line)
                return

    # ------------------------------------------------------------------ #
    # Statement dispatch
    # ------------------------------------------------------------------ #

    def handle_statement(self, stmt: Statement, line_num: int) -> None:
        """Record statement warnings, then dispatch to the type handler.

        A statement whose type has no handler in :attr:`_HANDLERS` (e.g. a
        custom type returned by a :class:`~jclparser.plugins.StatementPlugin`)
        is kept verbatim in :attr:`Job.custom_statements` (#130).
        """
        if stmt.warnings:
            self._warnings_sink().extend(stmt.warnings)
        if stmt.type in _KEYWORD_STATEMENTS:
            self._check_duplicate_keywords(stmt, line_num)
        if self.current_cntl is not None and stmt.type != "ENDCNTL":
            self._unclosed_cntl()
        if (
            self.job is None
            and self.current_procedure is None
            and stmt.type in _JOB_SCOPE_TYPES
        ):
            self.before_job.append((line_num, stmt.type))

        handler_name = self._HANDLERS.get(stmt.type, "_on_custom")
        getattr(self, handler_name)(stmt, line_num)

    def _check_duplicate_keywords(self, stmt: Statement, line_num: int) -> None:
        """Report a keyword coded twice (or with its alias) on one statement.

        z/OS rejects the statement; the parse keeps the last value (the
        warning on ``job.warnings`` says which), and for ``DSN``/``DSNAME``
        or ``VOL``/``VOLUME`` both keys.
        """
        for warning in stmt.warnings:
            match = _RE_DUPLICATE_WARNING.search(warning)
            if match is not None:
                self.statement_findings.append(
                    (
                        line_num,
                        (
                            f"keyword {match.group(1)} is coded more than once "
                            f"on the {stmt.type} statement"
                        ),
                        ErrorSeverity.ERROR,
                    )
                )
        for short, long in _KEYWORD_ALIASES:
            if short in stmt.parameters and long in stmt.parameters:
                self._statement_error(
                    line_num,
                    f"{short} and {long} are the same keyword and are both coded "
                    f"on the {stmt.type} statement",
                )

    # ------------------------------------------------------------------ #
    # Per-statement-type handlers
    # ------------------------------------------------------------------ #

    def _on_job(self, stmt: Statement, line_num: int) -> None:
        if self.job is not None:
            raise JCLSyntaxError("Multiple JOB statements found", line_num)
        self.job = _create_job_from_statement(stmt)
        # On z/OS the records before a JOB statement are not part of its job
        # (JES reads them as the end of the previous job, or rejects them).
        for before_line, statement_type in self.before_job:
            self._statement_error(
                before_line,
                f"{statement_type} statement comes before the JOB statement; "
                "only JES control statements and comments may precede it",
            )

    def _on_exec(self, stmt: Statement, line_num: int) -> None:
        if self.job is None and self.current_procedure is None:
            raise JCLSyntaxError("EXEC statement before JOB statement", line_num)

        # Basic syntax check for EXEC - must have program, procedure, or positional parameter
        if not _exec_has_program_spec(stmt.parameters):
            raise JCLSyntaxError(
                "EXEC statement missing program or procedure", line_num
            )

        self.current_step = _create_step_from_statement(stmt)
        if self.job is not None and self.current_procedure is None:
            # SET values in effect at this step (see finish()).
            self.current_step.set_symbols = {
                **self.pending_sets,
                **self.job.set_statements,
            }
            self.job_level_steps.append(self.current_step)
        elif self.current_procedure is not None:
            # A SET inside the procedure is in effect from where it is coded,
            # so this step sees the procedure's SET values as they stand now.
            self.current_step.set_symbols = dict(self.current_procedure.set_statements)
            self.procedure_steps.append((self.current_procedure, self.current_step))
        self.in_joblib_concat = False  # JOBLIB concatenation ends at first EXEC
        self.concat_override_key = None

        # Attach DDs seen before the first EXEC of this scope to this step.
        # Job-level DDs (SYSCHK, JOBCAT, ...) wait for the first job-level
        # EXEC: a step inside an in-stream PROC definition must never pick
        # them up, or every expansion of the PROC would copy them (#103).
        if self.current_procedure is not None:
            pending_dds, self.proc_orphaned_dds = self.proc_orphaned_dds, []
        else:
            pending_dds, self.orphaned_dds = self.orphaned_dds, []
            for misplaced in self.misplaced_dds:
                self._statement_error(*misplaced)
            self.misplaced_dds = []
        for dd in pending_dds:
            self.current_step.add_dd(dd)

        # Add step to the open IF branch, the PROC being defined, or the job
        self._attach(self.current_step)

    def _on_dd(self, stmt: Statement, line_num: int) -> None:
        # Create the DD statement
        self.current_dd = _create_dd_from_statement(stmt)
        current_dd = self.current_dd

        if self.current_step is None:
            self._on_dd_before_exec(stmt, current_dd, line_num)
        elif stmt.name and "." in stmt.name:
            # This is a DD override for a procedure step
            parts = stmt.name.split(".", 1)  # Split on first dot only
            if len(parts) == 2:
                # Store as override on the current step, keeping the
                # qualified name for matching during explosion.
                self.current_step.dd_overrides[stmt.name] = current_dd
                self.concat_override_key = stmt.name
                step = self.current_step
                if step.program is not None and not step.is_procedure:
                    # Only an EXEC of a procedure has steps for the
                    # qualifier to name; explode_job never applies this
                    # override, so say so here rather than drop it (#64).
                    self._warnings_sink().append(
                        f"DD override {stmt.name} names no step in PROC: "
                        f"step {step.name} runs PGM={step.program}, "
                        "not a procedure; override ignored"
                    )
            else:
                # Regular DD statement
                self.current_step.add_dd(current_dd)
        elif not stmt.name and self.concat_override_key is not None:
            # An unnamed DD after a PROCSTEP.DDNAME override overrides the
            # next member of that DD's concatenation; added to the step's own
            # DDs it was appended after the PROC step's last DD instead.
            self.current_step.dd_override_concatenations.setdefault(
                self.concat_override_key, []
            ).append(current_dd)
        else:
            # Regular DD statement
            if not stmt.name and not self.current_step.dd_statements:
                self._statement_error(
                    line_num,
                    "unnamed DD statement right after EXEC concatenates onto "
                    "no DD; only a DD that follows a named DD may omit its name",
                )
            self.concat_override_key = None
            self.current_step.add_dd(current_dd)

        # Check for inline data marker (only for non-override DDs)
        instream = instream_delimiter(current_dd.parameters)
        if instream is not None:
            logger.debug(
                "inline-data block started at DD %s (line %d)",
                current_dd.name or "(unnamed)",
                line_num,
            )
            self.in_inline_data = True
            self.inline_data_lines = []
            current_delimiter, terminates_on_slash = instream
            if not isinstance(current_delimiter, str):
                raise JCLSyntaxError(
                    f"DLM= must be a one- or two-character delimiter, got "
                    f"{jcl_value_text(current_delimiter)}",
                    line_num,
                )
            self.current_delimiter = current_delimiter
            self.current_terminates_on_slash = terminates_on_slash

    def _statement_error(self, line_num: int, message: str) -> None:
        """Record a statement z/OS rejects that the parse recovers from."""
        self.statement_findings.append((line_num, message, ErrorSeverity.ERROR))
        self._warnings_sink().append(f"Line {line_num}: {message}")

    def _on_dd_before_exec(
        self, stmt: Statement, current_dd: DDStatement, line_num: int
    ) -> None:
        """Place a DD coded before the first EXEC of its job or PROC."""
        if self.current_procedure is not None:
            # DD in a PROC body before its first EXEC: z/OS rejects it; it is
            # attached to the procedure's first step.
            self.proc_orphaned_dds.append(current_dd)
            self._statement_error(
                line_num,
                f"DD {stmt.name or '(unnamed)'} comes before the first EXEC of "
                f"PROC {self.current_procedure.name} (it is attached to the "
                "procedure's first step, if it has one)",
            )
            return
        name = stmt.name or self.last_job_dd
        if stmt.name:
            self.last_job_dd = stmt.name
        if self.job is not None and name not in _JOB_LEVEL_DDS:
            self.misplaced_dds.append(
                (
                    line_num,
                    (
                        f"DD {stmt.name or '(unnamed)'} comes before the first "
                        "EXEC; only JOBLIB, JOBCAT and SYSCHK may precede it "
                        "(it is attached to the first step)"
                    ),
                )
            )
        # JOBLIB is a special job-level DD: keep it separate so
        # job.joblib and job.get_library_search_order() can expose it.
        if stmt.name == "JOBLIB" and self.job is not None:
            self.job.joblib_dds.append(current_dd)
            self.in_joblib_concat = True
        elif not stmt.name and self.in_joblib_concat and self.job is not None:
            # Empty-name DD concatenating onto the JOBLIB group
            self.job.joblib_dds.append(current_dd)
        else:
            self.in_joblib_concat = False
            # Job-level DD: attached to the next job-level step
            self.orphaned_dds.append(current_dd)

    def _on_proc(self, stmt: Statement, line_num: int) -> None:
        # Inline procedure definition - start tracking procedure
        outer = self.current_procedure
        if outer is not None and self.job is not None:
            # z/OS rejects a PROC statement inside an in-stream procedure;
            # the parse ends the outer one here (its later steps belong to
            # the inner one), which empties or truncates it.
            self._statement_error(
                line_num,
                f"PROC {stmt.name or '(unnamed)'} is defined inside in-stream "
                f"PROC {outer.name}; procedure definitions cannot be nested "
                "(add a PEND before it)",
            )
        self.current_procedure = Procedure(
            name=stmt.name or "UNNAMED",
            parameters=stmt.parameters,
            line_number=stmt.line_number,
        )
        if self.job:
            self.job.add_procedure(self.current_procedure)
        else:
            self.pending_procedures.append(self.current_procedure)
        # IF blocks already open belong to the job, not to this procedure.
        self.proc_cond_depth = len(self.conditional_stack)
        # Reset current_step since we're now inside procedure
        self.current_step = None
        self.in_joblib_concat = False
        self.proc_orphaned_dds = []

    def _on_pend(self, stmt: Statement, line_num: int) -> None:
        # End of procedure definition - stop tracking.  PEND closes the PROC
        # scope: an IF opened in the body and never closed by ENDIF ends here
        # (it is already attached to the procedure), so later job steps are
        # not read into it (#102).
        procedure = self.current_procedure
        if procedure is not None:
            while len(self.conditional_stack) > self.proc_cond_depth:
                cond, _branch = self.conditional_stack.pop()
                self._warnings_sink().append(
                    f"Line {cond.line_number}: IF block in PROC {procedure.name} "
                    f"has no matching ENDIF; closed at PEND (line {line_num})"
                )
                self.conditional_errors.append(
                    (
                        cond.line_number,
                        (
                            f"IF statement in PROC {procedure.name} has no "
                            "matching ENDIF before PEND"
                        ),
                    )
                )
            self._warn_proc_orphaned_dds(procedure, line_num)
        elif self.job is not None:
            self._statement_error(line_num, "PEND statement with no PROC to end")
        self.proc_orphaned_dds = []
        self.proc_cond_depth = 0
        self.current_procedure = None
        self.current_step = None

    def _warn_proc_orphaned_dds(self, procedure: Procedure, line_num: int) -> None:
        """Report DDs of a PROC body that had no EXEC step to attach to."""
        if self.proc_orphaned_dds:
            dd_names = ", ".join(
                dd.name or "(unnamed)" for dd in self.proc_orphaned_dds
            )
            self._warnings_sink().append(
                f"Line {line_num}: PROC {procedure.name} has DD statement(s) "
                f"but no EXEC step to attach them to; discarded: {dd_names}"
            )

    def _on_set(self, stmt: Statement, line_num: int) -> None:
        # SET symbol=value statement.  A SET before the JOB statement (or in a
        # JOB-less member) is buffered rather than dropped; finish() flushes it.
        # A SET inside a PROC/PEND body belongs to the procedure: it only takes
        # effect when the procedure is expanded (explosion applies it), so it
        # must not leak into the job's SET table.
        procedure = self.current_procedure
        if procedure is not None:
            symbols = procedure.set_statements
        else:
            symbols = self.job.set_statements if self.job else self.pending_sets

        def _record(symbol: str, value: str) -> None:
            resolved = _resolve_set_value(
                value,
                symbols,
                symbol=symbol,
                line_number=stmt.line_number,
                strict=self.strict,
                warnings=self._warnings_sink(),
            )
            if procedure is not None:
                procedure.set_statements[symbol] = resolved
            elif self.job:
                previous = self.job.set_statements.get(
                    symbol, self.pending_sets.get(symbol)
                )
                if previous is not None and previous != resolved:
                    self.set_redefined = True
                self.job.add_set(symbol, resolved)
            else:
                self.pending_sets[symbol] = resolved

        # For SET statements, parameters are in the format SYMBOL=VALUE. A
        # parenthesised value (SET SP=(TRK,1)) arrives tokenized as a list and
        # is kept as its JCL text.
        for key, value in stmt.parameters.items():
            if not is_positional_key(key) and value is not True:
                _record(key, jcl_value_text(value))
            elif isinstance(value, str) and "=" in value:
                # Positional parameter might be SYMBOL=VALUE without keyword
                sym, val = value.split("=", 1)
                _record(sym.strip(), val.strip())
            else:
                operand = key if value is True else jcl_value_text(value)
                self._warnings_sink().append(
                    f"Line {stmt.line_number}: SET operand {operand!r} is not "
                    "SYMBOL=value; ignored"
                )

    def _on_export(self, stmt: Statement, line_num: int) -> None:
        # EXPORT SYMLIST=(A,B,...)  or  EXPORT SYMLIST=*
        symlist = stmt.parameters.get("SYMLIST")
        names: list[str] = []
        if isinstance(symlist, list):
            names = [str(n).strip().upper() for n in symlist if n]
        elif isinstance(symlist, str):
            names = [
                n.strip().upper() for n in symlist.strip("()").split(",") if n.strip()
            ]
        sink = self.job.exported_symbols if self.job else self.pending_exported
        for n in names:
            sink.add(n)

    def _on_jcllib(self, stmt: Statement, line_num: int) -> None:
        # JCLLIB ORDER=(lib1,lib2,...)
        self._check_jcllib_placement(line_num)
        if "ORDER" not in stmt.parameters:
            return
        order_value = stmt.parameters["ORDER"]
        sink = self.job.jcllib_order if self.job else self.pending_jcllib
        # ORDER parameter might already be parsed as a list
        libs: list[str] = []
        if isinstance(order_value, list):
            libs = [str(lib) for lib in order_value]
        elif isinstance(order_value, str):
            libs = [lib.strip() for lib in order_value.strip("()").split(",")]
        # Only the SETs coded before this statement are in effect here.
        symbols = (
            {**self.pending_sets, **self.job.set_statements}
            if self.job
            else self.pending_sets
        )
        for lib in libs:
            resolved = _resolve_jcllib_library(lib, symbols)
            if resolved is None:
                self._warnings_sink().append(
                    f"Line {stmt.line_number}: JCLLIB ORDER library {lib} "
                    "contains an unresolved symbol; kept as written"
                )
                resolved = lib
            sink.append(resolved)

    def _check_jcllib_placement(self, line_num: int) -> None:
        """Report a second JCLLIB, or one after the job's first EXEC.

        z/OS allows one JCLLIB per job, after the JOB statement and before
        the first EXEC. The parse still uses its libraries.
        """
        if self.current_procedure is not None:
            return
        if self.jcllib_line is not None:
            self._statement_error(
                line_num,
                f"second JCLLIB statement (the first is on line "
                f"{self.jcllib_line}); a job may have only one",
            )
        elif self.job_level_steps:
            self._statement_error(
                line_num,
                "JCLLIB statement comes after the first EXEC; it must come before it",
            )
        if self.jcllib_line is None:
            self.jcllib_line = line_num

    def _on_include(self, stmt: Statement, line_num: int) -> None:
        # INCLUDE MEMBER=name
        member = stmt.parameters.get("MEMBER") or stmt.parameters.get(
            f"{POSITIONAL_PARAM_PREFIX}0"
        )
        if member:
            sink = self.job.includes if self.job else self.pending_includes
            sink.append(member)
            # Found members are expanded before the parse loop runs, so an
            # INCLUDE that reaches here could not be loaded.
            if str(member) in self.too_deep_includes:
                from .include_loader import MAX_INCLUDE_DEPTH

                self._statement_error(
                    line_num,
                    f"INCLUDE member {member} is nested more than "
                    f"{MAX_INCLUDE_DEPTH} levels deep (the z/OS limit); it was "
                    "not expanded",
                )
            else:
                self._warnings_sink().append(self._include_warning(stmt, str(member)))

    def _include_warning(self, stmt: Statement, member: str) -> str:
        """The warning for an INCLUDE whose member could not be loaded."""
        line = f"Line {stmt.line_number}: INCLUDE member"
        missing = " its statements are missing from the job"
        if "&" in member:
            from .include_loader import _substitute_member_symbols

            symbols = (
                {**self.pending_sets, **self.job.set_statements}
                if self.job
                else self.pending_sets
            )
            resolved = _substitute_member_symbols(member, symbols)
            if "&" in resolved:
                # Not a missing member: its name could not be built (#180).
                return (
                    f"{line} {member} uses a symbol with no SET value before "
                    f"it;{missing}"
                )
            if resolved in self.recursive_includes:
                return self._recursive_include_warning(line, resolved)
            member = f"{resolved} (from {member})"
        elif member in self.recursive_includes:
            return self._recursive_include_warning(line, member)
        return (
            f"{line} {member} not found in the JCLLIB / procedure libraries;{missing}"
        )

    @staticmethod
    def _recursive_include_warning(line: str, member: str) -> str:
        return (
            f"{line} {member} includes itself (directly or through other "
            "members); the recursive INCLUDE is ignored"
        )

    def _on_conditional(self, stmt: Statement, line_num: int) -> None:
        # Conditional logic - track conditionals properly
        if stmt.type == "IF":
            self._open_if(stmt)
        elif stmt.type in ("THEN", "ELSE"):
            self._switch_branch(stmt.type, line_num)
        elif stmt.type == "ENDIF":
            self._close_if(line_num)

    @staticmethod
    def _if_condition_text(stmt: Statement) -> str:
        """Rebuild the relational expression text of an ``IF`` statement."""
        # stmt.name is the IF statement's label (``//CHK1 IF ...``), never
        # part of its relational expression.
        condition_parts = []
        for key, value in stmt.parameters.items():
            if not key.startswith("_"):
                condition_parts.append(f"{key}={value}")
            else:
                condition_parts.append(str(value))
        condition = " ".join(condition_parts)
        match = _RE_ENDS_WITH_THEN.search(condition)
        if match is not None:
            condition = condition[: match.start() + len(match.group(1))].rstrip()
        return condition

    def _innermost_if(self) -> tuple[ConditionalBlock, str] | None:
        """The innermost IF block open in the current scope, or None.

        Inside a PROC/PEND body only IF blocks opened in that body count; an
        IF the job opened before the PROC statement stays the job's (#102).
        """
        floor = self.proc_cond_depth if self.current_procedure is not None else 0
        if len(self.conditional_stack) > floor:
            return self.conditional_stack[-1]
        return None

    def _attach(self, item: Step | ConditionalBlock) -> None:
        """Place a step or IF block in the open branch, PROC, job or buffer."""
        open_if = self._innermost_if()
        if open_if is not None:
            active_cond, active_branch = open_if
            if active_branch == "THEN":
                active_cond.add_then_step(item)
            else:
                active_cond.add_else_step(item)
        elif self.current_procedure is not None:
            self.current_procedure.steps.append(item)
        elif self.job is not None:
            self.job.steps.append(item)
        else:
            self.pending_steps.append(item)

    def _open_if(self, stmt: Statement) -> None:
        """Handle ``IF``: record a new :class:`ConditionalBlock` and enter it."""
        condition = self._if_condition_text(stmt)
        operands = " ".join(str(v) for v in stmt.parameters.values())
        if not _RE_ENDS_WITH_THEN.search(operands):
            self._statement_error(
                stmt.line_number,
                "IF statement has no THEN; the relational expression must be "
                "followed by THEN",
            )
        conditional = ConditionalBlock(
            condition=condition,
            condition_ast=parse_condition(condition),
            line_number=stmt.line_number,
        )
        if self.job is not None:
            self.job.add_conditional(conditional)
        else:
            self.pending_conditionals.append(conditional)
        self._attach(conditional)
        self.conditional_stack.append((conditional, "THEN"))
        self._check_if_depth(stmt.line_number)

    def _check_if_depth(self, line_num: int) -> None:
        """Report IF nesting beyond the z/OS limit; refuse a runaway one.

        z/OS allows 15 levels. Far deeper nesting would overflow the Python
        stack in every recursive walker of the model (explode, RC analysis,
        JSON export), so it stops the parse instead.
        """
        depth = len(self.conditional_stack)
        if depth == MAX_IF_NESTING + 1:
            self._statement_error(
                line_num,
                f"IF statements are nested more than {MAX_IF_NESTING} levels "
                "deep (the z/OS limit)",
            )
        if depth > _MAX_IF_NESTING_PARSED:
            raise JCLSyntaxError(
                f"IF statements nested more than {_MAX_IF_NESTING_PARSED} levels "
                f"deep (z/OS allows {MAX_IF_NESTING})",
                line_num,
            )

    def _switch_branch(self, branch: str, line_num: int) -> None:
        """Handle ``THEN`` / ``ELSE``: make *branch* the open IF's active one."""
        open_if = self._innermost_if()
        if open_if is None:
            self._warnings_sink().append(
                f"Line {line_num}: {branch} with no matching IF; ignored"
            )
            self.conditional_errors.append(
                (line_num, f"{branch} statement with no matching IF")
            )
            return
        if branch == "ELSE" and open_if[1] == "ELSE":
            # An IF has at most one ELSE clause; the second one's steps are
            # still read into the ELSE branch.
            self._warnings_sink().append(
                f"Line {line_num}: second ELSE for the IF on line "
                f"{open_if[0].line_number}"
            )
            self.conditional_errors.append(
                (
                    line_num,
                    (
                        "ELSE statement repeats the ELSE of the IF on line "
                        f"{open_if[0].line_number}"
                    ),
                )
            )
        self.conditional_stack[-1] = (open_if[0], branch)

    def _close_if(self, line_num: int) -> None:
        """Handle ``ENDIF``: leave the innermost open IF block."""
        if self._innermost_if() is not None:
            self.conditional_stack.pop()
        else:
            self._warnings_sink().append(
                f"Line {line_num}: ENDIF with no matching IF; ignored"
            )
            self.conditional_errors.append(
                (line_num, "ENDIF statement with no matching IF")
            )

    def _on_jes(self, stmt: Statement, line_num: int) -> None:
        raw_params = stmt.parameters.get("_raw", "")
        jes_content = f"/*{stmt.name} {raw_params}".strip()
        # Also try to promote to a typed JES control statement.
        from .jes_statements import parse_jes_control

        typed = parse_jes_control(stmt.name, raw_params, stmt.line_number)
        if stmt.name.upper() == "XMIT":
            # The records that follow are a job stream for another node,
            # not JCL of this job; they end at /* or DLM= (issue #117).
            self.current_dd = None
            self._start_transmitted_data(
                jes_xmit_delimiter(raw_params), stmt.line_number
            )
        if self.dialect == "jes3" and stmt.name.upper() not in _JES3_SLASH_STAR:
            # JES3 does not process JES2 control statements: keep the text,
            # but do not interpret it, and say so.
            typed = None
            self._warnings_sink().append(
                f"Line {stmt.line_number}: JES2 control statement /*{stmt.name} "
                "is not processed under the jes3 dialect"
            )
        if self.job is not None:
            self.job.jes_statements.append(jes_content)
            if typed is not None:
                self.job.jes_typed_statements.append(typed)
        else:
            # JES2/JES3 control cards (e.g. /*JOBPARM) may legally
            # precede the JOB statement; buffer until job exists.
            self.pending_jes_statements.append(jes_content)
            if typed is not None:
                self.pending_jes_typed.append(typed)

    def _on_output(self, stmt: Statement, line_num: int) -> None:
        # OUTPUT statement - JES output descriptor; promote to typed model.
        # Coded after an EXEC it is step-level, before the first EXEC
        # job-level (or, in a PROC body, procedure-level): DD OUTPUT=*.name
        # resolution depends on which (#85).
        step = self.current_step
        procedure = self.current_procedure
        if not stmt.name:
            self._statement_error(
                line_num, "OUTPUT statement has no name; z/OS requires one"
            )
        output = OutputStatement.from_statement(
            stmt,
            step_name=(step.name or "") if step is not None else None,
            procedure_name=procedure.name if procedure is not None else None,
        )
        sink = self.job.output_statements if self.job else self.pending_outputs
        sink.append(output)

    def _on_null(self, stmt: Statement, line_num: int) -> None:
        # The null statement (//) marks the end of the job on z/OS: what
        # follows, up to the next JOB statement, is not part of it (#124).
        # Before the JOB statement it delimits nothing and is ignored.
        if self.job is not None and self.null_line is None:
            self.null_line = line_num

    def skip_after_null(self, line: str, line_num: int) -> bool:
        """True if *line* follows the null statement that ended the job.

        Such a record is not part of the job, so the caller skips it; it is
        counted for the warning :meth:`finish` adds.  A JOB statement is not
        skipped: a second job is still the "Multiple JOB statements" error.
        """
        if self.null_line is None or _RE_JOB_RECORD.match(line):
            return False
        self.after_null_lines.append(line_num)
        return True

    def _on_control(self, stmt: Statement, line_num: int) -> None:
        """Record a COMMAND / SCHEDULE / CNTL / NOTIFY statement verbatim."""
        # No richer model representation, but they are real statements —
        # record them verbatim rather than discarding them.
        if stmt.type == "CNTL":
            stmt.parameters.setdefault("_records", [])
            self.current_cntl = stmt
        sink = self.job.control_statements if self.job else self.pending_control
        sink.append(stmt)

    def _on_endcntl(self, stmt: Statement, line_num: int) -> None:
        # Closes the CNTL block opened by _on_control; the block itself is
        # already recorded, so there is nothing more to keep.
        if self.current_cntl is None:
            self._statement_error(line_num, "ENDCNTL statement with no CNTL to end")
        self.current_cntl = None

    def _unclosed_cntl(self) -> None:
        """Report the open CNTL block, which the scan ended without ENDCNTL.

        The scan's own warning is already on ``job.warnings``.
        """
        cntl = self.current_cntl
        if cntl is None:
            return
        self.current_cntl = None
        self.statement_findings.append(
            (
                cntl.line_number,
                f"CNTL {cntl.name or '(unnamed)'} has no matching ENDCNTL",
                ErrorSeverity.ERROR,
            )
        )

    def handle_control_data(self, line: str) -> None:
        """Collect a program control record from inside a CNTL/ENDCNTL block."""
        if self.current_cntl is not None:
            self.current_cntl.parameters["_records"].append(line)

    def _on_custom(self, stmt: Statement, line_num: int) -> None:
        """Keep a statement of a type the builder has no handler for.

        Such statements come from a :class:`~jclparser.plugins.StatementPlugin`
        returning a custom ``Statement.type``; they used to be dropped
        silently (#130).
        """
        logger.debug(
            "no handler for statement type %r at line %d; kept in "
            "Job.custom_statements",
            stmt.type,
            line_num,
        )
        sink = self.job.custom_statements if self.job else self.pending_custom
        sink.append(stmt)

    def _on_unknown(self, stmt: Statement, line_num: int) -> None:
        # Unknown statement type - log but continue processing
        statement_type_name = stmt.parameters.get("_statement_type", "")
        logger.debug(
            "unknown statement type %r at line %d; ignoring",
            statement_type_name,
            line_num,
        )
        unknown_msg = (
            f"Line {line_num}: unrecognized statement type "
            f"'{statement_type_name}' ignored"
        )
        self._warnings_sink().append(unknown_msg)

    def _on_xmit(self, stmt: Statement, line_num: int) -> None:
        # XMIT statement - similar to DD but for data transmission
        if self.current_step:
            self.current_dd = DDStatement(
                name=stmt.name or "XMIT",
                parameters=stmt.parameters,
                line_number=stmt.line_number,
            )
            self.current_step.add_dd(self.current_dd)
        else:
            # Job-level XMIT has no step to attach a DD to, but the
            # transmitted data block that follows must still be
            # consumed as inline data -- otherwise those lines fall
            # through to parse_statement() and raise as invalid
            # JCL. There is nowhere to store this data, so discard
            # it; clear current_dd so the inline-data-end handler
            # doesn't misattach it to an unrelated earlier DD.
            self.current_dd = None
            self._warnings_sink().append(
                f"Line {stmt.line_number}: job-level XMIT has no step to attach "
                f"its data to; the transmitted records were discarded"
            )
        self._start_transmitted_data(xmit_delimiter(stmt.parameters), stmt.line_number)

    def _start_transmitted_data(self, delimiter: Any, line_num: int) -> None:
        """Open the data block of an XMIT / ``/*XMIT`` statement.

        The transmitted records are a job stream for another node, so a
        ``//`` record never ends them: only ``/*`` or the ``DLM=`` delimiter
        does (the pre-scan in ``_merge_source_lines`` uses the same rule).
        """
        if not isinstance(delimiter, str):
            raise JCLSyntaxError(
                f"DLM= must be a one- or two-character delimiter, got "
                f"{jcl_value_text(delimiter)}",
                line_num,
            )
        self.in_inline_data = True
        self.inline_data_lines = []
        self.current_delimiter = delimiter
        self.current_terminates_on_slash = False

    # ------------------------------------------------------------------ #
    # Finalisation
    # ------------------------------------------------------------------ #

    def _unclosed_data_warning(self) -> str | None:
        """Warn when an unterminated in-stream block swallowed JCL statements.

        End of input closes in-stream data by design, so ordinary
        unterminated data stays silent; but a ``DD DATA`` / ``DLM=`` block
        whose delimiter never came and whose records include an ``EXEC``
        statement has almost certainly eaten the rest of the job.
        """
        if not self.in_inline_data:
            return None
        swallowed = next(
            (line for line in self.inline_data_lines if _RE_EXEC_RECORD.match(line)),
            None,
        )
        if swallowed is None:
            return None
        dd = self.current_dd
        if dd is None:
            # Job-level XMIT: its records are discarded, no DD holds them.
            where = "In-stream data"
        else:
            where = (
                f"Line {dd.line_number}: in-stream data of DD {dd.name or '(unnamed)'}"
            )
        return (
            f"{where} was never closed by its delimiter "
            f"{self.current_delimiter!r}; it ran to the end of input and "
            f"swallowed JCL statements such as {swallowed.strip()!r}"
        )

    def finish(self) -> Job:
        """Flush pending state and return the assembled :class:`Job`.

        Raises :class:`JCLSyntaxError` when no JOB statement (and no
        procedures, for PROC-only files) was found.
        """
        # In-stream data that runs to end-of-file without a closing delimiter
        # is still valid: end-of-input terminates it.  Flush whatever was
        # collected rather than silently discarding it -- even nothing: a
        # ``DD *`` that is the last statement is an empty in-stream dataset,
        # as it is before a following statement or a ``/*``.
        if self.in_inline_data and self.current_dd:
            self.current_dd.inline_data = "\n".join(self.inline_data_lines)
        unclosed_data_warning = self._unclosed_data_warning()

        job = self._job_or_procedure_member()

        if self.pending_warnings:
            job.warnings.extend(self.pending_warnings)
        self._warn_missing_pend(job)
        if unclosed_data_warning is not None:
            job.warnings.append(unclosed_data_warning)

        self._flush_pending_statements(job)
        self._unclosed_cntl()
        self._warn_orphaned_dds(job)
        self._warn_unclosed_ifs(job)
        self._warn_after_null(job)
        job.statement_findings.extend(self.statement_findings)

        return job

    def _warn_after_null(self, job: Job) -> None:
        if self.null_line is not None and self.after_null_lines:
            job.warnings.append(
                f"Line {self.null_line}: null statement (//) ends job "
                f"{job.name or '(unnamed)'}; {len(self.after_null_lines)} "
                f"record(s) after it (lines {self.after_null_lines[0]}-"
                f"{self.after_null_lines[-1]}) are not part of the job and "
                "were ignored"
            )

    def _job_or_procedure_member(self) -> Job:
        """The parsed Job, or a synthetic one for a JOB-less PROC member."""
        if self.job is not None:
            return self.job
        if not self.pending_procedures:
            raise JCLSyntaxError("No JOB statement found", 0)
        job = Job(name="", line_number=0, is_procedure_member=True)
        for proc in self.pending_procedures:
            job.add_procedure(proc)
            # A JOB-less member (a cataloged procedure) has no job
            # scope of its own: its procedures' SETs are the member's
            # SETs, so the synthetic job exposes them too. The
            # Procedure keeps its own copy for explosion.
            job.set_statements.update(proc.set_statements)
        return job

    def _warn_missing_pend(self, job: Job) -> None:
        # An in-stream PROC with no PEND reads every later statement into the
        # procedure, so the job silently loses its steps.  A JOB-less member
        # (a cataloged PROC) needs no PEND, so only a real job is warned.
        if self.job is not None and self.current_procedure is not None:
            job.warnings.append(
                f"Line {self.current_procedure.line_number}: PROC "
                f"{self.current_procedure.name} has no PEND; the statements "
                "after it were read as part of the procedure"
            )

    def _flush_pending_statements(self, job: Job) -> None:
        """Attach statements buffered before the JOB statement onto *job*."""
        if self.pending_jes_statements:
            job.jes_statements.extend(self.pending_jes_statements)
        if self.pending_jes_typed:
            job.jes_typed_statements.extend(self.pending_jes_typed)

        self._flush_pending_sets(job)
        job.exported_symbols |= self.pending_exported
        job.jcllib_order[:0] = self.pending_jcllib
        for member in self.pending_includes:
            if member not in job.includes:
                job.includes.append(member)
        job.output_statements[:0] = self.pending_outputs
        job.conditionals[:0] = self.pending_conditionals
        job.steps[:0] = self.pending_steps
        job.control_statements[:0] = self.pending_control
        job.custom_statements[:0] = self.pending_custom

    def _flush_pending_sets(self, job: Job) -> None:
        # Statements seen before the JOB statement (or in a JOB-less member)
        # are attached now.  Later definitions of the same SET symbol win, so
        # buffered values only fill in symbols the job does not already define.
        for symbol, value in self.pending_sets.items():
            job.set_statements.setdefault(symbol, value)
        # A step's SET snapshot only matters when a later SET redefined a
        # symbol it could see; everywhere else the final table is the same.
        for step in self.job_level_steps:
            if not self.set_redefined or all(
                job.set_statements.get(k) == v
                for k, v in (step.set_symbols or {}).items()
            ):
                step.set_symbols = None
        for procedure, step in self.procedure_steps:
            if all(
                procedure.set_statements.get(k) == v
                for k, v in (step.set_symbols or {}).items()
            ):
                step.set_symbols = None

    def _warn_orphaned_dds(self, job: Job) -> None:
        # orphaned_dds is only ever non-empty here when the whole job had no
        # job-level EXEC statement at all (the first one always flushes and
        # clears the list) -- those DD statements have nowhere to attach and are
        # discarded, so record what was lost instead of vanishing them silently.
        if self.orphaned_dds:
            dd_names = ", ".join(dd.name or "(unnamed)" for dd in self.orphaned_dds)
            job.warnings.append(
                f"{len(self.orphaned_dds)} DD statement(s) found with no EXEC step "
                f"anywhere in the job; discarded: {dd_names}"
            )

    def _warn_unclosed_ifs(self, job: Job) -> None:
        # An IF block left open (no matching ENDIF) at end-of-job is malformed
        # JCL; the then/else steps collected so far are still attached to the
        # ConditionalBlock and not lost, but the imbalance itself is worth
        # flagging.
        for _cond, _branch in self.conditional_stack:
            job.warnings.append(
                f"Line {_cond.line_number}: IF block has no matching ENDIF"
            )
            self.conditional_errors.append(
                (_cond.line_number, "IF statement has no matching ENDIF")
            )
        job.conditional_errors.extend(sorted(self.conditional_errors))
