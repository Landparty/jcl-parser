"""
JSON serialisation of the parsed model.

:func:`job_to_dict` turns a :class:`~jclparser.model.Job` (parsed or exploded)
into plain ``dict`` / ``list`` / ``str`` / ``int`` / ``bool`` / ``None`` values
that :func:`json.dumps` accepts as-is.  The shape is described by
:data:`JOB_JSON_SCHEMA` (JSON Schema 2020-12) and versioned by
:data:`SCHEMA_VERSION`, so a consumer can validate a document and detect a
change of shape without importing this library.

Versioning: adding an optional key is a minor bump (``1.0`` -> ``1.1``);
renaming, removing or retyping a key is a major bump (``1.x`` -> ``2.0``).

The ``jcl-parser FILE --json`` output is ``job_to_dict(job)``, and
``jcl-parser --json-schema`` prints :data:`JOB_JSON_SCHEMA`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .model import (
        ConditionalBlock,
        DDStatement,
        Job,
        OutputStatement,
        Procedure,
        Statement,
        Step,
    )

#: Version of the document shape produced by :func:`job_to_dict`.
SCHEMA_VERSION = "1.0"


def to_jsonable(value: Any) -> Any:
    """Return *value* as JSON-compatible data.

    Lists and tuples become lists, sets become sorted lists, dict keys become
    strings, and any other non-JSON object becomes its ``str()``, so a
    parameter value of an unexpected type never makes :func:`json.dumps` fail.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(str(v) for v in value)
    return str(value)


def dd_to_dict(dd: DDStatement) -> dict[str, Any]:
    """Serialise a DD statement.  ``inline_data`` is present only for ``DD *`` /
    ``DD DATA`` (and other in-stream) DDs."""
    d: dict[str, Any] = {
        "name": dd.name,
        "dataset_name": dd.dataset_name,
        "disposition": to_jsonable(dd.disposition),
        "parameters": to_jsonable(dd.parameters),
        "line_number": dd.line_number,
        "comments": list(dd.comments),
    }
    if dd.has_inline_data:
        d["inline_data"] = dd.inline_data
    return d


def step_to_dict(step: Step) -> dict[str, Any]:
    """Serialise a step (``"type": "step"``)."""
    return {
        "type": "step",
        "name": step.name,
        "program": step.program,
        "procedure": step.procedure,
        "parameters": to_jsonable(step.parameters),
        "dd_statements": [dd_to_dict(dd) for dd in step.dd_statements],
        "line_number": step.line_number,
        "comments": list(step.comments),
        "is_exploded": step.is_exploded,
        "original_proc_call": step.original_proc_call,
        "dd_overrides": {k: dd_to_dict(v) for k, v in step.dd_overrides.items()},
        "dd_override_concatenations": {
            k: [dd_to_dict(dd) for dd in v]
            for k, v in step.dd_override_concatenations.items()
        },
    }


def conditional_to_dict(block: ConditionalBlock) -> dict[str, Any]:
    """Serialise an ``IF``/``THEN``/``ELSE`` block (``"type": "conditional"``).

    Only the raw ``condition`` string is emitted (invariant 3: it is the
    authoritative form; ``condition_ast`` may be ``None``)."""
    return {
        "type": "conditional",
        "condition": block.condition,
        "then_steps": [step_or_conditional_to_dict(s) for s in block.then_steps],
        "else_steps": [step_or_conditional_to_dict(s) for s in block.else_steps],
        "line_number": block.line_number,
    }


def step_or_conditional_to_dict(item: Step | ConditionalBlock) -> dict[str, Any]:
    """Serialise one entry of ``Job.steps`` / ``Procedure.steps``."""
    from .model import ConditionalBlock

    if isinstance(item, ConditionalBlock):
        return conditional_to_dict(item)
    return step_to_dict(item)


def procedure_to_dict(proc: Procedure) -> dict[str, Any]:
    """Serialise a PROC definition (in-stream or loaded from a library)."""
    return {
        "name": proc.name,
        "source": "external" if proc.is_external else "inline",
        "line_number": proc.line_number,
        "parameters": to_jsonable(proc.parameters),
        "set_statements": dict(proc.set_statements),
        "steps": [step_or_conditional_to_dict(s) for s in proc.steps],
    }


def _statement_to_dict(stmt: Statement) -> dict[str, Any]:
    return {
        "type": stmt.type,
        "name": stmt.name,
        "parameters": to_jsonable(stmt.parameters),
        "line_number": stmt.line_number,
    }


def _output_to_dict(out: OutputStatement) -> dict[str, Any]:
    return {
        "name": out.name,
        "parameters": to_jsonable(out.parameters),
        "line_number": out.line_number,
        "step_name": out.step_name,
        "procedure_name": out.procedure_name,
    }


def job_to_dict(job: Job) -> dict[str, Any]:
    """Serialise a whole job.  See :data:`JOB_JSON_SCHEMA` for the shape."""
    return {
        "schema_version": SCHEMA_VERSION,
        "name": job.name,
        "accounting_info": job.accounting_info,
        "parameters": to_jsonable(job.parameters),
        "line_number": job.line_number,
        "is_procedure_member": job.is_procedure_member,
        "steps": [step_or_conditional_to_dict(s) for s in job.steps],
        "procedures": [procedure_to_dict(p) for p in job.procedures],
        "set_statements": dict(job.set_statements),
        "jcllib_order": list(job.jcllib_order),
        "includes": list(job.includes),
        "joblib_dds": [dd_to_dict(dd) for dd in job.joblib_dds],
        "output_statements": [_output_to_dict(o) for o in job.output_statements],
        "control_statements": [_statement_to_dict(s) for s in job.control_statements],
        "custom_statements": [_statement_to_dict(s) for s in job.custom_statements],
        "jes_statements": list(job.jes_statements),
        "exported_symbols": sorted(job.exported_symbols),
        "comments": list(job.comments),
        "warnings": list(job.warnings),
    }


def job_to_json(job: Job, **kwargs: Any) -> str:
    """``json.dumps(job_to_dict(job), **kwargs)``."""
    return json.dumps(job_to_dict(job), **kwargs)


# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------

_NULLABLE_STR: dict[str, Any] = {"type": ["string", "null"]}
_STR_LIST: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
_STR_MAP: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {"type": "string"},
}
_LINE: dict[str, Any] = {"type": "integer", "minimum": 0}
#: A parameter value as the parser keeps it: a string, a (nested) list of
#: sub-parameters, ``true`` for a bare keyword such as ``*``, or a mapping.
_PARAMS: dict[str, Any] = {"type": "object"}


def _obj(properties: dict[str, Any], optional: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": [k for k in properties if k not in optional],
        "additionalProperties": False,
    }


_DD = _obj(
    {
        "name": {"type": "string"},
        "dataset_name": _NULLABLE_STR,
        "disposition": {"type": ["string", "array", "null"]},
        "parameters": _PARAMS,
        "line_number": _LINE,
        "comments": _STR_LIST,
        "inline_data": {"type": "string"},
    },
    optional=("inline_data",),
)

_STEP = _obj(
    {
        "type": {"const": "step"},
        "name": _NULLABLE_STR,
        "program": _NULLABLE_STR,
        "procedure": _NULLABLE_STR,
        "parameters": _PARAMS,
        "dd_statements": {"type": "array", "items": {"$ref": "#/$defs/dd"}},
        "line_number": _LINE,
        "comments": _STR_LIST,
        "is_exploded": {"type": "boolean"},
        "original_proc_call": _NULLABLE_STR,
        "dd_overrides": {
            "type": "object",
            "additionalProperties": {"$ref": "#/$defs/dd"},
        },
        "dd_override_concatenations": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"$ref": "#/$defs/dd"},
            },
        },
    }
)

_STEP_LIST: dict[str, Any] = {
    "type": "array",
    "items": {"$ref": "#/$defs/step_or_conditional"},
}

_CONDITIONAL = _obj(
    {
        "type": {"const": "conditional"},
        "condition": {"type": "string"},
        "then_steps": _STEP_LIST,
        "else_steps": _STEP_LIST,
        "line_number": _LINE,
    }
)

_PROCEDURE = _obj(
    {
        "name": {"type": "string"},
        "source": {"enum": ["inline", "external"]},
        "line_number": _LINE,
        "parameters": _PARAMS,
        "set_statements": _STR_MAP,
        "steps": _STEP_LIST,
    }
)

_STATEMENT = _obj(
    {
        "type": {"type": "string"},
        "name": {"type": "string"},
        "parameters": _PARAMS,
        "line_number": _LINE,
    }
)

_OUTPUT = _obj(
    {
        "name": {"type": "string"},
        "parameters": _PARAMS,
        "line_number": _LINE,
        "step_name": _NULLABLE_STR,
        "procedure_name": _NULLABLE_STR,
    }
)


def _array_of(ref: str) -> dict[str, Any]:
    return {"type": "array", "items": {"$ref": f"#/$defs/{ref}"}}


#: JSON Schema (draft 2020-12) for the document :func:`job_to_dict` returns.
JOB_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": f"https://github.com/landparty/jcl-parser/schema/job-{SCHEMA_VERSION}.json",
    "title": "jcl-parser Job",
    **_obj(
        {
            "schema_version": {"const": SCHEMA_VERSION},
            "name": {"type": "string"},
            "accounting_info": _NULLABLE_STR,
            "parameters": _PARAMS,
            "line_number": _LINE,
            "is_procedure_member": {"type": "boolean"},
            "steps": _STEP_LIST,
            "procedures": _array_of("procedure"),
            "set_statements": _STR_MAP,
            "jcllib_order": _STR_LIST,
            "includes": _STR_LIST,
            "joblib_dds": _array_of("dd"),
            "output_statements": _array_of("output"),
            "control_statements": _array_of("statement"),
            "custom_statements": _array_of("statement"),
            "jes_statements": _STR_LIST,
            "exported_symbols": _STR_LIST,
            "comments": _STR_LIST,
            "warnings": _STR_LIST,
        }
    ),
    "$defs": {
        "dd": _DD,
        "step": _STEP,
        "conditional": _CONDITIONAL,
        "step_or_conditional": {
            "oneOf": [{"$ref": "#/$defs/step"}, {"$ref": "#/$defs/conditional"}]
        },
        "procedure": _PROCEDURE,
        "statement": _STATEMENT,
        "output": _OUTPUT,
    },
}
