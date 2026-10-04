"""Regression tests for validation / explosion issues #57, #60, #64 and #65."""

from __future__ import annotations

import pytest

from jclparser import ErrorSeverity, parse_jcl, validate_jcl
from jclparser.cli import main

DUP_STEP_JCL = "//J JOB\n//S1 EXEC PGM=A\n//S1 EXEC PGM=B\n"


@pytest.mark.unit
class TestValidateJclReportsStructuralErrors:
    """#57: validate_jcl() must not swallow job.validate() ERROR findings."""

    @pytest.mark.parametrize("level", ["basic", "structure", "semantic"])
    def test_duplicate_step_name_reported_at_every_level(self, level):
        errors = validate_jcl(DUP_STEP_JCL, level=level)
        dup = [e for e in errors if "Duplicate step name: S1" in e.message]
        assert len(dup) == 1
        assert dup[0].severity == ErrorSeverity.ERROR

    def test_structure_level_matches_job_validate(self):
        expected = [e.message for e in parse_jcl(DUP_STEP_JCL).validate()]
        got = [e.message for e in validate_jcl(DUP_STEP_JCL, level="structure")]
        assert got == expected

    def test_basic_level_omits_warnings(self):
        # Duplicate DD names are a WARNING finding: only the structure and
        # semantic levels report it; basic reports what fails a strict parse.
        src = "//J JOB\n//S1 EXEC PGM=A\n//D DD DUMMY\n//D DD DUMMY\n"
        structure = validate_jcl(src, level="structure")
        assert any(e.severity == ErrorSeverity.WARNING for e in structure)
        assert validate_jcl(src, level="basic") == []

    def test_cli_validate_exits_nonzero(self, tmp_path, capsys):
        jcl = tmp_path / "dup.jcl"
        jcl.write_text(DUP_STEP_JCL)
        rc = main([str(jcl), "--validate"])
        out = capsys.readouterr().out
        assert rc == 1
        assert "Duplicate step name: S1" in out
        assert "OK - no errors found." not in out
