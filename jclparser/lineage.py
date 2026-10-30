"""
Cross-job dataset lineage for a set of jobs (a JCL library, a directory).

:func:`load_job_stream` parses every JCL file in a directory, exploding PROC
calls where it can; :func:`build_lineage` then records which job writes and
which job reads each permanent dataset, and from that derives job-to-job
dependencies (a job that reads a dataset another job writes runs after it),
a run order, and the jobs a dependency cycle keeps out of that order.

Datasets are matched by name (:func:`dataset_key`).  A relative GDG
generation is its base (``G.H(+1)`` written by one job is ``G.H(0)`` read by
the next, and both are ``G.H``).  A PDS member keeps its member name: a write
of ``P.L(M1)`` feeds the reads of ``P.L(M1)`` and the whole-library reads of
``P.L`` (a STEPLIB, a BIND of the library), but not a read of ``P.L(M2)``;
a write of the bare ``P.L`` feeds every read of the library or of one of its
members.  A job that writes members of a library and also reads the whole
library (a compile job's PRECOMP writes ``DBRMLIB(PROG)``, its BIND reads
``DBRMLIB``) is taken to read its own members there, so compile jobs that
share a load library or DBRMLIB do not depend on one another (issue #145).  The name as coded is kept on each
:class:`DatasetUse`.

A DD's role comes from its ``DISP`` status: ``NEW`` / ``MOD`` write the
dataset, ``SHR`` / ``OLD`` read it (``OLD`` may also update it in place, which
DISP alone can't tell).  A normal disposition of ``DELETE`` makes any status
but ``NEW`` a read (a delete runs after the dataset's producer), and
``(NEW,DELETE)`` -- a scratch dataset -- neither.  Temporary datasets (``&&TEMP``), ``NULLFILE``,
``SYSOUT`` and DDs without a ``DISP`` are left out; a ``DSN=*.STEP.DD``
backward reference counts as the dataset it points at.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dataset_lifecycle import analyze_dataset_lifecycle
from .errors import JCLParseError
from .explosion import _job_proc_loader
from .model import Job, Procedure
from .parser import parse_jcl
from .proc_loader import (
    CompositeProcedureLoader,
    InlineProcedureLoader,
    ProcedureLoader,
)

_WRITE_STATUSES = frozenset({"NEW", "MOD"})
_READ_STATUSES = frozenset({"SHR", "OLD"})
_RE_PAREN_SUFFIX = re.compile(r"^(?P<base>[^(]+)\((?P<inner>.*)\)$")
_RE_GDG_GENERATION = re.compile(r"^[+-]?\d+$")


def dataset_key(dsn: str) -> str:
    """The name lineage matches *dsn* by: uppercased, a relative GDG
    generation dropped (``G.H(+1)`` is ``G.H``), a PDS member kept
    (``P.L(M)`` stays ``P.L(M)``; see :func:`library_of`)."""
    dsn = dsn.strip().upper()
    match = _RE_PAREN_SUFFIX.match(dsn)
    if match and _RE_GDG_GENERATION.match(match.group("inner").strip()):
        return match.group("base")
    return dsn


def library_of(key: str) -> str:
    """The library part of a :func:`dataset_key`: ``P.L(M)`` -> ``P.L``."""
    return key.split("(", 1)[0]


def _feeds(written: str, read: str) -> bool:
    """True if a write of key *written* feeds a read of key *read*.

    Same key; a member write feeds a whole-library read; a whole-library
    write feeds every read of the library or one of its members.
    """
    if written == read:
        return True
    library = library_of(written)
    if library != library_of(read):
        return False
    return library in (written, read)


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
        written = [k for k, v in self.datasets.items() if v.writers]
        return [
            k
            for k, v in self.datasets.items()
            if v.readers and not any(_feeds(w, k) for w in written)
        ]

    @property
    def final_outputs(self) -> list[str]:
        """Datasets written but read by none of the jobs."""
        read = [k for k, v in self.datasets.items() if v.readers]
        return [
            k
            for k, v in self.datasets.items()
            if v.writers and not any(_feeds(k, r) for r in read)
        ]

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
            role = _role(evt.disp_status, evt.disp_normal)
            if role == "write":
                lineage.writers.append(use)
            elif role == "read":
                lineage.readers.append(use)


def _role(status: str, normal: str) -> str | None:
    """``"write"``, ``"read"`` or ``None`` (not a lasting use) for a DISP.

    A normal disposition of ``DELETE`` deletes the dataset: it must run after
    the job that created it, so it counts as a read, whatever the status --
    the IEFBR14 ``DISP=(MOD,DELETE)`` clean-up idiom is not a write.
    ``(NEW,DELETE)`` is a scratch dataset and counts as neither.
    """
    if normal == "DELETE":
        return None if status == "NEW" else "read"
    if status in _WRITE_STATUSES:
        return "write"
    if status in _READ_STATUSES:
        return "read"
    return None


def _member_writers(datasets: Mapping[str, DatasetLineage]) -> dict[str, set[str]]:
    """Library -> the jobs that write one of its members."""
    writers: dict[str, set[str]] = {}
    for key, lineage in datasets.items():
        if key != library_of(key):
            writers.setdefault(library_of(key), set()).update(lineage.writer_jobs)
    return writers


def _dependencies(datasets: Mapping[str, DatasetLineage]) -> list[JobDependency]:
    by_library: dict[str, list[str]] = {}
    for key in datasets:
        by_library.setdefault(library_of(key), []).append(key)
    member_writers = _member_writers(datasets)
    edges: dict[tuple[str, str], list[str]] = {}
    for library, keys in by_library.items():
        for written, read in ((w, r) for w in keys for r in keys if _feeds(w, r)):
            # Label the edge with the more specific name (the member).
            label = read if written == library else written
            consumers = datasets[read].reader_jobs
            if read == library != written:
                # A job that writes members of the library and reads the
                # whole of it (a compile job's BIND of its DBRMLIB) is taken
                # to read its own members, not the ones other jobs write.
                consumers = [c for c in consumers if c not in member_writers[library]]
            for producer in datasets[written].writer_jobs:
                for consumer in consumers:
                    if producer != consumer:
                        labels = edges.setdefault((producer, consumer), [])
                        if label not in labels:
                            labels.append(label)
    return [
        JobDependency(producer, consumer, tuple(sorted(keys)))
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
            The jobs are exploded with them (see :func:`load_job_stream`).
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


def _explode(job: Job, job_id: str, stream: JobStream, members: ProcedureLoader) -> Job:
    # In-stream PROCs first, then the directory's PROC members, then the
    # usual chain (--proc-path libraries, built-in PROCs).
    loader = CompositeProcedureLoader(
        [InlineProcedureLoader(job.procedures), members, _job_proc_loader(job)]
    )
    try:
        return job.explode(audit=False, loader=loader)
    except JCLParseError as exc:
        stream.warnings[job_id] = f"not exploded: {exc}"
        return job


class _MemberLoader(ProcedureLoader):
    """The PROC members of a directory, by member name."""

    def __init__(self, procedures: dict[str, Procedure]) -> None:
        self._procedures = procedures

    def load_procedure(
        self, name: str, libraries: Sequence[str] | None = None
    ) -> Procedure | None:
        return self._procedures.get(name.upper())


def _member_procedures(path: Path, member: Job) -> dict[str, Procedure]:
    """The procedures of PROC member *member* read from *path*, by name.

    A member is called by its member name -- the file name without its
    suffix (``.prc``, ``.proc``, ``.jcl`` or none) -- whatever its PROC
    statement's label says; each PROC in it is also known by that label.
    """
    procs: dict[str, Procedure] = {}
    for proc in member.procedures:
        if proc.name:
            procs.setdefault(proc.name.upper(), proc)
    if member.procedures:
        procs[path.stem.upper()] = member.procedures[0]
    return procs


def _bare_procedure_member(path: Path) -> Procedure | None:
    """*path* read as a cataloged PROC member with no ``PROC`` statement.

    On z/OS the PROC statement of a cataloged procedure is optional (it only
    gives symbolic parameters defaults), so a member may start at its first
    ``EXEC``.  :func:`parse_jcl` rejects such a JOB-less file ("EXEC
    statement before JOB statement"); the file-based PROC loader reads it as
    the body of a procedure named after the member, and so does this
    (issue #147).  None when *path* is not such a member.
    """
    from .jcl_file_type import FileType, detect_file_type_from_content
    from .proc_loader import _build_procedure_from_content
    from .utils import _read_file_with_fallback

    try:
        content = _read_file_with_fallback(path)
        if detect_file_type_from_content(content) != FileType.PROC:
            return None
        return _build_procedure_from_content(content, path.stem.upper())
    except (JCLParseError, OSError, UnicodeError, ValueError):
        return None


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
    listed in :attr:`JobStream.procedures`, and so is a member with no
    ``PROC`` statement that starts at its first ``EXEC`` (issue #147).  With
    *explode* (the default) each job's PROC calls are expanded: a PROC is looked up in the job
    itself, then among the PROC members of the directory (by member name,
    see :func:`_member_procedures`; issue #144), then in *proc_base_path* as
    :func:`parse_jcl` does, then among the built-in PROCs.  A job whose
    explosion fails is kept as parsed, with a :attr:`JobStream.warnings`
    entry.
    """
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    stream = JobStream(root)
    parsed: dict[str, Job] = {}
    members: dict[str, Procedure] = {}
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
            bare = _bare_procedure_member(path)
            if bare is None:
                stream.errors[job_id] = _first_line(str(exc))
            else:
                stream.procedures.append(job_id)
                members.setdefault(path.stem.upper(), bare)
            continue
        if job.is_procedure_member:
            stream.procedures.append(job_id)
            for name, proc in _member_procedures(path, job).items():
                members.setdefault(name, proc)
            continue
        parsed[job_id] = job
    member_loader = _MemberLoader(members)
    for job_id, job in parsed.items():
        stream.jobs[job_id] = (
            _explode(job, job_id, stream, member_loader) if explode else job
        )
    return stream
