"""
Return-code feasibility analysis.

Walks a :class:`~jclparser.model.Job` in execution order and, for each
``IF …`` conditional, determines whether the condition can be satisfied under
*any* combination of predecessor return codes.  Each step's return codes are
drawn from one representative per class of the constants the condition
compares it against (preferring values of the ``{0, 4, 8, 12, 16}`` default
domain), so the search is exact over 0..4095 -- a range such as
``RC GT 4 AND RC LT 8`` is explored.  The predecessors of an
``IF`` are the steps that precede it in execution order; a step that may not
run (it sits inside an ``IF`` branch or carries ``COND=``) is also explored as
"not run" (:data:`~jclparser.condition_parser.NOT_RUN`), so ``STEP.RUN`` /
``NOT STEP.RUN`` and tests of a skipped step's RC are judged correctly.  Step-level ``COND=``
guards themselves are not analysed.

The analysis is conservative: it reports a step as *unreachable* only when
the guard evaluates to ``False`` for every combination in the domain.  A
condition whose search would exceed :data:`MAX_COMBINATIONS` is not analysed
and is listed in :attr:`FeasibilityReport.unanalysed_conditions` instead.  It
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
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .condition_parser import (
    NOT_RUN,
    AbendCondition,
    ConditionNode,
    ReturnCodeCondition,
    StepResult,
)
from .model import ConditionalBlock, Step, iter_execution_steps

if TYPE_CHECKING:
    from .model import Job


DEFAULT_RC_DOMAIN = (0, 4, 8, 12, 16)

#: Highest return code a z/OS step can end with.
_MAX_RC = 4095

#: Stands for every predecessor a condition does not name (not a valid step
#: name, so it cannot collide with one).
_ANONYMOUS_PREDECESSOR = "*OTHER*"

#: Upper bound on the outcome combinations explored for one condition.  The
#: product grows with the states of *every* named step (RC classes x ABEND x
#: not-run), so capping the step count alone still let a condition with a
#: few constants per step take hours (issue #65).  At a few microseconds per
#: evaluation this keeps one condition to about a second; a larger search is
#: skipped and recorded in :attr:`FeasibilityReport.unanalysed_conditions`.
MAX_COMBINATIONS = 250_000


@dataclass
class FeasibilityReport:
    """Summary of the RC feasibility pass."""

    unreachable_steps: list[str] = field(default_factory=list)
    always_skipped: list[str] = field(default_factory=list)
    contradictory_conditions: list[tuple[str, str]] = field(default_factory=list)
    duplicate_if_branches: list[tuple[int, str]] = field(default_factory=list)
    #: ``(condition, reason)`` for each IF whose search was too large to run.
    #: Nothing is claimed about those branches; they are not findings, so
    #: :meth:`is_empty` ignores them.
    unanalysed_conditions: list[tuple[str, str]] = field(default_factory=list)

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

    def _walk(items: list[Step | ConditionalBlock], nested: bool) -> None:
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


def _collect_tested_attributes(
    ast: ConditionNode,
) -> tuple[dict[str | None, set[int]], set[str | None]]:
    """Return what *ast* tests about each step (``None`` = unqualified atom).

    The first map gives, per step, the constants its ``RC`` is compared
    against; the set names the steps whose ``ABEND`` flag is tested.
    """
    constants: dict[str | None, set[int]] = {}
    abends: set[str | None] = set()

    def _walk(node: ConditionNode) -> None:
        key = getattr(node, "step_name", None)
        key = key.upper() if isinstance(key, str) and key else None
        if isinstance(node, ReturnCodeCondition):
            constants.setdefault(key, set()).add(node.value)
        elif isinstance(node, AbendCondition):
            abends.add(key)
        for attr in ("operand", "left", "right"):
            child = getattr(node, attr, None)
            if isinstance(child, ConditionNode):
                _walk(child)

    _walk(ast)
    return constants, abends


def _representative_rcs(
    rc_domain: tuple[int, ...], values: set[int]
) -> tuple[int, ...]:
    """One RC per class of return codes that compare alike against *values*.

    The constants split 0..4095 into the constants themselves and the gaps
    between them; every RC in one class gives every comparison against the
    constants the same outcome, so one representative per class is exact
    (a range test such as ``RC GT 4 AND RC LT 8`` is satisfiable here
    whenever it is satisfiable at all) and costs at most ``2k + 1`` values
    for ``k`` constants.  A gap is represented by its smallest *rc_domain*
    value when it has one, else by its lower bound.
    """
    classes: list[tuple[int, int]] = []
    low = 0
    for c in sorted(v for v in values if 0 <= v <= _MAX_RC):
        if low < c:
            classes.append((low, c - 1))
        classes.append((c, c))
        low = c + 1
    if low <= _MAX_RC:
        classes.append((low, _MAX_RC))
    preferred = sorted(rc_domain)
    return tuple(
        next((rc for rc in preferred if lo <= rc <= hi), lo) for lo, hi in classes
    )


def _evaluate_over_domain(
    ast: ConditionNode,
    predecessors: list[str],
    rc_domain: tuple[int, ...],
    abend_values: tuple[bool, ...] = (False,),
    optional_steps: frozenset[str] = frozenset(),
    max_combinations: int = MAX_COMBINATIONS,
) -> tuple[bool, bool, bool] | int:
    """Evaluate *ast* over the product of every predecessor's possible outcomes.

    Returns ``(ever_true, ever_false, ever_unknown)`` — a triple of booleans
    indicating whether the condition evaluated to True, False, or ``None``
    (unknown) at least once across the explored combinations.  Callers use
    the ``ever_unknown`` flag to avoid flagging a branch as unreachable when
    every evaluation was indeterminate.

    When the product of the per-step outcome counts exceeds
    *max_combinations*, nothing is evaluated and that product (an ``int``)
    is returned instead, so the caller can report the condition as not
    analysed rather than guess.
    """
    ever_true = False
    ever_false = False
    ever_unknown = False

    # Always include the steps explicitly named by the condition (even one
    # that is not a predecessor): a named step missing from the results
    # makes its tests unknown.
    referenced = _collect_referenced_steps(ast)

    if not predecessors and not referenced:
        step_results: dict[str, StepResult] = {}
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
    # Each step's RC only meets the constants it is compared against (and,
    # through the unqualified ``RC`` = highest RC, the unqualified ones), so
    # its domain is one representative per class of those constants rather
    # than a fixed list.  A dimension the condition never tests for a step
    # (its RC, its ABEND flag) is pinned to a single value -- together these
    # keep the product small when a condition tests several steps.
    constants, abends = _collect_tested_attributes(ast)
    unqualified = constants.get(None)

    def _states(name: str) -> list[StepResult]:
        if name in constants or unqualified is not None:
            domain = _representative_rcs(
                rc_domain, constants.get(name, set()) | (unqualified or set())
            )
        else:
            domain = rc_domain[:1]
        flags = abend_values if name in abends or None in abends else (False,)
        states: list[StepResult] = [(rc, ab) for rc in domain for ab in flags]
        # A step that may not have run (inside an IF branch, or with COND=)
        # is also explored as not run, which makes ``STEP.RUN`` and any
        # ``STEP.RC`` / ``STEP.ABEND`` test of it false.
        if name in optional_steps:
            states.append(NOT_RUN)
        return states

    # Bound the search by its size, not by the number of steps: dropping a
    # named step made its tests unknown (issue #61), and a step count cap
    # still allowed (2k + 1) * 2 * ... states per step (issue #65).
    per_step = [_states(name) for name in names]
    combinations = math.prod(len(states) for states in per_step)
    if combinations > max_combinations:
        return combinations
    for states in itertools.product(*per_step):
        results = dict(zip(names, states))
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


def compute_feasible_paths(  # noqa: C901 -- complexity baseline, split when touched
    job: Job,
    rc_domain: tuple[int, ...] = DEFAULT_RC_DOMAIN,
    include_abends: bool = True,
) -> FeasibilityReport:
    """Analyse *job* and return a :class:`FeasibilityReport`.

    Args:
        job: Job to analyse.  Not modified.
        rc_domain: Preferred RC values.  Each predecessor is explored with one
            RC per class of the constants the condition compares it against,
            taken from this domain when the class contains one of its values
            (else the class's lowest RC); a predecessor whose RC is never
            tested uses its first value.  Default covers the canonical JCL
            "success / warning / error / severe / fatal" set.
        include_abends: When True, also explore the ``abended`` flag per
            predecessor to exercise ``ABEND`` / ``NOT ABEND`` atoms.

    Returns:
        :class:`FeasibilityReport` aggregating the findings.
    """
    report = FeasibilityReport()
    optional_steps = _collect_optional_steps(job)
    # Not a ternary: Cython's type inference rejects unifying two
    # differently-sized tuple literals in one conditional expression, and
    # this keeps the module compilable.
    abend_values: tuple[bool, ...]
    if include_abends:
        abend_values = (False, True)
    else:
        abend_values = (False,)

    def _walk(  # noqa: C901 -- complexity baseline, split when touched
        steps: list[Step | ConditionalBlock],
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

                outcome = _evaluate_over_domain(
                    ast,
                    predecessors=running_preds,
                    rc_domain=rc_domain,
                    abend_values=abend_values,
                    optional_steps=optional_steps,
                )
                if isinstance(outcome, int):
                    # Too many combinations to search: claim nothing.
                    report.unanalysed_conditions.append(
                        (
                            item.condition,
                            (
                                f"not analysed: {outcome} outcome combinations "
                                f"exceed the limit of {MAX_COMBINATIONS}"
                            ),
                        )
                    )
                    ever_true, ever_false, ever_unknown = False, False, True
                else:
                    ever_true, ever_false, ever_unknown = outcome
                # Only mark THEN as unreachable / ELSE as dead code when
                # every evaluation was concrete and *none* of them produced
                # the relevant outcome.  An unknown (None) evaluation could
                # be either outcome -- typically a named step left out of
                # the bounded search -- so any unknown means "say nothing";
                # treating it as false reported reachable branches as dead
                # (issue #61).
                has_concrete = (ever_true or ever_false) and not ever_unknown
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
    "MAX_COMBINATIONS",
    "FeasibilityReport",
    "compute_feasible_paths",
]
