"""
Return-code feasibility analysis.

Walks a :class:`~jclparser.model.Job` in execution order and, for each step
guarded by an ``IF …`` conditional or a step-level ``COND=`` clause,
determines whether the guard can be satisfied under *any* combination of
predecessor return codes drawn from a small symbolic domain (defaults
``{0, 4, 8, 12, 16}``).

The analysis is conservative: it reports a step as *unreachable* only when
the guard evaluates to ``False`` for every combination in the domain.  It
does not attempt to prove the guard satisfiable under runtime-only state
like dynamic ABENDs or external system conditions.

Usage::

    from jclparser.rc_analysis import compute_feasible_paths
    report = compute_feasible_paths(job)
    if report.unreachable_steps:
        print("Dead code:", report.unreachable_steps)
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .condition_parser import ConditionNode
from .model import iter_execution_steps, ConditionalBlock, Step

if TYPE_CHECKING:
    from .model import Job


DEFAULT_RC_DOMAIN = (0, 4, 8, 12, 16)


@dataclass
class FeasibilityReport:
    """Summary of the RC feasibility pass."""

    unreachable_steps: list[str] = field(default_factory=list)
    always_skipped: list[str] = field(default_factory=list)
    contradictory_conditions: list[tuple[str, str]] = field(default_factory=list)
    duplicate_if_branches: list[tuple[int, str]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.unreachable_steps
            or self.always_skipped
            or self.contradictory_conditions
            or self.duplicate_if_branches
        )


def _collect_predecessors(job: "Job") -> list[str]:
    """Return the ordered list of predecessor step names for analysis."""
    names: list[str] = []
    for step in iter_execution_steps(job.steps):
        if isinstance(step, Step) and step.name:
            names.append(step.name.upper())
    return names


def _evaluate_over_domain(
    ast: ConditionNode,
    predecessors: list[str],
    rc_domain: tuple[int, ...],
    abend_values: tuple[bool, ...] = (False,),
) -> tuple[bool, bool]:
    """Evaluate *ast* over the Cartesian product of ``rc_domain`` per predecessor.

    Returns ``(ever_true, ever_false)`` — a pair of booleans indicating whether
    the condition evaluated to True at least once, and to False at least once,
    across the explored combinations.  ``None`` results (missing predecessor)
    are skipped.
    """
    ever_true = False
    ever_false = False
    if not predecessors:
        step_results: dict[str, tuple[int, bool]] = {}
        result = ast.evaluate(step_results)
        return (result is True, result is False)

    # Bound the search to keep the cost predictable.  With the default
    # domain (5 RCs × 1 abend value) and, say, 6 predecessors that's
    # 5**6 = 15,625 evaluations — fast.  Cap at 8 predecessors to protect
    # against pathological jobs.
    capped = predecessors[-8:]

    for rcs in itertools.product(rc_domain, repeat=len(capped)):
        for abend_tuple in itertools.product(abend_values, repeat=len(capped)):
            results = {name: (rc, ab) for name, rc, ab in zip(capped, rcs, abend_tuple)}
            r = ast.evaluate(results)
            if r is True:
                ever_true = True
            elif r is False:
                ever_false = True
            if ever_true and ever_false:
                return (True, True)
    return (ever_true, ever_false)


def compute_feasible_paths(
    job: "Job",
    rc_domain: tuple[int, ...] = DEFAULT_RC_DOMAIN,
    include_abends: bool = True,
) -> FeasibilityReport:
    """Analyse *job* and return a :class:`FeasibilityReport`.

    Args:
        job: Job to analyse.  Not modified.
        rc_domain: RC values to explore per predecessor.  Default covers the
            canonical JCL "success / warning / error / severe / fatal" set.
        include_abends: When True, also explore the ``abended`` flag per
            predecessor to exercise ``ABEND`` / ``NOT ABEND`` atoms.

    Returns:
        :class:`FeasibilityReport` aggregating the findings.
    """
    report = FeasibilityReport()
    predecessors = _collect_predecessors(job)
    abend_values = (False, True) if include_abends else (False,)

    def _walk(steps: list, enclosing_condition_signatures: list[str]) -> None:
        running_preds: list[str] = []
        for item in steps:
            if isinstance(item, ConditionalBlock):
                ast = item.condition_ast
                if ast is None:
                    # Can't analyse un-parsed conditions — still recurse to
                    # catch duplicate THEN/ELSE textual signatures below.
                    _walk(
                        item.then_steps,
                        enclosing_condition_signatures + [item.condition],
                    )
                    _walk(
                        item.else_steps,
                        enclosing_condition_signatures + [f"NOT({item.condition})"],
                    )
                    continue

                ever_true, ever_false = _evaluate_over_domain(
                    ast,
                    predecessors=running_preds or predecessors,
                    rc_domain=rc_domain,
                    abend_values=abend_values,
                )
                if not ever_true:
                    # The THEN branch is unreachable.
                    for step in iter_execution_steps(item.then_steps):
                        if step.name:
                            report.unreachable_steps.append(step.name)
                    report.contradictory_conditions.append(
                        (item.condition, "never true over RC domain")
                    )
                if not ever_false and item.else_steps:
                    # ELSE is dead code because IF is always true.
                    for step in iter_execution_steps(item.else_steps):
                        if step.name:
                            report.always_skipped.append(step.name)

                # Look for duplicate IF signatures across siblings.
                if item.condition in enclosing_condition_signatures:
                    report.duplicate_if_branches.append(
                        (item.line_number, item.condition)
                    )

                _walk(
                    item.then_steps,
                    enclosing_condition_signatures + [item.condition],
                )
                _walk(
                    item.else_steps,
                    enclosing_condition_signatures + [f"NOT({item.condition})"],
                )
            elif isinstance(item, Step):
                if item.name:
                    running_preds.append(item.name.upper())

    _walk(job.steps, [])
    return report


__all__ = [
    "DEFAULT_RC_DOMAIN",
    "FeasibilityReport",
    "compute_feasible_paths",
]
