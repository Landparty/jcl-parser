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
from typing import Any

from ._model_factories import (
    _create_dd_from_statement,
    _create_job_from_statement,
    _create_step_from_statement,
    _exec_has_program_spec,
    _resolve_set_value,
)
from .condition_parser import parse_condition
from .errors import JCLSyntaxError
from .model import (
    ConditionalBlock,
    DDStatement,
    Job,
    OutputStatement,
    Procedure,
    Statement,
    Step,
)
from .utils import POSITIONAL_PARAM_PREFIX, is_positional_key

# Backward-compatible re-exports: these helpers historically lived in this
# module (and before that in ``jclparser.parser``) and are imported from here
# by ``parser.py`` and downstream code. Keep them importable from this path.
from ._model_factories import (  # noqa: F401
    _SET_SYMBOL_PATTERN,
    _has_unresolved_symbol_ref,
)
from ._post_parse import (  # noqa: F401
    _extract_output_ref_names,
    _resolve_output_refs,
    enforce_strict_dd_structure,
    load_external_procedures,
    resolve_set_symbols,
)

logger = logging.getLogger(__name__)

#: Explicit re-export list: mypy strict (``no_implicit_reexport``) would
#: otherwise reject the historical ``from ._job_builder import ...`` imports
#: in ``parser.py`` for the helpers that moved to the sibling modules.
__all__ = [
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


class JobBuilder:
    """Accumulates parse-loop state and assembles the :class:`Job` model.

    The ``parse_jcl()`` core loop feeds it one merged line / parsed
    :class:`Statement` at a time; each JCL statement type has its own
    ``_on_<type>`` handler. Call :meth:`finish` after the last line to obtain
    the assembled :class:`Job`.
    """

    def __init__(self) -> None:
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
        #: Track DDs that appear before first EXEC
        self.orphaned_dds: list[DDStatement] = []
        #: True while accumulating JOBLIB concatenation lines
        self.in_joblib_concat = False
        #: Warnings collected before the JOB statement is seen (no job.warnings
        #: yet to append to); flushed onto job.warnings once the Job object exists.
        self.pending_warnings: list[str] = []
        #: JES2/JES3 control statements (e.g. /*JOBPARM) seen before the JOB
        #: statement, which is legal per z/OS; flushed once job exists.
        self.pending_jes_statements: list[str] = []
        self.pending_jes_typed: list[Any] = []

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
        if line.strip() == self.current_delimiter or line.strip().startswith(
            self.current_delimiter
        ):
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

    def handle_comment_line(self, line: str, line_num: int) -> None:
        """Recognise JES3 ``//*ROUTE XEQ`` control statements before dropping
        the comment line."""
        if line.strip().startswith("//*") and self.job is not None:
            from .jes_statements import parse_jes3_route_xeq

            jes3 = parse_jes3_route_xeq(line, line_num)
            if jes3 is not None:
                self.job.jes_typed_statements.append(jes3)

    # ------------------------------------------------------------------ #
    # Statement dispatch
    # ------------------------------------------------------------------ #

    def handle_statement(self, stmt: Statement, line_num: int) -> None:
        """Record statement warnings, then dispatch to the type handler."""
        if stmt.warnings:
            self._warnings_sink().extend(stmt.warnings)

        if stmt.type == "JOB":
            self._on_job(stmt, line_num)
        elif stmt.type == "EXEC":
            self._on_exec(stmt, line_num)
        elif stmt.type == "DD":
            self._on_dd(stmt, line_num)
        elif stmt.type == "PROC":
            self._on_proc(stmt)
        elif stmt.type == "PEND":
            self._on_pend()
        elif stmt.type == "SET":
            self._on_set(stmt)
        elif stmt.type == "EXPORT":
            self._on_export(stmt)
        elif stmt.type == "JCLLIB":
            self._on_jcllib(stmt)
        elif stmt.type == "INCLUDE":
            self._on_include(stmt)
        elif stmt.type in ["IF", "THEN", "ELSE", "ENDIF"]:
            self._on_conditional(stmt, line_num)
        elif stmt.type == "JES":
            self._on_jes(stmt)
        elif stmt.type == "OUTPUT":
            self._on_output(stmt)
        elif stmt.type == "NULL":
            # NULL statement (//) - just ignore, used as delimiter
            pass
        elif stmt.type == "COMMAND":
            # COMMAND statement - operator commands, just ignore
            pass
        elif stmt.type in ["CNTL", "ENDCNTL"]:
            # CNTL/ENDCNTL statements - utility control, just ignore
            pass
        elif stmt.type == "SCHEDULE":
            # SCHEDULE statement - scheduling control, no model representation
            pass
        elif stmt.type == "UNKNOWN":
            self._on_unknown(stmt, line_num)
        elif stmt.type == "XMIT":
            self._on_xmit(stmt)

    # ------------------------------------------------------------------ #
    # Per-statement-type handlers
    # ------------------------------------------------------------------ #

    def _on_job(self, stmt: Statement, line_num: int) -> None:
        if self.job is not None:
            raise JCLSyntaxError("Multiple JOB statements found", line_num)
        self.job = _create_job_from_statement(stmt)

    def _on_exec(self, stmt: Statement, line_num: int) -> None:
        if self.job is None and self.current_procedure is None:
            raise JCLSyntaxError("EXEC statement before JOB statement", line_num)

        # Basic syntax check for EXEC - must have program, procedure, or positional parameter
        if not _exec_has_program_spec(stmt.parameters):
            raise JCLSyntaxError(
                "EXEC statement missing program or procedure", line_num
            )

        self.current_step = _create_step_from_statement(stmt)
        self.in_joblib_concat = False  # JOBLIB concatenation ends at first EXEC

        # Attach any orphaned DDs to this first step
        if self.orphaned_dds:
            for dd in self.orphaned_dds:
                self.current_step.add_dd(dd)
            self.orphaned_dds = []

        # Add step to procedure if we're inside PROC/PEND, otherwise to job
        if self.conditional_stack:
            active_cond, active_branch = self.conditional_stack[-1]
            if active_branch == "THEN":
                active_cond.add_then_step(self.current_step)
            else:
                active_cond.add_else_step(self.current_step)
        elif self.current_procedure is not None:
            self.current_procedure.steps.append(self.current_step)
        else:
            assert self.job is not None
            self.job.add_step(self.current_step)

    def _on_dd(self, stmt: Statement, line_num: int) -> None:
        # Create the DD statement
        self.current_dd = _create_dd_from_statement(stmt)
        current_dd = self.current_dd

        if self.current_step is None:
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
                # Store as orphaned DD to be attached to next step
                self.orphaned_dds.append(current_dd)
        elif stmt.name and "." in stmt.name:
            # This is a DD override for a procedure step
            parts = stmt.name.split(".", 1)  # Split on first dot only
            if len(parts) == 2:
                # Store as override on the current step, keeping the
                # qualified name for matching during explosion.
                self.current_step.dd_overrides[stmt.name] = current_dd
            else:
                # Regular DD statement
                self.current_step.add_dd(current_dd)
        else:
            # Regular DD statement
            self.current_step.add_dd(current_dd)

        # Check for inline data marker (only for non-override DDs)
        has_star_pos = any(
            v == "*" for k, v in current_dd.parameters.items() if is_positional_key(k)
        )
        is_star_dd = bool(current_dd.parameters.get("*") or has_star_pos)
        if current_dd and (is_star_dd or "DATA" in current_dd.parameters):
            logger.debug(
                "inline-data block started at DD %s (line %d)",
                current_dd.name or "(unnamed)",
                line_num,
            )
            self.in_inline_data = True
            self.inline_data_lines = []
            has_dlm = "DLM" in current_dd.parameters
            current_delimiter = current_dd.parameters.get("DLM", "/*")
            # Handle quoted delimiter
            if current_delimiter.startswith("'") and current_delimiter.endswith("'"):
                current_delimiter = current_delimiter[1:-1]
            self.current_delimiter = current_delimiter
            # ``DD *`` without an explicit ``DLM=`` also terminates at the
            # next ``//`` record; ``DD DATA`` does not (so // can be data).
            self.current_terminates_on_slash = is_star_dd and not has_dlm

    def _on_proc(self, stmt: Statement) -> None:
        # Inline procedure definition - start tracking procedure
        self.current_procedure = Procedure(
            name=stmt.name or "UNNAMED",
            parameters=stmt.parameters,
            line_number=stmt.line_number,
        )
        if self.job:
            self.job.add_procedure(self.current_procedure)
        else:
            self.pending_procedures.append(self.current_procedure)
        # Reset current_step since we're now inside procedure
        self.current_step = None

    def _on_pend(self) -> None:
        # End of procedure definition - stop tracking
        self.current_procedure = None
        self.current_step = None

    def _on_set(self, stmt: Statement) -> None:
        # SET symbol=value statement
        if self.job:
            # For SET statements, parameters are in the format SYMBOL=VALUE
            for key, value in stmt.parameters.items():
                if not is_positional_key(key):
                    self.job.add_set(
                        key, _resolve_set_value(value, self.job.set_statements)
                    )
                else:
                    # Positional parameter might be SYMBOL=VALUE without keyword
                    param_val = value
                    if "=" in param_val:
                        sym, val = param_val.split("=", 1)
                        self.job.add_set(
                            sym.strip(),
                            _resolve_set_value(val.strip(), self.job.set_statements),
                        )

    def _on_export(self, stmt: Statement) -> None:
        # EXPORT SYMLIST=(A,B,...)  or  EXPORT SYMLIST=*
        if self.job:
            symlist = stmt.parameters.get("SYMLIST")
            names: list[str] = []
            if isinstance(symlist, list):
                names = [str(n).strip().upper() for n in symlist if n]
            elif isinstance(symlist, str):
                names = [
                    n.strip().upper()
                    for n in symlist.strip("()").split(",")
                    if n.strip()
                ]
            for n in names:
                self.job.exported_symbols.add(n)

    def _on_jcllib(self, stmt: Statement) -> None:
        # JCLLIB ORDER=(lib1,lib2,...)
        if self.job and "ORDER" in stmt.parameters:
            order_value = stmt.parameters["ORDER"]
            # ORDER parameter might already be parsed as a list
            if isinstance(order_value, list):
                self.job.jcllib_order.extend(order_value)
            elif isinstance(order_value, str):
                libs = order_value.strip("()").split(",")
                self.job.jcllib_order.extend([lib.strip() for lib in libs])

    def _on_include(self, stmt: Statement) -> None:
        # INCLUDE MEMBER=name
        if self.job:
            member = stmt.parameters.get("MEMBER") or stmt.parameters.get(
                f"{POSITIONAL_PARAM_PREFIX}0"
            )
            if member:
                self.job.includes.append(member)

    def _on_conditional(self, stmt: Statement, line_num: int) -> None:
        # Conditional logic - track conditionals properly
        if stmt.type == "IF" and self.job:
            condition_parts = []
            if stmt.name and stmt.name != "IF":
                condition_parts.append(stmt.name)
            for key, value in stmt.parameters.items():
                if not key.startswith("_"):
                    condition_parts.append(f"{key}={value}")
                else:
                    condition_parts.append(str(value))
            condition = " ".join(condition_parts)
            if condition.upper().endswith(" THEN"):
                condition = condition[:-5]
            conditional = ConditionalBlock(
                condition=condition,
                condition_ast=parse_condition(condition),
                line_number=stmt.line_number,
            )
            self.job.add_conditional(conditional)
            if self.conditional_stack:
                active_cond, active_branch = self.conditional_stack[-1]
                if active_branch == "THEN":
                    active_cond.add_then_step(conditional)
                else:
                    active_cond.add_else_step(conditional)
            elif self.current_procedure is not None:
                self.current_procedure.steps.append(conditional)
            else:
                self.job.steps.append(conditional)
            self.conditional_stack.append((conditional, "THEN"))
        elif stmt.type == "THEN":
            if self.conditional_stack:
                active_cond, _ = self.conditional_stack.pop()
                self.conditional_stack.append((active_cond, "THEN"))
            else:
                self._warnings_sink().append(
                    f"Line {line_num}: THEN with no matching IF; ignored"
                )
        elif stmt.type == "ELSE":
            if self.conditional_stack:
                active_cond, _ = self.conditional_stack.pop()
                self.conditional_stack.append((active_cond, "ELSE"))
            else:
                self._warnings_sink().append(
                    f"Line {line_num}: ELSE with no matching IF; ignored"
                )
        elif stmt.type == "ENDIF":
            if self.conditional_stack:
                self.conditional_stack.pop()
            else:
                self._warnings_sink().append(
                    f"Line {line_num}: ENDIF with no matching IF; ignored"
                )

    def _on_jes(self, stmt: Statement) -> None:
        raw_params = stmt.parameters.get("_raw", "")
        jes_content = f"/*{stmt.name} {raw_params}".strip()
        # Also try to promote to a typed JES control statement.
        from .jes_statements import parse_jes_control

        typed = parse_jes_control(stmt.name, raw_params, stmt.line_number)
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

    def _on_output(self, stmt: Statement) -> None:
        # OUTPUT statement - JES output descriptor; promote to typed model
        if self.job:
            self.job.output_statements.append(OutputStatement.from_statement(stmt))

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

    def _on_xmit(self, stmt: Statement) -> None:
        # XMIT statement - similar to DD but for data transmission
        if self.current_step:
            self.current_dd = DDStatement(
                name=stmt.name or "XMIT",
                parameters=stmt.parameters,
                line_number=stmt.line_number,
            )
            self.current_step.add_dd(self.current_dd)
            self.in_inline_data = True
            self.inline_data_lines = []
        else:
            # Job-level XMIT has no step to attach a DD to, but the
            # transmitted data block that follows must still be
            # consumed as inline data -- otherwise those lines fall
            # through to parse_statement() and raise as invalid
            # JCL. There is nowhere to store this data, so discard
            # it; clear current_dd so the inline-data-end handler
            # doesn't misattach it to an unrelated earlier DD.
            self.current_dd = None
            self.in_inline_data = True
            self.inline_data_lines = []

    # ------------------------------------------------------------------ #
    # Finalisation
    # ------------------------------------------------------------------ #

    def finish(self) -> Job:
        """Flush pending state and return the assembled :class:`Job`.

        Raises :class:`JCLSyntaxError` when no JOB statement (and no
        procedures, for PROC-only files) was found.
        """
        # In-stream data that runs to end-of-file without a closing delimiter
        # is still valid: end-of-input terminates it.  Flush whatever was
        # collected rather than silently discarding it.
        if self.in_inline_data and self.current_dd and self.inline_data_lines:
            self.current_dd.inline_data = "\n".join(self.inline_data_lines)

        job = self.job
        if job is None:
            if self.pending_procedures:
                job = Job(name="", line_number=0)
                for proc in self.pending_procedures:
                    job.add_procedure(proc)
            else:
                raise JCLSyntaxError("No JOB statement found", 0)

        if self.pending_warnings:
            job.warnings.extend(self.pending_warnings)

        if self.pending_jes_statements:
            job.jes_statements.extend(self.pending_jes_statements)
        if self.pending_jes_typed:
            job.jes_typed_statements.extend(self.pending_jes_typed)

        # orphaned_dds is only ever non-empty here when the whole job had no
        # EXEC statement at all (the first EXEC always flushes and clears the
        # list) -- those DD statements have nowhere to attach and are
        # discarded, so record what was lost instead of vanishing them silently.
        if self.orphaned_dds:
            dd_names = ", ".join(dd.name or "(unnamed)" for dd in self.orphaned_dds)
            job.warnings.append(
                f"{len(self.orphaned_dds)} DD statement(s) found with no EXEC step "
                f"anywhere in the job; discarded: {dd_names}"
            )

        # An IF block left open (no matching ENDIF) at end-of-job is malformed
        # JCL; the then/else steps collected so far are still attached to the
        # ConditionalBlock and not lost, but the imbalance itself is worth
        # flagging.
        for _cond, _branch in self.conditional_stack:
            job.warnings.append(
                f"Line {_cond.line_number}: IF block has no matching ENDIF"
            )

        return job
