"""
Base types for the program-profile registry.

A *program profile* analyses a single :class:`~jclparser.model.Step` according
to the semantics of its program — e.g. IDCAMS, SORT, IEBGENER.  Profiles
produce :class:`ProgramAnalysis` reports that summarise what the step will
do (datasets created, deleted, sorted, copied, etc.) without running the
program.

This is a tiny, pluggable framework intended to grow one program at a time.
The built-in profiles live in sibling modules; register new profiles via
:func:`jclparser.program_profiles.registry.register_profile`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..dataset_lifecycle import (
    DatasetEvent,
    _action_from_disp,
    _parse_disp_tokens,
)
from ..utils import control_card_text

if TYPE_CHECKING:
    from ..model import DDStatement, Step


@dataclass
class ProgramAnalysis:
    """Result of analysing one step.

    Attributes:
        program: Program name the profile matched on.
        step_name: Name of the analysed step (or empty string).
        summary: Short human-readable summary.
        dataset_events: DatasetEvents derived from program semantics (may
            duplicate or extend those produced by
            :func:`jclparser.dataset_lifecycle.analyze_dataset_lifecycle`).
        notes: Free-form annotations (e.g. "SORT with INCLUDE filter").
        raw_control: The raw SYSIN text that was parsed (if any).
        invoked_programs: Application programs the step actually runs that are
            named inside the control text rather than on ``EXEC PGM=`` — e.g. a
            program named in a DSN ``RUN PROGRAM(...)`` subcommand or a TSO
            ``CALL`` under IKJEFT01.  Upper-cased and de-duplicated.
    """

    program: str
    step_name: str = ""
    summary: str = ""
    dataset_events: list[DatasetEvent] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw_control: str | None = None
    invoked_programs: list[str] = field(default_factory=list)


class ProgramProfile(ABC):
    """Abstract base for per-program analysis plugins."""

    #: Frozenset of uppercase program names this profile claims to handle.
    program_names: frozenset[str] = frozenset()

    def handles(self, program_name: str | None) -> bool:
        """Return True if this profile should run for *program_name*."""
        if not program_name:
            return False
        return program_name.upper() in self.program_names

    @abstractmethod
    def analyze(self, step: Step) -> ProgramAnalysis:
        """Analyse *step* and return a :class:`ProgramAnalysis`."""
        raise NotImplementedError


def _dd_event(
    step: Step,
    dd_name: str,
    dd,
    *,
    default_status: str,
) -> DatasetEvent:
    """Build a :class:`DatasetEvent` for *dd* from the DISP the JCL states.

    A profile knows what its program *does* with a DD — IEBGENER reads
    SYSUT1 and writes SYSUT2 — but not on what terms, and the two are
    separate facts.  ``//SYSUT2 DD DSN=OUT,DISP=MOD`` appends to an existing
    dataset; reporting it as ``ALLOCATE``/``NEW`` because SYSUT2 is "the
    output" tells a lifecycle consumer the step creates the dataset, which
    is how a dataset written by an earlier step reads as clobbered here.

    So the action and the status both come from the DD's own DISP, through
    the same :func:`_action_from_disp` mapping
    :func:`~jclparser.dataset_lifecycle.analyze_dataset_lifecycle` uses, and
    *default_status* only fills in for a DD that states no DISP at all (or
    states one that has not been substituted yet, e.g. ``DISP=&STATUS``, in
    which case the unresolved token is still reported verbatim).
    """
    status, _, _ = _parse_disp_tokens(dd.disposition)
    status = status or default_status
    action = _action_from_disp(status)
    if action == "UNKNOWN":
        action = _action_from_disp(default_status)
    return DatasetEvent(
        step_name=step.name or "",
        dd_name=dd_name,
        action=action,
        disp_status=status,
        line_number=dd.line_number,
    )


def _concatenation(step: Step, dd_name: str) -> list[DDStatement]:
    """The DD named *dd_name* and the unnamed DDs concatenated to it.

    A concatenation is coded as a named DD followed by DDs with a blank
    name field; it ends at the next named DD.
    """
    members: list[DDStatement] = []
    current: str | None = None
    for dd in step.dd_statements:
        if dd.name:
            current = dd.name
        if current == dd_name:
            members.append(dd)
    return members


def _sysin_text(step: Step, *, card_images: bool = False) -> str | None:
    """Return the inline data from the step's SYSIN DD, or None if absent.

    The records are cut to columns 1-71 (:func:`control_card_text`) unless
    *card_images* is set, for a reader that handles columns 72-80 itself.
    """
    dd = step.get_dd("SYSIN")
    if dd is None or not dd.inline_data:
        return None
    return dd.inline_data if card_images else control_card_text(dd.inline_data)


__all__ = [
    "ProgramAnalysis",
    "ProgramProfile",
    "_concatenation",
    "_dd_event",
    "_sysin_text",
]
