"""
Unit tests for the feature-ideas branch additions:

* A1 typed JES2/JES3 control statements
* A2 EXPORT / SYMLIST parsing
* A3 OUTPUT=*.name back-reference resolution
* A4 auto SQL detection via ParserConfig.detect_sql
* B1 program-profile registry
* B2 RC feasibility analysis
* B3 lint rule pack
* B4 job metrics
"""

from __future__ import annotations

import jclparser as jp
from jclparser.parser import _extract_output_ref_names
from jclparser.jes_statements import (
    parse_jes_control,
    parse_jes3_route_xeq,
    JobParmStatement,
    RouteStatement,
    XmitStatement,
    SignonStatement,
    MessageStatement,
    NetacctStatement,
    NotifyStatement,
    PriorityStatement,
    Jes3RouteXeqStatement,
)
from jclparser.metrics import compute_metrics
from jclparser.rc_analysis import compute_feasible_paths
from jclparser.program_profiles import analyze_job, get_profile
from jclparser.lint import lint_job, LintConfig, to_sarif


# ---------------------------------------------------------------------------
# A1: Typed JES control statements
# ---------------------------------------------------------------------------


class TestTypedJESStatements:
    def test_jobparm_parses_keyword_params(self):
        stmt = parse_jes_control("JOBPARM", "CLASS=A,LINES=5000", line_number=3)
        assert isinstance(stmt, JobParmStatement)
        assert stmt.parameters == {"CLASS": "A", "LINES": "5000"}
        assert stmt.line_number == 3

    def test_route_splits_subcommand_and_destination(self):
        stmt = parse_jes_control("ROUTE", "XEQ NODE2")
        assert isinstance(stmt, RouteStatement)
        assert stmt.subcommand == "XEQ"
        assert stmt.destination == "NODE2"

    def test_xmit_extracts_destination_and_dlm(self):
        stmt = parse_jes_control("XMIT", "NODE1.USER DLM=XX")
        assert isinstance(stmt, XmitStatement)
        assert stmt.destination == "NODE1.USER"
        assert stmt.dlm == "XX"

    def test_signon_message_netacct_notify(self):
        assert isinstance(parse_jes_control("SIGNON", ""), SignonStatement)
        msg = parse_jes_control("MESSAGE", "HELLO WORLD")
        assert isinstance(msg, MessageStatement) and msg.text == "HELLO WORLD"
        net = parse_jes_control("NETACCT", "12345")
        assert isinstance(net, NetacctStatement) and net.account == "12345"
        notify = parse_jes_control("NOTIFY", "TSOUSER")
        assert isinstance(notify, NotifyStatement) and notify.destination == "TSOUSER"

    def test_priority_parses_integer(self):
        ok = parse_jes_control("PRIORITY", "8")
        assert isinstance(ok, PriorityStatement) and ok.value == 8
        bad = parse_jes_control("PRIORITY", "NOTANINT")
        assert isinstance(bad, PriorityStatement) and bad.value is None

    def test_unknown_jes_command_returns_none(self):
        assert parse_jes_control("WIBBLE", "stuff") is None

    def test_jes3_route_xeq_detected(self):
        typed = parse_jes3_route_xeq("//*ROUTE XEQ NYNODE", line_number=1)
        assert isinstance(typed, Jes3RouteXeqStatement)
        assert typed.node == "NYNODE"

    def test_jes3_route_xeq_missing_args_returns_none(self):
        assert parse_jes3_route_xeq("//*ROUTE", line_number=1) is None

    def test_jes3_route_xeq_ignores_regular_comment(self):
        assert parse_jes3_route_xeq("//* THIS IS A COMMENT", line_number=1) is None

    def test_parse_jcl_populates_jes_typed_statements(self):
        src = (
            "//MYJOB    JOB  (ACCT),'OWNER'\n"
            "/*JOBPARM CLASS=A,LINES=5000\n"
            "/*ROUTE XEQ REMOTE\n"
            "/*PRIORITY 8\n"
            "//*ROUTE XEQ NY1\n"
            "//STEP1   EXEC PGM=IEFBR14\n"
        )
        job = jp.parse_jcl(src)
        kinds = {type(s).__name__ for s in job.jes_typed_statements}
        assert "JobParmStatement" in kinds
        assert "RouteStatement" in kinds
        assert "PriorityStatement" in kinds
        assert "Jes3RouteXeqStatement" in kinds
        # Raw list still populated:
        assert any("JOBPARM" in s for s in job.jes_statements)


# ---------------------------------------------------------------------------
# A2: EXPORT / SYMLIST
# ---------------------------------------------------------------------------


class TestExportSymlist:
    def test_export_symlist_list_form(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "// EXPORT SYMLIST=(DSN,HLQ)\n"
            "//STEP1   EXEC PGM=IEFBR14\n"
        )
        job = jp.parse_jcl(src)
        assert {"DSN", "HLQ"} <= job.exported_symbols

    def test_export_symlist_star(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n// EXPORT SYMLIST=*\n//STEP1   EXEC PGM=IEFBR14\n"
        )
        job = jp.parse_jcl(src)
        assert "*" in job.exported_symbols

    def test_export_symbols_survive_explosion(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "// EXPORT SYMLIST=DSN\n"
            "//STEP1   EXEC PGM=IEFBR14\n"
        )
        job = jp.parse_jcl(src)
        exploded = job.explode()
        assert "DSN" in exploded.exported_symbols


# ---------------------------------------------------------------------------
# A3: OUTPUT back-reference resolution
# ---------------------------------------------------------------------------


class TestOutputBackReferences:
    def test_extract_simple_star_ref(self):
        assert _extract_output_ref_names("*.REPORT") == ["REPORT"]

    def test_extract_list_form(self):
        assert _extract_output_ref_names(["*.A", "*.B"]) == ["A", "B"]

    def test_extract_qualified_takes_last_segment(self):
        assert _extract_output_ref_names("*.STEP.NAME") == ["NAME"]

    def test_extract_ignores_non_starred(self):
        assert _extract_output_ref_names("PROD") == []
        assert _extract_output_ref_names(None) == []

    def test_resolve_populates_output_refs(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//MYOUT    OUTPUT DEST=REMOTE\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//REPORT   DD SYSOUT=A,OUTPUT=*.MYOUT\n"
        )
        job = jp.parse_jcl(src)
        dd = job.steps[0].get_dd("REPORT")
        assert dd is not None
        assert len(dd.output_refs) == 1
        assert dd.output_refs[0].name == "MYOUT"
        assert job.unresolved_output_refs == []

    def test_unresolved_reference_recorded(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//REPORT   DD SYSOUT=A,OUTPUT=*.NOPE\n"
        )
        job = jp.parse_jcl(src)
        assert job.unresolved_output_refs
        step_name, ref, _ln = job.unresolved_output_refs[0]
        assert step_name == "STEP1"
        assert ref == "NOPE"

    def test_validation_emits_warning_for_unresolved(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//REPORT   DD SYSOUT=A,OUTPUT=*.NOPE\n"
        )
        job = jp.parse_jcl(src)
        errors = job.validate()
        assert any(
            e.error_type.name == "SEMANTIC_ERROR" and "NOPE" in e.message
            for e in errors
        )


# ---------------------------------------------------------------------------
# A4: Auto SQL detection
# ---------------------------------------------------------------------------


class TestAutoSQLDetection:
    def test_sql_detection_opt_in(self):
        from jclparser.plugins import ParserConfig

        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=DSNTEP2\n"
            "//SYSIN    DD *\n"
            "SELECT * FROM T;\n"
            "/*\n"
        )
        cfg = ParserConfig(detect_sql=True)
        job = jp.parse_jcl(src, config=cfg)
        assert "STEP1" in job.sql_detections
        assert job.sql_detections["STEP1"].is_db2_program

    def test_sql_detection_off_by_default(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=DSNTEP2\n"
        job = jp.parse_jcl(src)
        assert job.sql_detections == {}


# ---------------------------------------------------------------------------
# B1: Program profiles
# ---------------------------------------------------------------------------


class TestProgramProfiles:
    def test_iefbr14_profile_reports_allocation(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//NEWDD    DD DSN=PROD.DATA,DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,\n"
            "//             SPACE=(CYL,(1,1))\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert results
        assert results[0].program == "IEFBR14"
        assert any(e.action == "ALLOCATE" for e in results[0].dataset_events)

    def test_idcams_profile_detects_delete_and_define(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IDCAMS\n"
            "//SYSIN    DD *\n"
            "  DELETE PROD.OLD.DATA\n"
            "  DEFINE CLUSTER (NAME(PROD.NEW.DATA) CYLINDERS(10 5))\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        result = results[0]
        assert result.program == "IDCAMS"
        assert any("DELETE" in n for n in result.notes)
        assert any("DEFINE CLUSTER" in n for n in result.notes)

    def test_iebgener_detects_sysut1_sysut2_flow(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR\n"
            "//SYSUT2   DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,\n"
            "//             SPACE=(CYL,(1,1))\n"
            "//SYSIN    DD DUMMY\n"
            "//SYSPRINT DD SYSOUT=*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        result = results[0]
        assert result.program == "IEBGENER"
        assert any("reads" in n for n in result.notes)
        assert any("writes" in n for n in result.notes)

    def test_sort_profile_detects_filters(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=SORT\n"
            "//SYSIN    DD *\n"
            "  SORT FIELDS=(1,10,CH,A)\n"
            "  INCLUDE COND=(1,4,CH,EQ,C'KEEP')\n"
            "  OUTREC BUILD=(1,10)\n"
            "/*\n"
            "//SORTIN   DD DSN=IN,DISP=SHR\n"
            "//SORTOUT  DD DSN=OUT,DISP=(NEW,CATLG,DELETE)\n"
            "//SYSOUT   DD SYSOUT=*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        notes = " ".join(results[0].notes)
        assert "SORT FIELDS" in notes
        assert "INCLUDE" in notes
        assert "OUTREC" in notes

    def test_ikjeft01_detects_bind_and_sql(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IKJEFT01\n"
            "//SYSTSIN  DD *\n"
            "  DSN SYSTEM(DB2P)\n"
            "  BIND PACKAGE(MYPKG) MEMBER(MYPROG)\n"
            "  RUN PROGRAM(MYPROG)\n"
            "  END\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        notes = " | ".join(results[0].notes)
        assert "DSN SYSTEM(DB2P)" in notes
        assert "BIND" in notes
        assert "RUN PROGRAM" in notes

    def test_unknown_program_returns_no_analysis(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=MYCUSTOM\n"
        job = jp.parse_jcl(src)
        assert analyze_job(job) == []
        assert get_profile("MYCUSTOM") is None


# ---------------------------------------------------------------------------
# B2: RC feasibility
# ---------------------------------------------------------------------------


class TestRCFeasibility:
    def test_normal_rc_condition_is_feasible(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=PROG1\n"
            "//         IF (STEP1.RC EQ 0) THEN\n"
            "//STEP2    EXEC PGM=PROG2\n"
            "//         ENDIF\n"
        )
        job = jp.parse_jcl(src)
        report = compute_feasible_paths(job)
        assert "STEP2" not in report.unreachable_steps

    def test_unsatisfiable_rc_marks_unreachable(self):
        # RC > 100 is outside the default domain {0,4,8,12,16} → never true
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=PROG1\n"
            "//         IF (STEP1.RC GT 100) THEN\n"
            "//STEP2    EXEC PGM=PROG2\n"
            "//         ENDIF\n"
        )
        job = jp.parse_jcl(src)
        report = compute_feasible_paths(job)
        assert "STEP2" in report.unreachable_steps

    def test_always_true_skips_else_branch(self):
        # RC >= 0 is true for every value in the default domain.
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=PROG1\n"
            "//         IF (STEP1.RC GE 0) THEN\n"
            "//STEP2    EXEC PGM=PROG2\n"
            "//         ELSE\n"
            "//STEP3    EXEC PGM=PROG3\n"
            "//         ENDIF\n"
        )
        job = jp.parse_jcl(src)
        report = compute_feasible_paths(job)
        assert "STEP3" in report.always_skipped


# ---------------------------------------------------------------------------
# B3: Lint pack
# ---------------------------------------------------------------------------


class TestLintPack:
    def test_missing_time_and_region_reported(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IEFBR14\n"
        job = jp.parse_jcl(src)
        findings = lint_job(job)
        codes = {f.error_code for f in findings}
        assert "JCL-LINT-004" in codes
        assert "JCL-LINT-005" in codes

    def test_sysda_unit_flagged(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//NEW      DD DSN=PROD.DATA,UNIT=SYSDA,DISP=(NEW,CATLG,DELETE)\n"
        )
        job = jp.parse_jcl(src)
        findings = lint_job(job)
        assert any(f.error_code == "JCL-LINT-002" for f in findings)

    def test_critical_dataset_pattern_rule(self):
        src = (
            "//MYJOB    JOB  (ACCT),TIME=60,REGION=4M\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//NEW      DD DSN=PROD.MASTER.FILE,UNIT=TAPE,\n"
            "//             DISP=(NEW,CATLG,DELETE)\n"
        )
        job = jp.parse_jcl(src)
        cfg = LintConfig(critical_dataset_patterns=["PROD.MASTER"])
        findings = lint_job(job, cfg)
        assert any(f.error_code == "JCL-LINT-003" for f in findings)

    def test_disabled_rule_skipped(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IEFBR14\n"
        job = jp.parse_jcl(src)
        cfg = LintConfig(disabled={"JCL-LINT-004"})
        findings = lint_job(job, cfg)
        assert not any(f.error_code == "JCL-LINT-004" for f in findings)

    def test_enabled_set_restricts_rules(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IEFBR14\n"
        job = jp.parse_jcl(src)
        cfg = LintConfig(enabled={"JCL-LINT-005"})
        codes = {f.error_code for f in lint_job(job, cfg)}
        assert codes == {"JCL-LINT-005"}

    def test_sarif_roundtrip(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IEFBR14\n"
        job = jp.parse_jcl(src)
        findings = lint_job(job)
        sarif = to_sarif(findings)
        assert sarif["version"] == "2.1.0"
        assert sarif["runs"][0]["results"]
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert {r["id"] for r in rules} & {"JCL-LINT-004", "JCL-LINT-005"}

    def test_error_code_in_validation_error_str(self):
        from jclparser.errors import ValidationError, ErrorSeverity

        err = ValidationError(
            "boom",
            severity=ErrorSeverity.WARNING,
            line_number=5,
            error_code="JCL-LINT-999",
        )
        s = str(err)
        assert "JCL-LINT-999" in s
        assert "WARNING" in s


# ---------------------------------------------------------------------------
# B4: Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_metrics_basic_counts(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//IN       DD DSN=IN.FILE,DISP=SHR\n"
            "//OUT      DD DSN=OUT.FILE,DISP=(NEW,CATLG,DELETE)\n"
            "//STEP2    EXEC PGM=IEFBR14\n"
            "//REP      DD DSN=OUT.FILE,DISP=OLD\n"
        )
        job = jp.parse_jcl(src)
        m = compute_metrics(job)
        assert m.step_count == 2
        assert m.exec_step_count == 2
        assert m.dd_count == 3
        assert m.dataset_fanin >= 1
        assert m.dataset_fanout >= 1
        assert m.unique_datasets == 2
        assert m.cyclomatic_score == 1

    def test_metrics_conditional_depth(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=PROG1\n"
            "//         IF (STEP1.RC EQ 0) THEN\n"
            "//STEP2    EXEC PGM=PROG2\n"
            "//         IF (STEP2.RC EQ 0) THEN\n"
            "//STEP3    EXEC PGM=PROG3\n"
            "//         ENDIF\n"
            "//         ENDIF\n"
        )
        job = jp.parse_jcl(src)
        m = compute_metrics(job)
        assert m.conditional_count == 2
        assert m.conditional_depth >= 1
        assert m.cyclomatic_score > 1

    def test_metrics_to_dict(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IEFBR14\n"
        job = jp.parse_jcl(src)
        d = compute_metrics(job).to_dict()
        assert d["job_name"] == "MYJOB"
        assert d["step_count"] == 1


# ---------------------------------------------------------------------------
# End-to-end smoke: everything works together
# ---------------------------------------------------------------------------


def test_smoke_parse_everything():
    src = (
        "//MYJOB    JOB  (ACCT),TIME=30,REGION=4M\n"
        "/*JOBPARM CLASS=A\n"
        "//MYOUT    OUTPUT DEST=REMOTE\n"
        "// EXPORT SYMLIST=(HLQ)\n"
        "// SET HLQ=PROD\n"
        "//STEP1    EXEC PGM=IDCAMS\n"
        "//SYSIN    DD *\n"
        "  DELETE PROD.OLD\n"
        "/*\n"
        "//SYSPRINT DD SYSOUT=A,OUTPUT=*.MYOUT\n"
        "//STEP2    EXEC PGM=DSNTEP2\n"
        "//SYSIN    DD *\n"
        "SELECT * FROM T;\n"
        "/*\n"
        "//SYSPRINT DD SYSOUT=*\n"
    )
    job = jp.parse_jcl(src)
    assert any(type(s).__name__ == "JobParmStatement" for s in job.jes_typed_statements)
    sysprint = job.steps[0].get_dd("SYSPRINT")
    assert len(sysprint.output_refs) == 1
    assert "HLQ" in job.exported_symbols
    assert [r for r in analyze_job(job) if r.program == "IDCAMS"]
    m = compute_metrics(job)
    assert m.step_count == 2
    findings = lint_job(job)
    codes = {f.error_code for f in findings}
    assert "JCL-LINT-004" not in codes
    assert "JCL-LINT-005" not in codes


# ---------------------------------------------------------------------------
# Regression tests for PR #18 review comments
# ---------------------------------------------------------------------------


class TestReviewFixes:
    """Covers the six Copilot review findings on PR #18."""

    def test_strict_mode_ignores_output_ref_warning(self):
        """Review #4: WARNING-severity findings must not fail strict_mode."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//REPORT   DD SYSOUT=A,OUTPUT=*.NOPE\n"
        )
        # Would raise if strict_mode treated the WARNING as fatal.
        job = jp.parse_jcl(src, strict_mode=True)
        # Warning is still emitted by the validator — just not fatal.
        errors = job.validate()
        assert any(e.error_code is None and "NOPE" in e.message for e in errors)

    def test_strict_mode_still_raises_on_real_errors(self):
        import pytest

        from jclparser.errors import JCLValidationError

        # Duplicate step names are an ERROR-severity structural issue.
        # STEP1 appears twice -> must still raise in strict_mode.
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
        )
        with pytest.raises(JCLValidationError):
            jp.parse_jcl(src, strict_mode=True)

    def test_explode_preserves_unresolved_output_refs(self):
        """Review #2: analysis fields must survive explosion."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//REPORT   DD SYSOUT=A,OUTPUT=*.NOPE\n"
        )
        job = jp.parse_jcl(src)
        assert job.unresolved_output_refs
        exploded = job.explode()
        assert exploded.unresolved_output_refs == job.unresolved_output_refs

    def test_explode_preserves_jes_typed_statements(self):
        src = "//MYJOB    JOB  (ACCT)\n/*JOBPARM CLASS=A\n//STEP1    EXEC PGM=IEFBR14\n"
        job = jp.parse_jcl(src)
        assert job.jes_typed_statements
        exploded = job.explode()
        assert len(exploded.jes_typed_statements) == len(job.jes_typed_statements)
        # Must be a copy, not a shared reference.
        assert exploded.jes_typed_statements is not job.jes_typed_statements

    def test_explode_preserves_sql_detections(self):
        from jclparser.plugins import ParserConfig

        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=DSNTEP2\n"
            "//SYSIN    DD *\n"
            "SELECT * FROM T;\n"
            "/*\n"
        )
        job = jp.parse_jcl(src, config=ParserConfig(detect_sql=True))
        assert "STEP1" in job.sql_detections
        exploded = job.explode()
        assert "STEP1" in exploded.sql_detections

    def test_lint_rule_crash_produces_tagged_finding(self):
        """Review #1: a crashing rule should yield a SEMANTIC_ERROR WARNING,
        not a generic ErrorType.VALIDATION_ERROR at severity ERROR."""
        from jclparser.errors import ErrorType, ErrorSeverity
        from jclparser.lint.base import LintRule
        from jclparser.lint import lint_job as _lint_job
        from jclparser.lint.runner import register_rule, unregister_rule

        class BoomRule(LintRule):
            code = "JCL-TEST-BOOM"
            description = "Always crashes"
            default_severity = ErrorSeverity.WARNING

            def check(self, job, config):
                raise RuntimeError("kaboom")

        rule = BoomRule()
        register_rule(rule)
        try:
            src = (
                "//MYJOB    JOB  (ACCT),TIME=60,REGION=4M\n"
                "//STEP1    EXEC PGM=IEFBR14\n"
            )
            job = jp.parse_jcl(src)
            findings = _lint_job(job)
            crash = [f for f in findings if "kaboom" in f.message]
            assert crash
            assert crash[0].error_code == "JCL-LINT-000"
            assert crash[0].error_type == ErrorType.SEMANTIC_ERROR
            assert crash[0].severity == ErrorSeverity.WARNING
        finally:
            unregister_rule(rule.code)
            # Also clean up JCL-LINT-000 if it somehow lingered
            unregister_rule("JCL-LINT-000")

    def test_lint_rule_crash_severity_overridable(self):
        from jclparser.errors import ErrorSeverity
        from jclparser.lint import LintConfig, lint_job as _lint_job
        from jclparser.lint.base import LintRule
        from jclparser.lint.runner import register_rule, unregister_rule

        class Boom2Rule(LintRule):
            code = "JCL-TEST-BOOM2"
            description = "crashes"
            default_severity = ErrorSeverity.WARNING

            def check(self, job, config):
                raise ValueError("bang")

        rule = Boom2Rule()
        register_rule(rule)
        try:
            src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IEFBR14\n"
            job = jp.parse_jcl(src)
            cfg = LintConfig(severities={"JCL-LINT-000": ErrorSeverity.INFO})
            findings = _lint_job(job, cfg)
            crash = [f for f in findings if "bang" in f.message]
            assert crash and crash[0].severity == ErrorSeverity.INFO
        finally:
            unregister_rule(rule.code)

    def test_rc_analysis_does_not_flag_unknown_only_condition(self):
        """Review #6: when every evaluation is None (unknown) the branch must
        not be marked unreachable.  We build a condition that references
        a step absent from the job — the AST's evaluate() returns None for
        every combination, which previously misled the pass."""
        from jclparser.condition_parser import parse_condition
        from jclparser.model import ConditionalBlock, Job, Step
        from jclparser.rc_analysis import compute_feasible_paths

        ast = parse_condition("GHOST.RC EQ 0")
        assert ast is not None  # sanity — the condition parses

        cond = ConditionalBlock(
            condition="GHOST.RC EQ 0",
            condition_ast=ast,
            line_number=5,
        )
        cond.then_steps.append(Step(name="INSIDE", program="IEFBR14"))

        job = Job(name="MYJOB", steps=[cond])
        report = compute_feasible_paths(job)
        assert "INSIDE" not in report.unreachable_steps

    def test_rc_analysis_still_flags_unsatisfiable(self):
        """Sanity: the conservative fix must not mask genuinely dead code."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=PROG1\n"
            "//         IF (STEP1.RC GT 100) THEN\n"
            "//DEAD     EXEC PGM=PROG2\n"
            "//         ENDIF\n"
        )
        job = jp.parse_jcl(src)
        report = compute_feasible_paths(job)
        assert "DEAD" in report.unreachable_steps

    def test_output_ref_docstring_matches_impl_on_qualified_non_star_form(self):
        """Review #3: a qualified STEP.PROCSTEP.N form *without* the leading
        ``*.`` must yield an empty list (not a spurious name) — docstring
        behaviour is now the contract."""
        assert _extract_output_ref_names("STEP.PROCSTEP.N") == []
        assert _extract_output_ref_names("*.STEP.PROCSTEP.N") == ["N"]
