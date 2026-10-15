"""Regression tests for the severity:medium validation fixes.

* #119 -- step / DD / job validation findings carry their source line.
"""

from __future__ import annotations

import pytest

from jclparser import parse_jcl, validate_jcl
from jclparser.errors import ErrorSeverity
from jclparser.model import DDStatement, Step
from jclparser.validators import validate_step_structure

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# #119 -- validation findings report the line of the step / DD they are about
# ---------------------------------------------------------------------------

_ISSUE_119_JCL = (
    "//J1 JOB (A),'X'\n"
    "//S1 EXEC PGM=IEFBR14\n"
    "//OK DD DSN=A.B,DISP=SHR\n"
    "//TOOLONGDDNAME DD DSN=A..B,DISP=(SHR,BOGUS)\n"
    "//S1 EXEC PGM=X\n"
)


class TestIssue119FindingLines:
    def test_validate_jcl_reports_step_and_dd_lines(self) -> None:
        findings = validate_jcl(_ISSUE_119_JCL, level="structure")
        assert [(f.line_number, f.message.split(":")[0]) for f in findings] == [
            (5, "Duplicate step name"),
            (4, "Invalid DD name 'TOOLONGDDNAME'"),
            (4, "Invalid dataset name 'A..B'"),
            (4, "Invalid DISP parameter '['SHR', 'BOGUS']' on DD TOOLONGDDNAME"),
        ]

    def test_job_validate_str_includes_line(self) -> None:
        messages = [str(e) for e in parse_jcl(_ISSUE_119_JCL).validate()]
        assert messages[0] == "Line 5: Duplicate step name: S1"
        assert all(m.startswith(("Line 4:", "Line 5:")) for m in messages)

    def test_step_rules_use_step_line(self) -> None:
        step = Step(name="BAD.NAME!", line_number=7)
        findings = validate_step_structure(step)
        assert findings
        assert {f.line_number for f in findings} == {7}

    def test_both_program_and_procedure_uses_step_line(self) -> None:
        step = Step(name="S1", program="P", procedure="Q", line_number=9)
        [finding] = validate_step_structure(step)
        assert "both program and procedure" in finding.message
        assert finding.line_number == 9

    def test_duplicate_dd_and_dd_source_rules_use_dd_line(self) -> None:
        step = Step(
            name="S1",
            program="P",
            line_number=2,
            dd_statements=[
                DDStatement(name="A", dataset_name="X.Y", line_number=3),
                DDStatement(name="A", dataset_name="X.Z", line_number=4),
                DDStatement(name="B", line_number=5),
                DDStatement(
                    name="C",
                    dataset_name="X.Y",
                    parameters={"SYSOUT": "A"},
                    line_number=6,
                ),
            ],
        )
        by_message = {f.message: f.line_number for f in validate_step_structure(step)}
        assert by_message["Duplicate DD name in step S1: A"] == 4
        assert (
            by_message[
                "DD B must specify a data source (DSN, SYSOUT, DUMMY, or inline data)"
            ]
            == 5
        )
        assert by_message["DD C has conflicting data source specifications"] == 6

    def test_invalid_job_name_uses_job_line(self) -> None:
        job = parse_jcl("//* lead comment\n//TOOLONGJOB JOB (A)\n//S1 EXEC PGM=X\n")
        [finding] = [f for f in job.validate() if "job name" in f.message]
        assert finding.line_number == 2

    def test_temporary_dataset_findings_use_dd_lines(self) -> None:
        jcl = (
            "//J1 JOB (A)\n"
            "//S1 EXEC PGM=A\n"
            "//O1 DD DSN=&&T,DISP=(NEW,PASS)\n"
            "//S2 EXEC PGM=B\n"
            "//O2 DD DSN=&&T,DISP=(NEW,PASS)\n"
            "//I1 DD DSN=&&NEVER,DISP=(OLD,DELETE)\n"
        )
        by_message = {f.message: f for f in parse_jcl(jcl).validate()}
        dup = by_message["Temporary dataset &&T created in multiple steps: S1 and S2"]
        assert dup.line_number == 5
        unused = by_message["Temporary dataset &&NEVER used but never created"]
        assert unused.line_number == 6
        assert unused.severity == ErrorSeverity.WARNING
