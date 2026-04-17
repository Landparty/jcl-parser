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

from ..dataset_lifecycle import DatasetEvent

if TYPE_CHECKING:
    from ..model import Step


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
    """

    program: str
    step_name: str = ""
    summary: str = ""
    dataset_events: list[DatasetEvent] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw_control: str | None = None


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
    def analyze(self, step: "Step") -> ProgramAnalysis:
        """Analyse *step* and return a :class:`ProgramAnalysis`."""
        raise NotImplementedError


def _sysin_text(step: "Step") -> str | None:
    """Return the inline data from the step's SYSIN DD, or None if absent."""
    dd = step.get_dd("SYSIN")
    if dd is None or not dd.inline_data:
        return None
    return dd.inline_data


__all__ = ["ProgramAnalysis", "ProgramProfile", "_sysin_text"]
