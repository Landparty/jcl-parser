"""Profile for batch ``FTP`` (``PGM=FTP``).

z/OS batch FTP reads its commands from the ``INPUT`` DD, and from ``SYSIN``
only when the step has no ``INPUT`` DD.  The remote host is the first
operand of ``PARM=`` (after any ``/``-terminated Language Environment
options); without one, the first input line is the host and the line after
it answers the login prompt (user ID, often followed by the password).
``OPEN`` names a host explicitly, ``USER`` authenticates, ``PUT``/``GET``/
``MPUT``/``MGET`` transfer files, and ``ASCII``/``BINARY`` set transfer
mode.  The profile surfaces the host, the user ID and the file operations
without attempting to resolve remote paths; a password is never reported.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..utils import control_card_text
from .base import ProgramAnalysis, ProgramProfile, _sysin_text

if TYPE_CHECKING:
    from ..model import Step

_RE_OPEN = re.compile(r"^\s*OPEN\s+(\S+)", re.IGNORECASE | re.MULTILINE)
_RE_USER = re.compile(r"^\s*USER\s+(\S+)", re.IGNORECASE | re.MULTILINE)
_RE_TRANSFER = re.compile(
    r"^\s*(PUT|GET|MPUT|MGET)\s+(\S+)", re.IGNORECASE | re.MULTILINE
)
_RE_MODE = re.compile(r"^\s*(ASCII|BINARY)\b", re.IGNORECASE | re.MULTILINE)

#: FTP client subcommands: a first input line starting with one of these is
#: a command, not the host (or the login reply).
_SUBCOMMANDS = frozenset(
    {
        "!",
        "?",
        "ACCOUNT",
        "APPEND",
        "ASCII",
        "BINARY",
        "BLOCK",
        "CD",
        "CDUP",
        "CLOSE",
        "DEBUG",
        "DELETE",
        "DIR",
        "EBCDIC",
        "GET",
        "HELP",
        "LCD",
        "LOCSITE",
        "LS",
        "MDELETE",
        "MGET",
        "MKDIR",
        "MODE",
        "MPUT",
        "NOOP",
        "OPEN",
        "PASS",
        "PUT",
        "PWD",
        "QUIT",
        "QUOTE",
        "RENAME",
        "RMDIR",
        "SENDSITE",
        "SITE",
        "STRUCTURE",
        "TYPE",
        "USER",
    }
)


def _command_text(step: Step) -> tuple[str, list[str]]:
    """The FTP command text, and notes on where it comes from.

    ``INPUT`` wins; ``SYSIN`` is read only when there is no ``INPUT`` DD.
    An ``INPUT`` DD naming a dataset is noted, its content being unknown.
    """
    dd = step.get_dd("INPUT")
    if dd is None:
        return _sysin_text(step) or "", []
    if dd.inline_data:
        return control_card_text(dd.inline_data), []
    if dd.dataset_name:
        return "", [f"commands from INPUT: {dd.dataset_name}"]
    return "", []


def _parm_host(step: Step) -> str | None:
    """The host named on ``PARM=``: its first operand, after any LE options."""
    parm = step.parameters.get("PARM")
    if not isinstance(parm, str):
        return None
    text = parm.strip().strip("'")
    text = text.partition("/")[2] if "/" in text else text
    operand = text.partition("(")[0].split()
    return operand[0] if operand else None


def _first_word(line: str) -> str:
    words = line.split()
    return words[0] if words else ""


def _is_login_reply(line: str) -> bool:
    """True when *line* reads as the reply to the login prompt, ``userid
    [password]``, rather than as a subcommand.  ``USER id pw`` (three
    words) is the ``USER`` subcommand; ``user pw`` is a user ID that
    happens to be spelt ``user``."""
    words = line.split()
    if not words:
        return False
    first = words[0].upper()
    if first == "USER":
        return len(words) < 3
    return first not in _SUBCOMMANDS


def _connection(step: Step, lines: list[str]) -> tuple[list[str], int]:
    """``OPEN host`` / ``USER id`` notes for the implicit connection, and how
    many leading *lines* it consumed (the host line, the login reply).

    The host comes from ``PARM=`` or, without one, the first input line;
    the line after it answers the login prompt.  Only the user ID is
    reported: the rest of the reply is the password.
    """
    host = _parm_host(step)
    used = 0
    if host is None:
        if not lines or _first_word(lines[0]).upper() in _SUBCOMMANDS:
            return [], 0
        host, used = _first_word(lines[0]), 1
    notes = [f"OPEN {host}"]
    if used < len(lines) and _is_login_reply(lines[used]):
        notes.append(f"USER {_first_word(lines[used])}")
        used += 1
    return notes, used


def _subcommand_notes(text: str) -> list[str]:
    notes: list[str] = []
    host_m = _RE_OPEN.search(text)
    if host_m:
        notes.append(f"OPEN {host_m.group(1)}")
    user_m = _RE_USER.search(text)
    if user_m:
        notes.append(f"USER {user_m.group(1)}")
    for m in _RE_TRANSFER.finditer(text):
        notes.append(f"{m.group(1).upper()} {m.group(2)}")
    mode_m = _RE_MODE.search(text)
    if mode_m:
        notes.append(mode_m.group(1).upper())
    return notes


class FTPProfile(ProgramProfile):
    program_names = frozenset({"FTP"})

    def analyze(self, step: Step) -> ProgramAnalysis:
        text, source_notes = _command_text(step)
        lines = [line for line in text.splitlines() if line.strip()]
        connection, used = _connection(step, lines)
        # The consumed host / login lines are not subcommands: ``user pw``
        # must not read as ``USER pw`` and report the password.
        commands = "\n".join(lines[used:])
        notes = list(
            dict.fromkeys([*source_notes, *connection, *_subcommand_notes(commands)])
        )

        summary = (
            f"FTP: {len(notes)} subcommand(s)"
            if notes
            else "FTP with no recognised INPUT/SYSIN subcommands"
        )
        return ProgramAnalysis(
            program="FTP",
            step_name=step.name or "",
            summary=summary,
            dataset_events=[],
            notes=notes,
            raw_control=text or None,
        )
