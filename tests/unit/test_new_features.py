"""
Tests for the six new parser features:

1. Typed JOB parameter properties (NOTIFY, TYPRUN, RESTART, MSGCLASS, CLASS, etc.)
2. OutputStatement typed model
3. JOBLIB / STEPLIB dataset search order
4. Three-level condition references (STEP.PROCSTEP.RC)
5. INCLUDE statement resolution
6. Cross-step dataset lifecycle tracking
"""

import pytest
from jclparser import parse_jcl
from jclparser.condition_parser import parse_condition, ReturnCodeCondition, AbendCondition, RunCondition
from jclparser.include_loader import DictMemberLoader, resolve_includes, _extract_include_member
from jclparser.dataset_lifecycle import analyze_dataset_lifecycle, validate_dataset_lifecycle
from jclparser.model import OutputStatement


# ─────────────────────────────────────────────────────────────────────────────
# 1. Typed JOB parameter properties
# ─────────────────────────────────────────────────────────────────────────────


class TestJobParameterProperties:
    """Typed accessors for NOTIFY, TYPRUN, RESTART, MSGCLASS, CLASS, etc."""

    def _job(self, params: str):
        return parse_jcl(f"//TESTJOB JOB (ACCT),'USER',{params}\n//S1 EXEC PGM=IEFBR14\n")

    def test_notify(self):
        job = self._job("NOTIFY=JOEUSER")
        assert job.notify == "JOEUSER"

    def test_notify_absent(self):
        job = parse_jcl("//TESTJOB JOB (ACCT),'USER'\n//S1 EXEC PGM=IEFBR14\n")
        assert job.notify is None

    def test_typrun_scan(self):
        job = self._job("TYPRUN=SCAN")
        assert job.typrun == "SCAN"

    def test_typrun_hold(self):
        job = self._job("TYPRUN=HOLD")
        assert job.typrun == "HOLD"

    def test_restart(self):
        job = self._job("RESTART=STEP2")
        assert job.restart == "STEP2"

    def test_restart_star(self):
        job = self._job("RESTART=*")
        assert job.restart == "*"

    def test_msgclass(self):
        job = self._job("MSGCLASS=X")
        assert job.msgclass == "X"

    def test_job_class(self):
        job = self._job("CLASS=A")
        assert job.job_class == "A"

    def test_prty_integer(self):
        job = self._job("PRTY=8")
        assert job.prty == 8

    def test_prty_absent(self):
        job = parse_jcl("//TESTJOB JOB (ACCT),'USER'\n//S1 EXEC PGM=IEFBR14\n")
        assert job.prty is None

    def test_region(self):
        job = self._job("REGION=4M")
        assert job.region == "4M"

    def test_time_simple(self):
        job = self._job("TIME=1440")
        assert job.time is not None

    def test_time_paren(self):
        job = self._job("TIME=(2,30)")
        assert job.time is not None

    def test_msglevel(self):
        job = self._job("MSGLEVEL=(1,1)")
        assert job.msglevel is not None

    def test_cond(self):
        job = self._job("COND=(4,LT)")
        assert job.cond is not None

    def test_multiple_params_together(self):
        jcl = (
            "//PRODJOB JOB (ACCT),'PROD',\n"
            "//     CLASS=A,MSGCLASS=X,\n"
            "//     NOTIFY=OPS,TYPRUN=HOLD,\n"
            "//     REGION=8M,MSGLEVEL=(1,1)\n"
            "//S1   EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        assert job.job_class == "A"
        assert job.msgclass == "X"
        assert job.notify == "OPS"
        assert job.typrun == "HOLD"
        assert job.region == "8M"


# ─────────────────────────────────────────────────────────────────────────────
# 2. OutputStatement typed model
# ─────────────────────────────────────────────────────────────────────────────


class TestOutputStatement:
    """OutputStatement is a proper typed model, not a raw Statement."""

    def _job(self, output_line: str):
        return parse_jcl(
            f"//MYJOB  JOB (ACCT),'TEST'\n"
            f"{output_line}\n"
            f"//S1     EXEC PGM=IEFBR14\n"
        )

    def test_is_output_statement_instance(self):
        job = self._job("//OUT1   OUTPUT DEST=LOCAL,CLASS=A")
        stmt = job.output_statements[0]
        assert isinstance(stmt, OutputStatement)

    def test_type_attribute_still_output(self):
        job = self._job("//OUT1   OUTPUT DEST=LOCAL")
        assert job.output_statements[0].type == "OUTPUT"

    def test_dest(self):
        job = self._job("//OUT1   OUTPUT DEST=REMOTE")
        assert job.output_statements[0].dest == "REMOTE"

    def test_output_class(self):
        job = self._job("//OUT1   OUTPUT CLASS=B")
        assert job.output_statements[0].output_class == "B"

    def test_copies_as_int(self):
        job = self._job("//OUT1   OUTPUT COPIES=5")
        assert job.output_statements[0].copies == 5

    def test_copies_none_when_absent(self):
        job = self._job("//OUT1   OUTPUT DEST=LOCAL")
        assert job.output_statements[0].copies is None

    def test_forms(self):
        job = self._job("//OUT1   OUTPUT FORMS=STD")
        assert job.output_statements[0].forms == "STD"

    def test_writer(self):
        job = self._job("//OUT1   OUTPUT WRITER=MYWRITE")
        assert job.output_statements[0].writer == "MYWRITE"

    def test_outlim(self):
        job = self._job("//OUT1   OUTPUT OUTLIM=1000")
        assert job.output_statements[0].outlim == 1000

    def test_jesds(self):
        job = self._job("//OUT1   OUTPUT JESDS=ALL")
        assert job.output_statements[0].jesds == "ALL"

    def test_combined_params(self):
        job = self._job("//OUTDD  OUTPUT DEST=LOCAL,CLASS=A,COPIES=2,FORMS=STD")
        stmt = job.output_statements[0]
        assert stmt.dest == "LOCAL"
        assert stmt.output_class == "A"
        assert stmt.copies == 2
        assert stmt.forms == "STD"

    def test_name_preserved(self):
        job = self._job("//MYOUT  OUTPUT DEST=LOCAL")
        assert job.output_statements[0].name == "MYOUT"

    def test_line_number_positive(self):
        job = self._job("//OUT1   OUTPUT DEST=LOCAL")
        assert job.output_statements[0].line_number > 0

    def test_from_statement_classmethod(self):
        from jclparser.model import Statement
        raw = Statement(type="OUTPUT", name="X", parameters={"DEST": "LOCAL"}, line_number=5)
        out = OutputStatement.from_statement(raw)
        assert out.name == "X"
        assert out.dest == "LOCAL"
        assert out.line_number == 5


# ─────────────────────────────────────────────────────────────────────────────
# 3. JOBLIB / STEPLIB dataset search order
# ─────────────────────────────────────────────────────────────────────────────


class TestJOBLIBSTEPLIB:
    """JOBLIB and STEPLIB tracking and library search order."""

    def test_joblib_single_dataset(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//JOBLIB  DD DSN=SYS2.LOADLIB,DISP=SHR\n"
            "//S1      EXEC PGM=MYPROG\n"
        )
        job = parse_jcl(jcl)
        assert job.joblib == ["SYS2.LOADLIB"]

    def test_joblib_concatenation(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//JOBLIB  DD DSN=SYS2.LOADLIB,DISP=SHR\n"
            "//         DD DSN=USER.LOADLIB,DISP=SHR\n"
            "//S1      EXEC PGM=MYPROG\n"
        )
        job = parse_jcl(jcl)
        assert job.joblib == ["SYS2.LOADLIB", "USER.LOADLIB"]

    def test_joblib_three_way_concatenation(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//JOBLIB  DD DSN=LIB1,DISP=SHR\n"
            "//         DD DSN=LIB2,DISP=SHR\n"
            "//         DD DSN=LIB3,DISP=SHR\n"
            "//S1      EXEC PGM=MYPROG\n"
        )
        job = parse_jcl(jcl)
        assert job.joblib == ["LIB1", "LIB2", "LIB3"]

    def test_joblib_empty_when_absent(self):
        jcl = "//MYJOB  JOB (ACCT),'USER'\n//S1 EXEC PGM=IEFBR14\n"
        job = parse_jcl(jcl)
        assert job.joblib == []

    def test_steplib_on_step(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1     EXEC PGM=MYPROG\n"
            "//STEPLIB  DD DSN=USER.LOADLIB,DISP=SHR\n"
        )
        job = parse_jcl(jcl)
        step = job.get_step("S1")
        assert step.steplib == ["USER.LOADLIB"]

    def test_steplib_concatenation(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1     EXEC PGM=MYPROG\n"
            "//STEPLIB  DD DSN=USER.LOADLIB,DISP=SHR\n"
            "//           DD DSN=SYS2.LOADLIB,DISP=SHR\n"
        )
        job = parse_jcl(jcl)
        step = job.get_step("S1")
        assert step.steplib == ["USER.LOADLIB", "SYS2.LOADLIB"]

    def test_steplib_concatenation_search_order(self):
        """STEPLIB concat all appear in get_library_search_order, not JOBLIB."""
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//JOBLIB  DD DSN=JOBLIB.DS,DISP=SHR\n"
            "//S1     EXEC PGM=MYPROG\n"
            "//STEPLIB  DD DSN=STEPLIB1,DISP=SHR\n"
            "//           DD DSN=STEPLIB2,DISP=SHR\n"
        )
        job = parse_jcl(jcl)
        order = job.get_library_search_order("S1")
        assert order == ["STEPLIB1", "STEPLIB2"]

    def test_steplib_empty_when_absent(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1     EXEC PGM=IEFBR14\n"
        )
        job = parse_jcl(jcl)
        step = job.get_step("S1")
        assert step.steplib == []

    def test_library_search_order_steplib_overrides_joblib(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//JOBLIB  DD DSN=SYS2.LOADLIB,DISP=SHR\n"
            "//S1     EXEC PGM=MYPROG\n"
            "//STEPLIB  DD DSN=USER.LOADLIB,DISP=SHR\n"
        )
        job = parse_jcl(jcl)
        order = job.get_library_search_order("S1")
        assert order == ["USER.LOADLIB"]

    def test_library_search_order_falls_back_to_joblib(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//JOBLIB  DD DSN=SYS2.LOADLIB,DISP=SHR\n"
            "//S1     EXEC PGM=MYPROG\n"
        )
        job = parse_jcl(jcl)
        order = job.get_library_search_order("S1")
        assert order == ["SYS2.LOADLIB"]

    def test_library_search_order_empty_without_either(self):
        jcl = "//MYJOB  JOB (ACCT),'USER'\n//S1 EXEC PGM=IEFBR14\n"
        job = parse_jcl(jcl)
        assert job.get_library_search_order("S1") == []

    def test_library_search_order_unknown_step(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//JOBLIB  DD DSN=SYS2.LOADLIB,DISP=SHR\n"
            "//S1      EXEC PGM=MYPROG\n"
        )
        job = parse_jcl(jcl)
        order = job.get_library_search_order("NOSUCHSTEP")
        assert order == ["SYS2.LOADLIB"]

    def test_joblib_dds_stored_separately(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//JOBLIB  DD DSN=SYS2.LOADLIB,DISP=SHR\n"
            "//S1      EXEC PGM=MYPROG\n"
        )
        job = parse_jcl(jcl)
        assert len(job.joblib_dds) == 1
        assert job.joblib_dds[0].name == "JOBLIB"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Three-level condition references
# ─────────────────────────────────────────────────────────────────────────────


class TestThreeLevelConditionRef:
    """PROC.STEP.RC, PROC.STEP.ABEND, PROC.STEP.RUN conditions."""

    def test_three_level_rc_parses(self):
        node = parse_condition("OUTERST.INNERST.RC EQ 0")
        assert node is not None

    def test_three_level_rc_is_return_code_condition(self):
        node = parse_condition("OUTERST.INNERST.RC EQ 4")
        assert isinstance(node, ReturnCodeCondition)

    def test_three_level_step_name_is_qualified(self):
        node = parse_condition("OUTERST.INNERST.RC EQ 0")
        assert node.step_name == "OUTERST.INNERST"
        assert node.operator == "EQ"
        assert node.value == 0

    def test_three_level_abend_parses(self):
        node = parse_condition("OUTERST.INNERST.ABEND")
        assert isinstance(node, AbendCondition)
        assert node.step_name == "OUTERST.INNERST"

    def test_three_level_run_parses(self):
        node = parse_condition("OUTERST.INNERST.RUN")
        assert isinstance(node, RunCondition)
        assert node.step_name == "OUTERST.INNERST"

    def test_three_level_evaluate_with_matching_key(self):
        node = parse_condition("OUTERST.INNERST.RC EQ 0")
        result = node.evaluate({"OUTERST.INNERST": (0, False)})
        assert result is True

    def test_three_level_evaluate_non_matching(self):
        node = parse_condition("OUTERST.INNERST.RC EQ 0")
        result = node.evaluate({"OUTERST.INNERST": (4, False)})
        assert result is False

    def test_three_level_evaluate_missing_step_returns_none(self):
        node = parse_condition("OUTERST.INNERST.RC EQ 0")
        result = node.evaluate({})
        assert result is None

    def test_three_level_in_compound_expression(self):
        node = parse_condition("OUTERST.INNERST.RC EQ 0 AND NOT STEP2.ABEND")
        assert node is not None

    def test_three_level_with_various_operators(self):
        for op, val, rc, expected in [
            ("NE", 4, 0, True),
            ("LT", 4, 0, True),
            ("GT", 0, 4, True),
            ("LE", 4, 4, True),
            ("GE", 0, 0, True),
        ]:
            node = parse_condition(f"OUTER.INNER.RC {op} {val}")
            assert node is not None
            result = node.evaluate({"OUTER.INNER": (rc, False)})
            assert result is expected, f"op={op} val={val} rc={rc}"

    def test_two_level_still_works(self):
        node = parse_condition("STEP1.RC EQ 0")
        assert node is not None
        assert isinstance(node, ReturnCodeCondition)
        assert node.step_name == "STEP1"

    def test_parser_captures_three_level_condition_in_job(self):
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1     EXEC PGM=IEFBR14\n"
            "// IF OUTER.INNER.RC EQ 0 THEN\n"
            "//S2     EXEC PGM=IEFBR14\n"
            "// ENDIF\n"
        )
        job = parse_jcl(jcl)
        assert len(job.conditionals) == 1
        cond = job.conditionals[0]
        assert cond.condition_ast is not None


# ─────────────────────────────────────────────────────────────────────────────
# 5. INCLUDE statement resolution
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractIncludeMember:
    """Unit tests for _extract_include_member helper."""

    def test_basic(self):
        assert _extract_include_member("// INCLUDE MEMBER=MYMBR") == "MYMBR"

    def test_with_label(self):
        assert _extract_include_member("//INCL1  INCLUDE MEMBER=COMMON") == "COMMON"

    def test_parenthesised(self):
        assert _extract_include_member("// INCLUDE MEMBER=(MYMBR)") == "MYMBR"

    def test_case_insensitive_keyword(self):
        assert _extract_include_member("// include member=mymbr") == "MYMBR"

    def test_not_include_returns_none(self):
        assert _extract_include_member("//S1  EXEC PGM=IEFBR14") is None

    def test_empty_line_returns_none(self):
        assert _extract_include_member("") is None

    # Regression tests for the no-space form (//INCLUDE MEMBER=...)
    def test_no_space_after_slashes(self):
        """//INCLUDE MEMBER=... — INCLUDE is the operation, not a label."""
        assert _extract_include_member("//INCLUDE MEMBER=MYMBR") == "MYMBR"

    def test_comment_line_returns_none(self):
        assert _extract_include_member("//* INCLUDE MEMBER=XXX") is None

    def test_dsn_containing_include_returns_none(self):
        assert _extract_include_member("//DD1 DD DSN=MY.INCLUDE.LIB,DISP=SHR") is None


class TestResolveIncludes:
    """Tests for the resolve_includes pre-processing function."""

    def test_single_include_expanded(self):
        loader = DictMemberLoader({"COMMON": "//S2 EXEC PGM=SORT\n"})
        src = "//S1 EXEC PGM=IEFBR14\n// INCLUDE MEMBER=COMMON\n"
        result = resolve_includes(src, loader)
        assert "//S2 EXEC PGM=SORT" in result
        assert "INCLUDE" not in result

    def test_unresolvable_include_left_intact(self):
        loader = DictMemberLoader({})
        src = "//S1 EXEC PGM=IEFBR14\n// INCLUDE MEMBER=MISSING\n"
        result = resolve_includes(src, loader)
        assert "INCLUDE" in result

    def test_nested_include_expanded(self):
        loader = DictMemberLoader({
            "OUTER": "// INCLUDE MEMBER=INNER\n",
            "INNER": "//S3 EXEC PGM=SORT\n",
        })
        src = "// INCLUDE MEMBER=OUTER\n"
        result = resolve_includes(src, loader)
        assert "//S3 EXEC PGM=SORT" in result

    def test_max_depth_prevents_infinite_recursion(self):
        loader = DictMemberLoader({"SELF": "// INCLUDE MEMBER=SELF\n"})
        src = "// INCLUDE MEMBER=SELF\n"
        # Should not raise; result may contain the unresolved INCLUDE after depth exceeded
        result = resolve_includes(src, loader, max_depth=3)
        assert result is not None

    def test_non_include_lines_preserved(self):
        loader = DictMemberLoader({"M": "//STEP2 EXEC PGM=X\n"})
        src = "//* COMMENT\n//S1 EXEC PGM=Y\n// INCLUDE MEMBER=M\n"
        result = resolve_includes(src, loader)
        assert "//* COMMENT" in result
        assert "//S1 EXEC PGM=Y" in result


class TestIncludeInParser:
    """End-to-end: INCLUDE is resolved before the parse loop."""

    def test_included_exec_step_appears_in_job(self):
        loader = DictMemberLoader({
            "COMMON": "//COMSTEP EXEC PGM=IEFBR14\n"
        })
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1     EXEC PGM=IEFBR14\n"
            "// INCLUDE MEMBER=COMMON\n"
        )
        job = parse_jcl(jcl, include_loader=loader)
        step_names = [s.name for s in job.steps]
        assert "COMSTEP" in step_names

    def test_included_member_name_still_in_job_includes(self):
        loader = DictMemberLoader({"COMMON": "//COMSTEP EXEC PGM=IEFBR14\n"})
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1     EXEC PGM=IEFBR14\n"
            "// INCLUDE MEMBER=COMMON\n"
        )
        job = parse_jcl(jcl, include_loader=loader)
        # The INCLUDE statement itself is parsed but the member content is inlined
        # so no unresolved INCLUDE step appears — check that COMSTEP was inlined
        assert job.get_step("COMSTEP") is not None

    def test_no_space_include_form_resolved(self):
        """//INCLUDE MEMBER=... (no leading space) is expanded correctly."""
        loader = DictMemberLoader({"COMMON": "//COMSTEP EXEC PGM=IEFBR14\n"})
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1     EXEC PGM=IEFBR14\n"
            "//INCLUDE MEMBER=COMMON\n"
        )
        job = parse_jcl(jcl, include_loader=loader)
        assert job.get_step("COMSTEP") is not None

    def test_unresolvable_include_does_not_crash(self):
        loader = DictMemberLoader({})
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1     EXEC PGM=IEFBR14\n"
            "// INCLUDE MEMBER=MISSING\n"
        )
        # Should not raise; INCLUDE line is left intact and treated as INCLUDE stmt
        job = parse_jcl(jcl, include_loader=loader)
        assert job.name == "MYJOB"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Cross-step dataset lifecycle tracking
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetLifecycleAnalysis:
    """analyze_dataset_lifecycle builds per-dataset event log."""

    def _job(self, steps_jcl: str):
        return parse_jcl(f"//MYJOB  JOB (ACCT),'USER'\n{steps_jcl}")

    def test_single_allocation_recorded(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=MY.DATA,DISP=(NEW,CATLG,DELETE)\n"
        )
        events = analyze_dataset_lifecycle(self._job(jcl))
        assert "MY.DATA" in events
        assert events["MY.DATA"][0].action == "ALLOCATE"

    def test_open_old_recorded(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=MY.DATA,DISP=OLD\n"
        )
        events = analyze_dataset_lifecycle(self._job(jcl))
        assert events["MY.DATA"][0].action == "OPEN_EXCLUSIVE"

    def test_open_shr_recorded(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=MY.DATA,DISP=SHR\n"
        )
        events = analyze_dataset_lifecycle(self._job(jcl))
        assert events["MY.DATA"][0].action == "OPEN_SHARED"

    def test_extend_recorded(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=MY.DATA,DISP=(MOD,KEEP)\n"
        )
        events = analyze_dataset_lifecycle(self._job(jcl))
        assert events["MY.DATA"][0].action == "EXTEND"

    def test_multi_step_lifecycle(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=MY.DATA,DISP=(NEW,CATLG,DELETE)\n"
            "//S2  EXEC PGM=IEFBR14\n"
            "//DD2   DD DSN=MY.DATA,DISP=SHR\n"
        )
        events = analyze_dataset_lifecycle(self._job(jcl))
        assert len(events["MY.DATA"]) == 2
        assert events["MY.DATA"][0].action == "ALLOCATE"
        assert events["MY.DATA"][1].action == "OPEN_SHARED"

    def test_normal_disp_captured(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=MY.DATA,DISP=(NEW,CATLG,DELETE)\n"
        )
        events = analyze_dataset_lifecycle(self._job(jcl))
        evt = events["MY.DATA"][0]
        assert evt.disp_normal == "CATLG"
        assert evt.disp_abnormal == "DELETE"

    def test_dsn_key_is_uppercase(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=My.Dataset,DISP=SHR\n"
        )
        events = analyze_dataset_lifecycle(self._job(jcl))
        assert "MY.DATASET" in events

    def test_dd_without_dsn_ignored(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//SYSOUT  DD SYSOUT=*\n"
        )
        events = analyze_dataset_lifecycle(self._job(jcl))
        assert events == {}


class TestDatasetLifecycleValidation:
    """validate_dataset_lifecycle detects lifecycle errors."""

    def _job(self, steps_jcl: str):
        return parse_jcl(f"//MYJOB  JOB (ACCT),'USER'\n{steps_jcl}")

    def test_no_errors_for_clean_job(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=MY.DATA,DISP=(NEW,CATLG,DELETE)\n"
            "//S2  EXEC PGM=IEFBR14\n"
            "//DD2   DD DSN=MY.DATA,DISP=SHR\n"
        )
        errors = validate_dataset_lifecycle(self._job(jcl))
        assert errors == []

    def test_duplicate_catlg_flagged(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=DUP.DS,DISP=(NEW,CATLG,DELETE)\n"
            "//S2  EXEC PGM=IEFBR14\n"
            "//DD2   DD DSN=DUP.DS,DISP=(NEW,CATLG,DELETE)\n"
        )
        errors = validate_dataset_lifecycle(self._job(jcl))
        assert len(errors) >= 1
        assert any("DUP.DS" in e.message for e in errors)

    def test_use_after_uncatalog_flagged(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=MY.DATA,DISP=(NEW,CATLG,DELETE)\n"
            "//S2  EXEC PGM=IEFBR14\n"
            "//DD2   DD DSN=MY.DATA,DISP=(OLD,UNCATLG)\n"
            "//S3  EXEC PGM=IEFBR14\n"
            "//DD3   DD DSN=MY.DATA,DISP=OLD\n"
        )
        errors = validate_dataset_lifecycle(self._job(jcl))
        assert any("MY.DATA" in e.message for e in errors)

    def test_forward_reference_flagged(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=FWD.DATA,DISP=OLD\n"
            "//S2  EXEC PGM=IEFBR14\n"
            "//DD2   DD DSN=FWD.DATA,DISP=(NEW,CATLG,DELETE)\n"
        )
        errors = validate_dataset_lifecycle(self._job(jcl))
        assert any("FWD.DATA" in e.message for e in errors)

    def test_temp_datasets_not_double_checked(self):
        jcl = (
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=&&TEMP,DISP=(NEW,PASS)\n"
            "//S2  EXEC PGM=IEFBR14\n"
            "//DD2   DD DSN=&&TEMP,DISP=(OLD,DELETE)\n"
        )
        # validate_dataset_lifecycle should not flag &&TEMP — leave that to
        # the existing validate_data_dependencies check
        errors = validate_dataset_lifecycle(self._job(jcl))
        assert all("&&TEMP" not in e.message for e in errors)

    def test_validate_dataset_lifecycle_integrated_via_job_validate(self):
        """lifecycle errors are surfaced through Job.validate()."""
        jcl = (
            "//MYJOB  JOB (ACCT),'USER'\n"
            "//S1  EXEC PGM=IEFBR14\n"
            "//DD1   DD DSN=DUP.DS,DISP=(NEW,CATLG,DELETE)\n"
            "//S2  EXEC PGM=IEFBR14\n"
            "//DD2   DD DSN=DUP.DS,DISP=(NEW,CATLG,DELETE)\n"
        )
        job = parse_jcl(jcl)
        errs = job.validate()
        assert any("DUP.DS" in e.message for e in errs)
