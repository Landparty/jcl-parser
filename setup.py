"""Build script for the closed-source PyPI release build.

A stock ``pip install .`` / ``pip install -e .`` builds no extensions at
all -- jclparser ships as plain Python for normal development, exactly as
before this file existed.

Closed-source release build (used only by release CI, never local dev):
    JCLPARSER_CLOSED_SOURCE=1
Cythonizes every jclparser/**/*.py module (except __init__.py/__main__.py,
which stay plain Python shims) and excludes every compiled module's .py
source from the built distribution. Mirrors the cobol-parser sibling repo's
setup.py -- see that repo's
docs/superpowers/specs/2026-08-14-pypi-closed-source-release-design.md for
the design rationale this was copied from.
"""

import os
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.extension import Extension

_PKG = "jclparser"
_CLOSED_SOURCE_ENV = "JCLPARSER_CLOSED_SOURCE"
_REPO_ROOT = Path(__file__).resolve().parent

# File names that must stay plain .py source even in a closed-source build.
#
# __init__.py: the whole strategy assumes package __init__ files are thin
#   re-export stubs with no business logic of their own -- true for
#   jclparser's package __init__ files.
# __main__.py: runpy needs a code object to execute `python -m jclparser`,
#   and extension-module loaders return None from get_code(), which fails
#   with an opaque "No code object available". It is a thin shim over
#   jclparser.cli:main, so shipping it as source discloses nothing.
# profiling.py: ProfilerContext wraps stdlib cProfile, which records calls
#   via sys.setprofile -- a hook the CPython bytecode interpreter fires on
#   Python-level call/return events. A Cython-compiled function runs as
#   direct C code and does not dispatch through that interpreter loop for
#   its own body, so a compiled ProfilerContext.__enter__/__exit__ silently
#   collects zero samples (pstats.Stats then raises TypeError: "Cannot
#   create ... from <cProfile.Profile ...>" -- caught by
#   tests/unit/test_profiling.py, which is exactly why this module is
#   excluded rather than assumed fine). Keeping it plain Python trades a
#   small amount of source disclosure (a stdlib cProfile/tracemalloc
#   wrapper, not JCL-parsing logic) for a profiler that actually profiles.
_UNCOMPILED_FILENAMES = frozenset({"__init__.py", "__main__.py", "profiling.py"})


def _closed_source_enabled() -> bool:
    return os.environ.get(_CLOSED_SOURCE_ENV) == "1"


def _iter_closed_source_py_files():
    """Yield (dotted.module.name, relative/path.py) for every jclparser
    module that should be compiled and stripped of its .py source, i.e.
    everything except the _UNCOMPILED_FILENAMES shims."""
    pkg_dir = _REPO_ROOT / _PKG
    for path in sorted(pkg_dir.rglob("*.py")):
        if path.name in _UNCOMPILED_FILENAMES:
            continue
        rel = path.relative_to(_REPO_ROOT)
        dotted = ".".join(rel.with_suffix("").parts)
        yield dotted, str(rel)


class _ClosedSourceBuildPy(_build_py):
    """Only copy the _UNCOMPILED_FILENAMES shims -- every other .py module has
    a compiled extension twin (see _iter_closed_source_py_files) and must not
    ship as readable source in the built distribution."""

    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        return [
            (pkg, mod, file)
            for (pkg, mod, file) in modules
            if os.path.basename(file) in _UNCOMPILED_FILENAMES
        ]


def _build_ext_modules() -> list:
    if not _closed_source_enabled():
        return []

    from Cython.Build import cythonize

    closed_source_extensions = [
        Extension(dotted, [rel]) for dotted, rel in _iter_closed_source_py_files()
    ]
    return cythonize(
        closed_source_extensions,
        # Closed-source mode cythonizes every jclparser module; translating
        # them one at a time dominates the build. 0 means "serial" to
        # Cython, so clamp to at least 1 when os.cpu_count() returns None.
        nthreads=os.cpu_count() or 1,
        compiler_directives={
            "language_level": "3",
            # Deliberately NOT boundscheck/wraparound/cdivision=False --
            # this is ordinary business-logic code, not a hand-audited
            # hot-path accelerator, so Cython's real defaults
            # (bounds- and wraparound-checked) are correctness-over-speed.
            #
            # annotation_typing=False: without it, Cython enforces PEP 484
            # annotations as runtime C-level argument types, which breaks on
            # any `def f(x: str = ...)`-style overload/default stub that
            # relies on ordinary Python semantics rather than a real C type.
            "annotation_typing": False,
        },
    )


setup(
    ext_modules=_build_ext_modules(),
    cmdclass={"build_py": _ClosedSourceBuildPy} if _closed_source_enabled() else {},
)
