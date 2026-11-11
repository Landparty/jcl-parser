"""Regression tests for the bugs found by the 2026-11-10/11 bug hunts.

Passes 3 to 21 (everything reported after #192 and #193 landed).
"""

from __future__ import annotations

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl
from jclparser.errors import ErrorSeverity

pytestmark = pytest.mark.unit

_JOB = "//J JOB (A),'X'\n"


def _messages(jcl: str, level: str = "semantic", **kwargs: object) -> list[str]:
    return [e.message for e in validate_jcl(jcl, level=level, **kwargs)]


def _has(messages: list[str], fragment: str) -> bool:
    return any(fragment in m for m in messages)


# ---------------------------------------------------------------------------
# Pass 3
# ---------------------------------------------------------------------------


class TestOverlongRecord:
    """A statement record over 80 columns is read whole and reported."""

    JCL = _JOB + (
        "//S1 EXEC PGM=A\n"
        "//O DD DSN=A.B,DISP=(NEW,CATLG),UNIT=SYSDA,VOL=SER=ABCDEF,"
        "LABEL=RETPD=30,MGMTCLAS=STANDARD\n"
    )

    def test_operands_past_column_71_kept(self):
        dd = parse_jcl(self.JCL).steps[0].dd_statements[0]
        assert dd.parameters["LABEL"] == "RETPD=30"
        assert dd.parameters["MGMTCLAS"] == "STANDARD"

    def test_reported_by_validate(self):
        findings = validate_jcl(self.JCL, level="semantic")
        assert [(f.line_number, f.severity) for f in findings] == [
            (3, ErrorSeverity.WARNING)
        ]
        assert "90 characters long" in findings[0].message

    def test_card_image_with_trailing_blanks_still_cut(self):
        card = "//S1 EXEC PGM=A".ljust(72) + "00000010" + "    "
        job = parse_jcl(_JOB + card + "\n")
        assert job.steps[0].program == "A"
        assert job.statement_findings == []

    def test_overlong_comment_not_reported(self):
        jcl = _JOB + "//* " + "x" * 90 + "\n//S1 EXEC PGM=A\n"
        assert parse_jcl(jcl).statement_findings == []


class TestNestedProcDefinition:
    """A PROC inside an in-stream PROC, and a PEND with no PROC."""

    JCL = _JOB + ("//P PROC\n//Q PROC\n//S EXEC PGM=X\n// PEND\n// PEND\n//R EXEC P\n")

    def test_nested_proc_and_stray_pend_are_errors(self):
        findings = [(e.line_number, e.message) for e in validate_jcl(self.JCL)]
        assert findings == [
            (
                3,
                (
                    "PROC Q is defined inside in-stream PROC P; procedure "
                    "definitions cannot be nested (add a PEND before it)"
                ),
            ),
            (6, "PEND statement with no PROC to end"),
        ]

    def test_stray_pend_alone(self):
        jcl = _JOB + "//S EXEC PGM=X\n// PEND\n"
        assert _messages(jcl, "basic") == ["PEND statement with no PROC to end"]

    def test_proc_member_pend_not_flagged(self):
        assert _messages("//P PROC\n//S EXEC PGM=X\n// PEND\n") == []


class TestMalformedIf:
    def test_if_without_then_is_an_error(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n// IF RC=0\n//S2 EXEC PGM=B\n// ENDIF\n"
        assert _messages(jcl, "basic") == [
            (
                "IF statement has no THEN; the relational expression must be "
                "followed by THEN"
            )
        ]

    def test_then_after_closing_paren_accepted(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n// IF (RC=0)THEN\n//S2 EXEC PGM=B\n// ENDIF\n"
        job = parse_jcl(jcl)
        assert job.statement_findings == []
        assert job.steps[1].condition == "(RC=0)"

    def test_unreadable_condition_warned_and_unanalysed(self):
        from jclparser.rc_analysis import compute_feasible_paths

        jcl = _JOB + "//S1 EXEC PGM=A\n// IF RC=FOO THEN\n//S2 EXEC PGM=B\n// ENDIF\n"
        findings = validate_jcl(jcl, level="semantic")
        assert [(f.severity, f.message) for f in findings] == [
            (
                ErrorSeverity.WARNING,
                (
                    "IF condition 'RC=FOO' is not a valid relational expression; "
                    "the steps under it are treated as possibly running"
                ),
            )
        ]
        report = compute_feasible_paths(parse_jcl(jcl))
        assert [c for c, _ in report.unanalysed_conditions] == ["RC=FOO"]

    def test_abendcc_not_warned(self):
        jcl = (
            _JOB
            + "//S1 EXEC PGM=A\n// IF S1.ABENDCC=S0C4 THEN\n//S2 EXEC PGM=B\n"
            + "// ENDIF\n"
        )
        assert _messages(jcl) == []


class TestStepReferences:
    def test_if_naming_missing_step(self):
        jcl = (
            _JOB + "//S1 EXEC PGM=A\n// IF NOPE.RC=0 THEN\n//S2 EXEC PGM=B\n// ENDIF\n"
        )
        assert _messages(jcl) == [
            "IF condition names step NOPE, which is not a step coded before it"
        ]

    def test_cond_naming_later_step(self):
        jcl = _JOB + "//S1 EXEC PGM=A,COND=(0,NE,S2)\n//S2 EXEC PGM=B\n"
        assert _messages(jcl) == [
            "COND on step S1 names step S2, which is not a step coded before it"
        ]

    def test_references_to_earlier_steps_accepted(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=A\n//S2 EXEC PGM=B,COND=(4,LT,S1)\n"
            "// IF S1.RC=0 & S2.PS1.RUN THEN\n//S3 EXEC PGM=C\n// ENDIF\n"
        )
        assert _messages(jcl) == []


class TestGdgGeneration:
    def test_out_of_range_generation(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n//G DD DSN=A.G(+1000),DISP=(NEW,CATLG)\n"
        assert _has(_messages(jcl), "relative generation +1000 of A.G(+1000)")

    def test_over_classic_limit_is_a_warning(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n//G DD DSN=A.G(+256),DISP=(NEW,CATLG)\n"
        (finding,) = validate_jcl(jcl, level="semantic")
        assert finding.severity == ErrorSeverity.WARNING
        assert "exceeds 255" in finding.message

    def test_new_generation_read_before_created(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n//G DD DSN=A.G(+1),DISP=SHR\n"
        assert _messages(jcl) == [
            (
                "A.G(+1) is read with DISP=SHR on DD G, but no earlier step of the "
                "job creates generation (+1)"
            )
        ]

    def test_new_generation_read_after_created(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=A\n"
            "//G DD DSN=A.G(+1),DISP=(NEW,CATLG),UNIT=SYSDA,SPACE=(TRK,1)\n"
            "//S2 EXEC PGM=B\n//G DD DSN=A.G(+1),DISP=SHR\n"
        )
        assert not _has(_messages(jcl), "no earlier step")


# ---------------------------------------------------------------------------
# Pass 4
# ---------------------------------------------------------------------------


class TestTrailingCommaBeforeNamelessStatement:
    @pytest.mark.parametrize(
        "record",
        [
            "// SET X=1",
            "// INCLUDE MEMBER=X",
            "// DD DSN=B,DISP=SHR",
            "// ENDIF",
            "// ELSE",
            "// PEND",
        ],
    )
    def test_statement_not_swallowed(self, record):
        jcl = _JOB + f"//S1 EXEC PGM=A\n//D DD DSN=A,\n{record}\n//S2 EXEC PGM=B\n"
        job = parse_jcl(jcl)
        assert job.steps[0].dd_statements[0].parameters == {"DSN": "A"}
        assert any(
            "statement ends with a comma" in message and line == 3
            for line, message, _ in job.statement_findings
        )

    def test_set_still_applies(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n//D DD DSN=A,\n// SET X=1\n//S2 EXEC PGM=B\n"
        assert parse_jcl(jcl).set_statements == {"X": "1"}

    def test_pend_still_closes_proc(self):
        jcl = _JOB + ("//P PROC\n//S EXEC PGM=A\n//D DD DSN=A,\n// PEND\n//R EXEC P\n")
        job = explode_job(parse_jcl(jcl))
        assert [s.name for s in job.steps] == ["R.S"]

    def test_real_continuation_still_merged(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n//D DD DSN=A,\n//   DISP=SHR\n"
        dd = parse_jcl(jcl).steps[0].dd_statements[0]
        assert dd.parameters == {"DSN": "A", "DISP": "SHR"}


class TestSymbolInsideCodedGroup:
    def test_dcb_group_rescanned(self):
        jcl = (
            _JOB
            + "// SET X='RECFM=FB,LRECL=80'\n//S1 EXEC PGM=A\n"
            + "//D DD DSN=A,DISP=SHR,DCB=(&X,BLKSIZE=0)\n"
        )
        dd = parse_jcl(jcl).steps[0].dd_statements[0]
        assert dd.parameters["DCB"] == ["RECFM=FB", "LRECL=80", "BLKSIZE=0"]
        assert dd.dcb.subparameters["LRECL"] == "80"

    def test_acct_group_rescanned(self):
        jcl = _JOB + "// SET A='1,2'\n//S1 EXEC PGM=A,ACCT=(&A)\n"
        assert parse_jcl(jcl).steps[0].parameters["ACCT"] == ["1", "2"]

    def test_through_proc(self):
        jcl = _JOB + (
            "//P PROC X='RECFM=FB,LRECL=80'\n//S EXEC PGM=A\n"
            "//D DD DSN=A,DISP=SHR,DCB=(&X)\n// PEND\n//R EXEC P\n"
        )
        step = explode_job(parse_jcl(jcl)).steps[0]
        assert step.dd_statements[0].parameters["DCB"] == ["RECFM=FB", "LRECL=80"]


class TestDdBeforeExecInProc:
    def test_in_stream_proc(self):
        jcl = _JOB + "//P PROC\n//D DD DUMMY\n//S EXEC PGM=A\n// PEND\n//R EXEC P\n"
        assert _messages(jcl, "basic") == [
            (
                "DD D comes before the first EXEC of PROC P (it is attached to the "
                "procedure's first step, if it has one)"
            )
        ]


# ---------------------------------------------------------------------------
# Pass 5
# ---------------------------------------------------------------------------


class TestJcllibPlacement:
    def test_after_exec(self):
        jcl = _JOB + "//R EXEC PGM=X\n//L JCLLIB ORDER=B.LIB\n"
        assert _messages(jcl, "basic") == [
            "JCLLIB statement comes after the first EXEC; it must come before it"
        ]

    def test_second_jcllib(self):
        jcl = _JOB + (
            "//L JCLLIB ORDER=A.LIB\n//L2 JCLLIB ORDER=B.LIB\n//R EXEC PGM=X\n"
        )
        assert _messages(jcl, "basic") == [
            "second JCLLIB statement (the first is on line 2); a job may have only one"
        ]

    def test_one_jcllib_before_exec_accepted(self):
        assert _messages(_JOB + "//L JCLLIB ORDER=A.LIB\n//R EXEC PGM=X\n") == []


class TestInstreamSymbols:
    JCL = "//J1 JOB (A),'X'\n" + (
        "// EXPORT SYMLIST=(H)\n// SET H=PROD\n// SET Q=SECRET\n"
        "//S EXEC PGM=IDCAMS\n//SYSIN DD *,SYMBOLS=JCLONLY\n"
        "  DEFINE CLUSTER (NAME(&H..KSDS)) &Q\n/*\n"
    )

    def test_exported_symbols_substituted(self):
        dd = parse_jcl(self.JCL).steps[0].dd_statements[0]
        # Q is not exported, so it stays as coded.
        assert dd.inline_data == "  DEFINE CLUSTER (NAME(PROD.KSDS)) &Q"

    def test_lineage_sees_the_dataset(self):
        from jclparser.program_profiles.idcams import idcams_dataset_uses

        step = parse_jcl(self.JCL).steps[0]
        assert idcams_dataset_uses(step) == [("write", "PROD.KSDS", "SYSIN")]

    def test_without_symbols_keyword_untouched(self):
        jcl = self.JCL.replace(",SYMBOLS=JCLONLY", "")
        dd = parse_jcl(jcl).steps[0].dd_statements[0]
        assert "&H..KSDS" in dd.inline_data

    def test_symlist_star_and_proc_body(self):
        jcl = "//J1 JOB (A),'X'\n" + (
            "// EXPORT SYMLIST=*\n// SET H=PROD\n//P PROC\n//S EXEC PGM=IDCAMS\n"
            "//SYSIN DD *,SYMBOLS=(EXECSYS,LOG)\n  NAME(&H..X)\n/*\n// PEND\n"
            "//R EXEC P\n"
        )
        dd = explode_job(parse_jcl(jcl)).steps[0].dd_statements[0]
        assert dd.inline_data == "  NAME(PROD.X)"


class TestIdcamsPlusContinuation:
    def test_name_split_with_plus(self):
        from jclparser.program_profiles.idcams import idcams_dataset_uses

        jcl = _JOB + (
            "//S EXEC PGM=IDCAMS\n//SYSIN DD *\n"
            "  DEFINE CLUSTER (NAME(A.K+\n  SDS) -\n  INDEXED)\n/*\n"
        )
        step = parse_jcl(jcl).steps[0]
        assert idcams_dataset_uses(step) == [("write", "A.KSDS", "SYSIN")]


# ---------------------------------------------------------------------------
# Pass 6
# ---------------------------------------------------------------------------


class TestCommentAfterContinuedQuote:
    def _step(self, second: str):
        jcl = _JOB + "//S EXEC PGM=A,PARM='AAA,\n" + second + "\n"
        return parse_jcl(jcl).steps[0]

    def test_comment_stripped(self):
        step = self._step("//             BBB'   COMMENT")
        assert step.parameters["PARM"] == "AAA,BBB"

    def test_operand_after_string(self):
        step = self._step("//             BBB',REGION=4M   COMMENT")
        assert step.parameters == {"PARM": "AAA,BBB", "REGION": "4M"}

    def test_doubled_apostrophe(self):
        step = self._step("//             B''B'   COMMENT")
        assert step.parameters["PARM"] == "AAA,B'B"

    def test_blank_inside_string_kept(self):
        step = self._step("//             B B'")
        assert step.parameters["PARM"] == "AAA,B B"

    def test_card_image(self):
        first = "//S EXEC PGM=A,PARM='AAA,".ljust(71) + "X" + "00000020"
        jcl = _JOB + first + "\n//             BBB'   COMMENT\n"
        parm = parse_jcl(jcl).steps[0].parameters["PARM"]
        assert parm.endswith("BBB") and "COMMENT" not in parm

    def test_job_field(self):
        jcl = "//J JOB (A),'SMITH,\n//   JOHN',CLASS=A   CMT\n//S EXEC PGM=A\n"
        assert parse_jcl(jcl).job_class == "A"

    def test_path_operand(self):
        jcl = _JOB + (
            "//S EXEC PGM=A\n//D DD PATH='/u/a,\n//   b',PATHOPTS=ORDONLY   COMMENT\n"
        )
        dd = parse_jcl(jcl).steps[0].dd_statements[0]
        assert dd.parameters["PATHOPTS"] == "ORDONLY"


# ---------------------------------------------------------------------------
# Pass 7
# ---------------------------------------------------------------------------


class TestParenthesisedProgramName:
    @pytest.mark.parametrize(
        ("operand", "message"),
        [
            ("PGM=(A,B)", "EXEC PGM= must name one program, got (A,B)"),
            ("PROC=(A,B)", "EXEC PROC= must name one procedure, got (A,B)"),
            ("(A,B)", "EXEC PROC= must name one procedure, got (A,B)"),
        ],
    )
    def test_clean_error(self, operand, message):
        from jclparser.errors import JCLSyntaxError

        jcl = _JOB + f"//S EXEC {operand}\n"
        with pytest.raises(JCLSyntaxError, match=r"must name one"):
            parse_jcl(jcl)
        assert _messages(jcl) == [message]


# ---------------------------------------------------------------------------
# Pass 8
# ---------------------------------------------------------------------------


class TestEmptySource:
    @pytest.mark.parametrize("source", ["", "//* only comment\n"])
    def test_validate_reports_missing_job(self, source):
        assert _messages(source) == ["No JOB statement found"]

    def test_validate_paths_fails_empty_file(self, tmp_path):
        from jclparser.checks import validate_paths

        (tmp_path / "empty.jcl").write_text("")
        (report,) = validate_paths([tmp_path])
        assert [f.message for f in report.findings] == ["No JOB statement found"]

    def test_proc_member_still_passes(self):
        assert _messages("//P PROC\n//S EXEC PGM=X\n") == []


# ---------------------------------------------------------------------------
# Pass 9
# ---------------------------------------------------------------------------


def _include_chain(levels: int) -> dict[str, str]:
    members = {f"M{i}": f"// INCLUDE MEMBER=M{i + 1}\n" for i in range(levels - 1)}
    members[f"M{levels - 1}"] = "//S EXEC PGM=Z\n"
    return members


class TestNestingLimits:
    def test_include_nested_15_levels(self):
        from jclparser.include_loader import DictMemberLoader

        job = parse_jcl(
            _JOB + "// INCLUDE MEMBER=M0\n",
            include_loader=DictMemberLoader(_include_chain(15)),
        )
        assert [s.name for s in job.steps] == ["S"]

    def test_include_nested_16_levels_reported_as_too_deep(self):
        from jclparser.include_loader import DictMemberLoader

        job = parse_jcl(
            _JOB + "// INCLUDE MEMBER=M0\n",
            include_loader=DictMemberLoader(_include_chain(16)),
        )
        assert job.statement_findings == [
            (
                2,
                (
                    "INCLUDE member M15 is nested more than 15 levels deep (the z/OS "
                    "limit); it was not expanded"
                ),
                ErrorSeverity.ERROR,
            )
        ]
        assert not _has(job.warnings, "not found")

    def test_proc_nested_15_levels_explodes(self):
        procs = "".join(
            f"//P{i} PROC\n//S{i} EXEC P{i + 1}\n// PEND\n" for i in range(14)
        )
        jcl = _JOB + procs + "//P14 PROC\n//SZ EXEC PGM=Z\n// PEND\n//R EXEC P0\n"
        steps = explode_job(parse_jcl(jcl)).steps
        assert [s.program for s in steps] == ["Z"]

    def test_if_nested_16_levels_is_an_error(self):
        jcl = (
            _JOB
            + "//S1 EXEC PGM=A\n"
            + "// IF RC=0 THEN\n" * 16
            + "//S2 EXEC PGM=B\n"
            + "// ENDIF\n" * 16
        )
        assert _messages(jcl, "basic") == [
            "IF statements are nested more than 15 levels deep (the z/OS limit)"
        ]

    def test_runaway_if_nesting_raises_cleanly(self):
        from jclparser.errors import JCLSyntaxError

        jcl = (
            _JOB
            + "//S1 EXEC PGM=A\n"
            + "// IF RC=0 THEN\n" * 500
            + "//S2 EXEC PGM=B\n"
            + "// ENDIF\n" * 500
        )
        with pytest.raises(JCLSyntaxError, match="nested more than 100"):
            parse_jcl(jcl)


# ---------------------------------------------------------------------------
# Pass 10
# ---------------------------------------------------------------------------


class TestStatementsBeforeJob:
    @pytest.mark.parametrize(
        ("record", "statement"),
        [
            ("//JOBLIB DD DSN=A,DISP=SHR", "DD"),
            ("// SET C=B", "SET"),
            ("//JL JCLLIB ORDER=A", "JCLLIB"),
            ("//O OUTPUT CLASS=A", "OUTPUT"),
        ],
    )
    def test_reported(self, record, statement):
        jcl = record + "\n" + _JOB + "//S EXEC PGM=A\n"
        assert _messages(jcl, "basic") == [
            (
                f"{statement} statement comes before the JOB statement; only JES "
                "control statements and comments may precede it"
            )
        ]

    def test_jes_statement_before_job_accepted(self):
        assert _messages("/*JOBPARM S=X\n" + _JOB + "//S EXEC PGM=A\n") == []

    def test_restart_naming_no_step(self):
        jcl = "//J JOB (A),'X',RESTART=NOPE\n//S EXEC PGM=A\n"
        assert _messages(jcl) == ["RESTART=NOPE names no step of job J"]

    def test_restart_forms_accepted(self):
        for restart in ("*", "S", "(S.PS1)", "(S,CHK1)"):
            jcl = f"//J JOB (A),'X',RESTART={restart}\n//S EXEC PGM=A\n"
            assert _messages(jcl) == [], restart


# ---------------------------------------------------------------------------
# Pass 11
# ---------------------------------------------------------------------------


class TestProcBodyValidation:
    BODY = (
        "//S EXEC PGM=X\n//1BAD DD DUMMY\n//D DD DSN=A..B,DISP=SHR\n"
        "//D DD DSN=C,DISP=XXX\n"
    )

    def test_in_stream_proc_body(self):
        jcl = _JOB + "//P PROC\n" + self.BODY + "// PEND\n//R EXEC P\n"
        messages = _messages(jcl)
        assert sorted(messages) == sorted(
            [
                "Duplicate DD name in step P.S: D",
                "Invalid DD name '1BAD': must be 1-8 characters, alphanumeric + @#$",
                "Invalid dataset name 'A..B'",
                "Invalid DISP parameter 'XXX' on DD D",
            ]
        )

    def test_proc_member(self):
        assert len(_messages("//P PROC\n" + self.BODY)) == 4

    def test_invalid_names(self):
        jcl = "//P PROC\n//STEPNAME9 EXEC PGM=X\n//&N DD DUMMY\n"
        assert _messages(jcl) == [
            (
                "Invalid step name 'P.STEPNAME9': must be 1-8 characters, "
                "alphanumeric + @#$"
            ),
            "Invalid DD name '&N': must be 1-8 characters, alphanumeric + @#$",
        ]

    def test_symbolic_values_not_judged(self):
        jcl = (
            "//P PROC D=SHR\n//S EXEC PGM=&PG,PARM=&P\n"
            "//E DD DSN=&H..X,DISP=&D\n//F DD &OPTS\n"
        )
        assert _messages(jcl) == []

    def test_exploded_job_not_reported_twice(self):
        jcl = _JOB + "//P PROC\n//S EXEC PGM=X\n//D DD DSN=A..B,DISP=SHR\n"
        jcl += "// PEND\n//R EXEC P\n"
        findings = explode_job(parse_jcl(jcl)).validate()
        assert [f.message for f in findings] == ["Invalid dataset name 'A..B'"]


# ---------------------------------------------------------------------------
# Pass 12
# ---------------------------------------------------------------------------


class TestDuplicateKeywords:
    @pytest.mark.parametrize(
        ("jcl", "message"),
        [
            (
                "//J JOB (A),'X',CLASS=A,CLASS=B\n//S EXEC PGM=A\n",
                "keyword CLASS is coded more than once on the JOB statement",
            ),
            (
                _JOB + "//S EXEC PGM=A,PGM=B\n",
                "keyword PGM is coded more than once on the EXEC statement",
            ),
            (
                _JOB + "//S EXEC PGM=A\n//D DD DSN=A,DISP=SHR,\n//   DISP=OLD\n",
                "keyword DISP is coded more than once on the DD statement",
            ),
            (
                _JOB + "//S EXEC PGM=A\n//D DD DSN=A,DSNAME=B,DISP=SHR\n",
                (
                    "DSN and DSNAME are the same keyword and are both coded on the "
                    "DD statement"
                ),
            ),
            (
                _JOB + "//S EXEC PGM=A\n//D DD DSN=A,VOL=SER=X,VOLUME=SER=Y,DISP=OLD\n",
                (
                    "VOL and VOLUME are the same keyword and are both coded on the "
                    "DD statement"
                ),
            ),
        ],
    )
    def test_reported_as_error(self, jcl, message):
        assert _messages(jcl, "basic") == [message]

    def test_strict_parse_rejects(self):
        from jclparser.errors import JCLValidationError

        with pytest.raises(JCLValidationError):
            parse_jcl(
                _JOB + "//S EXEC PGM=A\n//D DD DSN=A,DISP=SHR,DISP=OLD\n",
                strict_mode=True,
            )


# ---------------------------------------------------------------------------
# Passes 13 and 14
# ---------------------------------------------------------------------------


class TestCntlAndOutput:
    def test_undefined_cntl_reference(self):
        jcl = _JOB + "//S EXEC PGM=A\n//D DD SYSOUT=A,CNTL=*.NOPE\n"
        assert _messages(jcl) == ["CNTL=*.NOPE references an undefined CNTL statement"]

    def test_defined_cntl_reference_accepted(self):
        jcl = _JOB + (
            "//S EXEC PGM=A\n//C CNTL\n PRINTDEV X\n// ENDCNTL\n"
            "//D DD SYSOUT=A,CNTL=*.C\n"
        )
        assert _messages(jcl) == []

    def test_stray_endcntl(self):
        jcl = _JOB + "//S EXEC PGM=A\n// ENDCNTL\n"
        assert _messages(jcl, "basic") == ["ENDCNTL statement with no CNTL to end"]

    def test_cntl_without_endcntl(self):
        jcl = _JOB + "//S EXEC PGM=A\n//C CNTL\n PRINTDEV X\n//D DD DUMMY\n"
        assert _messages(jcl, "basic") == ["CNTL C has no matching ENDCNTL"]

    def test_duplicate_output_names(self):
        jcl = _JOB + "//O1 OUTPUT CLASS=A\n//O1 OUTPUT CLASS=B\n//S EXEC PGM=A\n"
        assert _messages(jcl, "basic") == [
            (
                "OUTPUT statement O1 repeats the name of the OUTPUT statement on "
                "line 2 in the same scope"
            )
        ]

    def test_same_output_name_in_another_step_accepted(self):
        jcl = _JOB + (
            "//S1 EXEC PGM=A\n//O1 OUTPUT CLASS=A\n//S2 EXEC PGM=B\n"
            "//O1 OUTPUT CLASS=B\n"
        )
        assert _messages(jcl) == []

    def test_nameless_output(self):
        jcl = _JOB + "// OUTPUT CLASS=A\n//S EXEC PGM=A\n"
        assert _messages(jcl, "basic") == [
            "OUTPUT statement has no name; z/OS requires one"
        ]

    @pytest.mark.parametrize("sysout", ["A", "*", "(A,,F1)", "(,)", "&C"])
    def test_sysout_class_accepted(self, sysout):
        jcl = _JOB + f"//S EXEC PGM=A\n//D DD SYSOUT={sysout}\n"
        assert _messages(jcl) == []

    def test_sysout_class_too_long(self):
        jcl = _JOB + "//S EXEC PGM=A\n//D DD SYSOUT=AB\n"
        assert _messages(jcl) == [
            "SYSOUT class 'AB' on DD D must be one character (A-Z, 0-9) or *"
        ]


# ---------------------------------------------------------------------------
# Pass 15
# ---------------------------------------------------------------------------


class TestSymbolsInIfCondition:
    def test_job_set_substituted(self):
        jcl = _JOB + (
            "// SET ST=S1\n//S1 EXEC PGM=A\n// IF &ST..RC = 0 THEN\n"
            "//S2 EXEC PGM=B\n// ENDIF\n"
        )
        job = parse_jcl(jcl)
        block = job.steps[1]
        assert block.condition == "S1.RC=0"
        assert block.condition_ast is not None
        assert explode_job(job).steps[1].condition_ast is not None

    def test_proc_parameter_substituted(self):
        jcl = _JOB + (
            "//P PROC ST=PS1\n//PS1 EXEC PGM=A\n// IF &ST..RC = 0 THEN\n"
            "//PS2 EXEC PGM=B\n// ENDIF\n// PEND\n//R EXEC P\n"
        )
        block = explode_job(parse_jcl(jcl)).steps[1]
        assert block.condition == "R.PS1.RC=0"
        assert block.condition_ast.step_name == "R.PS1"

    def test_rc_analysis_uses_substituted_guard(self):
        from jclparser.rc_analysis import compute_feasible_paths

        jcl = _JOB + (
            "// SET LIM=4\n//S1 EXEC PGM=A\n// IF S1.RC > &LIM THEN\n"
            "// IF S1.RC < 2 THEN\n//S2 EXEC PGM=B\n// ENDIF\n// ENDIF\n"
        )
        assert compute_feasible_paths(parse_jcl(jcl)).unreachable_steps == ["S2"]

    def test_unresolved_symbol_left_as_written(self):
        jcl = _JOB + "//S1 EXEC PGM=A\n// IF &NOPE..RC = 0 THEN\n//S2 EXEC PGM=B\n"
        jcl += "// ENDIF\n"
        block = parse_jcl(jcl).steps[1]
        assert block.condition == "&NOPE..RC=0"
        assert block.condition_ast is None


# ---------------------------------------------------------------------------
# Pass 18 / 19
# ---------------------------------------------------------------------------


class TestParm:
    def test_parm_over_100_characters(self):
        part = "A" * 45
        jcl = "//J    JOB 1\n" + (
            f"//S    EXEC PGM=X,PARM=('{part}',\n//             '{part}',\n"
            f"//             '{part}')\n"
        )
        assert _messages(jcl, "basic") == [
            (
                "PARM on step S is 137 characters long; z/OS passes at most 100 "
                "(use PARMDD for more)"
            )
        ]

    def test_parm_of_100_characters_accepted(self):
        jcl = "//J JOB 1\n//S EXEC PGM=X,PARM='" + "A" * 50 + "',\n"
        jcl += "//  REGION=0M\n"
        assert _messages(jcl) == []

    def test_long_parm_after_proc_substitution(self):
        jcl = "//J JOB 1\n//P PROC V=\n//S EXEC PGM=X,PARM='&V.&V'\n// PEND\n"
        jcl += "//R EXEC P,V='" + "B" * 60 + "'\n"
        job = parse_jcl(jcl)
        assert parse_jcl(jcl).validate() == []
        findings = explode_job(job).validate()
        assert any("characters long" in f.message for f in findings)

    def test_parm_and_parmdd(self):
        jcl = "//J JOB 1\n//T EXEC PGM=Y,PARM=ABC,PARMDD=MYDD\n//MYDD DD *\nX\n/*\n"
        assert _messages(jcl, "basic") == [
            "PARM and PARMDD are both coded on step T; they are mutually exclusive"
        ]

    def test_parm_override_and_parmdd_override(self):
        jcl = "//J JOB 1\n//P PROC\n//S EXEC PGM=X\n// PEND\n"
        jcl += "//R EXEC P,PARM.S=A,PARMDD.S=DD1\n"
        assert _has(_messages(jcl), "PARM.S and PARMDD.S are both coded on step R")


class TestCondSyntax:
    @pytest.mark.parametrize(
        ("cond", "problem"),
        [
            ("(4,XX)", "test (4,XX): operator must be one of"),
            ("(5000,LT)", "test (5000,LT): code must be a number 0-4095"),
            ("(A,LT)", "test (A,LT): code must be a number 0-4095"),
            ("((4,LT),EVEN,ONLY)", "codes both EVEN and ONLY"),
            ("((4,LT,S0,X))", "test (4,LT,S0,X) must be (code,operator[,stepname])"),
        ],
    )
    def test_malformed_exec_cond(self, cond, problem):
        jcl = _JOB + f"//S0 EXEC PGM=A\n//S EXEC PGM=A,COND={cond}\n"
        assert _has(_messages(jcl, "basic"), problem)

    @pytest.mark.parametrize(
        "cond", ["(4,LT)", "((4,LT),(8,GT,S0))", "EVEN", "((0,NE,S0),ONLY)", "&C"]
    )
    def test_valid_exec_cond(self, cond):
        jcl = _JOB + f"//S0 EXEC PGM=A\n//S EXEC PGM=A,COND={cond}\n"
        assert _messages(jcl) == []

    def test_job_cond_takes_no_step_or_even(self):
        jcl = "//J JOB (A),'X',COND=((4,LT,S1),EVEN)\n//S1 EXEC PGM=A\n"
        messages = _messages(jcl, "basic")
        assert _has(messages, "COND on the JOB statement codes EVEN/ONLY")
        assert _has(messages, "test (4,LT,S1) must be (code,operator)")

    def test_too_many_tests(self):
        tests = ",".join(["(4,LT)"] * 9)
        jcl = _JOB + f"//S EXEC PGM=A,COND=({tests})\n"
        assert _has(_messages(jcl, "basic"), "codes 9 tests (at most 8)")


# ---------------------------------------------------------------------------
# Pass 24
# ---------------------------------------------------------------------------


class TestTemporaryDatasetCase:
    def test_lowercase_creation_matches_uppercase_use(self):
        jcl = "//J  JOB 1\n" + (
            "//S3 EXEC PGM=X\n"
            "//T  DD DSN=&&tmp,DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S4 EXEC PGM=X\n//T  DD DSN=&&TMP,DISP=(OLD,DELETE)\n"
        )
        assert _messages(jcl) == []

    def test_second_creation_in_other_case_flagged(self):
        jcl = "//J  JOB 1\n" + (
            "//S3 EXEC PGM=X\n"
            "//T  DD DSN=&&tmp,DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
            "//S4 EXEC PGM=X\n"
            "//T  DD DSN=&&TMP,DISP=(NEW,PASS),SPACE=(TRK,1),UNIT=SYSDA\n"
        )
        assert _messages(jcl) == [
            "Temporary dataset &&TMP created in multiple steps: S3 and S4"
        ]
