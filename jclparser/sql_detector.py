"""
SQL and DB2 detection in JCL steps.

Detects embedded SQL statements in JCL inline data (DD * / DD DATA) and
identifies steps that execute known DB2 utility programs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Job, Step, DDStatement

# Programs known to execute SQL or DB2 operations.
DB2_PROGRAMS: frozenset = frozenset(
    {
        "DSNTEP2",  # DB2 batch SQL processor
        "DSNTEP4",  # DB2 batch SQL processor (extended)
        "DSNTIAD",  # DB2 interactive SQL
        "IKJEFT01",  # TSO batch - commonly used to run DB2 commands
        "IKJEFT1B",  # TSO batch (alias)
        "DSNUPROC",  # DB2 utility driver
        "DSNUTILB",  # DB2 utility (batch)
        "DSNTEP",  # DB2 test (short name)
    }
)

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
    r"^\s*(?:" + "|".join(re.escape(kw) for kw, _ in _SQL_STATEMENT_PATTERNS) + r")\b",
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
        is_db2_program: True when the program is a known DB2 utility.
        sql_statements: SQL statement keywords found in inline data,
            each as ``(keyword, category, dd_name)`` tuples.
        has_sql: True if any SQL was detected (program or inline).
    """

    step_name: Optional[str] = None
    program: Optional[str] = None
    is_db2_program: bool = False
    sql_statements: List[tuple] = field(default_factory=list)

    @property
    def has_sql(self) -> bool:
        """True if SQL was detected by any means."""
        return self.is_db2_program or bool(self.sql_statements)

    @property
    def sql_categories(self) -> frozenset:
        """Set of distinct SQL categories found (DML, DDL, DCL, UTILITY, EMBEDDED)."""
        return frozenset(cat for _, cat, _ in self.sql_statements)


def is_db2_program(program_name: Optional[str]) -> bool:
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
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        if _SQL_KW_RE.match(line):
            # Determine which keyword matched.
            upper = line.upper()
            for kw, cat in _SQL_STATEMENT_PATTERNS:
                if upper.startswith(kw) and (
                    len(upper) == len(kw) or not upper[len(kw)].isalpha()
                ):
                    results.append((kw, cat))
                    break
    return results


def detect_sql_in_dd(dd: "DDStatement") -> list[tuple[str, str]]:
    """Scan a single DD statement's inline data for SQL.

    Returns ``(keyword, category)`` pairs, or an empty list when the DD
    has no inline data or no SQL is found.
    """
    if not dd.inline_data:
        return []
    return detect_sql_in_text(dd.inline_data)


def detect_sql_in_step(step: "Step") -> SQLDetectionResult:
    """Analyse a step for SQL content.

    Checks both the program name and inline data of every DD statement.
    """
    result = SQLDetectionResult(
        step_name=step.name,
        program=step.program,
        is_db2_program=is_db2_program(step.program),
    )
    for dd in step.dd_statements:
        for kw, cat in detect_sql_in_dd(dd):
            result.sql_statements.append((kw, cat, dd.name))
    return result


def detect_sql_in_job(job: "Job") -> list[SQLDetectionResult]:
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
