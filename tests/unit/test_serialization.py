"""Tests for the public JSON export (jclparser.serialization)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jclparser import (
    JOB_JSON_SCHEMA,
    SCHEMA_VERSION,
    JCLParseError,
    explode_job,
    job_to_dict,
    parse_jcl,
)
from jclparser.cli import main
from jclparser.model import Statement
from jclparser.serialization import to_jsonable

jsonschema = pytest.importorskip("jsonschema")

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE_FILES = sorted(FIXTURES.rglob("*.jcl"))

RICH_JCL = """\
//RICHJOB  JOB (ACCT),'PGMR',CLASS=A,MSGCLASS=X
/*JOBPARM  SYSAFF=SYS1
//         EXPORT SYMLIST=(HLQ)
//         SET HLQ=PROD
//LIBS     JCLLIB ORDER=(MY.PROCLIB)
//JOBLIB   DD DSN=MY.LOADLIB,DISP=SHR
//OUT1     OUTPUT CLASS=A,DEST=LOCAL
//MYPROC   PROC MEMBER=X
//PS1      EXEC PGM=IEBGENER
//SYSUT1   DD DSN=&HLQ..IN(&MEMBER),DISP=SHR
//SYSUT2   DD SYSOUT=*
//         PEND
//S1       EXEC PGM=IEFBR14,PARM='A,B'
//DD1      DD DSN=&HLQ..DATA,DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(1,1)),DCB=(RECFM=FB,LRECL=80)
//SYSIN    DD *
  SOME DATA
/*
//         IF (S1.RC = 0) THEN
//S2       EXEC MYPROC,MEMBER=Y
//PS1.SYSUT2 DD DSN=&HLQ..OUT,DISP=(NEW,CATLG)
//         ELSE
//S3       EXEC PGM=IEFBR14
//         ENDIF
"""


def _validate(document: dict) -> None:
    jsonschema.Draft202012Validator(JOB_JSON_SCHEMA).validate(document)


@pytest.mark.unit
class TestSchema:
    def test_schema_is_a_valid_draft_2020_12_schema(self):
        jsonschema.Draft202012Validator.check_schema(JOB_JSON_SCHEMA)

    def test_schema_is_pure_json(self):
        assert json.loads(json.dumps(JOB_JSON_SCHEMA)) == JOB_JSON_SCHEMA

    def test_schema_pins_the_version(self):
        assert JOB_JSON_SCHEMA["properties"]["schema_version"] == {
            "const": SCHEMA_VERSION
        }
        assert SCHEMA_VERSION in JOB_JSON_SCHEMA["$id"]

    def test_document_with_unknown_key_is_rejected(self):
        doc = job_to_dict(parse_jcl(RICH_JCL))
        doc["surprise"] = 1
        with pytest.raises(jsonschema.ValidationError):
            _validate(doc)

    def test_step_missing_a_required_key_is_rejected(self):
        doc = job_to_dict(parse_jcl(RICH_JCL))
        del doc["steps"][0]["program"]
        with pytest.raises(jsonschema.ValidationError):
            _validate(doc)


@pytest.mark.unit
class TestRichJob:
    @pytest.fixture
    def doc(self) -> dict:
        return parse_jcl(RICH_JCL).to_dict()

    def test_validates_and_round_trips_through_json(self, doc):
        _validate(doc)
        assert json.loads(json.dumps(doc)) == doc

    def test_job_level_fields(self, doc):
        assert doc["schema_version"] == SCHEMA_VERSION
        assert doc["name"] == "RICHJOB"
        assert doc["parameters"]["CLASS"] == "A"
        assert doc["set_statements"] == {"HLQ": "PROD"}
        assert doc["jcllib_order"] == ["MY.PROCLIB"]
        assert doc["exported_symbols"] == ["HLQ"]
        assert [d["name"] for d in doc["joblib_dds"]] == ["JOBLIB"]
        assert [o["name"] for o in doc["output_statements"]] == ["OUT1"]
        assert doc["is_procedure_member"] is False

    def test_steps_and_conditional(self, doc):
        s1, cond = doc["steps"]
        assert s1["type"] == "step"
        assert s1["program"] == "IEFBR14"
        assert s1["parameters"]["PARM"] == "A,B"
        dd1, sysin = s1["dd_statements"]
        assert dd1["disposition"] == ["NEW", "CATLG", "DELETE"]
        assert "inline_data" not in dd1
        assert sysin["inline_data"].strip() == "SOME DATA"
        assert cond["type"] == "conditional"
        assert cond["condition"] == "(S1.RC = 0)"
        assert [s["name"] for s in cond["then_steps"]] == ["S2"]
        assert [s["name"] for s in cond["else_steps"]] == ["S3"]
        assert cond["then_steps"][0]["procedure"] == "MYPROC"

    def test_procedure(self, doc):
        (proc,) = doc["procedures"]
        assert proc["name"] == "MYPROC"
        assert proc["source"] == "inline"
        assert proc["parameters"] == {"MEMBER": "X"}
        assert [s["name"] for s in proc["steps"]] == ["PS1"]

    def test_exploded_job_validates(self):
        job = explode_job(parse_jcl(RICH_JCL))
        doc = job.to_dict()
        _validate(doc)
        exploded = [s for s in doc["steps"][1]["then_steps"] if s["is_exploded"]]
        assert exploded, doc["steps"][1]
        assert exploded[0]["original_proc_call"]

    def test_to_json_matches_to_dict(self):
        job = parse_jcl(RICH_JCL)
        assert json.loads(job.to_json()) == job.to_dict()
        assert job.to_json(indent=2).startswith("{\n")


@pytest.mark.unit
class TestModelMethods:
    def test_component_to_dict_methods(self):
        job = parse_jcl(RICH_JCL)
        step = job.steps[0]
        assert step.to_dict()["name"] == "S1"
        assert step.dd_statements[0].to_dict()["name"] == "DD1"
        assert job.steps[1].to_dict()["type"] == "conditional"
        assert job.procedures[0].to_dict()["name"] == "MYPROC"

    def test_control_and_custom_statements(self):
        job = parse_jcl("//J JOB\n//S EXEC PGM=X\n")
        job.custom_statements.append(
            Statement(type="ZZZ", name="C1", parameters={"K": "V"}, line_number=3)
        )
        doc = job.to_dict()
        assert doc["custom_statements"] == [
            {"type": "ZZZ", "name": "C1", "parameters": {"K": "V"}, "line_number": 3}
        ]
        _validate(doc)


@pytest.mark.unit
class TestToJsonable:
    def test_scalars_pass_through(self):
        for v in (None, "x", True, 3, 1.5):
            assert to_jsonable(v) == v

    def test_containers(self):
        assert to_jsonable(("a", ["b"])) == ["a", ["b"]]
        assert to_jsonable({1: {"x"}}) == {"1": ["x"]}
        assert to_jsonable(frozenset({"b", "a"})) == ["a", "b"]

    def test_unknown_object_becomes_str(self):
        class Odd:
            def __str__(self) -> str:
                return "odd"

        assert to_jsonable({"K": Odd()}) == {"K": "odd"}


@pytest.mark.integration
@pytest.mark.parametrize(
    "path", FIXTURE_FILES, ids=lambda p: str(p.relative_to(FIXTURES))
)
def test_every_fixture_validates_against_schema(path: Path):
    try:
        job = parse_jcl(path)
    except JCLParseError:
        pytest.skip("fixture is intentionally invalid JCL")
    doc = job_to_dict(job)
    _validate(doc)
    json.dumps(doc)


@pytest.mark.unit
class TestCLI:
    def test_json_schema_flag_needs_no_file(self, capsys):
        assert main(["--json-schema"]) == 0
        assert json.loads(capsys.readouterr().out) == JOB_JSON_SCHEMA

    def test_cli_json_output_validates(self, tmp_path, capsys):
        src = tmp_path / "rich.jcl"
        src.write_text(RICH_JCL)
        assert main([str(src), "--json"]) == 0
        _validate(json.loads(capsys.readouterr().out))
