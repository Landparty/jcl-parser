"""Keyword parameters z/OS defines for the JOB, EXEC and DD statements.

Internal module. :func:`jclparser._statement_parser._find_comment_start` uses
these sets to tell a blank inside the operand field (``DSN=A,   DISP=SHR``,
illegal but common) from the start of a comment field that happens to hold
an ``=`` (``DSN=A,   RETAIN=30 DAYS``): only a keyword the statement accepts
resumes the operands.  Sources: z/OS MVS JCL Reference, "Keyword parameters"
of the JOB, EXEC and DD statements (z/OS 3.1), DCB subparameters included,
since they may be coded directly on a DD.
"""

from __future__ import annotations

#: JOB statement keyword parameters.
JOB_KEYWORDS: frozenset[str] = frozenset(
    {
        "ADDRSPC",
        "BYTES",
        "CARDS",
        "CCSID",
        "CLASS",
        "COND",
        "DSENQSHR",
        "EMAIL",
        "GDGBIAS",
        "GROUP",
        "JESLOG",
        "JOBRC",
        "LINES",
        "MEMLIMIT",
        "MSGCLASS",
        "MSGLEVEL",
        "NOTIFY",
        "PAGES",
        "PASSWORD",
        "PERFORM",
        "PRTY",
        "RD",
        "REGION",
        "REGIONX",
        "RESTART",
        "SCHENV",
        "SECLABEL",
        "SYSAFF",
        "SYSTEM",
        "TIME",
        "TYPRUN",
        "UJOBCORR",
        "USER",
    }
)

#: EXEC statement keyword parameters (an EXEC of a procedure also takes any
#: symbolic parameter name, so these only bound an ``EXEC PGM=``).
EXEC_KEYWORDS: frozenset[str] = frozenset(
    {
        "ACCT",
        "ADDRSPC",
        "CCSID",
        "COND",
        "DYNAMNBR",
        "MEMLIMIT",
        "PARM",
        "PARMDD",
        "PERFORM",
        "PGM",
        "PROC",
        "RD",
        "REGION",
        "REGIONX",
        "RLSTMOUT",
        "TIME",
        "TVSAMCOM",
        "TVSMSG",
    }
)

#: DCB subparameters, which a DD statement may also code as keywords.
_DCB_KEYWORDS: frozenset[str] = frozenset(
    {
        "BFALN",
        "BFTEK",
        "BLKSIZE",
        "BUFIN",
        "BUFL",
        "BUFMAX",
        "BUFNO",
        "BUFOFF",
        "BUFOUT",
        "BUFSIZE",
        "CPRI",
        "CYLOFL",
        "DEN",
        "DIAGNS",
        "DSORG",
        "EROPT",
        "FUNC",
        "GNCP",
        "INTVL",
        "IPLTXID",
        "KEYLEN",
        "LIMCT",
        "LRECL",
        "MODE",
        "NCP",
        "NTM",
        "OPTCD",
        "PCI",
        "PRTSP",
        "RECFM",
        "RESERVE",
        "RKP",
        "STACK",
        "THRESH",
        "TRTCH",
    }
)

#: DD statement keyword parameters.
DD_KEYWORDS: frozenset[str] = _DCB_KEYWORDS | frozenset(
    {
        "ACCODE",
        "AMP",
        "AVGREC",
        "BLKSZLIM",
        "BURST",
        "CCSID",
        "CHARS",
        "CHKPT",
        "CNTL",
        "COPIES",
        "DATACLAS",
        "DCB",
        "DDNAME",
        "DEST",
        "DISP",
        "DLM",
        "DSID",
        "DSKEYLBL",
        "DSN",
        "DSNAME",
        "DSNTYPE",
        "EATTR",
        "EXPDT",
        "FCB",
        "FILEDATA",
        "FLASH",
        "FREE",
        "FREEVOL",
        "GDGORDER",
        "HOLD",
        "KEYENCD1",
        "KEYENCD2",
        "KEYLABL1",
        "KEYLABL2",
        "KEYOFF",
        "LABEL",
        "LGSTREAM",
        "LIKE",
        "MAXGENS",
        "MGMTCLAS",
        "MODIFY",
        "OUTLIM",
        "OUTPUT",
        "PATH",
        "PATHDISP",
        "PATHMODE",
        "PATHOPTS",
        "PROTECT",
        "QNAME",
        "RECORG",
        "REFDD",
        "RETPD",
        "RLS",
        "ROACCESS",
        "SECMODEL",
        "SEGMENT",
        "SPACE",
        "SPIN",
        "STORCLAS",
        "SUBSYS",
        "SYMBOLS",
        "SYMLIST",
        "SYSOUT",
        "TERM",
        "UCS",
        "UNIT",
        "VOL",
        "VOLUME",
    }
)


def resuming_keywords(operation: str, operands: str) -> frozenset[str] | None:
    """The keywords that may resume *operation*'s operands after a blank.

    ``None`` means any ``KEY=`` does: the statement's keywords are not known
    here, or (an EXEC of a procedure) may be symbolic parameter names.
    """
    if operation == "DD":
        return DD_KEYWORDS
    if operation == "JOB":
        return JOB_KEYWORDS
    if operation == "EXEC" and operands.lstrip().upper().startswith("PGM="):
        return EXEC_KEYWORDS
    return None
