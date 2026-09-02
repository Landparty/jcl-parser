"""Program-profile registry: per-utility static analysis for JCL steps.

See :mod:`jclparser.program_profiles.base` for the :class:`ProgramProfile`
interface and :mod:`jclparser.program_profiles.registry` for registration
and dispatch.
"""

from .base import ProgramAnalysis, ProgramProfile
from .registry import (
    analyze_job,
    analyze_step,
    get_profile,
    register_profile,
)

__all__ = [
    "ProgramAnalysis",
    "ProgramProfile",
    "analyze_job",
    "analyze_step",
    "get_profile",
    "register_profile",
]
