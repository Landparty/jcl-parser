"""Central registry for :class:`ProgramProfile` plugins.

Use :func:`register_profile` to add a custom profile, and
:func:`analyze_step` / :func:`analyze_job` to run all registered profiles
against a step or an entire job.  The built-in profiles are registered
automatically when this module is first imported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ProgramProfile, ProgramAnalysis

if TYPE_CHECKING:
    from ..model import Job, Step


_PROFILES: list[ProgramProfile] = []


def register_profile(profile: ProgramProfile) -> None:
    """Add *profile* to the registry.

    Profiles registered later take precedence over earlier ones for the
    same program name (last-wins).  The registry is a flat list for
    simplicity; duplicate registration of the same profile instance is
    a no-op.
    """
    if profile in _PROFILES:
        return
    _PROFILES.append(profile)


def get_profile(program_name: str | None) -> ProgramProfile | None:
    """Return the most recently registered profile that handles *program_name*.

    Returns ``None`` if no profile matches.
    """
    if not program_name:
        return None
    for prof in reversed(_PROFILES):
        if prof.handles(program_name):
            return prof
    return None


def analyze_step(step: "Step") -> ProgramAnalysis | None:
    """Run the matching profile (if any) against *step*."""
    profile = get_profile(step.program)
    if profile is None:
        return None
    return profile.analyze(step)


def analyze_job(job: "Job") -> list[ProgramAnalysis]:
    """Run all applicable profiles across every step in *job*."""
    from ..model import iter_execution_steps

    results: list[ProgramAnalysis] = []
    for step in iter_execution_steps(job.steps):
        analysis = analyze_step(step)
        if analysis is not None:
            results.append(analysis)
    return results


# ---------------------------------------------------------------------------
# Register built-in profiles at import time
# ---------------------------------------------------------------------------


def _register_builtins() -> None:
    from .iefbr14 import IEFBR14Profile
    from .idcams import IDCAMSProfile
    from .iebgener import IEBGENERProfile, IEBCOPYProfile, ICEGENERProfile
    from .sort import SortProfile
    from .ikjeft01 import IKJEFT01Profile
    from .db2_batch import DB2BatchProfile
    from .dfsrrc00 import DFSRRC00Profile
    from .icetool import ICETOOLProfile
    from .adrdssu import ADRDSSUProfile
    from .iehlist import IEHLISTProfile
    from .iehprogm import IEHPROGMProfile
    from .iebupdte import IEBUPDTEProfile
    from .iebptpch import IEBPTPCHProfile
    from .iebdg import IEBDGProfile
    from .binder import BinderProfile
    from .compilers import CompilerProfile
    from .irxjcl import IRXJCLProfile
    from .ftp import FTPProfile

    register_profile(IEFBR14Profile())
    register_profile(IDCAMSProfile())
    register_profile(IEBGENERProfile())
    register_profile(IEBCOPYProfile())
    register_profile(ICEGENERProfile())
    register_profile(SortProfile())
    register_profile(IKJEFT01Profile())
    register_profile(DB2BatchProfile())
    register_profile(DFSRRC00Profile())
    register_profile(ICETOOLProfile())
    register_profile(ADRDSSUProfile())
    register_profile(IEHLISTProfile())
    register_profile(IEHPROGMProfile())
    register_profile(IEBUPDTEProfile())
    register_profile(IEBPTPCHProfile())
    register_profile(IEBDGProfile())
    register_profile(BinderProfile())
    register_profile(CompilerProfile())
    register_profile(IRXJCLProfile())
    register_profile(FTPProfile())


_register_builtins()


__all__ = [
    "register_profile",
    "get_profile",
    "analyze_step",
    "analyze_job",
]
