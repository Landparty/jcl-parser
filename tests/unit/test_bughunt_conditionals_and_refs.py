"""Regression tests for the 2026-10-29 bug hunt.

* ``validate_jcl`` passed JCL whose IF/THEN/ELSE/ENDIF statements do not pair
  up, which z/OS rejects; the parser only warned.
* A ``*.`` backward reference (DSN=, VOL=REF=, DCB=, REFDD=, PGM=) to a DD that
  does not exist, or is coded later, was never reported.
* ``SPACE=(CYL,(1,1),,CONTIG)`` read the omitted positional as a ``''``
  subparameter.
"""

import pytest

from jclparser import explode_job, parse_jcl, validate_jcl
from jclparser.errors import ErrorSeverity, JCLParseError

pytestmark = pytest.mark.unit

_JOB = "//J JOB 1\n//S0 EXEC PGM=X\n"


def _messages(jcl: str, level: str = "basic") -> list[str]:
    return [e.message for e in validate_jcl(jcl, level=level)]


class TestUnbalancedConditionals:
    def test_if_without_endif_is_an_error(self):
        jcl = _JOB + "// IF RC = 0 THEN\n//S1 EXEC PGM=Y\n"
        errors = validate_jcl(jcl)
        assert [(e.message, e.line_number) for e in errors] == [
            ("IF statement has no matching ENDIF", 3)
        ]
        assert errors[0].severity == ErrorSeverity.ERROR

    def test_endif_without_if_is_an_error(self):
        assert _messages(_JOB + "// ENDIF\n//S1 EXEC PGM=Y\n") == [
            "ENDIF statement with no matching IF"
        ]

    def test_else_without_if_is_an_error(self):
        assert _messages(_JOB + "// ELSE\n//S1 EXEC PGM=Y\n") == [
            "ELSE statement with no matching IF"
        ]

    def test_second_else_is_an_error(self):
        jcl = _JOB + (
            "// IF RC = 0 THEN\n"
            "//S1 EXEC PGM=Y\n"
            "// ELSE\n"
            "//S2 EXEC PGM=Z\n"
            "// ELSE\n"
            "//S3 EXEC PGM=W\n"
            "// ENDIF\n"
        )
        job = parse_jcl(jcl)
        assert any("second ELSE" in w for w in job.warnings)
        assert _messages(jcl) == ["ELSE statement repeats the ELSE of the IF on line 3"]

    def test_if_in_proc_closed_by_pend_is_an_error(self):
        jcl = (
            "//J JOB 1\n"
            "//P PROC\n"
            "//PS EXEC PGM=X\n"
            "// IF PS.RC = 0 THEN\n"
            "//PT EXEC PGM=Y\n"
            "// PEND\n"
            "//S1 EXEC P\n"
        )
        assert _messages(jcl) == [
            "IF statement in PROC P has no matching ENDIF before PEND"
        ]

    def test_balanced_conditionals_stay_valid(self):
        jcl = _JOB + (
            "// IF RC = 0 THEN\n"
            "// IF S0.RC = 0 THEN\n"
            "//S1 EXEC PGM=Y\n"
            "// ENDIF\n"
            "// ELSE\n"
            "//S2 EXEC PGM=Z\n"
            "// ENDIF\n"
        )
        assert _messages(jcl, "structure") == []

    def test_strict_parse_rejects_unclosed_if(self):
        with pytest.raises(JCLParseError, match="no matching ENDIF"):
            parse_jcl(_JOB + "// IF RC = 0 THEN\n//S1 EXEC PGM=Y\n", strict_mode=True)

    def test_exploded_job_keeps_the_finding(self):
        job = parse_jcl(_JOB + "// ENDIF\n")
        assert job.conditional_errors == [(3, "ENDIF statement with no matching IF")]
        assert explode_job(job).conditional_errors == job.conditional_errors

    def test_line_number_inside_include_member_maps_to_include(self, tmp_path):
        lib = tmp_path / "MY.LIB"
        lib.mkdir()
        (lib / "MEM.jcl").write_text("//S1 EXEC PGM=Y\n// ENDIF\n")
        jcl = "//J JOB 1\n// JCLLIB ORDER=MY.LIB\n// INCLUDE MEMBER=MEM\n"
        job = parse_jcl(jcl, proc_base_path=tmp_path)
        assert job.conditional_errors == [(3, "ENDIF statement with no matching IF")]


def _unresolved(reference: str) -> str:
    return f"{reference} does not refer to a DD statement coded before it"


def _backref_warnings(jcl: str, explode: bool = False) -> list[str]:
    job = parse_jcl(jcl)
    if explode:
        job = explode_job(job)
    return [
        e.message
        for e in job.validate()
        if "coded before it" in e.message and e.severity == ErrorSeverity.WARNING
    ]


class TestBackwardReferences:
    def test_valid_references_are_clean(self):
        jcl = (
            "//J JOB 1\n"
            "//S1 EXEC PGM=X\n"
            "//OUT DD DSN=A.B,DISP=(NEW,CATLG)\n"
            "//LOAD DD DSN=L.LOAD,DISP=SHR\n"
            "//S2 EXEC PGM=*.S1.LOAD\n"
            "//IN DD DSN=*.S1.OUT,DISP=SHR\n"
            "//IN2 DD DSN=C.D,DISP=(NEW,CATLG),VOL=REF=*.S1.OUT,DCB=*.IN\n"
            "//IN3 DD DSN=E.F,DISP=(NEW,CATLG),REFDD=*.S1.OUT\n"
        )
        assert _backref_warnings(jcl) == []

    def test_reference_to_a_missing_dd(self):
        jcl = (
            "//J JOB 1\n"
            "//S1 EXEC PGM=X\n"
            "//OUT DD DSN=A.B,DISP=SHR\n"
            "//S2 EXEC PGM=Y\n"
            "//IN DD DSN=*.S1.NOPE,DISP=SHR\n"
        )
        assert _backref_warnings(jcl) == [
            _unresolved("DSN=*.S1.NOPE on DD IN in step S2")
        ]

    def test_forward_references_are_reported(self):
        jcl = (
            "//J JOB 1\n"
            "//S1 EXEC PGM=*.S2.LOAD\n"
            "//IN DD DSN=*.LATER,DISP=SHR\n"
            "//LATER DD DSN=A.B,DISP=SHR\n"
            "//S2 EXEC PGM=Y\n"
            "//LOAD DD DSN=L.LOAD,DISP=SHR\n"
        )
        assert _backref_warnings(jcl) == [
            _unresolved("PGM=*.S2.LOAD on step S1"),
            _unresolved("DSN=*.LATER on DD IN in step S1"),
        ]

    def test_vol_ref_dcb_and_refdd(self):
        jcl = (
            "//J JOB 1\n"
            "//S1 EXEC PGM=X\n"
            "//A DD DSN=A.A,DISP=(NEW,CATLG),VOL=(,,,REF=*.S0.X),\n"
            "//         DCB=(*.S0.Y,LRECL=80),REFDD=*.S0.Z\n"
        )
        assert _backref_warnings(jcl) == [
            _unresolved("VOL=REF=*.S0.X on DD A in step S1"),
            _unresolved("DCB=*.S0.Y on DD A in step S1"),
            _unresolved("REFDD=*.S0.Z on DD A in step S1"),
        ]

    _PROC = (
        "//J JOB 1\n"
        "//P PROC\n"
        "//PS1 EXEC PGM=X\n"
        "//OUT DD DSN=A.B,DISP=(NEW,PASS)\n"
        "//PS2 EXEC PGM=Y\n"
        "//IN DD DSN=*.PS1.OUT,DISP=SHR\n"
        "// PEND\n"
        "//S1 EXEC P\n"
        "//S2 EXEC PGM=Z\n"
    )

    def test_reference_into_unexploded_proc_is_not_checked(self):
        jcl = self._PROC + "//D DD DSN=*.S1.PS9.NOPE,DISP=SHR\n"
        assert _backref_warnings(jcl) == []

    def test_references_in_exploded_job(self):
        ok = self._PROC + "//D DD DSN=*.S1.PS2.IN,DISP=SHR\n"
        assert _backref_warnings(ok, explode=True) == []
        bad = self._PROC + "//D DD DSN=*.S1.PS2.NOPE,DISP=SHR\n"
        assert _backref_warnings(bad, explode=True) == [
            _unresolved("DSN=*.S1.PS2.NOPE on DD D in step S2")
        ]

    def test_symbolic_reference_is_not_checked(self):
        jcl = _JOB + "//S1 EXEC PGM=Y\n//D DD DSN=*.&STEP..OUT,DISP=SHR\n"
        assert _backref_warnings(jcl) == []

    def test_strict_parse_is_not_broken_by_a_warning(self):
        jcl = _JOB + "//S1 EXEC PGM=Y\n//D DD DSN=*.S0.NOPE,DISP=SHR\n"
        parse_jcl(jcl, strict_mode=True)


class TestSpaceOmittedPositional:
    def test_omitted_rlse_slot_is_not_a_subparameter(self):
        job = parse_jcl(
            "//J JOB 1\n//S EXEC PGM=X\n"
            "//D DD DSN=A.B,DISP=(NEW,CATLG),SPACE=(CYL,(1,1,5),,CONTIG)\n"
        )
        space = job.steps[0].dd_statements[0].space
        assert "" not in space.subparameters
        assert space.contig and not space.rlse
        assert space.directory == 5
