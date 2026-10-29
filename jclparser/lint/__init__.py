"""JCL lint package.

See :mod:`jclparser.lint.base` for the :class:`LintRule` interface,
:mod:`jclparser.lint.rules` for the built-in rules, and
:mod:`jclparser.lint.runner` for :func:`lint_job` and the SARIF renderer,
:mod:`jclparser.lint.config` for TOML configuration and
:mod:`jclparser.lint.suppress` for ``//* jcl-lint: disable=`` comments.
"""

from .base import LintRule
from .config import (
    LintConfig,
    LintConfigError,
    find_lint_config,
    lint_config_from_mapping,
    load_lint_config,
)
from .rules import BUILTIN_RULES
from .runner import (
    PARSE_ERROR_CODE,
    all_rules,
    lint_job,
    register_rule,
    to_sarif,
    to_sarif_files,
    unregister_rule,
)
from .suppress import Suppressions, parse_suppressions

__all__ = [
    "BUILTIN_RULES",
    "PARSE_ERROR_CODE",
    "LintConfig",
    "LintConfigError",
    "LintRule",
    "Suppressions",
    "all_rules",
    "find_lint_config",
    "lint_config_from_mapping",
    "lint_job",
    "load_lint_config",
    "parse_suppressions",
    "register_rule",
    "to_sarif",
    "to_sarif_files",
    "unregister_rule",
]
