"""Regression tests for the bugs found by the 2026-11-10 bug hunts.

Pass 1, pass 2 and the run over every available JCL sample (repo fixtures,
AWS CardDemo, the Open Mainframe Project COBOL course).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl
from jclparser.dataset_lifecycle import validate_dataset_lifecycle
from jclparser.errors import ErrorSeverity
from jclparser.include_loader import DictMemberLoader
from jclparser.lineage import build_lineage
from jclparser.lint import lint_job
from jclparser.proc_loader import JCLLIBProcedureLoader
from jclparser.rc_analysis import compute_feasible_paths

pytestmark = pytest.mark.unit

_JOB = "//J JOB (A),'X'\n"


def _messages(jcl: str, level: str = "semantic") -> list[str]:
    return [e.message for e in validate_jcl(jcl, level=level)]


def _findings(jcl: str, level: str = "semantic") -> list[tuple[str, ErrorSeverity]]:
    return [(e.message, e.severity) for e in validate_jcl(jcl, level=level)]


# ---------------------------------------------------------------------------
# Pass 1
# ---------------------------------------------------------------------------


class TestDeletedTemporaryDatasetRead:
    """A temporary dataset deleted by one step and read by a later one."""

    def test_explicit_delete_then_read_warns(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=A\n"
            "//O DD DSN=&&T,DISP=(NEW,DELETE),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S2 EXEC PGM=B\n"
            "//I DD DSN=&&T,DISP=SHR\n"
        )
        findings = _findings(jcl)
        assert findings == [
            (
                (
                    "Temporary dataset &&T is read in step S2 after step S1 "
                    "deleted it (DISP=PASS keeps a temporary dataset for later "
                    "steps)"
                ),
                ErrorSeverity.WARNING,
            )
        ]

    def test_omitted_disp_defaults_to_delete(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=A\n"
            "//O DD DSN=&&T,SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S2 EXEC PGM=B\n"
            "//I DD DSN=&&T,DISP=OLD\n"
        )
        assert any("after step S1 deleted it" in m for m in _messages(jcl))

    def test_old_delete_twice(self):
        jcl = _JOB + (
            "//S0 EXEC PGM=A\n"
            "//O DD DSN=&&T,DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S1 EXEC PGM=A\n"
            "//I DD DSN=&&T,DISP=(OLD,DELETE)\n"
            "//S2 EXEC PGM=B\n"
            "//I DD DSN=&&T,DISP=(OLD,DELETE)\n"
        )
        assert _messages(jcl) == [
            (
                "Temporary dataset &&T is read in step S2 after step S1 deleted "
                "it (DISP=PASS keeps a temporary dataset for later steps)"
            )
        ]

    def test_pass_keeps_it(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=A\n"
            "//O DD DSN=&&T,DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S2 EXEC PGM=B\n"
            "//I DD DSN=&&T,DISP=(OLD,DELETE)\n"
        )
        assert _messages(jcl) == []

    def test_delete_in_other_branch_does_not_count(self):
        jcl = _JOB + (
            "//S0 EXEC PGM=A\n"
            "//O DD DSN=&&T,DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
            "// IF RC = 0 THEN\n"
            "//S1 EXEC PGM=A\n"
            "//I DD DSN=&&T,DISP=(OLD,DELETE)\n"
            "// ELSE\n"
            "//S2 EXEC PGM=B\n"
            "//I DD DSN=&&T,DISP=(OLD,DELETE)\n"
            "// ENDIF\n"
        )
        assert _messages(jcl) == []

    def test_same_step_reads_before_step_end(self):
        # The disposition runs when the step ends.
        jcl = _JOB + (
            "//S1 EXEC PGM=A\n"
            "//O DD DSN=&&T,DISP=(NEW,DELETE),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//I DD DSN=&&T,DISP=SHR\n"
        )
        assert _messages(jcl) == []

    def test_recreated_after_delete_is_readable(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=A\n"
            "//O DD DSN=&&T,DISP=(NEW,DELETE),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S2 EXEC PGM=A\n"
            "//O DD DSN=&&T,DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S3 EXEC PGM=B\n"
            "//I DD DSN=&&T,DISP=SHR\n"
        )
        assert _messages(jcl) == []


class TestCommentAfterTrailingComma:
    def test_unknown_keyword_comment_does_not_eat_continuation(self):
        job = parse_jcl(
            _JOB
            + "//S1 EXEC PGM=A\n"
            + "//O DD DSN=A.B,         RETAIN=30 DAYS PER AUDIT\n"
            + "//      DISP=SHR\n"
        )
        assert job.steps[0].dd_statements[0].parameters == {
            "DSN": "A.B",
            "DISP": "SHR",
        }
        assert any("RETAIN=30 DAYS" in w for w in job.warnings)

    def test_known_keyword_after_blank_still_resumes(self):
        job = parse_jcl(_JOB + "//S1 EXEC PGM=A\n//O DD DSN=A.B,   DISP=SHR\n")
        assert job.steps[0].dd_statements[0].parameters == {
            "DSN": "A.B",
            "DISP": "SHR",
        }

    def test_job_and_exec_pgm_keywords(self):
        job = parse_jcl(
            "//J JOB (A),'X',   CLASS=A\n//S1 EXEC PGM=A,   REGION=4M\n"
            "//S2 EXEC PGM=B,   NOTE=SOMETHING\n//          COND=(0,NE)\n"
        )
        assert job.parameters.get("CLASS") == "A"
        assert job.steps[0].parameters.get("REGION") == "4M"
        assert job.steps[1].parameters.get("COND") == ["0", "NE"]
        assert "NOTE" not in job.steps[1].parameters

    def test_proc_call_symbolics_stay_lenient(self):
        job = parse_jcl(
            _JOB + "//P PROC HLQ=X\n//PS EXEC PGM=A\n// PEND\n//S EXEC P,   HLQ=Y\n"
        )
        assert job.steps[0].parameters.get("HLQ") == "Y"


class TestDDBeforeFirstExec:
    def test_misplaced_dd_is_an_error(self):
        jcl = _JOB + "//INPUT DD DSN=A.B,DISP=SHR\n//S1 EXEC PGM=A\n"
        job = parse_jcl(jcl)
        assert job.steps[0].get_dd("INPUT") is not None
        assert job.statement_findings[0][0] == 2
        findings = validate_jcl(jcl, level="basic")
        assert [(e.line_number, e.severity) for e in findings] == [
            (2, ErrorSeverity.ERROR)
        ]
        assert "DD INPUT comes before the first EXEC" in findings[0].message

    @pytest.mark.parametrize("name", ["JOBLIB", "JOBCAT", "SYSCHK"])
    def test_job_level_dds_allowed(self, name):
        jcl = _JOB + f"//{name} DD DSN=A.B,DISP=SHR\n// DD DSN=A.C,DISP=SHR\n"
        jcl += "//S1 EXEC PGM=A\n"
        assert _messages(jcl) == []

    def test_strict_parse_raises(self):
        from jclparser.errors import JCLValidationError

        with pytest.raises(JCLValidationError, match="before the first EXEC"):
            parse_jcl(_JOB + "//I DD DUMMY\n//S1 EXEC PGM=A\n", strict_mode=True)


class TestLateContinuation:
    def test_continuation_after_column_16_warns(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n//O DD DSN=A.B,\n//" + " " * 18 + "DISP=SHR\n"
        job = parse_jcl(jcl)
        assert job.steps[0].dd_statements[0].parameters["DISP"] == "SHR"
        assert _findings(jcl) == [
            (
                (
                    "continuation record starts in column 21; a continuation "
                    "must start in columns 4-16"
                ),
                ErrorSeverity.WARNING,
            )
        ]
        # Only a warning: a strict parse still succeeds.
        parse_jcl(jcl, strict_mode=True)

    def test_column_16_is_fine(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n//O DD DSN=A.B,\n//" + " " * 13 + "DISP=SHR\n"
        assert _messages(jcl) == []


# ---------------------------------------------------------------------------
# Pass 2
# ---------------------------------------------------------------------------


class TestSymbolValuesAreRescanned:
    def test_set_value_with_operands(self):
        jcl = _JOB + "// SET V='A.B,DISP=SHR'\n//S EXEC PGM=A\n//D DD DSN=&V\n"
        dd = parse_jcl(jcl, strict_mode=True).steps[0].dd_statements[0]
        assert dd.parameters == {"DSN": "A.B", "DISP": "SHR"}
        assert dd.dataset_name == "A.B"
        assert dd.disposition == "SHR"
        assert dd.coded_dataset_name == "&V"
        assert _messages(jcl) == []

    def test_whole_keyword_list(self):
        jcl = _JOB + "// SET P='DSN=A.B,DISP=SHR'\n//S EXEC PGM=A\n//D DD &P\n"
        dd = parse_jcl(jcl).steps[0].dd_statements[0]
        assert dd.parameters == {"DSN": "A.B", "DISP": "SHR"}
        assert dd.dataset_name == "A.B"
        assert _messages(jcl) == []

    def test_parenthesised_disp_is_a_list(self):
        jcl = _JOB + "// SET D=(NEW,CATLG)\n//S1 EXEC PGM=A\n//O DD DSN=A.B,DISP=&D\n"
        dd = parse_jcl(jcl).steps[0].dd_statements[0]
        assert dd.disposition == ["NEW", "CATLG"]
        assert dd.parameters["DISP"] == ["NEW", "CATLG"]

    def test_cond_on_exec(self):
        jcl = _JOB + "// SET C=(0,LE)\n//S1 EXEC PGM=A,COND=&C\n"
        assert parse_jcl(jcl).steps[0].parameters["COND"] == ["0", "LE"]

    def test_parm_value_is_kept_whole(self):
        jcl = _JOB + "// SET P='A,B'\n//S1 EXEC PGM=A,PARM=&P\n"
        assert parse_jcl(jcl).steps[0].parameters["PARM"] == "A,B"

    def test_coded_keyword_wins_over_rescanned_one(self):
        jcl = _JOB + "// SET V='A.B,DISP=OLD'\n//S EXEC PGM=A\n//D DD DSN=&V,DISP=SHR\n"
        dd = parse_jcl(jcl).steps[0].dd_statements[0]
        assert dd.parameters == {"DSN": "A.B", "DISP": "SHR"}

    def test_explosion_path(self):
        jcl = _JOB + (
            "// SET C=(0,LE)\n"
            "//P PROC D=(NEW,CATLG),V='X.Y,DISP=OLD'\n"
            "//PS EXEC PGM=B,COND=&C\n"
            "//O DD DSN=&V\n"
            "//O2 DD DSN=Q,DISP=&D\n"
            "// PEND\n"
            "//S2 EXEC P\n"
        )
        step = explode_job(parse_jcl(jcl)).steps[0]
        assert step.parameters["COND"] == ["0", "LE"]
        o, o2 = step.dd_statements
        assert (o.dataset_name, o.disposition) == ("X.Y", "OLD")
        assert o2.disposition == ["NEW", "CATLG"]

    def test_quoted_value_with_comma_untouched(self):
        jcl = _JOB + "// SET V='''A,B'''\n//S EXEC PGM=A,PARM=X\n//D DD DSN=&V\n"
        dd = parse_jcl(jcl).steps[0].dd_statements[0]
        assert list(dd.parameters) == ["DSN"]


class TestMissingContinuation:
    def test_trailing_comma_before_next_statement(self):
        jcl = _JOB + "//S EXEC PGM=A\n//D DD DSN=A.B,\n//E DD DUMMY\n"
        job = parse_jcl(jcl)
        assert [d.name for d in job.steps[0].dd_statements] == ["D", "E"]
        findings = validate_jcl(jcl, level="basic")
        assert len(findings) == 1
        assert findings[0].line_number == 3
        assert "expected continuation not received" in findings[0].message

    def test_trailing_comma_at_end_of_file(self):
        jcl = _JOB + "//S EXEC PGM=A,\n"
        assert any("no continuation record follows" in m for m in _messages(jcl))

    def test_comment_between_comma_and_continuation_is_fine(self):
        jcl = _JOB + "//S EXEC PGM=A\n//D DD DSN=A.B,\n//* note\n//   DISP=SHR\n"
        assert _messages(jcl) == []

    def test_records_after_null_statement_not_reported(self):
        jcl = _JOB + "//S EXEC PGM=A\n//\n//D DD DSN=A.B,\n"
        job = parse_jcl(jcl)
        assert job.statement_findings == []
        assert not any("continuation" in w for w in job.warnings)


class TestRecursiveInclude:
    def test_self_include_reported_as_recursive(self):
        loader = DictMemberLoader({"A": "// INCLUDE MEMBER=A\n"})
        job = parse_jcl(
            _JOB + "// INCLUDE MEMBER=A\n//S EXEC PGM=X\n", include_loader=loader
        )
        assert len(job.warnings) == 1
        assert "INCLUDE member A includes itself" in job.warnings[0]
        assert "not found" not in job.warnings[0]

    def test_indirect_recursion(self):
        loader = DictMemberLoader(
            {"A": "// INCLUDE MEMBER=B\n", "B": "// INCLUDE MEMBER=A\n"}
        )
        job = parse_jcl(
            _JOB + "// INCLUDE MEMBER=A\n//S EXEC PGM=X\n", include_loader=loader
        )
        assert any("A includes itself" in w for w in job.warnings)

    def test_symbolic_member_name(self):
        loader = DictMemberLoader({"A": "// INCLUDE MEMBER=&M\n"})
        job = parse_jcl(
            _JOB + "// SET M=A\n// INCLUDE MEMBER=&M\n//S EXEC PGM=X\n",
            include_loader=loader,
        )
        assert any("A includes itself" in w for w in job.warnings)


class TestUnnamedDDAfterExec:
    def test_reported(self):
        jcl = _JOB + "//S EXEC PGM=A\n//  DD DSN=A.B,DISP=SHR\n"
        findings = validate_jcl(jcl, level="basic")
        assert [f.line_number for f in findings] == [3]
        assert "unnamed DD statement right after EXEC" in findings[0].message

    def test_concatenation_is_fine(self):
        jcl = (
            _JOB + "//S EXEC PGM=A\n//L DD DSN=A.B,DISP=SHR\n//  DD DSN=A.C,DISP=SHR\n"
        )
        assert _messages(jcl) == []


class TestOverrideNamesMissingProcStep:
    _JCL = _JOB + (
        "//P PROC\n//S1 EXEC PGM=X\n//D DD DUMMY\n// PEND\n"
        "//R EXEC P,REGION.NOPE=4M,REGION.S1=2M\n//NOPE.D DD DUMMY\n//S1.D DD DUMMY\n"
    )

    def test_validate_reports_both(self):
        findings = validate_jcl(self._JCL, level="structure")
        assert [(f.line_number, f.severity) for f in findings] == [
            (6, ErrorSeverity.WARNING),
            (7, ErrorSeverity.WARNING),
        ]
        assert "EXEC override REGION.NOPE names no step" in findings[0].message
        assert "DD override NOPE.D names no step" in findings[1].message

    def test_unloaded_proc_is_not_checked(self):
        from jclparser.explosion import unknown_override_steps
        from jclparser.model import Procedure, Step

        call = Step(name="R", procedure="P", parameters={"REGION.X": "1M"})
        assert unknown_override_steps(call, Procedure(name="P")) == []


# ---------------------------------------------------------------------------
# All samples
# ---------------------------------------------------------------------------


class TestMissingProcDoesNotHideFindings:
    def test_all_findings_reported(self):
        jcl = (
            "//J JOB 1\n//LIB JCLLIB ORDER=(MY.PROCLIB)\n//A EXEC NOPE\n"
            "//A EXEC PGM=Y\n//DD1 DD DSN=X,DISP=BOGUS\n//DD1 DD DSN=Y,DISP=SHR\n"
        )
        messages = _messages(jcl)
        assert messages[0].startswith("Procedure 'NOPE' not found")
        assert "Duplicate step name: A" in messages
        assert "Invalid DISP parameter 'BOGUS' on DD DD1" in messages
        assert "Duplicate DD name in step A: DD1" in messages
        # The PROC is reported once, not again as a WARNING.
        assert sum("NOPE" in m for m in messages) == 1


class TestPrcProcMembers:
    def test_prc_member_loaded(self, tmp_path: Path):
        lib = tmp_path / "MY.PROCLIB"
        lib.mkdir()
        (lib / "REPROC.prc").write_text("//REPROC PROC\n//S1 EXEC PGM=IEFBR14\n")
        job = parse_jcl(
            "//J JOB 1\n//LIB JCLLIB ORDER=(MY.PROCLIB)\n//A EXEC REPROC\n",
            proc_base_path=tmp_path,
            strict_mode=True,
        )
        assert [p.name for p in job.procedures] == ["REPROC"]
        assert [s.name for s in explode_job(job).steps] == ["A.S1"]
        assert JCLLIBProcedureLoader(base_path=tmp_path).list_all_procedures() == {
            "MY.PROCLIB": ["REPROC"]
        }


class TestIdcamsLineage:
    _PRODUCER = (
        "//ACCTFILE JOB 1\n"
        "//DEF EXEC PGM=IDCAMS\n"
        "//SYSIN DD *\n"
        "  DEFINE CLUSTER (NAME(AWS.ACCT.KSDS) -\n"
        "         KEYS(11 0)) -\n"
        "         DATA (NAME(AWS.ACCT.KSDS.DATA))\n"
        "/*\n"
        "//LOAD EXEC PGM=IDCAMS\n"
        "//ACCTREC DD DSN=AWS.ACCT.PS,DISP=SHR\n"
        "//ACCTVSAM DD DSN=AWS.ACCT.KSDS2,DISP=SHR\n"
        "//SYSIN DD *\n"
        "  REPRO INFILE(ACCTREC) OUTFILE(ACCTVSAM)\n"
        "  REPRO INDATASET(AWS.OTHER.IN) OUTDATASET('AWS.OTHER.OUT')\n"
        "/*\n"
    )

    def _report(self, consumer_dsn: str):
        consumer = parse_jcl(
            f"//READ JOB 1\n//S1 EXEC PGM=X\n//F DD DSN={consumer_dsn},DISP=SHR\n"
        )
        return build_lineage({"ACCTFILE": parse_jcl(self._PRODUCER), "READ": consumer})

    @pytest.mark.parametrize(
        "dsn", ["AWS.ACCT.KSDS", "AWS.ACCT.KSDS2", "AWS.OTHER.OUT"]
    )
    def test_define_and_repro_targets_are_written(self, dsn):
        report = self._report(dsn)
        assert [(d.producer, d.consumer) for d in report.dependencies] == [
            ("ACCTFILE", "READ")
        ]
        assert dsn not in report.external_inputs

    def test_repro_sources_are_read(self):
        report = self._report("AWS.ACCT.KSDS")
        assert "AWS.ACCT.PS" in report.external_inputs
        assert "AWS.OTHER.IN" in report.external_inputs
        # The DISP=SHR DD REPRO loads is a write, not also a read.
        assert report.datasets["AWS.ACCT.KSDS2"].readers == []


class TestBackupDeleteRecreate:
    def test_no_forward_reference_warning(self):
        job = parse_jcl(
            "//J JOB 1\n"
            "//S1 EXEC PGM=IEBGENER\n"
            "//SYSUT1 DD DSN=A.TRANTYPE.PS,DISP=SHR\n"
            "//S2 EXEC PGM=IEFBR14\n"
            "//D DD DSN=A.TRANTYPE.PS,DISP=(MOD,DELETE),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S3 EXEC PGM=X\n"
            "//O DD DSN=A.TRANTYPE.PS,DISP=(NEW,CATLG),SPACE=(TRK,1),UNIT=SYSDA\n"
        )
        assert validate_dataset_lifecycle(job) == []

    def test_plain_forward_reference_still_warns(self):
        job = parse_jcl(
            "//J JOB 1\n"
            "//S1 EXEC PGM=X\n"
            "//I DD DSN=A.B,DISP=SHR\n"
            "//S2 EXEC PGM=X\n"
            "//O DD DSN=A.B,DISP=(NEW,CATLG),SPACE=(TRK,1),UNIT=SYSDA\n"
        )
        assert len(validate_dataset_lifecycle(job)) == 1


class TestDuplicateStepNamesAreWarnings:
    _JCL = _JOB + "//COBRUN EXEC PGM=A\n//COBRUN EXEC PGM=B\n"

    def test_validate(self):
        assert _findings(self._JCL) == [
            ("Duplicate step name: COBRUN", ErrorSeverity.WARNING)
        ]
        parse_jcl(self._JCL, strict_mode=True)

    def test_lint(self):
        dup = [f for f in lint_job(parse_jcl(self._JCL)) if "Duplicate" in f.message]
        assert [f.severity for f in dup] == [ErrorSeverity.WARNING]


# ---------------------------------------------------------------------------
# Nested IF return-code contradictions (pass 1, confirmed)
# ---------------------------------------------------------------------------


class TestNestedIfContradictions:
    def test_contradiction_across_nested_ifs(self):
        job = parse_jcl(
            _JOB + "//S1 EXEC PGM=A\n"
            "// IF S1.RC > 4 THEN\n"
            "// IF S1.RC < 2 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// ELSE\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        report = compute_feasible_paths(job)
        assert report.unreachable_steps == ["S2"]
        assert report.always_skipped == []

    def test_else_branch_of_outer(self):
        job = parse_jcl(
            _JOB + "//S1 EXEC PGM=A\n"
            "// IF S1.RC > 4 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// ELSE\n"
            "// IF S1.RC > 8 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert compute_feasible_paths(job).unreachable_steps == ["S3"]

    def test_compatible_nested_ifs(self):
        job = parse_jcl(
            _JOB + "//S1 EXEC PGM=A\n"
            "// IF S1.RC > 4 THEN\n"
            "// IF S1.RC > 8 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        report = compute_feasible_paths(job)
        assert report.unreachable_steps == []
        assert report.always_skipped == []

    def test_unqualified_rc_guard_not_carried_past_a_step(self):
        # RC is the highest RC so far: S2 may raise it between the IFs.
        job = parse_jcl(
            _JOB + "//S1 EXEC PGM=A\n"
            "// IF RC < 4 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// IF RC > 8 THEN\n"
            "//S3 EXEC PGM=C\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert compute_feasible_paths(job).unreachable_steps == []

    def test_outer_contradiction_not_reported_twice(self):
        job = parse_jcl(
            _JOB + "//S1 EXEC PGM=A\n"
            "// IF S1.RC > 4 & S1.RC < 2 THEN\n"
            "// IF S1.RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n"
            "// ENDIF\n"
            "// ENDIF\n"
        )
        assert compute_feasible_paths(job).unreachable_steps == ["S2"]
