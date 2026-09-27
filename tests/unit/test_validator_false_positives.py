"""Validation accepts common, valid DD forms.

``validate_dd_statement`` looked for a ``DUMMY`` key (DUMMY is stored as the
positional ``_pos_0``) and knew no other data sources, and the dataset-name
validator read any ``(...)`` suffix as a GDG generation. So ``DD DUMMY``, a
``UNIT=``/``SPACE=`` work file and ``DSN=LIB(MEMBER)`` were ERRORs, and
``parse_jcl(strict_mode=True)`` rejected jobs containing them.
"""

import pytest

from jclparser import JCLValidationError, parse_jcl
from jclparser.parameter_validators import DatasetNameValidator
from jclparser.validators import validate_dd_statement


def _dd_errors(body: str) -> list[str]:
    job = parse_jcl(f"//J JOB\n//S EXEC PGM=X\n{body}\n")
    return [str(e) for e in validate_dd_statement(job.steps[0].dd_statements[0])]


@pytest.mark.unit
class TestValidatorFalsePositives:
    @pytest.mark.parametrize(
        "body",
        [
            "//D DD DUMMY",
            "//D DD DUMMY,DSN=X.Y",
            "//D DD UNIT=SYSDA,SPACE=(CYL,(1,1))",
            "//D DD SPACE=(TRK,1)",
            "//D DD DSN=A.B(MEMBER),DISP=SHR",
            "//D DD DSN=&&TEMP(MEM),DISP=(NEW,PASS)",
            "//D DD DSN=*.STEP1.OUT,DISP=SHR",
            "//D DD DSN=*.STEP1.PSTEP.OUT,DISP=SHR",
            "//D DD DDNAME=SYSIN2",
            "//D DD PATH='/u/x',PATHOPTS=ORDONLY",
            "//D DD SUBSYS=(DB2P)",
            "//D DD DYNAM",
            "//D DD *\n/*",
            "//D DD DSN=A.B,DISP=(,CATLG,DELETE),SPACE=(TRK,1)",
            "//D DD DSN=&SYSUID..WORK.DATA,DISP=SHR",
        ],
    )
    def test_valid_dd_has_no_errors(self, body):
        assert _dd_errors(body) == []

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ("//D DD", "must specify a data source"),
            ("//D DD DSN=A.B,SYSOUT=*", "conflicting data source"),
            ("//D DD DSN=A.B(BAD-MEM)", "Invalid dataset name"),
            ("//D DD DSN=A.B(TOOLONGMEM)", "Invalid dataset name"),
        ],
    )
    def test_invalid_dd_still_reported(self, body, message):
        assert any(message in e for e in _dd_errors(body))

    def test_strict_mode_accepts_common_forms(self):
        jcl = (
            "//J        JOB (ACCT),'T'\n"
            "//S1       EXEC PGM=IGYCRCTL\n"
            "//SYSLIB   DD DSN=A.COPYLIB(MEMBER),DISP=SHR\n"
            "//SYSUT1   DD UNIT=SYSDA,SPACE=(CYL,(1,1))\n"
            "//SYSIN    DD DUMMY\n"
            "//S2       EXEC PGM=X\n"
            "//IN       DD DSN=*.S1.SYSUT1,DISP=SHR\n"
        )
        assert parse_jcl(jcl, strict_mode=True).name == "J"

    def test_strict_mode_still_rejects_bad_dd(self):
        with pytest.raises(JCLValidationError):
            parse_jcl(
                "//J JOB\n//S EXEC PGM=X\n//D DD DSN=A.B,SYSOUT=*\n", strict_mode=True
            )

    def test_member_on_gdg_style_name(self):
        assert DatasetNameValidator.validate("A.B(0)").is_valid
        assert not DatasetNameValidator.validate("A.B(+X)").is_valid
