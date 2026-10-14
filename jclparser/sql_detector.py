"""
SQL and DB2 detection in JCL steps.

Detects embedded SQL statements in JCL inline data (DD * / DD DATA) and
identifies steps that execute known DB2 utility programs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .utils import split_source_lines

if TYPE_CHECKING:
    from .model import DDStatement, Job, Step

# Programs known to execute SQL or DB2 operations.
DB2_PROGRAMS: frozenset[str] = frozenset(
    {
        "DSNTEP2",  # DB2 batch SQL processor
        "DSNTEP4",  # DB2 batch SQL processor (extended)
        "DSNTIAD",  # DB2 interactive SQL
        "DSNTIAUL",  # DB2 sample unload utility
        "IKJEFT01",  # TSO batch - commonly used to run DB2 commands
        "IKJEFT1A",  # TSO batch (alias)
        "IKJEFT1B",  # TSO batch (alias)
        "DSNUPROC",  # DB2 utility driver
        "DSNUTILB",  # DB2 utility (batch)
        "DSNTEP",  # DB2 test (short name)
    }
)

# Catalogued PROCs that run DB2 work (``EXEC DSNUPROC`` names a PROC, not a
# program).  On an exploded job their steps run the DB2 programs themselves.
DB2_PROCEDURES: frozenset[str] = frozenset(
    {
        "DSNUPROC",  # DB2 online utility PROC (runs DSNUTILB)
        "DSNHASM",  # DB2 precompile + assemble
        "DSNHC",  # DB2 precompile + C compile
        "DSNHCOB",  # DB2 precompile + COBOL compile
        "DSNHCOB2",
        "DSNHCPP",  # DB2 precompile + C++ compile
        "DSNHICOB",  # DB2 precompile + Enterprise COBOL compile
        "DSNHPLI",  # DB2 precompile + PL/I compile
    }
)

# Programs whose in-stream data is their own control language, not SQL.  Their
# statements reuse SQL verbs -- IDCAMS ``DELETE`` / ``ALTER``, FTP ``DELETE``
# / ``RENAME`` -- so scanning that data for SQL only yields false positives.
NON_SQL_CONTROL_PROGRAMS: frozenset[str] = frozenset(
    {
        "ADRDSSU",
        "BPXBATCH",
        "DFSORT",
        "FTP",
        "ICEGENER",
        "ICEMAN",
        "ICETOOL",
        "IDCAMS",
        "IEBCOMPR",
        "IEBCOPY",
        "IEBDG",
        "IEBGENER",
        "IEBPTPCH",
        "IEBUPDTE",
        "IEFBR14",
        "IEHINITT",
        "IEHLIST",
        "IEHPROGM",
        "IRXJCL",
        "SORT",
        "SORTD",
        "SYNCSORT",
        "SYNCTOOL",
    }
)

# DB2 online-utility programs.  Their in-stream data is utility control
# statements (``RUNSTATS ... UPDATE ALL``, ``MODIFY RECOVERY ... DELETE AGE(n)``)
# whose options reuse SQL verbs; only the SQL inside an ``EXEC SQL ...
# ENDEXEC`` utility statement is SQL.
DB2_UTILITY_CONTROL_PROGRAMS: frozenset[str] = frozenset({"DSNUTILB"})

_EXEC_SQL_RE = re.compile(r"\bEXEC\s+SQL\b", re.IGNORECASE)
_ENDEXEC_RE = re.compile(r"\bENDEXEC\b", re.IGNORECASE)

# SYSTSIN holds TSO commands (``DELETE``, ``RENAME`` and ``ALTER`` are TSO
# commands too); only the DB2 DSN subcommands in it are SQL-related.
_TSO_COMMAND_DD = "SYSTSIN"
_TSO_SQL_CATEGORIES = frozenset({"UTILITY"})

# SQL statement keywords that start a statement.  Order matters for matching:
# longer prefixes first so "INSERT INTO" beats "INSERT".
_SQL_STATEMENT_PATTERNS: list[tuple[str, str]] = [
    # DML
    ("SELECT", "DML"),
    ("INSERT", "DML"),
    ("UPDATE", "DML"),
    ("DELETE", "DML"),
    ("MERGE", "DML"),
    # DDL
    ("CREATE", "DDL"),
    ("ALTER", "DDL"),
    ("DROP", "DDL"),
    ("TRUNCATE", "DDL"),
    ("RENAME", "DDL"),
    ("COMMENT", "DDL"),
    # DCL
    ("GRANT", "DCL"),
    ("REVOKE", "DCL"),
    # DB2 utility / admin
    ("BIND", "UTILITY"),
    ("REBIND", "UTILITY"),
    ("EXPLAIN", "UTILITY"),
    # Embedded SQL marker
    ("EXEC SQL", "EMBEDDED"),
]

# Compiled regex that matches any SQL keyword at the start of a
# (whitespace-stripped) line.  Word-boundary after the keyword prevents
# matching identifiers that merely *start* with a SQL keyword.
_SQL_KW_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(kw) for kw, _ in _SQL_STATEMENT_PATTERNS) + r")\b",
    re.IGNORECASE,
)

# Build a mapping from uppercase keyword -> category for quick lookup.
_KW_CATEGORY: dict[str, str] = {kw.upper(): cat for kw, cat in _SQL_STATEMENT_PATTERNS}


@dataclass
class SQLDetectionResult:
    """Result of SQL detection for a single step.

    Attributes:
        step_name: Name of the step.
        program: Program executed by the step (if any).
        is_db2_program: True when the program is a known DB2 utility, or
            the step executes a known DB2 PROC (:data:`DB2_PROCEDURES`).
        sql_statements: SQL statement keywords found in inline data,
            each as ``(keyword, category, dd_name)`` tuples.
        has_sql: True if any SQL was detected (program or inline).
    """

    step_name: str | None = None
    program: str | None = None
    is_db2_program: bool = False
    sql_statements: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def has_sql(self) -> bool:
        """True if SQL was detected by any means."""
        return self.is_db2_program or bool(self.sql_statements)

    @property
    def sql_categories(self) -> frozenset[str]:
        """Set of distinct SQL categories found (DML, DDL, DCL, UTILITY, EMBEDDED)."""
        return frozenset(cat for _, cat, _ in self.sql_statements)


def is_db2_program(program_name: str | None) -> bool:
    """Return True if *program_name* is a known DB2 utility."""
    if not program_name:
        return False
    return program_name.upper() in DB2_PROGRAMS


def detect_sql_in_text(text: str) -> list[tuple[str, str]]:
    """Scan *text* for SQL statement keywords.

    Returns a list of ``(keyword, category)`` pairs for each line that
    begins with a recognised SQL keyword.  Blank lines and SQL comments
    (lines starting with ``--``) are skipped.
    """
    results: list[tuple[str, str]] = []
    for raw_line in split_source_lines(text):
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        match = _SQL_KW_RE.match(line)
        if match:
            keyword = match.group(1).upper()
            results.append((keyword, _KW_CATEGORY[keyword]))
    return results


def detect_sql_in_utility_statements(text: str) -> list[tuple[str, str]]:
    """Scan DB2 utility control statements for SQL.

    Only ``EXEC SQL ... ENDEXEC`` utility statements contribute: the
    ``EXEC SQL`` marker itself (``EMBEDDED``) and the SQL statement keywords
    between it and ``ENDEXEC``, which may share a line with either.  Every
    other utility statement (``RUNSTATS``, ``REORG``, ``MODIFY RECOVERY``, ...)
    is skipped, so options such as ``UPDATE ALL`` or ``DELETE AGE(90)`` are
    not reported as DML.
    """
    results: list[tuple[str, str]] = []
    in_exec_sql = False
    for raw_line in split_source_lines(text):
        rest = raw_line.strip()
        while rest:
            if not in_exec_sql:
                start = _EXEC_SQL_RE.search(rest)
                if start is None:
                    break
                results.append(("EXEC SQL", _KW_CATEGORY["EXEC SQL"]))
                in_exec_sql = True
                rest = rest[start.end() :]
                continue
            end = _ENDEXEC_RE.search(rest)
            body = rest if end is None else rest[: end.start()]
            results.extend(detect_sql_in_text(body))
            if end is None:
                break
            in_exec_sql = False
            rest = rest[end.end() :]
    return results


def detect_sql_in_dd(dd: DDStatement) -> list[tuple[str, str]]:
    """Scan a single DD statement's inline data for SQL.

    Returns ``(keyword, category)`` pairs, or an empty list when the DD
    has no inline data or no SQL is found.
    """
    if not dd.inline_data:
        return []
    return detect_sql_in_text(dd.inline_data)


def detect_sql_in_step(step: Step) -> SQLDetectionResult:
    """Analyse a step for SQL content.

    Checks the program name (or, for ``EXEC procname``, the PROC name) and
    the inline data of every DD statement.
    In-stream data of a program in :data:`NON_SQL_CONTROL_PROGRAMS` is not
    scanned, and in a ``SYSTSIN`` DD (TSO commands) only DB2 subcommands such
    as ``BIND`` count.  For a program in
    :data:`DB2_UTILITY_CONTROL_PROGRAMS` only ``EXEC SQL ... ENDEXEC``
    utility statements are scanned
    (:func:`detect_sql_in_utility_statements`).
    """
    result = SQLDetectionResult(
        step_name=step.name,
        program=step.program,
        is_db2_program=is_db2_program(step.program)
        or bool(step.procedure and step.procedure.upper() in DB2_PROCEDURES),
    )
    program = step.program.upper() if step.program else ""
    if program in NON_SQL_CONTROL_PROGRAMS:
        return result
    utility_control = program in DB2_UTILITY_CONTROL_PROGRAMS
    is_tso_input = False
    for dd in step.dd_statements:
        # An unnamed DD is a concatenation member of the last named one, so
        # ``//  DD *`` after ``//SYSTSIN DD ...`` is TSO input too.
        if dd.name:
            is_tso_input = dd.name.upper() == _TSO_COMMAND_DD
        if utility_control:
            found = detect_sql_in_utility_statements(dd.inline_data or "")
        else:
            found = detect_sql_in_dd(dd)
        for kw, cat in found:
            if is_tso_input and cat not in _TSO_SQL_CATEGORIES:
                continue
            result.sql_statements.append((kw, cat, dd.name))
    return result


def detect_sql_in_job(job: Job) -> list[SQLDetectionResult]:
    """Analyse all steps in a job and return results for those containing SQL.

    Only steps with detected SQL are included in the returned list.
    """
    from .model import iter_execution_steps

    results: list[SQLDetectionResult] = []
    for step in iter_execution_steps(job.steps):
        det = detect_sql_in_step(step)
        if det.has_sql:
            results.append(det)
    return results
