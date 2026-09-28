"""Temporary datasets extended with DISP=MOD, and catalog state across steps."""

from __future__ import annotations

import pytest

from jclparser import parse_jcl
from jclparser.dataset_lifecycle import validate_dataset_lifecycle
from jclparser.validators import validate_data_dependencies

pytestmark = pytest.mark.unit

# Two compiles collecting their object decks in &&LOADSET for one link-edit:
# the second DISP=(MOD,PASS) extends the dataset, it does not create it again.
_ACCUMULATED_LOADSET = """\
//J        JOB 1
//COB1     EXEC PGM=IGYCRCTL
//SYSLIN   DD DSN=&&LOADSET,DISP=(MOD,PASS),UNIT=SYSDA,SPACE=(TRK,(5,5))
//COB2     EXEC PGM=IGYCRCTL
//SYSLIN   DD DSN=&&LOADSET,DISP=(MOD,PASS)
//LKED     EXEC PGM=IEWL
//SYSLIN   DD DSN=&&LOADSET,DISP=(OLD,DELETE)
"""


class TestTemporaryDatasetCreation:
    def test_mod_extending_a_passed_temporary_is_not_a_second_creation(self):
        job = parse_jcl(_ACCUMULATED_LOADSET)
        assert validate_data_dependencies(job) == []
        assert job.validate() == []

    def test_accumulated_loadset_parses_in_strict_mode(self):
        parse_jcl(_ACCUMULATED_LOADSET, strict_mode=True)

    def test_recreate_after_explicit_delete_is_allowed(self):
        job = parse_jcl(
            _ACCUMULATED_LOADSET
            + "//S4       EXEC PGM=X\n"
            + "//OUT      DD DSN=&&LOADSET,DISP=(NEW,PASS),UNIT=SYSDA,SPACE=(TRK,1)\n"
        )
        assert validate_data_dependencies(job) == []

    def test_new_twice_while_passed_is_still_reported(self):
        job = parse_jcl(
            "//J        JOB 1\n"
            "//S1       EXEC PGM=A\n"
            "//O        DD DSN=&&T,DISP=(NEW,PASS),UNIT=SYSDA,SPACE=(TRK,1)\n"
            "//S2       EXEC PGM=B\n"
            "//O        DD DSN=&&T,DISP=(NEW,PASS),UNIT=SYSDA,SPACE=(TRK,1)\n"
        )
        messages = [e.message for e in validate_data_dependencies(job)]
        assert messages == [
            "Temporary dataset &&T created in multiple steps: S1 and S2"
        ]

    def test_deleted_temporary_still_counts_as_created(self):
        job = parse_jcl(
            "//J        JOB 1\n"
            "//S1       EXEC PGM=A\n"
            "//O        DD DSN=&&T,DISP=(NEW,PASS),UNIT=SYSDA,SPACE=(TRK,1)\n"
            "//S2       EXEC PGM=B\n"
            "//I        DD DSN=&&T,DISP=(OLD,DELETE)\n"
        )
        assert validate_data_dependencies(job) == []


def _lifecycle_messages(source: str) -> list[str]:
    return [e.message for e in validate_dataset_lifecycle(parse_jcl(source))]


class TestCatalogState:
    def test_delete_if_exists_then_recreate_then_read(self):
        # The IEFBR14 DISP=(MOD,DELETE) "delete if it exists" idiom, then a
        # re-create: the dataset is cataloged again when S3 reads it.
        assert (
            _lifecycle_messages(
                "//J        JOB 1\n"
                "//S1       EXEC PGM=IEFBR14\n"
                "//D        DD DSN=A.B.C,DISP=(MOD,DELETE),UNIT=3390,SPACE=(TRK,0)\n"
                "//S2       EXEC PGM=B\n"
                "//O        DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),UNIT=3390,"
                "SPACE=(TRK,1)\n"
                "//S3       EXEC PGM=C\n"
                "//I        DD DSN=A.B.C,DISP=SHR\n"
            )
            == []
        )

    def test_abnormal_catlg_does_not_catalog_for_later_steps(self):
        assert (
            _lifecycle_messages(
                "//J        JOB 1\n"
                "//S1       EXEC PGM=A\n"
                "//O        DD DSN=A.B.C,DISP=(NEW,KEEP,CATLG),VOL=SER=V1,"
                "UNIT=3390,SPACE=(TRK,1)\n"
                "//S2       EXEC PGM=B\n"
                "//O        DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),UNIT=3390,"
                "SPACE=(TRK,1)\n"
            )
            == []
        )

    def test_duplicate_catalog_after_delete_and_recreate_is_reported(self):
        messages = _lifecycle_messages(
            "//J        JOB 1\n"
            "//S1       EXEC PGM=IEFBR14\n"
            "//D        DD DSN=A.B.C,DISP=(MOD,DELETE),UNIT=3390,SPACE=(TRK,0)\n"
            "//S2       EXEC PGM=B\n"
            "//O        DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),UNIT=3390,SPACE=(TRK,1)\n"
            "//S3       EXEC PGM=C\n"
            "//O        DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),UNIT=3390,SPACE=(TRK,1)\n"
        )
        assert len(messages) == 1
        assert "step 'S3'" in messages[0] and "cataloged in step 'S2'" in messages[0]

    def test_new_with_abnormal_catlg_after_catalog_is_still_reported(self):
        messages = _lifecycle_messages(
            "//J        JOB 1\n"
            "//S1       EXEC PGM=A\n"
            "//O        DD DSN=A.B.C,DISP=(NEW,CATLG,DELETE),UNIT=3390,SPACE=(TRK,1)\n"
            "//S2       EXEC PGM=B\n"
            "//O        DD DSN=A.B.C,DISP=(NEW,PASS,CATLG),UNIT=3390,SPACE=(TRK,1)\n"
        )
        assert len(messages) == 1 and "step 'S2'" in messages[0]
