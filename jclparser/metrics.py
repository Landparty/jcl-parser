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
    for step in flat_steps:
        if isinstance(step, Step):
            exec_steps += 1
            for dd in step.dd_statements:
                dd_count += 1
                if dd.dataset_name:
                    all_ds.add(dd.dataset_name.upper())
                    if dd.is_input():
                        inputs.add(dd.dataset_name.upper())
                    if dd.is_output():
                        outputs.add(dd.dataset_name.upper())

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
