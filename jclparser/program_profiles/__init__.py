"""Program-profile registry: per-utility static analysis for JCL steps.

See :mod:`jclparser.program_profiles.base` for the :class:`ProgramProfile`
interface and :mod:`jclparser.program_profiles.registry` for registration
and dispatch.
"""

from .base import ProgramProfile, ProgramAnalysis
from .registry import (
    register_profile,
    get_profile,
    analyze_step,
    analyze_job,
)

__all__ = [
    "ProgramProfile",
    "ProgramAnalysis",
    "register_profile",
    "get_profile",
    "analyze_step",
    "analyze_job",
]
