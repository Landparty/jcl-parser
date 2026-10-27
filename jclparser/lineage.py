"""
Cross-job dataset lineage for a set of jobs (a JCL library, a directory).

:func:`load_job_stream` parses every JCL file in a directory, exploding PROC
calls where it can; :func:`build_lineage` then records which job writes and
which job reads each permanent dataset, and from that derives job-to-job
dependencies (a job that reads a dataset another job writes runs after it),
a run order, and the jobs a dependency cycle keeps out of that order.

Datasets are matched by name with the parenthesised part dropped: a PDS
member is its library (``P.L(M1)`` is ``P.L``), and a relative GDG
generation is its base (``G.H(+1)`` written by one job is ``G.H(0)`` read by
the next, and both are ``G.H``).  The name as coded is kept on each
:class:`DatasetUse`.

A DD's role comes from its ``DISP`` status: ``NEW`` / ``MOD`` write the
dataset, ``SHR`` / ``OLD`` read it (``OLD`` may also update it in place, which
DISP alone can't tell).  Temporary datasets (``&&TEMP``), ``NULLFILE``,
``SYSOUT`` and DDs without a ``DISP`` are left out; a ``DSN=*.STEP.DD``
backward reference counts as the dataset it points at.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dataset_lifecycle import analyze_dataset_lifecycle
from .errors import JCLParseError
from .model import Job
from .parser import parse_jcl

_WRITE_STATUSES = frozenset({"NEW", "MOD"})
_READ_STATUSES = frozenset({"SHR", "OLD"})
_RE_PAREN_SUFFIX = re.compile(r"^(?P<base>[^(]+)\(.*\)$")


def dataset_key(dsn: str) -> str:
    """The name lineage matches *dsn* by: uppercased, member or GDG
    generation dropped."""
    dsn = dsn.strip().upper()
    match = _RE_PAREN_SUFFIX.match(dsn)
    return match.group("base") if match else dsn


@dataclass(frozen=True)
class DatasetUse:
    """One DD of one job that reads or writes a dataset."""

    job: str
    step: str
    dd: str
    dataset: str
    disp: str
    line_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job,
            "step": self.step,
            "dd": self.dd,
            "dataset": self.dataset,
            "disp": self.disp,
            "line_number": self.line_number,
        }


@dataclass
class DatasetLineage:
    """Every use of one dataset (see :func:`dataset_key`) across the jobs."""

    dataset: str
    writers: list[DatasetUse] = field(default_factory=list)
    readers: list[DatasetUse] = field(default_factory=list)

    @property
    def writer_jobs(self) -> list[str]:
        return _unique(u.job for u in self.writers)

    @property
    def reader_jobs(self) -> list[str]:
        return _unique(u.job for u in self.readers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "writers": [u.to_dict() for u in self.writers],
            "readers": [u.to_dict() for u in self.readers],
        }


@dataclass(frozen=True)
class JobDependency:
    """*consumer* reads datasets that *producer* writes."""

    producer: str
    consumer: str
    datasets: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer": self.producer,
            "consumer": self.consumer,
            "datasets": list(self.datasets),
        }


@dataclass
class LineageReport:
    """What :func:`build_lineage` found.

    Attributes:
        jobs: The job ids analysed, in the order given.
        datasets: Lineage per dataset key, sorted by key.
        dependencies: Producer -> consumer edges, sorted.
        run_order: The jobs in an order that runs every producer before its
            consumers (ties broken by the input order); jobs in a cycle are
            left out and listed in :attr:`cycles`.
        cycles: Jobs no order can satisfy: those in a dependency cycle and
            those that depend, directly or not, on a job in one.
    """

    jobs: list[str]
    datasets: dict[str, DatasetLineage]
    dependencies: list[JobDependency]
    run_order: list[str]
    cycles: list[str]

    @property
    def external_inputs(self) -> list[str]:
        """Datasets read but written by none of the jobs."""
        return [k for k, v in self.datasets.items() if v.readers and not v.writers]

    @property
    def final_outputs(self) -> list[str]:
        """Datasets written but read by none of the jobs."""
        return [k for k, v in self.datasets.items() if v.writers and not v.readers]

    def to_dict(self) -> dict[str, Any]:
        return {
            "jobs": list(self.jobs),
            "run_order": list(self.run_order),
            "cycles": list(self.cycles),
            "dependencies": [d.to_dict() for d in self.dependencies],
            "external_inputs": self.external_inputs,
            "final_outputs": self.final_outputs,
            "datasets": [v.to_dict() for v in self.datasets.values()],
        }

    def to_dot(self) -> str:
        """Graphviz DOT: one node per job, one edge per dependency, labelled
        with the datasets that create it."""
        lines = ["digraph lineage {", "  rankdir=LR;", "  node [shape=box];"]
        lines += [f"  {_dot_quote(job)};" for job in self.jobs]
        for dep in self.dependencies:
            label = '"' + "\\n".join(_dot_escape(d) for d in dep.datasets) + '"'
            lines.append(
                f"  {_dot_quote(dep.producer)} -> {_dot_quote(dep.consumer)}"
                f" [label={label}];"
            )
        lines.append("}")
        return "\n".join(lines) + "\n"

    def to_mermaid(self) -> str:
        """Mermaid ``flowchart`` of the same graph as :meth:`to_dot`."""
        ids = {job: f"j{i}" for i, job in enumerate(self.jobs)}
        lines = ["flowchart LR"]
        lines += [f'  {ids[job]}["{_mermaid_text(job)}"]' for job in self.jobs]
        for dep in self.dependencies:
            label = _mermaid_text("<br>".join(dep.datasets))
            lines.append(f'  {ids[dep.producer]} -->|"{label}"| {ids[dep.consumer]}')
        return "\n".join(lines) + "\n"


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _dot_quote(text: str) -> str:
    return f'"{_dot_escape(text)}"'


def _mermaid_text(text: str) -> str:
    return text.replace('"', "#quot;")


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------


def _record_uses(job_id: str, job: Job, datasets: dict[str, DatasetLineage]) -> None:
    for dsn, events in analyze_dataset_lifecycle(job).items():
        if dsn.startswith("&&"):
            continue
        key = dataset_key(dsn)
        lineage = datasets.setdefault(key, DatasetLineage(key))
        for evt in events:
            use = DatasetUse(
                job=job_id,
                step=evt.step_name,
                dd=evt.dd_name,
                dataset=dsn,
                disp=evt.disp_status,
                line_number=evt.line_number,
            )
            if evt.disp_status in _WRITE_STATUSES:
                lineage.writers.append(use)
            elif evt.disp_status in _READ_STATUSES:
                lineage.readers.append(use)


def _dependencies(datasets: Mapping[str, DatasetLineage]) -> list[JobDependency]:
    edges: dict[tuple[str, str], list[str]] = {}
    for key, lineage in datasets.items():
        for producer in lineage.writer_jobs:
            for consumer in lineage.reader_jobs:
                if producer != consumer:
                    edges.setdefault((producer, consumer), []).append(key)
    return [
        JobDependency(producer, consumer, tuple(keys))
        for (producer, consumer), keys in sorted(edges.items())
    ]


def _run_order(
    jobs: list[str], dependencies: list[JobDependency]
) -> tuple[list[str], list[str]]:
    """Kahn's algorithm, taking ready jobs in input order."""
    producers: dict[str, set[str]] = {job: set() for job in jobs}
    for dep in dependencies:
        producers[dep.consumer].add(dep.producer)
    order: list[str] = []
    done: set[str] = set()
    progress = True
    while progress:
        progress = False
        for job in jobs:
            if job not in done and producers[job] <= done:
                order.append(job)
                done.add(job)
                progress = True
    return order, [job for job in jobs if job not in done]


def build_lineage(jobs: Mapping[str, Job]) -> LineageReport:
    """Cross-job dataset lineage of *jobs*, keyed by a job id of your choice
    (a file name, a job name).

    Pass exploded jobs (:meth:`Job.explode`) to see the datasets of PROC
    steps; on an unexploded job only the PROC call's ``//PROCSTEP.DD``
    overrides are seen.
    """
    datasets: dict[str, DatasetLineage] = {}
    for job_id, job in jobs.items():
        _record_uses(job_id, job, datasets)
    datasets = dict(sorted(datasets.items()))
    dependencies = _dependencies(datasets)
    job_ids = list(jobs)
    run_order, cycles = _run_order(job_ids, dependencies)
    return LineageReport(job_ids, datasets, dependencies, run_order, cycles)


# ---------------------------------------------------------------------------
# Loading a directory
# ---------------------------------------------------------------------------


@dataclass
class JobStream:
    """The jobs :func:`load_job_stream` read from a directory.

    Attributes:
        root: The directory.
        jobs: Job id (path relative to *root*, ``/``-separated) -> job,
            exploded when that succeeded.
        procedures: Ids of the JOB-less PROC members found (not jobs).
        errors: Id -> message for each file that could not be parsed.
        warnings: Id -> message for each job that parsed but could not be
            exploded; it is kept unexploded.
    """

    root: Path
    jobs: dict[str, Job] = field(default_factory=dict)
    procedures: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    warnings: dict[str, str] = field(default_factory=dict)

    def lineage(self) -> LineageReport:
        """:func:`build_lineage` over :attr:`jobs`."""
        return build_lineage(self.jobs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "job_names": {k: job.name for k, job in self.jobs.items()},
            "procedures": list(self.procedures),
            "errors": dict(self.errors),
            "warnings": dict(self.warnings),
        }


def _first_line(message: str, limit: int = 200) -> str:
    """A one-line, bounded error message (a binary file's text is noise)."""
    line = message.splitlines()[0] if message else ""
    return line if len(line) <= limit else line[: limit - 3] + "..."


def _explode(job: Job, job_id: str, stream: JobStream) -> Job:
    try:
        return job.explode(audit=False)
    except JCLParseError as exc:
        stream.warnings[job_id] = f"not exploded: {exc}"
        return job


def load_job_stream(
    directory: str | Path,
    pattern: str = "*",
    *,
    explode: bool = True,
    proc_base_path: str | Path | None = None,
) -> JobStream:
    """Parse every file matching *pattern* under *directory*.

    *pattern* is a :meth:`pathlib.Path.glob` pattern (``"**/*.jcl"`` recurses).
    Hidden files are skipped.  A file that fails to parse is recorded in
    :attr:`JobStream.errors` rather than raised; a JOB-less PROC member is
    listed in :attr:`JobStream.procedures`.  With *explode* (the default)
    each job's PROC calls are expanded, looking PROCs up in *proc_base_path*
    as :func:`parse_jcl` does; a job whose explosion fails is kept as parsed,
    with a :attr:`JobStream.warnings` entry.
    """
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    stream = JobStream(root)
    for path in sorted(root.glob(pattern)):
        rel = path.relative_to(root)
        if not path.is_file() or any(p.startswith(".") for p in rel.parts):
            continue
        job_id = rel.as_posix()
        try:
            job = parse_jcl(
                path,
                proc_base_path=proc_base_path,
                enable_external_procs=proc_base_path is not None,
            )
        except (JCLParseError, UnicodeError, ValueError) as exc:
            stream.errors[job_id] = _first_line(str(exc))
            continue
        if job.is_procedure_member:
            stream.procedures.append(job_id)
            continue
        stream.jobs[job_id] = _explode(job, job_id, stream) if explode else job
    return stream
