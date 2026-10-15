"""
Complexity and size metrics for parsed JCL jobs.

Produces a :class:`JobMetrics` report summarising structural characteristics
of a :class:`~jclparser.model.Job` — step counts, PROC usage, conditional
nesting depth, dataset fan-in/fan-out, and a lightweight cyclomatic-style
score.  Metrics are read-only and never modify the job.

Usage::

    from jclparser.metrics import compute_metrics
    m = compute_metrics(job)
    print(m.step_count, m.cyclomatic_score)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .model import (
    ConditionalBlock,
    Job,
    Step,
    _dataset_dds,
    iter_execution_steps,
)


@dataclass
class JobMetrics:
    """Summary metrics for a single job."""

    job_name: str = ""
    step_count: int = 0
    exec_step_count: int = 0
    dd_count: int = 0
    proc_count: int = 0
    conditional_count: int = 0
    conditional_depth: int = 0
    conditional_branch_count: int = 0
    symbol_count: int = 0
    dataset_fanin: int = 0
    dataset_fanout: int = 0
    unique_datasets: int = 0
    include_count: int = 0
    jcllib_count: int = 0
    output_statement_count: int = 0
    #: Cyclomatic-style complexity: 1 + conditional_count + conditional_branch_count.
    #: Meant to be interpreted like McCabe's CC — higher means more paths.
    cyclomatic_score: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict representation suitable for JSON output."""
        return asdict(self)


def _walk(steps: list, depth: int = 0) -> tuple[int, int, int]:
    """Return ``(max_depth, cond_count, branch_count)`` for a step list.

    ``max_depth`` is the deepest nesting of ConditionalBlocks seen.
    ``cond_count`` is the total number of ConditionalBlocks.
    ``branch_count`` is the total number of non-empty THEN / ELSE branches.
    """
    max_depth = depth
    cond_count = 0
    branch_count = 0
    for s in steps:
        if isinstance(s, ConditionalBlock):
            cond_count += 1
            if s.then_steps:
                branch_count += 1
            if s.else_steps:
                branch_count += 1
            for branch in (s.then_steps, s.else_steps):
                sub_depth, sub_cc, sub_bc = _walk(branch, depth + 1)
                max_depth = max(max_depth, sub_depth)
                cond_count += sub_cc
                branch_count += sub_bc
    return max_depth, cond_count, branch_count


def _counted_dataset_name(
    dsn: str, step_name: str, by_dd: dict[str, str]
) -> str | None:
    """Return the dataset *dsn* names, uppercased, or None when it names none.

    ``DSN=NULLFILE`` is a dummy data set.  A backward reference
    (``DSN=*.STEP.DD`` / ``*.STEP.PROCSTEP.DD`` / ``*.DD``) is not a dataset
    name of its own: it counts as the dataset of the DD it points at, found in
    *by_dd* (``"STEP.DD"`` keys of the DDs seen so far), and not at all when
    that DD is unknown or names no dataset.
    """
    upper = dsn.upper()
    if upper == "NULLFILE":
        return None
    if not upper.startswith("*."):
        return upper
    ref = upper[2:]
    step_upper = step_name.upper()
    if "." not in ref:
        return by_dd.get(f"{step_upper}.{ref}")
    if ref in by_dd:
        return by_dd[ref]
    # In an exploded job a PROC's own *.PROCSTEP.DD references are left as
    # coded while its steps are named CALLER.PROCSTEP.
    if "." in step_upper:
        return by_dd.get(f"{step_upper.rsplit('.', 1)[0]}.{ref}")
    return None


def compute_metrics(job: Job) -> JobMetrics:
    """Compute structural metrics for *job*.

    This is a pure read: no caller-visible side effects.  Uses
    :func:`jclparser.model.iter_execution_steps` for the flattened step view
    so steps nested inside ConditionalBlocks are counted too.
    """
    flat_steps = list(iter_execution_steps(job.steps))

    dd_count = 0
    exec_steps = 0
    inputs: set[str] = set()
    outputs: set[str] = set()
    all_ds: set[str] = set()
    by_dd: dict[str, str] = {}  # "STEP.DD" -> dataset, for backward references
    for step in flat_steps:
        if isinstance(step, Step):
            exec_steps += 1
            step_name = step.name or ""
            # _dataset_dds: an unexploded PROC call's //PROCSTEP.DD overrides
            # allocate datasets too.
            for dd in _dataset_dds(step):
                dd_count += 1
                if not dd.dataset_name:
                    continue
                dsn = _counted_dataset_name(dd.dataset_name, step_name, by_dd)
                if dsn is None:
                    continue
                if dd.name:
                    by_dd[f"{step_name}.{dd.name}".upper()] = dsn
                all_ds.add(dsn)
                if dd.is_input():
                    inputs.add(dsn)
                if dd.is_output():
                    outputs.add(dsn)

    max_depth, cond_count, branch_count = _walk(job.steps)

    return JobMetrics(
        job_name=job.name or "",
        step_count=len(flat_steps),
        exec_step_count=exec_steps,
        dd_count=dd_count,
        proc_count=len(job.procedures),
        conditional_count=cond_count,
        conditional_depth=max_depth,
        conditional_branch_count=branch_count,
        symbol_count=len(job.set_statements),
        dataset_fanin=len(inputs),
        dataset_fanout=len(outputs),
        unique_datasets=len(all_ds),
        include_count=len(job.includes),
        jcllib_count=len(job.jcllib_order),
        output_statement_count=len(job.output_statements),
        cyclomatic_score=1 + cond_count + branch_count,
    )


__all__ = ["JobMetrics", "compute_metrics"]
