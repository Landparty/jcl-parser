"""PROC DD overrides merge into the PROC's DD instead of replacing it.

Per z/OS, an overriding DD statement changes only the parameters it codes; the
rest of the PROC DD's parameters are kept, and ``KEY=`` nullifies one.
"""

import pytest

from jclparser import parse_jcl
from jclparser.model import iter_execution_steps

PROC = (
    "//J        JOB (ACCT),'T'\n"
    "//P        PROC\n"
    "//PS       EXEC PGM=IEFBR14\n"
    "//D1       DD DSN=PROC.DATA,DISP=SHR,UNIT=SYSDA,DCB=(RECFM=FB,LRECL=80)\n"
    "//D2       DD DUMMY,DCB=BLKSIZE=800\n"
    "//D3       DD *\n"
    "PROC DATA\n"
    "/*\n"
    "//         PEND\n"
    "//S1       EXEC P\n"
)


def _dds(jcl: str) -> dict:
    job = parse_jcl(jcl).explode()
    step = next(iter_execution_steps(job.steps))
    return {dd.name: dd for dd in step.dd_statements}


@pytest.mark.unit
class TestDDOverrideMerge:
    def test_qualified_override_keeps_uncoded_parameters(self):
        dd = _dds(PROC + "//PS.D1    DD DSN=OVR.DATA\n")["D1"]
        assert dd.dataset_name == "OVR.DATA"
        assert dd.disposition == "SHR"
        assert dd.parameters["UNIT"] == "SYSDA"
        assert dd.parameters["DCB"] == ["RECFM=FB", "LRECL=80"]

    def test_unqualified_override_keeps_uncoded_parameters(self):
        dd = _dds(PROC + "//D1       DD DISP=OLD\n")["D1"]
        assert dd.dataset_name == "PROC.DATA"
        assert dd.disposition == "OLD"
        assert dd.parameters["UNIT"] == "SYSDA"

    def test_empty_value_nullifies_parameter(self):
        dd = _dds(PROC + "//PS.D1    DD UNIT=,DCB=\n")["D1"]
        assert "UNIT" not in dd.parameters
        assert "DCB" not in dd.parameters
        assert dd.dataset_name == "PROC.DATA"

    def test_dsn_override_nullifies_dummy(self):
        dd = _dds(PROC + "//PS.D2    DD DSN=REAL.DATA,DISP=SHR\n")["D2"]
        assert "_pos_0" not in dd.parameters
        assert dd.dataset_name == "REAL.DATA"
        assert dd.parameters["DCB"] == "BLKSIZE=800"

    def test_dsname_override_displaces_dsn(self):
        dd = _dds(PROC + "//PS.D1    DD DSNAME=LONG.FORM\n")["D1"]
        assert "DSN" not in dd.parameters
        assert dd.dataset_name == "LONG.FORM"
        assert dd.disposition == "SHR"

    def test_sysout_override_drops_dataset_name(self):
        dd = _dds(PROC + "//PS.D1    DD SYSOUT=*\n")["D1"]
        assert dd.dataset_name is None
        assert dd.parameters["SYSOUT"] == "*"

    def test_instream_override_replaces_dd(self):
        jcl = PROC + "//PS.D1    DD *\nNEW DATA\n/*\n"
        dd = _dds(jcl)["D1"]
        assert dd.dataset_name is None
        assert "DISP" not in dd.parameters
        assert dd.inline_data == "NEW DATA"

    def test_keyword_override_of_instream_dd_keeps_data(self):
        dd = _dds(PROC + "//PS.D3    DD DCB=LRECL=80\n")["D3"]
        assert dd.inline_data == "PROC DATA"
        assert dd.parameters["DCB"] == "LRECL=80"


@pytest.mark.unit
class TestDCBSubparameterOverride:
    """An overriding DCB= changes only the DCB subparameters it codes."""

    def test_dcb_override_keeps_uncoded_subparameters(self):
        dd = _dds(PROC + "//PS.D1    DD DCB=LRECL=133\n")["D1"]
        assert dd.parameters["DCB"] == ["RECFM=FB", "LRECL=133"]
        assert dd.dcb.recfm == "FB"
        assert dd.dcb.lrecl == 133

    def test_dcb_override_adds_new_subparameter(self):
        dd = _dds(PROC + "//PS.D1    DD DCB=(BLKSIZE=0)\n")["D1"]
        assert dd.parameters["DCB"] == ["RECFM=FB", "LRECL=80", "BLKSIZE=0"]

    def test_dcb_subparameter_with_no_value_is_nullified(self):
        dd = _dds(PROC + "//PS.D1    DD DCB=(LRECL=,BLKSIZE=0)\n")["D1"]
        assert dd.parameters["DCB"] == ["RECFM=FB", "BLKSIZE=0"]

    def test_unqualified_dcb_override_merges_too(self):
        dd = _dds(PROC + "//D1       DD DCB=RECFM=VB\n")["D1"]
        assert dd.parameters["DCB"] == ["RECFM=VB", "LRECL=80"]

    def test_dcb_override_positional_model_replaces_procs(self):
        jcl = PROC.replace("DCB=(RECFM=FB,LRECL=80)", "DCB=(OLD.MODEL,LRECL=80)")
        dd = _dds(jcl + "//PS.D1    DD DCB=(NEW.MODEL,RECFM=FB)\n")["D1"]
        assert dd.parameters["DCB"] == ["NEW.MODEL", "LRECL=80", "RECFM=FB"]

    def test_single_subparameter_string_form_is_kept(self):
        dd = _dds(PROC + "//PS.D2    DD DCB=BLKSIZE=0\n")["D2"]
        assert dd.parameters["DCB"] == "BLKSIZE=0"
