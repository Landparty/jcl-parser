"""
Integration tests for real-world JCL examples from metalbobinou/JCL-examples.

Each test maps to a fixture file whose content was pulled verbatim from:
https://github.com/metalbobinou/JCL-examples

Fixture files in tests/fixtures/real_world/ that have 80-char lines (sequence
numbers in cols 73-80) exercise normalize_jcl_line() stripping.  The assertions
here are tight on what the JCL *should* capture; failures are findings, not
reasons to soften the assertion.
"""

from pathlib import Path

import pytest

from jclparser import parse_jcl
from jclparser.jes_statements import JobParmStatement, RouteStatement
from jclparser.model import ConditionalBlock, Procedure

FIXTURES = Path(__file__).parent.parent / "fixtures" / "real_world"


# ---------------------------------------------------------------------------
# Utility programs — IEBGENER
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIebgenerCardToPrint:
    """LIB.JCL(CARD2PRT) — inline card data printed to SYSOUT=B."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "iebgener_card2prt.jcl")
        # Sequence numbers (cols 73-80) must be stripped
        assert job.name == "STAGE04C"
        assert len(job.steps) == 1
        assert job.steps[0].program == "IEBGENER"

    def test_job_parameters(self):
        job = parse_jcl(FIXTURES / "iebgener_card2prt.jcl")
        assert job.parameters["CLASS"] == "A"
        assert job.parameters["MSGCLASS"] == "A"
        assert job.parameters["MSGLEVEL"] == ["1", "1"]
        assert job.parameters["NOTIFY"] == "&SYSUID"

    def test_inline_data_captured(self):
        job = parse_jcl(FIXTURES / "iebgener_card2prt.jcl")
        step = job.steps[0]
        sysut1 = step.get_dd("SYSUT1")
        assert sysut1 is not None
        assert sysut1.has_inline_data
        assert "SLIM" in sysut1.inline_data
        assert "CHICOUTIMI" in sysut1.inline_data
        assert "ARTHUR" in sysut1.inline_data

    def test_output_dd(self):
        job = parse_jcl(FIXTURES / "iebgener_card2prt.jcl")
        step = job.steps[0]
        sysut2 = step.get_dd("SYSUT2")
        assert sysut2.parameters.get("SYSOUT") == "B"


@pytest.mark.integration
class TestIebgenerPdsToInternalReader:
    """LIB.JCL(PDS2IN) — copy PDS member to internal reader SYSOUT=(,INTRDR)."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "iebgener_pds2in.jcl")
        assert job.name == "STAGE04C"
        assert job.steps[0].program == "IEBGENER"

    def test_sysut1_pds_member(self):
        job = parse_jcl(FIXTURES / "iebgener_pds2in.jcl")
        sysut1 = job.steps[0].get_dd("SYSUT1")
        assert sysut1 is not None
        assert sysut1.dataset_name == "STAGE04.LIB.JCL(ECHO)"
        assert sysut1.disposition == "SHR"

    def test_internal_reader_sysout(self):
        """SYSOUT=(,INTRDR): class is blank, writer is INTRDR."""
        job = parse_jcl(FIXTURES / "iebgener_pds2in.jcl")
        sysut2 = job.steps[0].get_dd("SYSUT2")
        assert sysut2 is not None
        sysout = sysut2.parameters.get("SYSOUT")
        assert isinstance(sysout, list)
        assert sysout[0] == ""  # blank class
        assert sysout[1] == "INTRDR"


@pytest.mark.integration
class TestIebgenerDiskToDisk:
    """LIB.JCL(DSK2DSK) — copy PDS member to a new sequential dataset."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "iebgener_dsk2dsk.jcl")
        assert job.name == "STAGE04C"
        assert job.steps[0].program == "IEBGENER"

    def test_sysut1_source(self):
        job = parse_jcl(FIXTURES / "iebgener_dsk2dsk.jcl")
        sysut1 = job.steps[0].get_dd("SYSUT1")
        assert sysut1.dataset_name == "STAGE04.LIB.JCL(CREA1)"
        assert sysut1.disposition == "SHR"

    def test_sysut2_target_parameters(self):
        job = parse_jcl(FIXTURES / "iebgener_dsk2dsk.jcl")
        sysut2 = job.steps[0].get_dd("SYSUT2")
        assert sysut2.dataset_name == "STAGE04.LIB.NEW"
        assert sysut2.disposition == ["NEW", "CATLG", "DELETE"]
        assert sysut2.parameters["UNIT"] == "3390"
        dcb = sysut2.parameters["DCB"]
        assert "RECFM=FB" in dcb
        assert "LRECL=80" in dcb


# ---------------------------------------------------------------------------
# Utility programs — IEBCOPY
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIebcopyCompressInPlace:
    """LIB.JCL(COMPRESS) — IEBCOPY in-place PDS compress; &SYSUID.. double-dot."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "iebcopy_compress.jcl")
        assert job.name == "STAGE04C"
        assert job.steps[0].program == "IEBCOPY"

    def test_pds_dd_with_sysuid_symbol(self):
        """DSN=&SYSUID..LIB.JCL: double-dot separator preserved raw."""
        job = parse_jcl(FIXTURES / "iebcopy_compress.jcl")
        pds = job.steps[0].get_dd("PDS")
        assert pds is not None
        assert pds.dataset_name == "&SYSUID..LIB.JCL"
        assert pds.parameters.get("DISP") == "OLD"

    def test_sysin_inline_copy_command(self):
        job = parse_jcl(FIXTURES / "iebcopy_compress.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "COPY INDD=PDS,OUTDD=PDS" in sysin.inline_data


@pytest.mark.integration
class TestIebcopyPdsToPdse:
    """LIB.JCL(PDS2PDSE) — IEFBR14 delete old PDSE + IEBCOPY copy with DSNTYPE=LIBRARY."""

    def test_two_steps(self):
        job = parse_jcl(FIXTURES / "iebcopy_pds2pdse.jcl")
        assert job.name == "STAGE04C"
        assert len(job.steps) == 2
        assert job.steps[0].program == "IEFBR14"
        assert job.steps[1].program == "IEBCOPY"

    def test_step01_delete_old_pdse(self):
        """DISP=(MOD,DELETE,DELETE) on DD1 in STEP01."""
        job = parse_jcl(FIXTURES / "iebcopy_pds2pdse.jcl")
        dd1 = job.steps[0].get_dd("DD1")
        assert dd1.dataset_name == "&SYSUID..LIB.JCL.PDSE"
        assert dd1.disposition == ["MOD", "DELETE", "DELETE"]
        assert dd1.parameters["VOL"] == "SER=STGDSK"

    def test_step02_dsntype_library(self):
        """DSNTYPE=LIBRARY marks the target as a PDSE."""
        job = parse_jcl(FIXTURES / "iebcopy_pds2pdse.jcl")
        sysut2 = job.steps[1].get_dd("SYSUT2")
        assert sysut2 is not None
        assert sysut2.parameters.get("DSNTYPE") == "LIBRARY"
        assert sysut2.disposition == ["NEW", "CATLG", "DELETE"]

    def test_step02_sysin_copy_command(self):
        job = parse_jcl(FIXTURES / "iebcopy_pds2pdse.jcl")
        sysin = job.steps[1].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "COPY INDD=SYSUT1,OUTDD=SYSUT2" in sysin.inline_data


# ---------------------------------------------------------------------------
# Utility programs — IEFBR14
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIefbr14Allocate:
    """LIB.JCL(CREA1) — allocate a new sequential dataset."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "iefbr14_alloc.jcl")
        assert job.name == "STAGE04C"
        assert len(job.steps) == 1
        assert job.steps[0].program == "IEFBR14"

    def test_dd_allocation_parameters(self):
        """DD1's continuation spans a //* comment on line 00070008.

        Per z/OS, a comment card does not terminate a DD statement that has
        a pending comma continuation — it is transparent to the merge, so
        UNIT, SPACE, and DCB (all on post-comment lines) still merge into
        DD1 alongside DSN and DISP.
        """
        job = parse_jcl(FIXTURES / "iefbr14_alloc.jcl")
        dd1 = job.steps[0].get_dd("DD1")
        assert dd1.dataset_name == "STAGE04.ALLOC.PARJCL.DEMO"
        assert dd1.disposition == ["NEW", "CATLG", "DELETE"]
        assert dd1.parameters.get("UNIT") == "3390"
        assert dd1.parameters.get("SPACE") == ["TRK", "(2,5,25)"]
        assert "DCB" in dd1.parameters


@pytest.mark.integration
class TestIefbr14Delete:
    """LIB.JCL(DEL1) — delete a dataset via IEFBR14 DISP=(OLD,DELETE,DELETE)."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "iefbr14_delete.jcl")
        assert job.name == "STAGE04D"
        assert job.steps[0].program == "IEFBR14"

    def test_delete_disposition(self):
        job = parse_jcl(FIXTURES / "iefbr14_delete.jcl")
        dd1 = job.steps[0].get_dd("DD1")
        assert dd1.dataset_name == "STAGE04.ALLOC.PARJCL.DEMO"
        assert dd1.disposition == ["OLD", "DELETE", "DELETE"]


@pytest.mark.integration
class TestIefbr14DeleteRecreate:
    """LIB.JCL(DELCREAT) — 3-step job: delete, allocate, confirm."""

    def test_three_steps(self):
        job = parse_jcl(FIXTURES / "iefbr14_del_recreate.jcl")
        assert job.name == "STAGE04D"
        assert len(job.steps) == 3
        names = [s.name for s in job.steps]
        assert names == ["STEP01", "STEP02", "STEPEND"]
        for s in job.steps:
            assert s.program == "IEFBR14"

    def test_step01_delete(self):
        job = parse_jcl(FIXTURES / "iefbr14_del_recreate.jcl")
        dd = job.steps[0].get_dd("DD1")
        assert dd.disposition == ["OLD", "DELETE", "DELETE"]

    def test_step02_allocate(self):
        job = parse_jcl(FIXTURES / "iefbr14_del_recreate.jcl")
        dd = job.steps[1].get_dd("DD2")
        assert dd.disposition == ["NEW", "CATLG", "DELETE"]
        assert dd.parameters["UNIT"] == "3390"

    def test_stepend_keep(self):
        job = parse_jcl(FIXTURES / "iefbr14_del_recreate.jcl")
        dd = job.steps[2].get_dd("DDEND")
        assert dd.disposition == ["OLD", "CATLG", "KEEP"]


# ---------------------------------------------------------------------------
# IDCAMS / GDG operations
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIdcamsGdgCreate:
    """LIB.JCL(GDGCREAT) — DEFINE GDG base + allocate GDGMODEL dataset."""

    def test_two_steps(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_create.jcl")
        assert job.name == "STAGE04C"
        assert len(job.steps) == 2
        assert job.steps[0].program == "IDCAMS"
        assert job.steps[1].program == "IEFBR14"

    def test_sysin_define_gdg(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_create.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "DEFINE GDG" in sysin.inline_data
        assert "STAGE04.STOCK.GDGROUP" in sysin.inline_data

    def test_gdgmodel_allocation(self):
        """GDGMODEL DD with &SYSUID.. double-dot dataset name."""
        job = parse_jcl(FIXTURES / "idcams_gdg_create.jcl")
        gdgmodel = job.steps[1].get_dd("GDGMODEL")
        assert gdgmodel is not None
        assert gdgmodel.dataset_name == "&SYSUID..STOCK.GDGMODEL"
        assert gdgmodel.disposition == ["NEW", "CATLG", "DELETE"]
        assert gdgmodel.parameters["UNIT"] == "3390"


@pytest.mark.integration
class TestIdcamsGdgFeed:
    """LIB.JCL(GDGFEED) — write to GDG(+1) with DCB model back-reference."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_feed.jcl")
        assert job.name == "STAGE04F"
        assert job.steps[0].program == "IEBGENER"

    def test_gdg_relative_generation_plus_one(self):
        """GDG (+1) relative generation in dataset name."""
        job = parse_jcl(FIXTURES / "idcams_gdg_feed.jcl")
        sysut2 = job.steps[0].get_dd("SYSUT2")
        assert sysut2 is not None
        assert sysut2.dataset_name == "&SYSUID..STOCK.GDGROUP(+1)"
        assert sysut2.disposition == ["NEW", "CATLG", "DELETE"]

    def test_dcb_model_back_reference(self):
        """DCB=(&SYSUID..STOCK.GDGMODEL): symbol with double-dot in DCB."""
        job = parse_jcl(FIXTURES / "idcams_gdg_feed.jcl")
        sysut2 = job.steps[0].get_dd("SYSUT2")
        dcb = sysut2.parameters.get("DCB")
        assert dcb is not None
        assert "&SYSUID..STOCK.GDGMODEL" in dcb

    def test_sysut1_inline_data(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_feed.jcl")
        sysut1 = job.steps[0].get_dd("SYSUT1")
        assert sysut1.has_inline_data
        assert "ARTICLE1" in sysut1.inline_data


@pytest.mark.integration
class TestIdcamsGdgLast:
    """LIB.JCL(GDGLAST) — IDCAMS PRINT of current generation GDG(0)."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_last.jcl")
        assert job.name == "STAGE04V"
        assert job.steps[0].program == "IDCAMS"

    def test_gdg_generation_zero(self):
        """GDG (0) — current generation in dataset name."""
        job = parse_jcl(FIXTURES / "idcams_gdg_last.jcl")
        indd1 = job.steps[0].get_dd("INDD1")
        assert indd1 is not None
        assert indd1.dataset_name == "&SYSUID..STOCK.GDGROUP(0)"
        assert indd1.parameters.get("DISP") == "OLD"

    def test_sysin_print_command(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_last.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "PRINT INFILE(INDD1) CHARACTER" in sysin.inline_data


@pytest.mark.integration
class TestIdcamsGdgAlter:
    """LIB.JCL(GDGALTER) — ALTER GDG base limit."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_alter.jcl")
        assert job.name == "STAGE04A"
        assert job.steps[0].name == "GDALT1"
        assert job.steps[0].program == "IDCAMS"

    def test_sysin_alter_command(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_alter.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "ALTER STAGE04.STOCK.GDGROUP" in sysin.inline_data
        assert "LIMIT(5)" in sysin.inline_data


@pytest.mark.integration
class TestIdcamsGdgDelete:
    """LIB.JCL(GDGDELET) — IDCAMS DELETE of GDG base and model."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_delete.jcl")
        assert job.name == "STAGE04L"
        assert job.steps[0].program == "IDCAMS"

    def test_sysin_delete_commands(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_delete.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "DELETE" in sysin.inline_data
        assert "STAGE04.STOCK.GDGROUP" in sysin.inline_data
        assert "STAGE04.STOCK.GDGMODEL" in sysin.inline_data


@pytest.mark.integration
class TestIdcamsGdgListcat:
    """LIB.JCL(GDGVLCAT) — IDCAMS LISTCAT of GDG base."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_listcat.jcl")
        assert job.name == "STAGE04V"
        assert job.steps[0].program == "IDCAMS"

    def test_sysin_listcat_command(self):
        job = parse_jcl(FIXTURES / "idcams_gdg_listcat.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "LISTCAT" in sysin.inline_data
        assert "STAGE04.STOCK.GDGROUP" in sysin.inline_data


# ---------------------------------------------------------------------------
# IKJEFT01 / IEHLIST
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIkjeft01RexxBatch:
    """LIB.JCL(LREXX) — IKJEFT01 TSO batch to run a REXX exec."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "ikjeft01_rexx.jcl")
        assert job.name == "STAGE04R"
        assert job.steps[0].name == "BATREXX"
        assert job.steps[0].program == "IKJEFT01"

    def test_sysexec_dd_with_symbol(self):
        """SYSEXEC DD points to REXX lib using &SYSUID.. dataset name."""
        job = parse_jcl(FIXTURES / "ikjeft01_rexx.jcl")
        sysexec = job.steps[0].get_dd("SYSEXEC")
        assert sysexec is not None
        assert sysexec.dataset_name == "&SYSUID..LIB.REXX"
        assert sysexec.disposition == "SHR"

    def test_systsin_inline_command(self):
        job = parse_jcl(FIXTURES / "ikjeft01_rexx.jcl")
        systsin = job.steps[0].get_dd("SYSTSIN")
        assert systsin.has_inline_data
        assert "QUEUE" in systsin.inline_data


@pytest.mark.integration
class TestIehlistVtoc:
    """LIB.JCL(LVTOC) — IEHLIST with VOLUME=SER= (long-form keyword)."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "iehlist_vtoc.jcl")
        assert job.name == "STAGE04L"
        assert job.steps[0].program == "IEHLIST"

    def test_volume_ser_long_form(self):
        """VOLUME=SER=STGDSK: long-form keyword preserved as-is."""
        job = parse_jcl(FIXTURES / "iehlist_vtoc.jcl")
        dd1 = job.steps[0].get_dd("DD1")
        assert dd1 is not None
        assert dd1.parameters.get("UNIT") == "3390"
        # VOLUME= (long form) differs from VOL= (short form)
        assert dd1.parameters.get("VOLUME") == "SER=STGDSK"
        assert dd1.parameters.get("DISP") == "OLD"

    def test_sysin_listvtoc_command(self):
        job = parse_jcl(FIXTURES / "iehlist_vtoc.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "LISTVTOC" in sysin.inline_data


# ---------------------------------------------------------------------------
# Advanced: DLM=$$ (custom instream delimiter)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIebgenerDlmIntrdr:
    """LIB.JCL(CARD2IN) — DLM=$$ encapsulating a complete JCL job, output to INTRDR."""

    def test_basic_structure(self):
        """Outer job has one step; inner JCL is opaque inline data."""
        job = parse_jcl(FIXTURES / "iebgener_dlm_intrdr.jcl")
        assert job.name == "STAGE04C"
        assert len(job.steps) == 1
        assert job.steps[0].program == "IEBGENER"

    def test_sysut1_custom_delimiter(self):
        """DD DATA,DLM=$$ captures everything up to $$ as inline data."""
        job = parse_jcl(FIXTURES / "iebgener_dlm_intrdr.jcl")
        sysut1 = job.steps[0].get_dd("SYSUT1")
        assert sysut1 is not None
        assert sysut1.parameters.get("DLM") == "$$"
        assert sysut1.has_inline_data
        # Inner JCL is captured verbatim
        assert "STAGE04L" in sysut1.inline_data
        assert "IEBGENER" in sysut1.inline_data

    def test_sysut2_internal_reader(self):
        """Output goes to SYSOUT=(,INTRDR) — blank class, INTRDR writer."""
        job = parse_jcl(FIXTURES / "iebgener_dlm_intrdr.jcl")
        sysut2 = job.steps[0].get_dd("SYSUT2")
        sysout = sysut2.parameters.get("SYSOUT")
        assert isinstance(sysout, list)
        assert sysout[0] == ""
        assert sysout[1] == "INTRDR"


# ---------------------------------------------------------------------------
# SMTP email via ICEGENER
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSmtpMail:
    """envoi_mail/MYSMAIL.jcl — SMTP mail via ICEGENER + SYSOUT=(A,SMTP)."""

    def test_job_parameters(self):
        """MSGLEVEL=1 (scalar, not list); non-standard CLASS=I and MSGCLASS=Y."""
        job = parse_jcl(FIXTURES / "smtp_mail.jcl")
        assert job.name == "MYSMAIL"
        assert job.parameters["MSGLEVEL"] == "1"  # scalar form
        assert job.parameters["CLASS"] == "I"
        assert job.parameters["MSGCLASS"] == "Y"
        assert job.parameters["NOTIFY"] == "&SYSUID"

    def test_step_icegener(self):
        job = parse_jcl(FIXTURES / "smtp_mail.jcl")
        assert job.steps[0].name == "MAIL"
        assert job.steps[0].program == "ICEGENER"

    def test_sysut2_smtp_sysout(self):
        """SYSOUT=(A,SMTP): class A routed to SMTP writer."""
        job = parse_jcl(FIXTURES / "smtp_mail.jcl")
        sysut2 = job.steps[0].get_dd("SYSUT2")
        assert sysut2 is not None
        sysout = sysut2.parameters.get("SYSOUT")
        assert isinstance(sysout, list)
        assert sysout[0] == "A"
        assert sysout[1] == "SMTP"

    def test_sysut1_smtp_data(self):
        """SYSUT1 contains the SMTP conversation as inline data."""
        job = parse_jcl(FIXTURES / "smtp_mail.jcl")
        sysut1 = job.steps[0].get_dd("SYSUT1")
        assert sysut1.has_inline_data
        assert "HELO MYSERVERNAME" in sysut1.inline_data
        assert "MAIL FROM:" in sysut1.inline_data
        assert "SUBJECT: TEST MAIL" in sysut1.inline_data


@pytest.mark.integration
class TestSmtpMailAttach:
    """envoi_mail/MYSMAILP.jcl — SMTP mail with MIME attachment (DD concatenation)."""

    def test_job_step(self):
        job = parse_jcl(FIXTURES / "smtp_mail_attach.jcl")
        assert job.name == "MYSMAILP"
        assert job.steps[0].name == "MAILP"
        assert job.steps[0].program == "ICEGENER"

    def test_sysut2_smtp(self):
        job = parse_jcl(FIXTURES / "smtp_mail_attach.jcl")
        sysut2 = job.steps[0].get_dd("SYSUT2")
        sysout = sysut2.parameters.get("SYSOUT")
        assert sysout == ["A", "SMTP"]

    def test_sysut1_dd_concatenation(self):
        """SYSUT1 is the first of multiple concatenated DD * statements."""
        job = parse_jcl(FIXTURES / "smtp_mail_attach.jcl")
        step = job.steps[0]
        sysut1 = step.get_dd("SYSUT1")
        assert sysut1.has_inline_data
        # MIME header content
        assert "MIME-VERSION" in sysut1.inline_data or "BOUNDARY" in sysut1.inline_data


# ---------------------------------------------------------------------------
# C language compilation + link
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCCompileLink:
    """compilation_C/CC.jcl — C source compile (CCNDRVR) + link (IEWL)."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "c_compile_link.jcl")
        assert job.name == "COMPILNK"
        assert len(job.steps) == 2
        assert job.steps[0].name == "COMPILE"
        assert job.steps[0].program == "CCNDRVR"
        assert job.steps[1].name == "BIND1"
        assert job.steps[1].program == "IEWL"

    def test_set_and_job_parameters(self):
        job = parse_jcl(FIXTURES / "c_compile_link.jcl")
        assert job.set_statements.get("FICHIER") == "HELLOC"
        assert job.parameters["CLASS"] == "A"
        assert job.parameters["REGION"] == "0M"

    def test_compile_parm_nested_quotes(self):
        """PARM='/SEARCH(''CEE.SCEEH.+'') ...' — JCL doubled-quote unescaping."""
        job = parse_jcl(FIXTURES / "c_compile_link.jcl")
        parm = job.steps[0].parameters.get("PARM")
        assert parm is not None
        # After JCL quote unescaping, '' becomes '
        assert "/SEARCH(" in parm
        assert "NOOPT" in parm
        assert "OBJ LIST" in parm

    def test_steplib_concatenation(self):
        """STEPLIB has 3 concatenated DDs (CEE.SCEERUN, SCEERUN2, CBC.SCCNCMP)."""
        job = parse_jcl(FIXTURES / "c_compile_link.jcl")
        step = job.steps[0]
        # First DD is named STEPLIB; subsequent unnamed DDs concatenate it
        dd_names = [dd.name for dd in step.dd_statements]
        steplib_idx = dd_names.index("STEPLIB")
        concat_count = 1
        for name in dd_names[steplib_idx + 1 :]:
            if name == "":
                concat_count += 1
            else:
                break
        assert concat_count == 3  # STEPLIB + 2 unnamed concat DDs

    def test_bind1_opts_inline_data(self):
        """BIND1 step has OPTS DD * with linker option cards."""
        job = parse_jcl(FIXTURES / "c_compile_link.jcl")
        opts = job.steps[1].get_dd("OPTS")
        assert opts.has_inline_data
        assert "AMODE=31" in opts.inline_data
        assert "NORENT" in opts.inline_data

    def test_syslib_concatenation(self):
        """SYSLIB in BIND1 has multiple library concatenations."""
        job = parse_jcl(FIXTURES / "c_compile_link.jcl")
        step = job.steps[1]
        dd_names = [dd.name for dd in step.dd_statements]
        assert "SYSLIB" in dd_names
        syslib_idx = dd_names.index("SYSLIB")
        concat_count = 1
        for name in dd_names[syslib_idx + 1 :]:
            if name == "":
                concat_count += 1
            else:
                break
        assert concat_count >= 4  # CEE.SCEELKEX + at least 3 more libs


@pytest.mark.integration
class TestCExecDynamic:
    """compilation_C/EXECC.jcl — run compiled C program using SET symbol as PGM."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "c_exec_dynamic.jcl")
        assert job.name == "RUN"
        assert len(job.steps) == 1

    def test_set_symbol(self):
        job = parse_jcl(FIXTURES / "c_exec_dynamic.jcl")
        assert job.set_statements.get("FICHIER") == "HELLOC"

    def test_exec_pgm_is_symbol(self):
        """PGM=&FICHIER — program name is an unresolved SET symbol."""
        job = parse_jcl(FIXTURES / "c_exec_dynamic.jcl")
        # parse_jcl returns the raw (unresolved) value
        assert job.steps[0].program == "&FICHIER"
        assert job.steps[0].name == "RUNPRM"

    def test_standard_dump_dds(self):
        job = parse_jcl(FIXTURES / "c_exec_dynamic.jcl")
        step = job.steps[0]
        dd_names = [dd.name for dd in step.dd_statements]
        assert "SYSUDUMP" in dd_names
        assert "SYSABEND" in dd_names


# ---------------------------------------------------------------------------
# COBOL compilation + exec
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCobolCompileLink:
    """compilation_COBOL/COBC.jcl — COBOL compile (IGYCRCTL) + link (IEWL)."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "cobol_compile_link.jcl")
        assert job.name == "COBCOMP"
        assert len(job.steps) == 2
        assert job.steps[0].program == "IGYCRCTL"
        assert job.steps[1].program == "IEWL"

    def test_msgclass_numeric(self):
        """MSGCLASS=1 — numeric value (non-alphabetic) is valid JCL."""
        job = parse_jcl(FIXTURES / "cobol_compile_link.jcl")
        assert job.parameters["MSGCLASS"] == "1"

    def test_set_with_dollar_sign(self):
        """SET FICHIER=CHICOU$Z — $ in symbol value is valid."""
        job = parse_jcl(FIXTURES / "cobol_compile_link.jcl")
        assert job.set_statements.get("FICHIER") == "CHICOU$Z"

    def test_compile_step_sysut_dds(self):
        """COBOL compile needs 7 work DDs (SYSUT1–SYSUT7)."""
        job = parse_jcl(FIXTURES / "cobol_compile_link.jcl")
        step = job.steps[0]
        sysut_names = [
            dd.name for dd in step.dd_statements if dd.name.startswith("SYSUT")
        ]
        assert len(sysut_names) == 7

    def test_link_step_opts_inline(self):
        job = parse_jcl(FIXTURES / "cobol_compile_link.jcl")
        opts = job.steps[1].get_dd("OPTS")
        assert opts.has_inline_data
        assert "AMODE=31" in opts.inline_data


@pytest.mark.integration
class TestCobolExecParm:
    """compilation_COBOL/EXECC.jcl — run COBOL program with PARM and $ in SET."""

    def test_basic_structure(self):
        job = parse_jcl(FIXTURES / "cobol_exec_parm.jcl")
        assert job.name == "MYRUN"
        assert len(job.steps) == 1
        assert job.steps[0].name == "RUNPRM"

    def test_active_set_only(self):
        """Only the uncommented SET is active; commented //* SET lines are ignored."""
        job = parse_jcl(FIXTURES / "cobol_exec_parm.jcl")
        assert job.set_statements.get("FICHIER") == "CHICOU$Z"

    def test_exec_parm(self):
        """PARM='ADCDA.TEST' on EXEC statement."""
        job = parse_jcl(FIXTURES / "cobol_exec_parm.jcl")
        assert job.steps[0].parameters.get("PARM") == "ADCDA.TEST"

    def test_dollar_in_dsn(self):
        """Dataset name ADCDA.MALIB.DATA.IN.DEP$JAN contains $ character."""
        job = parse_jcl(FIXTURES / "cobol_exec_parm.jcl")
        depens = job.steps[0].get_dd("DEPENS")
        assert depens is not None
        assert "DEP$JAN" in depens.dataset_name


# ---------------------------------------------------------------------------
# Sequence-number stripping (cross-cutting)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSequenceNumberStripping:
    """Verify that 80-column mainframe records have cols 73-80 stripped."""

    def test_seqnum_lines_parse_as_clean_jcl(self):
        """iebgener_card2prt.jcl has 80-char lines; job name must not contain digits."""
        job = parse_jcl(FIXTURES / "iebgener_card2prt.jcl")
        # If seqnums weren't stripped, the job name would pick up garbage
        assert job.name == "STAGE04C"
        # The sequence column content (e.g. "00010001") must NOT appear in parameters
        for val in job.parameters.values():
            if isinstance(val, str):
                assert not val.isdigit() or len(val) <= 4

    def test_continuation_in_seqnum_file(self):
        """Continuation lines in an 80-col file must be correctly merged."""
        job = parse_jcl(FIXTURES / "iebcopy_pds2pdse.jcl")
        # SYSUT2 parameters span multiple continuation lines in the 80-col file
        sysut2 = job.steps[1].get_dd("SYSUT2")
        assert sysut2.parameters.get("DSNTYPE") == "LIBRARY"
        dcb = sysut2.parameters.get("DCB")
        assert "DSORG=PO" in dcb


# ---------------------------------------------------------------------------
# Amazon CardDemo — carddemo_creastmt.jcl
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCardDemoCreatStmt:
    """carddemo_creastmt.jcl — AWS CardDemo create-statement job."""

    def test_job_structure(self):
        job = parse_jcl(FIXTURES / "carddemo_creastmt.jcl")
        assert job.name == "CREASTMT"
        assert job.accounting_info == "Create Statement"
        assert len(job.steps) == 5

    def test_typed_job_properties(self):
        job = parse_jcl(FIXTURES / "carddemo_creastmt.jcl")
        assert job.time == "1440"
        assert job.notify == "&SYSUID"
        assert job.msgclass == "H"
        assert job.msglevel == ["1", "1"]

    def test_step_cond_parameters(self):
        job = parse_jcl(FIXTURES / "carddemo_creastmt.jcl")
        # STEP020/STEP030/STEP040 all run only if previous RC = 0
        assert job.steps[2].name == "STEP020"
        assert job.steps[2].parameters["COND"] == ["0", "NE"]
        assert job.steps[3].parameters["COND"] == ["0", "NE"]
        assert job.steps[4].parameters["COND"] == ["0", "NE"]

    def test_dcb_typed_properties(self):
        """STEP010/SORTOUT DCB=(LRECL=350,BLKSIZE=3500,RECFM=FB)."""
        job = parse_jcl(FIXTURES / "carddemo_creastmt.jcl")
        sortout = job.steps[1].get_dd("SORTOUT")
        assert sortout is not None
        dcb = sortout.dcb
        assert dcb is not None
        assert dcb.recfm == "FB"
        assert dcb.lrecl == 350
        assert dcb.blksize == 3500

    def test_space_typed_properties(self):
        """STEP010/SORTOUT SPACE=(CYL,(1,1),RLSE)."""
        job = parse_jcl(FIXTURES / "carddemo_creastmt.jcl")
        sortout = job.steps[1].get_dd("SORTOUT")
        sp = sortout.space
        assert sp is not None
        assert sp.unit == "CYL"
        assert sp.primary == 1
        assert sp.secondary == 1
        assert sp.rlse is True

    def test_steplib_dsn_list(self):
        """STEP040 has //STEPLIB DD DSN=AWS.M2.CARDDEMO.LOADLIB."""
        job = parse_jcl(FIXTURES / "carddemo_creastmt.jcl")
        step040 = next(s for s in job.steps if s.name == "STEP040")
        assert step040.steplib == ["AWS.M2.CARDDEMO.LOADLIB"]

    def test_step_input_output_datasets(self):
        """STEP040 reads from 4 VSAM datasets and writes 2 output files."""
        job = parse_jcl(FIXTURES / "carddemo_creastmt.jcl")
        step040 = next(s for s in job.steps if s.name == "STEP040")
        inputs = step040.get_input_datasets()
        outputs = step040.get_output_datasets()
        assert "AWS.M2.CARDDEMO.TRXFL.VSAM.KSDS" in inputs
        assert "AWS.M2.CARDDEMO.CARDXREF.VSAM.KSDS" in inputs
        assert "AWS.M2.CARDDEMO.STATEMNT.PS" in outputs
        assert "AWS.M2.CARDDEMO.STATEMNT.HTML" in outputs

    def test_deldef01_sysin_inline_data(self):
        """DELDEF01 step has VSAM DEFINE CLUSTER commands as inline data."""
        job = parse_jcl(FIXTURES / "carddemo_creastmt.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin is not None
        assert sysin.has_inline_data
        assert "DELETE" in sysin.inline_data
        assert "DEFINE" in sysin.inline_data
        assert "CLUSTER" in sysin.inline_data


# ---------------------------------------------------------------------------
# COND parameter forms — cond_codes.jcl
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCondCodesJob:
    """cond_codes.jcl — exercises every COND= form defined in JCL."""

    def test_job_level_cond(self):
        job = parse_jcl(FIXTURES / "cond_codes.jcl")
        assert job.name == "CONDJOB"
        assert job.accounting_info == "5555"
        # COND=(4,LT) at job level
        assert job.parameters["COND"] == ["4", "LT"]

    def test_five_steps_all_programs(self):
        job = parse_jcl(FIXTURES / "cond_codes.jcl")
        assert len(job.steps) == 5
        assert all(s.program == "IEFBR14" for s in job.steps)

    def test_step_cond_with_step_reference(self):
        """STEP2 COND=(0,NE,STEP1) — includes step-name qualifier."""
        job = parse_jcl(FIXTURES / "cond_codes.jcl")
        step2 = next(s for s in job.steps if s.name == "STEP2")
        assert step2.parameters["COND"] == ["0", "NE", "STEP1"]

    def test_cond_even(self):
        """STEP3 COND=EVEN — run only if any prior step abended."""
        job = parse_jcl(FIXTURES / "cond_codes.jcl")
        step3 = next(s for s in job.steps if s.name == "STEP3")
        assert step3.parameters["COND"] == "EVEN"

    def test_cond_only(self):
        """STEP4 COND=ONLY — run only if all prior steps abended."""
        job = parse_jcl(FIXTURES / "cond_codes.jcl")
        step4 = next(s for s in job.steps if s.name == "STEP4")
        assert step4.parameters["COND"] == "ONLY"

    def test_compound_cond(self):
        """STEP5 COND=((4,GT,STEP1),(8,EQ,STEP2)) — multiple conditions."""
        job = parse_jcl(FIXTURES / "cond_codes.jcl")
        step5 = next(s for s in job.steps if s.name == "STEP5")
        cond = step5.parameters["COND"]
        assert isinstance(cond, list)
        assert any("4,GT,STEP1" in c for c in cond)
        assert any("8,EQ,STEP2" in c for c in cond)

    def test_step1_has_no_cond(self):
        """STEP1 has no COND — it always runs."""
        job = parse_jcl(FIXTURES / "cond_codes.jcl")
        step1 = next(s for s in job.steps if s.name == "STEP1")
        assert step1.parameters.get("COND") is None


# ---------------------------------------------------------------------------
# DFSORT — sort_job.jcl
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSortJob:
    """sort_job.jcl — DFSORT with SORT/INCLUDE and ICEMAN MERGE."""

    def test_job_structure(self):
        job = parse_jcl(FIXTURES / "sort_job.jcl")
        assert job.name == "SORTJOB"
        assert job.accounting_info == "9999"
        assert job.parameters["CLASS"] == "S"
        assert len(job.steps) == 2

    def test_step1_sort_program(self):
        job = parse_jcl(FIXTURES / "sort_job.jcl")
        step1 = job.steps[0]
        assert step1.name == "STEP1"
        assert step1.program == "SORT"

    def test_sortin_is_input(self):
        job = parse_jcl(FIXTURES / "sort_job.jcl")
        sortin = job.steps[0].get_dd("SORTIN")
        assert sortin is not None
        assert sortin.dataset_name == "INPUT.DATA"
        assert sortin.is_input()

    def test_sortout_space_typed_properties(self):
        """SORTOUT SPACE=(CYL,(50,10)) — large allocation for sort work."""
        job = parse_jcl(FIXTURES / "sort_job.jcl")
        sortout = job.steps[0].get_dd("SORTOUT")
        sp = sortout.space
        assert sp is not None
        assert sp.unit == "CYL"
        assert sp.primary == 50
        assert sp.secondary == 10

    def test_step1_sysin_inline_sort_control(self):
        """SYSIN carries SORT FIELDS and INCLUDE control cards."""
        job = parse_jcl(FIXTURES / "sort_job.jcl")
        sysin = job.steps[0].get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "SORT FIELDS=" in sysin.inline_data
        assert "INCLUDE COND=" in sysin.inline_data

    def test_step2_iceman_merge(self):
        """STEP2 uses ICEMAN (SORT alias) for MERGE."""
        job = parse_jcl(FIXTURES / "sort_job.jcl")
        step2 = job.steps[1]
        assert step2.name == "STEP2"
        assert step2.program == "ICEMAN"
        sysin = step2.get_dd("SYSIN")
        assert sysin.has_inline_data
        assert "MERGE FIELDS=" in sysin.inline_data


# ---------------------------------------------------------------------------
# JES2 control statements — jobparm_usage.jcl
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestJes2TypedStatements:
    """jobparm_usage.jcl — /*JOBPARM and /*ROUTE typed JES2 statements."""

    def test_jes_raw_statements(self):
        job = parse_jcl(FIXTURES / "jobparm_usage.jcl")
        assert job.name == "JESJOB"
        assert job.accounting_info == "1234"
        assert len(job.jes_statements) == 2
        assert any("JOBPARM" in s for s in job.jes_statements)
        assert any("ROUTE" in s for s in job.jes_statements)

    def test_jobparm_typed_statement(self):
        """/*JOBPARM ROOM=123,TIME=60 → JobParmStatement."""
        job = parse_jcl(FIXTURES / "jobparm_usage.jcl")
        jp = next(
            (s for s in job.jes_typed_statements if isinstance(s, JobParmStatement)),
            None,
        )
        assert jp is not None
        assert jp.parameters["ROOM"] == "123"
        assert jp.parameters["TIME"] == "60"

    def test_route_typed_statement(self):
        """/*ROUTE PRINT LOCAL → RouteStatement."""
        job = parse_jcl(FIXTURES / "jobparm_usage.jcl")
        rt = next(
            (s for s in job.jes_typed_statements if isinstance(s, RouteStatement)),
            None,
        )
        assert rt is not None
        assert rt.subcommand == "PRINT"
        assert rt.destination == "LOCAL"

    def test_two_steps_present(self):
        job = parse_jcl(FIXTURES / "jobparm_usage.jcl")
        assert len(job.steps) == 2
        assert job.steps[0].name == "STEP1"
        assert job.steps[1].name == "STEP2"

    def test_dd_star_inline_data(self):
        """STEP1/DD1 is DD * with one line of inline data."""
        job = parse_jcl(FIXTURES / "jobparm_usage.jcl")
        dd1 = job.steps[0].get_dd("DD1")
        assert dd1 is not None
        assert dd1.has_inline_data
        assert "Data line 1" in dd1.inline_data


# ---------------------------------------------------------------------------
# GDG relative generations — gdg_usage.jcl
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGdgRelativeGenerations:
    """gdg_usage.jcl — GDG base with (+1), (0), (-1) and a temporary pass."""

    def test_job_structure(self):
        job = parse_jcl(FIXTURES / "gdg_usage.jcl")
        assert job.name == "GDGJOB"
        assert len(job.steps) == 2

    def test_new_generation_is_output(self):
        """GDG(+1) with DISP=(NEW,CATLG,DELETE) is an output dataset."""
        job = parse_jcl(FIXTURES / "gdg_usage.jcl")
        outfile = job.steps[0].get_dd("OUTFILE")
        assert outfile is not None
        assert outfile.dataset_name == "MY.GDG.BASE(+1)"
        assert outfile.is_output()
        assert not outfile.is_input()
        assert not outfile.is_temporary()

    def test_current_generation_is_input(self):
        """GDG(0) with DISP=SHR is an input dataset."""
        job = parse_jcl(FIXTURES / "gdg_usage.jcl")
        infile = job.steps[1].get_dd("INFILE")
        assert infile is not None
        assert infile.dataset_name == "MY.GDG.BASE(0)"
        assert infile.is_input()

    def test_prior_generation_is_input(self):
        """GDG(-1) with DISP=SHR is a prior-generation input."""
        job = parse_jcl(FIXTURES / "gdg_usage.jcl")
        hist = job.steps[1].get_dd("HIST")
        assert hist is not None
        assert hist.dataset_name == "MY.GDG.BASE(-1)"
        assert hist.is_input()

    def test_temporary_pass_dataset(self):
        """&&TEMP with DISP=(NEW,PASS) is a temporary dataset passed to next step."""
        job = parse_jcl(FIXTURES / "gdg_usage.jcl")
        temp = job.steps[1].get_dd("TEMP")
        assert temp is not None
        assert temp.dataset_name == "&&TEMP"
        assert temp.disposition == ["NEW", "PASS"]
        assert temp.is_temporary()

    def test_outfile_dcb_typed(self):
        """OUTFILE DCB=(LRECL=80,RECFM=FB,BLKSIZE=0)."""
        job = parse_jcl(FIXTURES / "gdg_usage.jcl")
        outfile = job.steps[0].get_dd("OUTFILE")
        dcb = outfile.dcb
        assert dcb is not None
        assert dcb.recfm == "FB"
        assert dcb.lrecl == 80
        assert dcb.blksize == 0

    def test_outfile_space_typed(self):
        """OUTFILE SPACE=(CYL,(1,1))."""
        job = parse_jcl(FIXTURES / "gdg_usage.jcl")
        outfile = job.steps[0].get_dd("OUTFILE")
        sp = outfile.space
        assert sp is not None
        assert sp.unit == "CYL"
        assert sp.primary == 1
        assert sp.secondary == 1


# ---------------------------------------------------------------------------
# Inline PROC with symbolic parameters — complex_proc.jcl
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestInlineProcDefinition:
    """complex_proc.jcl — inline PROC with symbolic params and IF/THEN/ELSE."""

    def test_job_structure(self):
        job = parse_jcl(FIXTURES / "complex_proc.jcl")
        assert job.name == "COMPLEX"
        assert job.parameters["CLASS"] == "A"

    def test_inline_proc_captured(self):
        """MYPROC is captured in job.procedures."""
        job = parse_jcl(FIXTURES / "complex_proc.jcl")
        assert len(job.procedures) == 1
        assert isinstance(job.procedures[0], Procedure)
        assert job.procedures[0].name == "MYPROC"

    def test_proc_symbolic_parameters(self):
        """MYPROC declares DSN, UNIT, SPACE, VOL with defaults."""
        job = parse_jcl(FIXTURES / "complex_proc.jcl")
        myproc = job.procedures[0]
        assert "DSN" in myproc.parameters
        assert "UNIT" in myproc.parameters
        assert myproc.parameters["UNIT"] == "SYSDA"

    def test_proc_contains_conditional_block(self):
        """MYPROC body includes an IF/THEN/ELSE/ENDIF block."""
        job = parse_jcl(FIXTURES / "complex_proc.jcl")
        myproc = job.procedures[0]
        cond_blocks = [s for s in myproc.steps if isinstance(s, ConditionalBlock)]
        assert len(cond_blocks) == 1
        assert cond_blocks[0].then_steps
        assert cond_blocks[0].else_steps

    def test_proc_invocation_steps(self):
        """RUN1 and RUN2 invoke MYPROC (no PGM=)."""
        job = parse_jcl(FIXTURES / "complex_proc.jcl")
        names = [s.name for s in job.steps]
        assert "RUN1" in names
        assert "RUN2" in names
        run1 = next(s for s in job.steps if s.name == "RUN1")
        run2 = next(s for s in job.steps if s.name == "RUN2")
        assert run1.procedure == "MYPROC"
        assert run1.program is None
        assert run2.procedure == "MYPROC"

    def test_run2_has_overrides(self):
        """RUN2 EXEC MYPROC,DSN='PRODUCTION.DATA',UNIT=VIO overrides two symbolics."""
        job = parse_jcl(FIXTURES / "complex_proc.jcl")
        run2 = next(s for s in job.steps if s.name == "RUN2")
        assert "DSN" in run2.parameters
        assert run2.parameters.get("UNIT") == "VIO"


# ---------------------------------------------------------------------------
# Nested inline PROCs — nested_proc_job.jcl
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestNestedProcDefinition:
    """nested_proc_job.jcl — OUTER PROC calls INNER PROC (nested invocation)."""

    def test_two_procs_captured(self):
        job = parse_jcl(FIXTURES / "nested_proc_job.jcl")
        assert len(job.procedures) == 2
        proc_names = {p.name for p in job.procedures}
        assert "INNER" in proc_names
        assert "OUTER" in proc_names

    def test_inner_proc_symbolic_parameter(self):
        """INNER PROC P=DEFAULT — P defaults to 'DEFAULT'."""
        job = parse_jcl(FIXTURES / "nested_proc_job.jcl")
        inner = next(p for p in job.procedures if p.name == "INNER")
        assert inner.parameters.get("P") == "DEFAULT"

    def test_inner_proc_step(self):
        """INNER/INSTEP runs IEFBR14 with PARM='&P' (symbolic substitution pending)."""
        job = parse_jcl(FIXTURES / "nested_proc_job.jcl")
        inner = next(p for p in job.procedures if p.name == "INNER")
        instep = next(s for s in inner.steps if s.name == "INSTEP")
        assert instep.program == "IEFBR14"
        assert instep.parameters.get("PARM") == "&P"

    def test_outer_proc_calls_inner(self):
        """OUTER/STEP1 invokes INNER with P=&VAL."""
        job = parse_jcl(FIXTURES / "nested_proc_job.jcl")
        outer = next(p for p in job.procedures if p.name == "OUTER")
        step1 = outer.steps[0]
        assert step1.procedure == "INNER"
        assert step1.parameters.get("P") == "&VAL"

    def test_runnest_invokes_outer_with_override(self):
        """RUNNEST EXEC OUTER,VAL=FINAL — final invocation."""
        job = parse_jcl(FIXTURES / "nested_proc_job.jcl")
        assert len(job.steps) == 1
        runnest = job.steps[0]
        assert runnest.name == "RUNNEST"
        assert runnest.procedure == "OUTER"
        assert runnest.parameters.get("VAL") == "FINAL"


# ---------------------------------------------------------------------------
# Parser edge cases — edge_cases.jcl
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEdgeCaseParsing:
    """edge_cases.jcl — DD concatenation, custom DLM, and special PARM chars."""

    def test_job_structure(self):
        job = parse_jcl(FIXTURES / "edge_cases.jcl")
        assert job.name == "EDGECASE"
        assert job.parameters["CLASS"] == "Z"
        assert len(job.steps) == 2

    def test_dd_concatenation_named_first(self):
        """DD2 is the first in a concatenation group; it has an explicit name."""
        job = parse_jcl(FIXTURES / "edge_cases.jcl")
        step1 = job.steps[0]
        dd2 = step1.get_dd("DD2")
        assert dd2 is not None
        assert dd2.dataset_name == "DATA.SET.ONE"

    def test_dd_concatenation_unnamed_members(self):
        """The two continuation DDs have empty names and distinct dataset names."""
        job = parse_jcl(FIXTURES / "edge_cases.jcl")
        unnamed = [d for d in job.steps[0].dd_statements if d.name == ""]
        assert len(unnamed) == 2
        dsns = {d.dataset_name for d in unnamed}
        assert "DATA.SET.TWO" in dsns
        assert "DATA.SET.THREE" in dsns

    def test_custom_dlm_inline_data(self):
        """DD3 uses DLM=$$ so a line containing '//' is included as data."""
        job = parse_jcl(FIXTURES / "edge_cases.jcl")
        dd3 = job.steps[0].get_dd("DD3")
        assert dd3 is not None
        assert dd3.has_inline_data
        assert dd3.parameters.get("DLM") == "$$"
        # The '//' line is data, not a JCL statement
        assert "//" in dd3.inline_data

    def test_parm_with_special_characters(self):
        """STEP2 PARM='A/B*C+D=E' — slashes and operators inside a quoted PARM."""
        job = parse_jcl(FIXTURES / "edge_cases.jcl")
        step2 = next(s for s in job.steps if s.name == "STEP2")
        assert step2.program == "UTILITY"
        assert step2.parameters.get("PARM") == "A/B*C+D=E"


# ---------------------------------------------------------------------------
# DUMMY DD and typed DSNTYPE accessor
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDummyDdAndDsntype:
    """iebcopy_pds2pdse.jcl — DUMMY DD and DSNTYPE=LIBRARY typed accessor."""

    def test_sysprint_dummy(self):
        """IEBCOPY STEP02 SYSPRINT is DUMMY — positional first param."""
        job = parse_jcl(FIXTURES / "iebcopy_pds2pdse.jcl")
        step02 = next(s for s in job.steps if s.name == "STEP02")
        sysprint = step02.get_dd("SYSPRINT")
        assert sysprint is not None
        assert sysprint.parameters.get("_pos_0") == "DUMMY"

    def test_sysut2_dsntype_typed_accessor(self):
        """SYSUT2 DSNTYPE=LIBRARY is accessible via dd.dsntype property."""
        job = parse_jcl(FIXTURES / "iebcopy_pds2pdse.jcl")
        sysut2 = job.steps[1].get_dd("SYSUT2")
        assert sysut2 is not None
        assert sysut2.dsntype == "LIBRARY"
