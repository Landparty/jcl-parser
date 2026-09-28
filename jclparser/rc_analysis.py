"""
Return-code feasibility analysis.

Walks a :class:`~jclparser.model.Job` in execution order and, for each
``IF …`` conditional, determines whether the condition can be satisfied under
*any* combination of predecessor return codes drawn from a small symbolic
domain (defaults ``{0, 4, 8, 12, 16}``).  The predecessors of an ``IF`` are
the steps that precede it in execution order; a step that may not run (it sits
inside an ``IF`` branch or carries ``COND=``) is also explored as "not run", so
``STEP.RUN`` / ``NOT STEP.RUN`` are judged correctly.  Step-level ``COND=``
guards themselves are not analysed.

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
from .model import ConditionalBlock, Step, iter_execution_steps

if TYPE_CHECKING:
    from .model import Job


DEFAULT_RC_DOMAIN = (0, 4, 8, 12, 16)

#: Stands for every predecessor a condition does not name (not a valid step
#: name, so it cannot collide with one).
_ANONYMOUS_PREDECESSOR = "*OTHER*"


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


def _collect_optional_steps(job: Job) -> frozenset[str]:
    """Names of steps that may not run: inside an IF branch, or with ``COND=``."""
    names: set[str] = set()

    def _walk(items: list, nested: bool) -> None:
        for item in items:
            if isinstance(item, ConditionalBlock):
                _walk(item.then_steps, True)
                _walk(item.else_steps, True)
            elif isinstance(item, Step) and item.name:
                if nested or item.parameters.get("COND") is not None:
                    names.add(item.name.upper())

    _walk(job.steps, False)
    return frozenset(names)


def _collect_referenced_steps(ast: ConditionNode) -> set[str]:
    """Walk *ast* and return the set of uppercase step names it references.

    ``None`` step_name (meaning "all steps so far") is not included.  This is used
    by :func:`_evaluate_over_domain` to guarantee the evaluation domain
    covers every predecessor actually named in the condition, so the
    conservative "unknown" outcome only fires when the condition truly
    depends on runtime state we can't model.
    """
    referenced: set[str] = set()

    def _walk(node: ConditionNode) -> None:
        sn = getattr(node, "step_name", None)
        if isinstance(sn, str) and sn:
            referenced.add(sn.upper())
        for attr in ("operand", "left", "right"):
            child = getattr(node, attr, None)
            if isinstance(child, ConditionNode):
                _walk(child)

    _walk(ast)
    return referenced


def _evaluate_over_domain(
    ast: ConditionNode,
    predecessors: list[str],
    rc_domain: tuple[int, ...],
    abend_values: tuple[bool, ...] = (False,),
    optional_steps: frozenset[str] = frozenset(),
) -> tuple[bool, bool, bool]:
    """Evaluate *ast* over the Cartesian product of ``rc_domain`` per predecessor.

    Returns ``(ever_true, ever_false, ever_unknown)`` — a triple of booleans
    indicating whether the condition evaluated to True, False, or ``None``
    (unknown) at least once across the explored combinations.  Callers use
    the ``ever_unknown`` flag to avoid flagging a branch as unreachable when
    every evaluation was indeterminate (typically because a referenced step
    was outside the bounded predecessor window).
    """
    ever_true = False
    ever_false = False
    ever_unknown = False

    # Always include the steps explicitly named by the condition — otherwise
    # a deep-enough job could push a referenced predecessor outside the
    # 8-step cap and produce all-None results that would be misread as
    # "never true".
    referenced = _collect_referenced_steps(ast)

    if not predecessors and not referenced:
        step_results: dict[str, tuple[int, bool]] = {}
        result = ast.evaluate(step_results)
        return (result is True, result is False, result is None)

    # Predecessors the condition does not name are only seen through the
    # unqualified atoms (``RC`` = highest RC, ``ABEND`` = any abended,
    # ``RUN`` = any ran), and every combination of those is already produced
    # by a single representative step.  Folding them into one keeps the
    # product exponential only in the steps the condition names — enumerating
    # them all made an 8-step job take minutes.  The representative may be
    # "not run" only when every step it stands for may not run.
    anonymous = [name for name in predecessors if name not in referenced]
    names = sorted(referenced)
    if anonymous:
        names.append(_ANONYMOUS_PREDECESSOR)
        if all(name in optional_steps for name in anonymous):
            optional_steps = optional_steps | {_ANONYMOUS_PREDECESSOR}
    # Bound the search to keep the cost predictable: with the default domain
    # (5 RCs × 2 abend values) 8 steps are 10**8 evaluations.
    capped = names[-8:]

    ran_states: list[tuple[int, bool] | None] = [
        (rc, ab) for rc in rc_domain for ab in abend_values
    ]
    # A step that may not have run (inside an IF branch, or with COND=) is
    # also explored as absent from the results, which is what makes
    # ``STEP.RUN`` false for it.
    per_step = [
        ran_states + [None] if name in optional_steps else ran_states for name in capped
    ]
    for states in itertools.product(*per_step):
        results = {
            name: state for name, state in zip(capped, states) if state is not None
        }
        r = ast.evaluate(results)
        if r is True:
            ever_true = True
        elif r is False:
            ever_false = True
        else:
            ever_unknown = True
        if ever_true and ever_false:
            return (True, True, ever_unknown)
    return (ever_true, ever_false, ever_unknown)


def compute_feasible_paths(
    job: Job,
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
    optional_steps = _collect_optional_steps(job)
    # Not a ternary: Cython's type inference tries to unify the two
    # differently-sized tuple literals of a single conditional expression
    # into one C-level type and rejects it (this module is cythonized for
    # the closed-source PyPI release build -- see setup.py).
    if include_abends:
        abend_values = (False, True)
    else:
        abend_values = (False,)

    def _walk(
        steps: list,
        enclosing_condition_signatures: list[str],
        preds_before: list[str],
    ) -> list[str]:
        """Walk *steps*; return the predecessor list after the last of them.

        *preds_before* are the steps that precede *steps* in execution order
        (for a THEN/ELSE branch: everything before the IF), so an IF is never
        evaluated against a step that runs after it.
        """
        running_preds = list(preds_before)
        for item in steps:
            if isinstance(item, ConditionalBlock):
                ast = item.condition_ast
                if ast is None:
                    # Can't analyse un-parsed conditions — still recurse to
                    # catch duplicate THEN/ELSE textual signatures below.
                    running_preds = _walk_branches(
                        item, enclosing_condition_signatures, running_preds
                    )
                    continue

                ever_true, ever_false, _ever_unknown = _evaluate_over_domain(
                    ast,
                    predecessors=running_preds,
                    rc_domain=rc_domain,
                    abend_values=abend_values,
                    optional_steps=optional_steps,
                )
                # Only mark THEN as unreachable / ELSE as dead code when we
                # have at least one concrete evaluation and *none* of them
                # produced the relevant outcome.  When every evaluation was
                # unknown (None), the condition depends on runtime state we
                # can't model — conservatively say nothing.
                has_concrete = ever_true or ever_false
                if has_concrete and not ever_true:
                    for step in iter_execution_steps(item.then_steps):
                        if step.name:
                            report.unreachable_steps.append(step.name)
                    report.contradictory_conditions.append(
                        (item.condition, "never true over RC domain")
                    )
                if has_concrete and not ever_false and item.else_steps:
                    for step in iter_execution_steps(item.else_steps):
                        if step.name:
                            report.always_skipped.append(step.name)

                # Look for duplicate IF signatures across siblings.
                if item.condition in enclosing_condition_signatures:
                    report.duplicate_if_branches.append(
                        (item.line_number, item.condition)
                    )

                running_preds = _walk_branches(
                    item, enclosing_condition_signatures, running_preds
                )
            elif isinstance(item, Step):
                if item.name:
                    running_preds.append(item.name.upper())
        return running_preds

    def _walk_branches(
        block: ConditionalBlock, signatures: list[str], preds_before: list[str]
    ) -> list[str]:
        then_preds = _walk(
            block.then_steps, signatures + [block.condition], preds_before
        )
        else_preds = _walk(
            block.else_steps, signatures + [f"NOT({block.condition})"], preds_before
        )
        # After ENDIF, a step of either branch may have run.
        return list(dict.fromkeys(then_preds + else_preds[len(preds_before) :]))

    _walk(job.steps, [], [])
    return report


__all__ = [
    "DEFAULT_RC_DOMAIN",
    "FeasibilityReport",
    "compute_feasible_paths",
]
