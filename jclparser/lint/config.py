"""Configuration for the lint runner.

Besides the :class:`LintConfig` dataclass, this module reads a lint
configuration from TOML: the ``[tool.jcl-parser.lint]`` table of a
``pyproject.toml`` (found with :func:`find_lint_config`), or the top level of
any other ``.toml`` file::

    [tool.jcl-parser.lint]
    select = ["JCL-LINT-001", "JCL-LINT-007"]   # default: every rule
    ignore = ["JCL-LINT-002"]
    critical-datasets = ["PROD.", ".MASTER."]
    fail-on = "warning"                         # info (default) | warning | error

    [tool.jcl-parser.lint.severity]
    "JCL-LINT-004" = "warning"
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import ErrorSeverity

#: How severe each :class:`ErrorSeverity` is, for :attr:`LintConfig.fail_on`.
SEVERITY_RANK: dict[ErrorSeverity, int] = {
    ErrorSeverity.INFO: 0,
    ErrorSeverity.WARNING: 1,
    ErrorSeverity.ERROR: 2,
}


@dataclass
class LintConfig:
    """User-facing lint configuration.

    Attributes:
        enabled: Set of rule codes to run.  Empty set means "run every
            registered rule" (the default).
        disabled: Set of rule codes to skip.  Takes precedence over
            :attr:`enabled`.
        severities: Per-rule severity override map, e.g.
            ``{"JCL-LINT-002": ErrorSeverity.INFO}``.
        critical_dataset_patterns: Dataset-name fragments (uppercased
            substring match) that mark a dataset as *critical* for rule
            JCL-LINT-003.  Example: ``["PROD.", ".MASTER."]``.
        fail_on: The lowest severity that makes the CLI exit 1.
            :func:`~jclparser.lint.runner.lint_job` itself ignores it.
    """

    enabled: set[str] = field(default_factory=set)
    disabled: set[str] = field(default_factory=set)
    severities: dict[str, ErrorSeverity] = field(default_factory=dict)
    critical_dataset_patterns: list[str] = field(default_factory=list)
    fail_on: ErrorSeverity = ErrorSeverity.INFO

    def should_run(self, code: str) -> bool:
        if code in self.disabled:
            return False
        if not self.enabled:
            return True
        return code in self.enabled

    def fails(self, severity: ErrorSeverity) -> bool:
        """True if a finding of *severity* reaches :attr:`fail_on`."""
        return SEVERITY_RANK[severity] >= SEVERITY_RANK[self.fail_on]


class LintConfigError(ValueError):
    """A lint configuration file or table that cannot be used."""


def parse_severity(value: object, where: str) -> ErrorSeverity:
    """The :class:`ErrorSeverity` named *value* (``"info"``, ``"warning"``,
    ``"error"``, any case); *where* names the setting in the error."""
    if isinstance(value, str):
        try:
            return ErrorSeverity(value.lower())
        except ValueError:
            pass
    raise LintConfigError(
        f"{where}: expected 'info', 'warning' or 'error', got {value!r}"
    )


def _codes(value: object, where: str) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise LintConfigError(f"{where}: expected a list of rule codes")
    return {v.upper() for v in value}


def lint_config_from_mapping(data: Mapping[str, Any]) -> LintConfig:
    """A :class:`LintConfig` from the keys of a ``[tool.jcl-parser.lint]``
    table; an unknown key raises :class:`LintConfigError`."""
    known = {"select", "ignore", "severity", "critical-datasets", "fail-on"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise LintConfigError(f"unknown lint setting(s): {', '.join(unknown)}")
    config = LintConfig()
    if "select" in data:
        config.enabled = _codes(data["select"], "select")
    if "ignore" in data:
        config.disabled = _codes(data["ignore"], "ignore")
    severity = data.get("severity", {})
    if not isinstance(severity, Mapping):
        raise LintConfigError("severity: expected a table of code = severity")
    config.severities = {
        code.upper(): parse_severity(value, f"severity.{code}")
        for code, value in severity.items()
    }
    patterns = data.get("critical-datasets", [])
    if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
        raise LintConfigError("critical-datasets: expected a list of strings")
    config.critical_dataset_patterns = list(patterns)
    if "fail-on" in data:
        config.fail_on = parse_severity(data["fail-on"], "fail-on")
    return config


def _load_toml(path: Path) -> dict[str, Any]:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover - exercised on Python 3.10 only
        try:
            import tomli as tomllib  # type: ignore[import-not-found]
        except ImportError as exc:
            raise LintConfigError(
                f"{path}: reading TOML on Python 3.10 needs the 'tomli' package"
            ) from exc
    try:
        with path.open("rb") as handle:
            data: dict[str, Any] = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise LintConfigError(f"{path}: {exc}") from exc
    return data


def _pyproject_table(data: Mapping[str, Any]) -> Mapping[str, Any] | None:
    tool = data.get("tool", {})
    section = tool.get("jcl-parser", {}) if isinstance(tool, Mapping) else {}
    table = section.get("lint") if isinstance(section, Mapping) else None
    return table if isinstance(table, Mapping) else None


def load_lint_config(path: str | Path) -> LintConfig:
    """Read the lint configuration in *path*.

    A ``pyproject.toml`` contributes its ``[tool.jcl-parser.lint]`` table
    (none means the defaults); any other file is the table itself.
    """
    path = Path(path)
    data = _load_toml(path)
    if path.name == "pyproject.toml":
        table = _pyproject_table(data)
        return lint_config_from_mapping(table or {})
    return lint_config_from_mapping(data)


def find_lint_config(start: str | Path) -> Path | None:
    """The nearest ``pyproject.toml`` with a ``[tool.jcl-parser.lint]`` table,
    looking in *start* (a file's directory when *start* is a file) and then
    each parent directory; ``None`` if there is none."""
    here = Path(start).resolve()
    if not here.is_dir():
        here = here.parent
    for directory in (here, *here.parents):
        candidate = directory / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            if _pyproject_table(_load_toml(candidate)) is not None:
                return candidate
        except LintConfigError:
            continue
    return None


__all__ = [
    "SEVERITY_RANK",
    "LintConfig",
    "LintConfigError",
    "find_lint_config",
    "lint_config_from_mapping",
    "load_lint_config",
    "parse_severity",
]
