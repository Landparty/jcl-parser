"""Semantic checks on operand values and cross-statement references.

Run by :func:`jclparser.validators.validate_job_structure` (and so by
``Job.validate()`` and :func:`~jclparser.validate_jcl`):

* per step (job steps and PROC body steps, :func:`check_step_operands`):
  PARM length and PARM with PARMDD, the COND= syntax, the SYSOUT class and
  the range of a GDG relative generation;
* per job (:func:`check_job_references`): IF conditions the parser cannot
  read, IF / COND= tests naming a step that does not come before them,
  ``RESTART=`` naming no step, ``CNTL=*.name`` naming no CNTL statement,
  two OUTPUT statements with one name in one scope, and a GDG generation
  read before any step of the job creates it.

A value that still holds a symbol (``PARM=&P`` in a PROC body) is not judged:
:func:`~jclparser.explode_job` resolves it, and the exploded job is checked.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from .errors import ErrorSeverity, ErrorType, ValidationError
from .model import ConditionalBlock, DDStatement, Job, Step, iter_execution_steps
from .utils import jcl_value_text

#: Longest PARM value z/OS passes to a program (JCL Reference, PARM).
MAX_PARM_LENGTH = 100
#: Highest return code a COND= test may name.
MAX_COND_CODE = 4095
#: Most return-code tests one COND= parameter may code.
MAX_COND_TESTS = 8
#: Generations of a classic GDG; an extended GDG allows 999.
MAX_GDG_GENERATIONS = 255
MAX_EXTENDED_GDG_GENERATIONS = 999

_COND_OPERATORS = frozenset({"GT", "GE", "EQ", "LT", "LE", "NE"})
_COND_FLAGS = frozenset({"EVEN", "ONLY"})
_RE_GDG_GENERATION = re.compile(r"\(([+-]?\d+)\)$")
_RE_SYSOUT_CLASS = re.compile(r"^[A-Z0-9*$]?$", re.IGNORECASE)
#: A step reference in IF condition text (the step part of ``S1.RC``,
#: ``S1.PS1.ABEND``, ...).
_RE_CONDITION_STEP_REF = re.compile(
    r"(?<![A-Z0-9@#$.&])([A-Z@#$][A-Z0-9@#$]*)"
    r"(?=\.(?:[A-Z@#$][A-Z0-9@#$]*\.)?(?:RC|ABENDCC|ABEND|RUN)(?![A-Z0-9@#$.]))",
    re.IGNORECASE,
)


def _finding(
    message: str,
    line_number: int,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
) -> ValidationError:
    return ValidationError(
        message,
        ErrorType.SEMANTIC_ERROR,
        line_number=line_number,
        severity=severity,
    )


def _has_symbol(value: Any) -> bool:
    return "&" in jcl_value_text(value)


# ---------------------------------------------------------------------------
# Per-step operand checks
# ---------------------------------------------------------------------------


def check_step_operands(step: Step) -> list[ValidationError]:
    """The operand findings of one step and its DDs."""
    errors = _check_parm(step)
    for key, value in step.parameters.items():
        if key == "COND" or key.startswith("COND."):
            errors.extend(
                _check_cond(value, step.line_number, f"COND on step {_label(step)}")
            )
    for dd in step.dd_statements:
        errors.extend(_check_dd_operands(dd))
    return errors


def _label(step: Step) -> str:
    return step.name or "(unnamed)"


def _parm_text(value: Any) -> str:
    """The PARM value as the program receives it (no outer parens/quotes)."""
    if isinstance(value, list):
        return ",".join(jcl_value_text(v) for v in value)
    return jcl_value_text(value)


def _check_parm(step: Step) -> list[ValidationError]:
    errors: list[ValidationError] = []
    targets: dict[str, set[str]] = {}
    for key, value in step.parameters.items():
        keyword, _, target = key.partition(".")
        if keyword not in ("PARM", "PARMDD"):
            continue
        targets.setdefault(target, set()).add(keyword)
        if keyword != "PARM" or _has_symbol(value):
            continue
        length = len(_parm_text(value))
        if length > MAX_PARM_LENGTH:
            errors.append(
                _finding(
                    f"{key} on step {_label(step)} is {length} characters long; "
                    f"z/OS passes at most {MAX_PARM_LENGTH} (use PARMDD for more)",
                    step.line_number,
                )
            )
    for target, keywords in targets.items():
        if keywords == {"PARM", "PARMDD"}:
            suffix = f".{target}" if target else ""
            errors.append(
                _finding(
                    f"PARM{suffix} and PARMDD{suffix} are both coded on step "
                    f"{_label(step)}; they are mutually exclusive",
                    step.line_number,
                )
            )
    return errors


def cond_tests(value: Any) -> tuple[list[list[str]], list[str]]:
    """Split a COND= value into its return-code tests and EVEN/ONLY flags.

    Each test is its list of subparameters (``["4", "LT", "S1"]``).
    """
    if isinstance(value, str):
        text = value.strip()
        if text.upper() in _COND_FLAGS:
            return [], [text.upper()]
        inner = text[1:-1] if text.startswith("(") and text.endswith(")") else text
        return [inner.split(",")], []
    if not isinstance(value, list):
        return [], []
    items = [jcl_value_text(v).strip() for v in value]
    if not any(i.startswith("(") or i.upper() in _COND_FLAGS for i in items):
        return [items], []
    tests: list[list[str]] = []
    flags: list[str] = []
    for item in items:
        if item.upper() in _COND_FLAGS:
            flags.append(item.upper())
        elif item.startswith("(") and item.endswith(")"):
            tests.append([part.strip() for part in item[1:-1].split(",")])
        else:
            tests.append([item])
    return tests, flags


def _check_cond(
    value: Any, line_number: int, where: str, *, job_level: bool = False
) -> list[ValidationError]:
    """Syntax findings for one COND= value (EXEC, or JOB with *job_level*)."""
    if _has_symbol(value):
        return []
    tests, flags = cond_tests(value)
    problems: list[str] = []
    if len(tests) > MAX_COND_TESTS:
        problems.append(f"codes {len(tests)} tests (at most {MAX_COND_TESTS})")
    if flags and job_level:
        problems.append("codes EVEN/ONLY, which only an EXEC COND may")
    elif len(set(flags)) > 1:
        problems.append("codes both EVEN and ONLY")
    for test in tests:
        problems.extend(_cond_test_problems(test, job_level))
    return [_finding(f"{where} {problem}", line_number) for problem in problems]


def _cond_test_problems(test: list[str], job_level: bool) -> list[str]:
    shown = "(" + ",".join(test) + ")"
    most = 2 if job_level else 3
    if not 2 <= len(test) <= most:
        return [
            f"test {shown} must be (code,operator{'' if job_level else '[,stepname]'})"
        ]
    problems = []
    code, operator = test[0], test[1]
    if not code.isdigit() or int(code) > MAX_COND_CODE:
        problems.append(f"test {shown}: code must be a number 0-{MAX_COND_CODE}")
    if operator.upper() not in _COND_OPERATORS:
        problems.append(f"test {shown}: operator must be one of GT, GE, EQ, LT, LE, NE")
    return problems


def _check_dd_operands(dd: DDStatement) -> list[ValidationError]:
    errors: list[ValidationError] = []
    name = dd.name or "(unnamed)"
    sysout = dd.parameters.get("SYSOUT")
    if sysout is not None and sysout is not True and not _has_symbol(sysout):
        sysout_class = (
            jcl_value_text(sysout[0]) if isinstance(sysout, list) and sysout else sysout
        )
        if isinstance(sysout_class, str) and not _RE_SYSOUT_CLASS.match(sysout_class):
            errors.append(
                _finding(
                    f"SYSOUT class {sysout_class!r} on DD {name} must be one "
                    "character (A-Z, 0-9) or *",
                    dd.line_number,
                )
            )
    generation = _gdg_generation(dd)
    if generation is not None:
        number = abs(generation)
        if number > MAX_EXTENDED_GDG_GENERATIONS:
            errors.append(
                _finding(
                    f"relative generation {generation:+d} of {dd.dataset_name} "
                    f"on DD {name} is out of range (a GDG holds at most "
                    f"{MAX_EXTENDED_GDG_GENERATIONS} generations)",
                    dd.line_number,
                )
            )
        elif number > MAX_GDG_GENERATIONS:
            errors.append(
                _finding(
                    f"relative generation {generation:+d} of {dd.dataset_name} "
                    f"on DD {name} exceeds {MAX_GDG_GENERATIONS}, the limit of "
                    "a classic GDG (only an extended GDG allows more)",
                    dd.line_number,
                    ErrorSeverity.WARNING,
                )
            )
    return errors


def _gdg_generation(dd: DDStatement) -> int | None:
    """The relative generation number of *dd*'s dataset name, if it has one."""
    dsn = dd.dataset_name
    if not isinstance(dsn, str) or "&" in dsn.removeprefix("&&"):
        return None
    match = _RE_GDG_GENERATION.search(dsn)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Job-level reference checks
# ---------------------------------------------------------------------------


def check_job_references(job: Job) -> list[ValidationError]:
    """The cross-statement findings of *job*."""
    errors = _check_if_conditions(job)
    if not job.is_procedure_member:
        errors.extend(_StepReferenceChecker().walk(job.steps))
        errors.extend(_check_restart(job))
        errors.extend(_check_job_cond(job))
        errors.extend(_check_generations_read(job))
    errors.extend(_check_cntl_refs(job))
    errors.extend(_check_duplicate_outputs(job))
    return errors


def _iter_blocks(
    items: list[Step | ConditionalBlock],
) -> Iterator[ConditionalBlock]:
    for item in items:
        if isinstance(item, ConditionalBlock):
            yield item
            yield from _iter_blocks(item.then_steps)
            yield from _iter_blocks(item.else_steps)


def _check_if_conditions(job: Job) -> list[ValidationError]:
    """A WARNING for each IF condition the parser could not read.

    ``ABENDCC`` tests are valid JCL the condition parser does not model, and
    a condition still holding a symbol is judged once it is resolved.
    """
    blocks = list(_iter_blocks(job.steps))
    for proc in job.procedures:
        if not proc.is_external:
            blocks.extend(_iter_blocks(proc.steps))
    return [
        _finding(
            f"IF condition {block.condition!r} is not a valid relational "
            "expression; the steps under it are treated as possibly running",
            block.line_number,
            ErrorSeverity.WARNING,
        )
        for block in blocks
        if block.condition_ast is None
        and "&" not in block.condition
        and "ABENDCC" not in block.condition.upper()
    ]


class _StepReferenceChecker:
    """IF and COND= tests that name a step not coded before them."""

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.errors: list[ValidationError] = []

    def walk(self, items: list[Step | ConditionalBlock]) -> list[ValidationError]:
        for item in items:
            if isinstance(item, ConditionalBlock):
                for ref in _RE_CONDITION_STEP_REF.findall(item.condition):
                    self._check(ref, item.line_number, "IF condition")
                self.walk(item.then_steps)
                self.walk(item.else_steps)
            else:
                self._check_step_cond(item)
                if item.name:
                    self.seen.add(item.name.split(".", 1)[0].upper())
        return self.errors

    def _check_step_cond(self, step: Step) -> None:
        for key, value in step.parameters.items():
            if key != "COND" or _has_symbol(value):
                continue
            tests, _flags = cond_tests(value)
            for test in tests:
                if len(test) == 3 and test[2]:
                    self._check(
                        test[2], step.line_number, f"COND on step {_label(step)}"
                    )

    def _check(self, ref: str, line_number: int, where: str) -> None:
        step = ref.split(".", 1)[0].upper()
        if step not in self.seen:
            self.errors.append(
                _finding(
                    f"{where} names step {ref.upper()}, which is not a step "
                    "coded before it",
                    line_number,
                    ErrorSeverity.WARNING,
                )
            )


def _job_step_names(job: Job) -> set[str]:
    return {
        step.name.split(".", 1)[0].upper()
        for step in iter_execution_steps(job.steps)
        if step.name
    }


def _check_restart(job: Job) -> list[ValidationError]:
    restart = job.parameters.get("RESTART")
    if restart is None or restart is True or _has_symbol(restart):
        return []
    first = restart[0] if isinstance(restart, list) and restart else restart
    target = jcl_value_text(first).strip()
    if not target or target == "*":
        return []
    step = target.split(".", 1)[0].upper()
    if step in _job_step_names(job):
        return []
    return [
        _finding(
            f"RESTART={target} names no step of job {job.name or '(unnamed)'}",
            job.line_number,
            ErrorSeverity.WARNING,
        )
    ]


def _check_job_cond(job: Job) -> list[ValidationError]:
    value = job.parameters.get("COND")
    if value is None:
        return []
    return _check_cond(
        value, job.line_number, "COND on the JOB statement", job_level=True
    )


def _check_cntl_refs(job: Job) -> list[ValidationError]:
    names = {
        (stmt.name or "").upper()
        for stmt in job.control_statements
        if stmt.type == "CNTL"
    }
    errors: list[ValidationError] = []
    for step in _all_steps(job):
        for dd in step.dd_statements:
            ref = dd.parameters.get("CNTL")
            if not isinstance(ref, str) or not ref.startswith("*.") or "&" in ref:
                continue
            if ref.rsplit(".", 1)[-1].upper() not in names:
                errors.append(
                    _finding(
                        f"CNTL={ref} references an undefined CNTL statement",
                        dd.line_number,
                        ErrorSeverity.WARNING,
                    )
                )
    return errors


def _all_steps(job: Job) -> Iterator[Step]:
    yield from iter_execution_steps(job.steps)
    for proc in job.procedures:
        if not proc.is_external:
            yield from iter_execution_steps(proc.steps)


def _check_duplicate_outputs(job: Job) -> list[ValidationError]:
    seen: dict[tuple[str | None, str | None, str], int] = {}
    errors: list[ValidationError] = []
    for output in job.output_statements:
        if not output.name:
            continue
        key = (output.procedure_name, output.step_name, output.name.upper())
        if key in seen:
            errors.append(
                _finding(
                    f"OUTPUT statement {output.name} repeats the name of the "
                    f"OUTPUT statement on line {seen[key]} in the same scope",
                    output.line_number,
                )
            )
        else:
            seen[key] = output.line_number
    return errors


def _disp_status(dd: DDStatement) -> str:
    disp = dd.disposition
    first = disp[0] if isinstance(disp, list) and disp else disp
    return jcl_value_text(first).strip().upper() if first else "NEW"


def _check_generations_read(job: Job) -> list[ValidationError]:
    """A WARNING for a new generation (+n) read before the job creates it."""
    created: set[tuple[str, int]] = set()
    errors: list[ValidationError] = []
    for step in iter_execution_steps(job.steps):
        for dd in step.dd_statements:
            generation = _gdg_generation(dd)
            if generation is None or generation <= 0 or dd.dataset_name is None:
                continue
            base = dd.dataset_name[: dd.dataset_name.rindex("(")].upper()
            status = _disp_status(dd)
            if status in ("NEW", "MOD"):
                created.add((base, generation))
            elif status in ("SHR", "OLD") and (base, generation) not in created:
                errors.append(
                    _finding(
                        f"{dd.dataset_name} is read with DISP={status} on DD "
                        f"{dd.name or '(unnamed)'}, but no earlier step of the "
                        f"job creates generation ({generation:+d})",
                        dd.line_number,
                        ErrorSeverity.WARNING,
                    )
                )
    return errors
