"""Tests for the diagnostic logging emitted across the parse pipeline.

These assert behavior of the INFO/DEBUG logging added to the core parser,
PROC/INCLUDE resolution, and validation. They rely on pytest's ``caplog``
fixture, which captures records propagated to the root logger; the package
``NullHandler`` does not interfere with propagation.
"""

import logging
import textwrap

import pytest

from jclparser import parse_jcl
from jclparser.errors import CircularProcedureError, ExplosionDepthError
from jclparser.explosion import explode_job


def _jclparser_records(caplog):
    """Return only the captured records emitted by jclparser loggers."""
    return [r for r in caplog.records if r.name.startswith("jclparser")]


SIMPLE_JOB = textwrap.dedent(
    """\
    //MYJOB    JOB (ACCT),'TEST',CLASS=A
    //STEP1    EXEC PGM=IEFBR14
    //DD1      DD DSN=MY.DATA,DISP=SHR
    """
)


class TestInfoSummary:
    """INFO-level milestones are emitted sparsely on a successful parse."""

    def test_parse_emits_info_summary_with_job_name_and_step_count(self, caplog):
        with caplog.at_level(logging.INFO, logger="jclparser"):
            parse_jcl(SIMPLE_JOB)

        summaries = [
            r
            for r in _jclparser_records(caplog)
            if r.levelno == logging.INFO and "parsed job" in r.getMessage().lower()
        ]
        assert summaries, "expected an INFO 'parsed job' summary record"
        msg = summaries[0].getMessage()
        assert "MYJOB" in msg
        assert "1" in msg  # one step

    def test_parameter_parsing_is_not_logged_at_info(self, caplog):
        """INFO stays sparse: parameter parsing logs only at DEBUG, not INFO."""
        with caplog.at_level(logging.INFO, logger="jclparser"):
            parse_jcl(SIMPLE_JOB)

        param_info = [
            r
            for r in _jclparser_records(caplog)
            if r.name == "jclparser.parameter_ast" and r.levelno >= logging.INFO
        ]
        assert param_info == []


class TestContinuationDebug:
    """Continuation merges are traced at DEBUG only when a merge happens."""

    def test_continuation_merge_logged_at_debug(self, caplog):
        jcl = textwrap.dedent(
            """\
            //MYJOB    JOB (ACCT),'TEST',CLASS=A
            //STEP1    EXEC PGM=IEFBR14
            //DD1      DD DSN=MY.DATA,DISP=SHR,
            //             UNIT=SYSDA,SPACE=(TRK,(1,1))
            """
        )
        with caplog.at_level(logging.DEBUG, logger="jclparser"):
            parse_jcl(jcl)

        merges = [
            r
            for r in _jclparser_records(caplog)
            if r.name == "jclparser.continuation_handler"
            and r.levelno == logging.DEBUG
            and "merged" in r.getMessage().lower()
        ]
        assert merges, "expected a DEBUG record about merging continuation lines"


class TestSymbolSubstitutionDebug:
    """Symbol resolution is traced at DEBUG."""

    def test_symbol_resolution_logged_at_debug(self, caplog):
        jcl = textwrap.dedent(
            """\
            //MYJOB    JOB (ACCT),'TEST',CLASS=A
            //         SET HLQ=PROD
            //STEP1    EXEC PGM=IEFBR14
            //DD1      DD DSN=&HLQ..MY.DATA,DISP=SHR
            """
        )
        with caplog.at_level(logging.DEBUG, logger="jclparser"):
            parse_jcl(jcl)

        resolved = [
            r
            for r in _jclparser_records(caplog)
            if r.name == "jclparser.explosion"
            and r.levelno == logging.DEBUG
            and "resolved" in r.getMessage().lower()
            and "HLQ" in r.getMessage()
        ]
        assert resolved, "expected a DEBUG record for resolving &HLQ"
        assert "PROD" in resolved[0].getMessage()


class TestExplodeInfo:
    """explode_job emits an INFO summary of the expansion."""

    def test_explode_job_emits_info_summary(self, caplog):
        jcl = textwrap.dedent(
            """\
            //MYJOB    JOB (ACCT),'TEST',CLASS=A
            //MYPROC   PROC
            //P1       EXEC PGM=IEFBR14
            //         PEND
            //STEP1    EXEC MYPROC
            """
        )
        job = parse_jcl(jcl)
        with caplog.at_level(logging.INFO, logger="jclparser"):
            explode_job(job)

        summaries = [
            r
            for r in _jclparser_records(caplog)
            if r.name == "jclparser.explosion"
            and r.levelno == logging.INFO
            and "exploded job" in r.getMessage().lower()
        ]
        assert summaries, "expected an INFO 'exploded job' summary record"


class TestProcExpansionDebug:
    """Entering a PROC expansion is traced at DEBUG with name and depth."""

    def test_proc_expansion_entered_logged_at_debug(self, caplog):
        jcl = textwrap.dedent(
            """\
            //MYJOB    JOB (ACCT),'TEST',CLASS=A
            //MYPROC   PROC
            //P1       EXEC PGM=IEFBR14
            //         PEND
            //STEP1    EXEC MYPROC
            """
        )
        job = parse_jcl(jcl)
        with caplog.at_level(logging.DEBUG, logger="jclparser"):
            explode_job(job)

        entered = [
            r
            for r in _jclparser_records(caplog)
            if r.name == "jclparser.explosion"
            and r.levelno == logging.DEBUG
            and "expanding proc" in r.getMessage().lower()
            and "MYPROC" in r.getMessage()
        ]
        assert entered, "expected a DEBUG record when entering a PROC expansion"
        assert "depth" in entered[0].getMessage().lower()

    def test_circular_reference_logged_at_debug(self, caplog):
        """A circular PROC chain logs a DEBUG before raising."""
        from jclparser.model import Job, Step, Procedure
        from jclparser.proc_loader import InlineProcedureLoader

        # PROCA calls PROCB which calls PROCA.
        proc_a = Procedure(name="PROCA", steps=[Step(name="S", procedure="PROCB")])
        proc_b = Procedure(name="PROCB", steps=[Step(name="S", procedure="PROCA")])
        job = Job(name="J", steps=[Step(name="TOP", procedure="PROCA")])
        loader = InlineProcedureLoader([proc_a, proc_b])

        with caplog.at_level(logging.DEBUG, logger="jclparser"):
            with pytest.raises(CircularProcedureError):
                explode_job(job, proc_loader=loader)

        circ = [
            r
            for r in _jclparser_records(caplog)
            if r.name == "jclparser.explosion"
            and r.levelno == logging.DEBUG
            and "circular" in r.getMessage().lower()
        ]
        assert circ, "expected a DEBUG record about the circular reference"

    def test_depth_limit_logged_at_debug(self, caplog):
        """Exceeding max_depth logs a DEBUG before raising."""
        from jclparser.model import Job, Step, Procedure
        from jclparser.proc_loader import InlineProcedureLoader

        # PROCA -> PROCB -> PROCC, exploded with max_depth=1.
        proc_a = Procedure(name="PROCA", steps=[Step(name="S", procedure="PROCB")])
        proc_b = Procedure(name="PROCB", steps=[Step(name="S", procedure="PROCC")])
        proc_c = Procedure(name="PROCC", steps=[Step(name="S", program="IEFBR14")])
        job = Job(name="J", steps=[Step(name="TOP", procedure="PROCA")])
        loader = InlineProcedureLoader([proc_a, proc_b, proc_c])

        with caplog.at_level(logging.DEBUG, logger="jclparser"):
            with pytest.raises(ExplosionDepthError):
                explode_job(job, proc_loader=loader, max_depth=1)

        depth = [
            r
            for r in _jclparser_records(caplog)
            if r.name == "jclparser.explosion"
            and r.levelno == logging.DEBUG
            and "depth" in r.getMessage().lower()
            and "limit" in r.getMessage().lower()
        ]
        assert depth, "expected a DEBUG record about exceeding the depth limit"


class TestParserPostLoopDebug:
    """The post-parse passes announce themselves at DEBUG."""

    def test_set_symbol_resolution_logged_at_debug(self, caplog):
        jcl = textwrap.dedent(
            """\
            //MYJOB    JOB (ACCT),'TEST',CLASS=A
            //         SET HLQ=PROD
            //STEP1    EXEC PGM=IEFBR14
            //DD1      DD DSN=&HLQ..MY.DATA,DISP=SHR
            """
        )
        with caplog.at_level(logging.DEBUG, logger="jclparser"):
            parse_jcl(jcl)

        passes = [
            r
            for r in _jclparser_records(caplog)
            if r.name == "jclparser.parser"
            and r.levelno == logging.DEBUG
            and "set symbol" in r.getMessage().lower()
        ]
        assert passes, "expected a DEBUG record when SET symbol resolution runs"


class TestSilentByDefault:
    """With no log level configured below WARNING, parsing is quiet."""

    def test_no_info_or_debug_when_level_is_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="jclparser"):
            parse_jcl(SIMPLE_JOB)

        chatty = [r for r in _jclparser_records(caplog) if r.levelno < logging.WARNING]
        assert chatty == []
