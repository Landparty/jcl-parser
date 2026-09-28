"""Regression tests for validation / model / JES / plugin bug fixes."""

import dataclasses
import json

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl
from jclparser.errors import ErrorSeverity
from jclparser.model import DDStatement
from jclparser.parameter_ast import DCBParameter
from jclparser.plugins import PluginRegistry, ValidationPlugin

pytestmark = pytest.mark.unit

_JOB = "//J JOB (A),'X',CLASS=A\n"


def _messages(jcl: str) -> list[str]:
    return [e.message for e in parse_jcl(jcl).validate()]


class TestExplodedStepNames:
    def test_qualified_exploded_step_names_are_valid(self):
        jcl = _JOB + (
            "//P PROC\n"
            "//PS1 EXEC PGM=X\n"
            "//D1 DD DSN=A.B,DISP=SHR\n"
            "// PEND\n"
            "//S1 EXEC P\n"
            "//S2 EXEC P\n"
        )
        job = explode_job(parse_jcl(jcl))
        assert [s.name for s in job.steps] == ["S1.PS1", "S2.PS1"]
        assert job.validate() == []

    def test_unnamed_proc_calls_not_duplicates(self):
        jcl = _JOB + (
            "//P PROC\n"
            "//PS1 EXEC PGM=X\n"
            "//D1 DD DSN=A.B,DISP=SHR\n"
            "// PEND\n"
            "//     EXEC P\n"
            "//     EXEC P\n"
        )
        assert explode_job(parse_jcl(jcl)).validate() == []

    def test_invalid_component_still_reported(self):
        jcl = _JOB + "//S1 EXEC PGM=X\n//D DD DSN=A.B,DISP=SHR\n"
        job = parse_jcl(jcl)
        job.steps[0].name = "S1.TOOLONGNAME"
        assert any("Invalid step name" in e.message for e in job.validate())

    def test_real_duplicate_still_reported(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=X\n//D DD DSN=A.B,DISP=SHR\n"
            "//S1 EXEC PGM=Y\n//D DD DSN=A.B,DISP=SHR\n"
        )
        assert "Duplicate step name: S1" in _messages(jcl)


class TestTemporaryDatasetLifecycle:
    def test_new_with_omitted_normal_disp_defaults_to_delete(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=IEBGENER\n"
            "//SYSUT1 DD DSN=&&WORK,DISP=NEW,UNIT=SYSDA,SPACE=(CYL,1)\n"
            "//S2 EXEC PGM=IEBGENER\n"
            "//SYSUT1 DD DSN=&&WORK,DISP=(NEW,,DELETE),UNIT=SYSDA,SPACE=(CYL,1)\n"
            "//S3 EXEC PGM=IEBGENER\n"
            "//SYSUT1 DD DSN=&&WORK,DISP=NEW,UNIT=SYSDA,SPACE=(CYL,1)\n"
        )
        assert not any("multiple steps" in m for m in _messages(jcl))
        parse_jcl(jcl, strict_mode=True)

    def test_passed_temp_recreated_still_reported(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=X\n"
            "//D DD DSN=&&T,DISP=(NEW,PASS),UNIT=SYSDA,SPACE=(CYL,1)\n"
            "//S2 EXEC PGM=X\n"
            "//D DD DSN=&&T,DISP=(NEW,PASS),UNIT=SYSDA,SPACE=(CYL,1)\n"
        )
        assert any("multiple steps" in m for m in _messages(jcl))

    def test_member_suffix_keys_to_dataset(self):
        jcl = _JOB + (
            "//LKED EXEC PGM=IEWL\n"
            "//SYSLMOD DD DSN=&&GOSET(GO),DISP=(NEW,PASS),UNIT=SYSDA,\n"
            "//  SPACE=(CYL,(1,1,1))\n"
            "//COPY EXEC PGM=IEBCOPY\n"
            "//IN DD DSN=&&GOSET,DISP=(OLD,DELETE)\n"
        )
        assert not any("never created" in m for m in _messages(jcl))


class TestDispDirection:
    @pytest.mark.parametrize(
        ("disp", "is_in", "is_out"),
        [
            ("(SHR,PASS,CATLG)", True, False),
            ("(OLD,KEEP,UNCATLG)", True, False),
            ("(NEW,CATLG)", False, True),
            ("(,CATLG)", False, True),
            ("MOD", False, True),
            ("SHR", True, False),
        ],
    )
    def test_status_only(self, disp, is_in, is_out):
        dd = DDStatement(name="D", dataset_name="A.B", disposition=disp)
        assert dd.is_input() is is_in
        assert dd.is_output() is is_out

    def test_no_disposition(self):
        dd = DDStatement(name="D")
        assert not dd.is_input()
        assert not dd.is_output()


class TestDDStatementSerialisable:
    def test_disposition_sets_are_not_fields(self):
        names = {f.name for f in dataclasses.fields(DDStatement)}
        assert "_INPUT_DISPOSITIONS" not in names
        assert "_OUTPUT_DISPOSITIONS" not in names

    def test_job_asdict_json_dumps(self):
        job = parse_jcl(_JOB + "//S1 EXEC PGM=X\n//D DD DSN=A.B,DISP=SHR\n")
        json.dumps(dataclasses.asdict(job), default=str)
        json.dumps(dataclasses.asdict(job.steps[0].dd_statements[0]))


class TestValidateJclSeverity:
    def test_structure_level_keeps_warning_severity(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=IEFBR14\n"
            "//D1 DD DSN=A.B,DISP=SHR\n"
            "//D1 DD DSN=A.C,DISP=SHR\n"
        )
        errors = validate_jcl(jcl, level="structure")
        dup = [e for e in errors if "Duplicate DD name" in e.message]
        assert dup and dup[0].severity == ErrorSeverity.WARNING

    def test_semantic_plugin_warning_kept(self, monkeypatch):
        from jclparser import parser as parser_mod
        from jclparser.errors import ValidationError

        class Warn(ValidationPlugin):
            def validate_job(self, job):
                return [
                    ValidationError(
                        "site rule", line_number=2, severity=ErrorSeverity.WARNING
                    )
                ]

            def validate_step(self, step):
                return []

            def validate_dd(self, dd):
                return []

        registry = PluginRegistry()
        registry.register_validation_plugin(Warn())
        monkeypatch.setattr(parser_mod, "get_plugin_registry", lambda: registry)
        jcl = _JOB + "//S1 EXEC PGM=IEFBR14\n//D1 DD DSN=A.B,DISP=SHR\n"
        errors = [
            e for e in validate_jcl(jcl, level="semantic") if e.message == "site rule"
        ]
        assert errors[0].severity == ErrorSeverity.WARNING
        assert errors[0].line_number == 2


class TestSmsAllocationSource:
    @pytest.mark.parametrize(
        "operand",
        [
            "DATACLAS=WORK",
            "STORCLAS=SC1",
            "MGMTCLAS=MC1",
            "LIKE=A.B",
            "REFDD=*.S1.D",
            "AVGREC=K",
        ],
    )
    def test_no_data_source_error(self, operand):
        jcl = _JOB + f"//S1 EXEC PGM=X\n//WRK DD DISP=(NEW,DELETE),{operand}\n"
        assert not any("must specify a data source" in m for m in _messages(jcl))

    def test_bare_disp_still_reported(self):
        jcl = _JOB + "//S1 EXEC PGM=X\n//WRK DD DISP=(NEW,DELETE)\n"
        assert any("must specify a data source" in m for m in _messages(jcl))


class TestJes2CommentField:
    def _jes(self, line: str):
        job = parse_jcl(_JOB + line + "\n//S1 EXEC PGM=IEFBR14\n")
        return job.jes_typed_statements[0]

    def test_route(self):
        stmt = self._jes("/*ROUTE PRINT RMT5                    ROUTE OUTPUT TO REMOTE")
        assert stmt.subcommand == "PRINT"
        assert stmt.destination == "RMT5"

    def test_notify(self):
        assert self._jes("/*NOTIFY USER1       TELL USER1").destination == "USER1"

    def test_priority(self):
        assert self._jes("/*PRIORITY 5          HIGH").value == 5

    def test_netacct(self):
        assert self._jes("/*NETACCT ACCT01     NETWORK ACCT").account == "ACCT01"

    def test_xmit(self):
        stmt = self._jes("/*XMIT NODE2 DLM=ZZ       SEND")
        assert stmt.destination == "NODE2"
        assert stmt.dlm == "ZZ"


class TestDsorgValues:
    @pytest.mark.parametrize(
        "dsorg", ["PSU", "POU", "DAU", "ISU", "CX", "GS", "TX", "TQ", "TR", "PS"]
    )
    def test_valid(self, dsorg):
        assert (
            DCBParameter(raw_value="", subparameters={"DSORG": dsorg}).validate() == []
        )

    def test_invalid(self):
        errors = DCBParameter(raw_value="", subparameters={"DSORG": "XX"}).validate()
        assert errors == ["Invalid DSORG value: XX"]


class TestPluginUnregisterSameClass:
    class Site(ValidationPlugin):
        def __init__(self, hlq):
            self.hlq = hlq

        def validate_job(self, job):
            return []

        def validate_step(self, step):
            return []

        def validate_dd(self, dd):
            return []

    def test_unregister_by_name_twice(self):
        registry = PluginRegistry()
        registry.register_validation_plugin(self.Site("A"))
        registry.register_validation_plugin(self.Site("B"))
        assert registry.unregister_plugin("Site") is True
        assert [p.hlq for p in registry.get_validators()] == ["A"]
        assert registry.unregister_plugin("Site") is True
        assert registry.get_validators() == []
        assert registry.unregister_plugin("Site") is False

    def test_unregister_specific_instance(self):
        registry = PluginRegistry()
        first, second = self.Site("A"), self.Site("B")
        registry.register_validation_plugin(first)
        registry.register_validation_plugin(second)
        assert registry.unregister_plugin(first) is True
        assert registry.get_validators() == [second]
        assert registry.unregister_plugin(first) is False


class TestDDLevelDcbKeywords:
    def _dd(self, operands: str) -> DDStatement:
        jcl = _JOB + f"//S1 EXEC PGM=X\n//D DD DSN=A.B,DISP=(NEW,CATLG),{operands}\n"
        return parse_jcl(jcl).steps[0].dd_statements[0]

    def test_keywords_without_dcb(self):
        dcb = self._dd("RECFM=FB,LRECL=80,BLKSIZE=0,DSORG=PS").dcb
        assert dcb is not None
        assert (dcb.recfm, dcb.lrecl, dcb.blksize, dcb.dsorg) == ("FB", 80, 0, "PS")

    def test_keywords_override_dcb_subparameters(self):
        dcb = self._dd("DCB=(RECFM=VB,LRECL=84),LRECL=100").dcb
        assert dcb.recfm == "VB"
        assert dcb.lrecl == 100

    def test_cached_and_invalidated(self):
        dd = self._dd("RECFM=FB,LRECL=80")
        assert dd.dcb is dd.dcb
        dd.parameters = {"RECFM": "VB"}
        assert dd.dcb.recfm == "VB"
        dd.parameters = {}
        assert dd.dcb is None
