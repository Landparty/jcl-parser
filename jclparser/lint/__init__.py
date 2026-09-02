"""JCL lint package.

See :mod:`jclparser.lint.base` for the :class:`LintRule` interface,
:mod:`jclparser.lint.rules` for the built-in rules, and
:mod:`jclparser.lint.runner` for :func:`lint_job` and the SARIF renderer.
"""

from .base import LintRule
from .config import LintConfig
from .rules import BUILTIN_RULES
from .runner import (
    all_rules,
    lint_job,
    register_rule,
    to_sarif,
    unregister_rule,
)

__all__ = [
    "BUILTIN_RULES",
    "LintConfig",
    "LintRule",
    "all_rules",
    "lint_job",
    "register_rule",
    "to_sarif",
    "unregister_rule",
]
