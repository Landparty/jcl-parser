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
run (it sits inside an ``IF`` branch or carries ``COND=``, or -- when abends
are explored -- follows a step that may abend, i.e. any step but the first) is
also explored as "not run" (:data:`~jclparser.condition_parser.NOT_RUN`), so
``STEP.RUN`` / ``NOT STEP.RUN`` and tests of a skipped step's RC are judged
correctly.  Step-level ``COND=`` guards themselves are not analysed.

The analysis is conservative: it reports a step as *unreachable* only when
the guard evaluates to ``False`` for every combination in the domain.  A
condition whose search would exceed :data:`MAX_COMBINATIONS` is not analysed
and is listed in :attr:`FeasibilityReport.unanalysed_conditions` instead; so
is, with ``include_abends=False``, a condition testing ``RUN`` or ``ABEND``,
whose outcome depends on the abends that mode does not model.  It does not
attempt to prove the guard satisfiable under runtime-only state like external
system conditions.

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
    AndCondition,
    ConditionNode,
    NotCondition,
    ReturnCodeCondition,
    RunCondition,
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
    #: ``(condition, reason)`` for each IF that was not judged: its search
    #: was too large to run, or (with ``include_abends=False``) it tests
    #: ``RUN`` / ``ABEND``.  Nothing is claimed about those branches; they are not findings, so
    #: :meth:`is_empty` ignores them.
    unanalysed_conditions: list[tuple[str, str]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.unreachable_steps
            or self.always_skipped
            or self.contradictory_conditions
            or self.duplicate_if_branches
        )


#: Suffix marking a PROC call in the optional-step set: every
#: ``stepname.procstep`` under it may not run (see :func:`_may_not_run`).
_ANY_PROCSTEP = ".*"


def _collect_optional_steps(job: Job, after_abends: bool = False) -> frozenset[str]:
    """Names of steps that may not run: inside an IF branch, or with ``COND=``.

    With *after_abends*, every step after the first in execution order may
    not run as well: any predecessor may abend, and z/OS then bypasses the
    following steps, so ``NOT S1.RUN`` is the classic abend-recovery test
    (issue #86).  Only the first step of the job is certain to run.

    A step that calls a PROC (on a job not yet exploded) is entered as
    ``NAME.*``: the PROC's own steps are not in the job, so whether one of
    them runs (it may carry ``COND=`` or sit in an IF of the PROC) is not
    known, and a ``NAME.PROCSTEP`` test must not assume it ran.
    """
    names: set[str] = set()

    def _walk(items: list[Step | ConditionalBlock], nested: bool) -> None:
        for item in items:
            if isinstance(item, ConditionalBlock):
                _walk(item.then_steps, True)
                _walk(item.else_steps, True)
            elif isinstance(item, Step) and item.name:
                if nested or item.parameters.get("COND") is not None:
                    names.add(item.name.upper())
                if item.is_procedure:
                    names.add(item.name.upper() + _ANY_PROCSTEP)

    _walk(job.steps, False)
    if after_abends:
        names.update(
            step.name.upper()
            for step in itertools.islice(iter_execution_steps(job.steps), 1, None)
            if step.name
        )
    return frozenset(names)


def _may_not_run(name: str, optional_steps: frozenset[str]) -> bool:
    """True when step *name* (``STEP`` or ``STEP.PROCSTEP``) may not run."""
    if name in optional_steps:
        return True
    caller, dot, _ = name.partition(".")
    return bool(dot) and caller + _ANY_PROCSTEP in optional_steps


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
        if _may_not_run(name, optional_steps):
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


def _tests_run_or_abend(ast: ConditionNode) -> bool:
    """True when *ast* contains a ``RUN`` or ``ABEND`` test (any polarity)."""
    if isinstance(ast, (RunCondition, AbendCondition)):
        return True
    return any(
        isinstance(child, ConditionNode) and _tests_run_or_abend(child)
        for child in (getattr(ast, attr, None) for attr in ("operand", "left", "right"))
    )


#: Why an IF testing ``RUN`` / ``ABEND`` is not judged without abends.
_ABENDS_NOT_MODELLED = (
    "not analysed: the condition tests RUN or ABEND, which depend on step "
    "abends, and include_abends=False does not model them"
)


#: An enclosing IF's condition text (``NOT(...)`` for its ELSE branch) and
#: how many steps preceded it in execution order.
_Signature = tuple[str, int]

#: An enclosing IF's parsed condition (wrapped in ``NOT`` for its ELSE
#: branch), or ``None`` when it did not parse, and how many steps preceded it.
_Guard = tuple["ConditionNode | None", int]


def _tests_running_state(ast: ConditionNode) -> bool:
    """True when *ast* has an unqualified ``RC`` / ``ABEND`` / ``RUN`` atom.

    Without a step name, ``RC`` is the highest RC *so far* and ``ABEND`` /
    ``RUN`` cover every step run so far, so the atom's value changes as
    soon as another step runs.
    """
    if isinstance(ast, (ReturnCodeCondition, AbendCondition, RunCondition)):
        return ast.step_name is None
    return any(
        isinstance(child, ConditionNode) and _tests_running_state(child)
        for child in (getattr(ast, attr, None) for attr in ("operand", "left", "right"))
    )


def _stable_guard(guard: ConditionNode, between: set[str]) -> bool:
    """True when nothing that ran since the enclosing IF can change *guard*.

    An unqualified ``RC`` / ``ABEND`` / ``RUN`` atom covers every step run so
    far, and a named step that ran in between was "not run" when the outer
    IF tested it (issue #109 has the same rule for repeated IFs).
    """
    if _tests_running_state(guard):
        return False
    return not any(
        name in between or name.partition(".")[0] in between
        for name in _collect_referenced_steps(guard)
    )


def _repeats_enclosing_if(
    block: ConditionalBlock, signatures: list[_Signature], preds: list[str]
) -> bool:
    """True when *block* re-tests an enclosing IF's condition and nothing
    between the two IFs can change the result.

    The condition text alone is not enough: a step that runs between them
    changes an unqualified ``RC`` / ``ABEND`` / ``RUN`` test, and a named
    step that runs between them changes the tests naming it (issue #109).
    """
    ast = block.condition_ast
    for condition, at_if in signatures:
        if condition != block.condition:
            continue
        between = set(preds[at_if:])
        if not between:
            return True
        if ast is None or _tests_running_state(ast):
            continue
        named = _collect_referenced_steps(ast)
        if not any(
            name in between or name.partition(".")[0] in between for name in named
        ):
            return True
    return False


class _FeasibilityWalker:
    """Walks a job's steps in execution order and judges each IF."""

    def __init__(
        self,
        report: FeasibilityReport,
        rc_domain: tuple[int, ...],
        include_abends: bool,
        optional_steps: frozenset[str],
    ) -> None:
        self.report = report
        self.rc_domain = rc_domain
        self.include_abends = include_abends
        self.optional_steps = optional_steps
        # Not a ternary: Cython's type inference rejects unifying two
        # differently-sized tuple literals in one conditional expression.
        self.abend_values: tuple[bool, ...]
        if include_abends:
            self.abend_values = (False, True)
        else:
            self.abend_values = (False,)

    def walk(
        self,
        steps: list[Step | ConditionalBlock],
        signatures: list[_Signature],
        preds_before: list[str],
        guards: list[_Guard] | None = None,
    ) -> list[str]:
        """Walk *steps*; return the predecessor list after the last of them.

        *preds_before* are the steps that precede *steps* in execution order
        (for a THEN/ELSE branch: everything before the IF), so an IF is never
        evaluated against a step that runs after it.  *signatures* are the
        conditions of the enclosing IFs (an ELSE branch's as ``NOT(...)``),
        *guards* the same parsed: a nested IF only runs when they hold.
        """
        guards = guards or []
        running_preds = list(preds_before)
        for item in steps:
            if isinstance(item, ConditionalBlock):
                # An un-parsed condition can't be analysed, but its branches
                # are still walked for duplicate IF signatures.
                if item.condition_ast is not None:
                    self._judge(
                        item,
                        item.condition_ast,
                        running_preds,
                        self._context(guards, running_preds),
                    )
                    if _repeats_enclosing_if(item, signatures, running_preds):
                        self.report.duplicate_if_branches.append(
                            (item.line_number, item.condition)
                        )
                running_preds = self._walk_branches(
                    item, signatures, running_preds, guards
                )
            elif isinstance(item, Step) and item.name:
                running_preds.append(item.name.upper())
        return running_preds

    def _walk_branches(
        self,
        block: ConditionalBlock,
        signatures: list[_Signature],
        preds_before: list[str],
        guards: list[_Guard],
    ) -> list[str]:
        at_if = len(preds_before)
        ast = block.condition_ast
        then_preds = self.walk(
            block.then_steps,
            [*signatures, (block.condition, at_if)],
            preds_before,
            [*guards, (ast, at_if)],
        )
        else_preds = self.walk(
            block.else_steps,
            [*signatures, (f"NOT({block.condition})", at_if)],
            preds_before,
            [*guards, (NotCondition(ast) if ast is not None else None, at_if)],
        )
        # After ENDIF, a step of either branch may have run.
        return list(dict.fromkeys(then_preds + else_preds[len(preds_before) :]))

    def _context(self, guards: list[_Guard], preds: list[str]) -> ConditionNode | None:
        """The enclosing IFs' conditions that still hold at a nested IF.

        Their conjunction, or ``None`` when none of them can be used: one
        that did not parse, that an intervening step may change
        (:func:`_stable_guard`), or that tests RUN / ABEND when abends are
        not modelled.
        """
        context: ConditionNode | None = None
        for guard, at_if in guards:
            if guard is None or not _stable_guard(guard, set(preds[at_if:])):
                continue
            if not self.include_abends and _tests_run_or_abend(guard):
                continue
            context = guard if context is None else AndCondition(context, guard)
        return context

    def _outcome(
        self, block: ConditionalBlock, ast: ConditionNode, preds: list[str]
    ) -> tuple[bool, bool, bool] | None:
        """``(ever_true, ever_false, ever_unknown)`` for *block*, or ``None``
        (recorded as unanalysed) when nothing may be claimed about it."""
        if not self.include_abends and _tests_run_or_abend(ast):
            # Whether a step ran, or abended, depends on predecessor abends,
            # which are not explored here: ``NOT S1.RUN`` is true when an
            # earlier step abends (issue #86), so judge nothing.
            self.report.unanalysed_conditions.append(
                (block.condition, _ABENDS_NOT_MODELLED)
            )
            return None
        outcome = _evaluate_over_domain(
            ast,
            predecessors=preds,
            rc_domain=self.rc_domain,
            abend_values=self.abend_values,
            optional_steps=self.optional_steps,
        )
        if isinstance(outcome, int):
            # Too many combinations to search: claim nothing.
            self.report.unanalysed_conditions.append(
                (
                    block.condition,
                    (
                        f"not analysed: {outcome} outcome combinations "
                        f"exceed the limit of {MAX_COMBINATIONS}"
                    ),
                )
            )
            return None
        return outcome

    def _judge(
        self,
        block: ConditionalBlock,
        ast: ConditionNode,
        preds: list[str],
        context: ConditionNode | None = None,
    ) -> None:
        outcome = (
            self._outcome(block, ast, preds)
            if context is None
            else self._nested_outcome(block, ast, preds, context)
        )
        if outcome is None:
            return
        ever_true, ever_false, ever_unknown = outcome
        # Only mark THEN as unreachable / ELSE as dead code when every
        # evaluation was concrete and *none* of them produced the relevant
        # outcome.  An unknown (None) evaluation could be either outcome --
        # typically a named step left out of the bounded search -- so any
        # unknown means "say nothing"; treating it as false reported
        # reachable branches as dead (issue #61).
        if ever_unknown or not (ever_true or ever_false):
            return
        if not ever_true:
            self.report.unreachable_steps.extend(
                step.name
                for step in iter_execution_steps(block.then_steps)
                if step.name
            )
            self.report.contradictory_conditions.append(
                (block.condition, "never true over RC domain")
            )
        if not ever_false:
            self.report.always_skipped.extend(
                step.name
                for step in iter_execution_steps(block.else_steps)
                if step.name
            )

    def _nested_outcome(
        self,
        block: ConditionalBlock,
        ast: ConditionNode,
        preds: list[str],
        context: ConditionNode,
    ) -> tuple[bool, bool, bool] | None:
        """The outcome of nested IF *block* while the enclosing IFs hold.

        Its THEN branch runs when ``context AND ast`` can be true, its ELSE
        branch when ``context AND NOT ast`` can be: ``IF S1.RC > 4`` around
        ``IF S1.RC < 2`` never runs its THEN steps.  When *context* itself
        can never be true the enclosing IF has said so already: ``None``.
        """
        then_outcome = self._outcome(block, AndCondition(context, ast), preds)
        if then_outcome is None:
            return None
        else_outcome = self._outcome(
            block, AndCondition(context, NotCondition(ast)), preds
        )
        if else_outcome is None:
            return None
        then_true, _, then_unknown = then_outcome
        else_true, _, else_unknown = else_outcome
        if not (then_true or else_true or then_unknown or else_unknown):
            return None
        return (then_true, else_true, then_unknown or else_unknown)


def compute_feasible_paths(
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
            predecessor to exercise ``ABEND`` / ``NOT ABEND`` atoms, and
            explore every step after the first as possibly not run (an
            abend bypasses the steps after it).  When False, abends are not
            modelled, so an IF testing ``RUN`` or ``ABEND`` is not judged:
            it goes to :attr:`FeasibilityReport.unanalysed_conditions`.

    Returns:
        :class:`FeasibilityReport` aggregating the findings.
    """
    report = FeasibilityReport()
    optional_steps = _collect_optional_steps(job, after_abends=include_abends)
    walker = _FeasibilityWalker(report, rc_domain, include_abends, optional_steps)
    walker.walk(job.steps, [], [])
    return report


__all__ = [
    "DEFAULT_RC_DOMAIN",
    "MAX_COMBINATIONS",
    "FeasibilityReport",
    "compute_feasible_paths",
]
