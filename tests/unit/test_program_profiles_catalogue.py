"""Unit tests for the extended program-profile catalogue.

Covers the utility/compiler profiles added alongside the original set
(IEFBR14, IDCAMS, IEBGENER/IEBCOPY, SORT, IKJEFT01, DB2 batch, DFSRRC00):
ICEGENER, ICETOOL, ADRDSSU, IEHLIST, IEHPROGM, IEBUPDTE, IEBPTPCH, IEBDG,
IEWL/HEWL (Binder), COBOL/PL/I/Assembler compilers, IRXJCL, and batch FTP.
"""

from __future__ import annotations

import jclparser as jp
from jclparser.program_profiles import analyze_job, get_profile


class TestICEGENER:
    def test_detects_sysut1_sysut2_flow(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=ICEGENER\n"
            "//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR\n"
            "//SYSUT2   DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,\n"
            "//             SPACE=(CYL,(1,1))\n"
            "//SYSIN    DD DUMMY\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].program == "ICEGENER"
        assert any("reads" in n for n in results[0].notes)
        assert any("writes" in n for n in results[0].notes)

    def test_symbolic_list_disposition_does_not_crash(self):
        """DISP=(&STATUS,CATLG,DELETE) parses disposition as a list, not a
        string — the shared copy-utility helper must not call .split() on
        it directly (same underlying issue as IEBUPDTE)."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=ICEGENER\n"
            "//SYSUT1   DD DSN=IN.FILE,DISP=(&STATUS,CATLG,DELETE)\n"
            "//SYSUT2   DD DSN=OUT.FILE,DISP=(NEW,CATLG,DELETE)\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        sysut1_events = [e for e in results[0].dataset_events if e.dd_name == "SYSUT1"]
        assert len(sysut1_events) == 1
        assert sysut1_events[0].disp_status == "&STATUS"


class TestICETOOL:
    def test_detects_operators_and_dds(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=ICETOOL\n"
            "//TOOLIN   DD *\n"
            "  COPY FROM(IN1) TO(OUT1)\n"
            "  COUNT FROM(IN1)\n"
            "/*\n"
            "//IN1      DD DSN=IN.FILE,DISP=SHR\n"
            "//OUT1     DD DSN=OUT.FILE,DISP=(NEW,CATLG,DELETE)\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].notes == ["COPY FROM(IN1) TO(OUT1)", "COUNT FROM(IN1)"]

    def test_no_toolin_graceful(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=ICETOOL\n"
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert "no recognised" in results[0].summary


class TestADRDSSU:
    def test_dump_with_dataset_include(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=ADRDSSU\n"
            "//SYSIN    DD *\n"
            " DUMP DATASET(INCLUDE(PROD.DATA)) OUTDDNAME(TAPE1)\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].program == "ADRDSSU"
        notes = " | ".join(results[0].notes)
        assert "DUMP" in notes
        assert "PROD.DATA" in notes

    def test_restore_and_copy_commands(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=ADRDSSU\n"
            "//SYSIN    DD *\n"
            " RESTORE INDDNAME(TAPE1)\n"
            " COPY DATASET(INCLUDE(PROD.A PROD.B))\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        notes = " | ".join(results[0].notes)
        assert "RESTORE" in notes
        assert "COPY" in notes
        assert "PROD.A" in notes and "PROD.B" in notes

    def test_include_not_misattributed_to_earlier_command(self):
        """A later command's DATASET(INCLUDE(...)) must not leak onto an
        earlier command that has none of its own (regression: the search
        used to scan a fixed 400-char window past the command keyword,
        which could reach into the next statement)."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=ADRDSSU\n"
            "//SYSIN    DD *\n"
            " RESTORE INDDNAME(TAPE1)\n"
            " COPY DATASET(INCLUDE(PROD.A PROD.B))\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert results[0].notes == [
            "RESTORE",
            "COPY DATASET(INCLUDE(PROD.A PROD.B))",
        ]

    @staticmethod
    def _notes(sysin: str) -> list[str]:
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=ADRDSSU\n"
            "//SYSIN    DD *\n" + sysin + "/*\n"
        )
        return analyze_job(jp.parse_jcl(src))[0].notes

    def test_keyword_on_continuation_line_is_not_a_command(self):
        """``COMPRESS`` is a DUMP keyword as well as a command: on a
        continuation line it is part of the DUMP, not a second command
        (it was reported as one, nightly 2026-10-14)."""
        notes = self._notes(
            " DUMP DATASET(INCLUDE(PROD.**)) -\n"
            "      OUTDDNAME(TAPE1) -\n"
            "      COMPRESS\n"
        )
        assert notes == ["DUMP DATASET(INCLUDE(PROD.**))"]

    def test_continued_include_list_comments_and_abbreviations(self):
        """A hyphen continuation inside the INCLUDE list is not a name, a
        plus continuation rejoins a split name, ``DS(INCL(...))`` is the
        abbreviated form, and a commented-out command is ignored."""
        notes = self._notes(
            " /* DUMP DATASET(INCLUDE(OLD.**)) */\n"
            " DUMP DATASET(INCLUDE(PROD.A, -\n"
            "      PROD.B)) OUTDDNAME(TAPE1)\n"
            " DUMP DS(INCL(PROD.LONG+\n"
            "      NAME)) OUTDD(TAPE2)\n"
            " COPY DATASET( -\n"
            "      INCLUDE(TEST.A)) RENAMEU((TEST.A,TEST.B))\n"
        )
        assert notes == [
            "DUMP DATASET(INCLUDE(PROD.A PROD.B))",
            "DUMP DATASET(INCLUDE(PROD.LONGNAME))",
            "COPY DATASET(INCLUDE(TEST.A))",
        ]


class TestIEHLIST:
    def test_listvtoc_and_listpds(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEHLIST\n"
            "//SYSIN    DD *\n"
            "  LISTVTOC FORMAT,VOL=SYSDA=VOL001\n"
            "  LISTPDS DSNAME=PROD.LOADLIB\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        notes = " | ".join(results[0].notes)
        assert "LISTVTOC" in notes
        assert "LISTPDS DSNAME=PROD.LOADLIB" in notes

    @staticmethod
    def _analyze(sysin: str):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEHLIST\n"
            "//SYSIN    DD *\n" + sysin + "/*\n"
        )
        return analyze_job(jp.parse_jcl(src))[0]

    def test_listpds_dsname_list_reports_every_dataset(self):
        """``DSNAME=(A,B)`` is the documented LISTPDS list form; the statement
        used to be dropped entirely because the name could not start with
        ``(`` (nightly 2026-10-14)."""
        result = self._analyze(
            "  LISTPDS DSNAME=(D42.PDSONE,'D42.PDSTWO'),VOL=3390=SYS001\n"
        )
        assert result.notes == [
            "LISTPDS DSNAME=D42.PDSONE",
            "LISTPDS DSNAME=D42.PDSTWO",
        ]
        assert result.summary == "IEHLIST: 1 listing command(s)"

    def test_statements_reported_in_coded_order_with_their_own_operands(self):
        """A labelled statement, a quoted name and a continued statement are
        read; LISTVTOC's VOL= stops at the next operand; notes keep the
        order of the statements (they were grouped by command)."""
        result = self._analyze(
            "  LISTPDS DSNAME=A.ONE,VOL=3390=SYS001\n"
            "  LISTVTOC DATE=2026.100,VOL=3390=SYS001,DSNAME=(A.B)\n"
            "LBL      LISTPDS DSNAME='A.TWO',VOL=3390=SYS001\n"
            + "  LISTPDS VOL=3390=SYS001,".ljust(71)
            + "C\n"
            + " " * 15
            + "DSNAME=A.THREE\n"
        )
        assert result.notes == [
            "LISTPDS DSNAME=A.ONE",
            "LISTVTOC VOL=3390=SYS001",
            "LISTPDS DSNAME=A.TWO",
            "LISTPDS DSNAME=A.THREE",
        ]
        assert result.summary == "IEHLIST: 4 listing command(s)"


class TestIEHPROGM:
    def test_scratch_catlg_uncatlg(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEHPROGM\n"
            "//SYSIN    DD *\n"
            "  SCRATCH DSNAME=PROD.OLD,VOL=SYSDA=VOL001\n"
            "  CATLG DSNAME=PROD.NEW,VOL=SYSDA=VOL001\n"
            "  UNCATLG DSNAME=PROD.STALE\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        result = results[0]
        assert result.program == "IEHPROGM"
        actions = {e.action for e in result.dataset_events}
        assert actions == {"DELETE", "ALLOCATE", "UNCATALOG"}
        notes = " | ".join(result.notes)
        assert "SCRATCH PROD.OLD" in notes
        assert "CATLG PROD.NEW" in notes
        assert "UNCATLG PROD.STALE" in notes


class TestIEBUPDTE:
    def test_add_and_repl_members(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBUPDTE\n"
            "//SYSUT2   DD DSN=PROD.SRCLIB,DISP=SHR\n"
            "//SYSIN    DD *\n"
            "./ ADD NAME=MEMBER1\n"
            "SOME DATA\n"
            "./ REPL NAME=MEMBER2\n"
            "MORE DATA\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        notes = " | ".join(results[0].notes)
        assert "ADD NAME=MEMBER1" in notes
        assert "REPL NAME=MEMBER2" in notes
        assert any(e.dd_name == "SYSUT2" for e in results[0].dataset_events)

    def test_symbolic_list_disposition_does_not_crash(self):
        """DISP=(&STATUS,CATLG,DELETE) parses disposition as a list, not a
        string — the profile must not call .split() on it directly."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBUPDTE\n"
            "//SYSUT1   DD DSN=PROD.SRCLIB,DISP=(&STATUS,CATLG,DELETE)\n"
            "//SYSIN    DD *\n"
            "./ ADD NAME=MEMBER1\n"
            "DATA\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        sysut1_events = [e for e in results[0].dataset_events if e.dd_name == "SYSUT1"]
        assert len(sysut1_events) == 1
        assert sysut1_events[0].disp_status == "&STATUS"


class TestIEBPTPCH:
    def test_print_with_member_and_title(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBPTPCH\n"
            "//SYSUT1   DD DSN=PROD.SRCLIB,DISP=SHR\n"
            "//SYSIN    DD *\n"
            "  PRINT TYPORG=PO\n"
            "  TITLE ITEM=1,LIST='REPORT'\n"
            "  MEMBER NAME=MEMBER1\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        notes = " | ".join(results[0].notes)
        assert "PRINT" in notes
        assert "TITLE" in notes
        assert "MEMBER MEMBER1" in notes
        assert "reads PROD.SRCLIB" in notes


class TestIEBDG:
    def test_dsd_fd_create(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBDG\n"
            "//SYSUT2   DD DSN=&&TEMP,DISP=(NEW,PASS)\n"
            "//SYSIN    DD *\n"
            "  DSD OUTPUT=(SYSUT2),DDNAME=SYSUT2\n"
            "  FD NAME=FLD1,STARTLOC=1,LENGTH=10\n"
            "  CREATE NAME=(FLD1),QUANTITY=100,REPEAT=100\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        notes = " | ".join(results[0].notes)
        assert "DSD DDNAME=SYSUT2" in notes
        assert "FLD1" in notes
        assert "CREATE REPEAT=100" in notes


class TestBinder:
    def test_iewl_include_entry_name(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEWL\n"
            "//SYSLMOD  DD DSN=PROD.LOADLIB(MYPROG),DISP=SHR\n"
            "//SYSIN    DD *\n"
            "  INCLUDE OBJLIB(MOD1)\n"
            "  ENTRY MAINEP\n"
            "  NAME MYPROG(R)\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].program == "IEWL"
        notes = " | ".join(results[0].notes)
        assert "INCLUDE" in notes
        assert "ENTRY MAINEP" in notes
        assert "output module: PROD.LOADLIB(MYPROG)" in notes

    def test_hewl_also_matched(self):
        assert get_profile("HEWL") is not None


class TestCompilers:
    def test_cobol_compile_reports_dds(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IGYCRCTL\n"
            "//SYSIN    DD DSN=PROD.COBOL.SRC(MYPROG),DISP=SHR\n"
            "//SYSLIB   DD DSN=PROD.COPYLIB,DISP=SHR\n"
            "//SYSLIN   DD DSN=&&OBJSET,DISP=(NEW,PASS)\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].program == "IGYCRCTL"
        assert "COBOL" in results[0].summary
        notes = " | ".join(results[0].notes)
        assert "source: PROD.COBOL.SRC(MYPROG)" in notes
        assert "copy/include library: PROD.COPYLIB" in notes

    def test_assembler_recognised(self):
        assert get_profile("ASMA90") is not None


class TestIRXJCL:
    def test_exec_name_and_args_from_parm(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IRXJCL,PARM='MYEXEC ARG1 ARG2'\n"
            "//SYSEXEC  DD DSN=PROD.EXEC.LIB,DISP=SHR\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        result = results[0]
        assert result.program == "IRXJCL"
        assert result.invoked_programs == ["MYEXEC"]
        notes = " | ".join(result.notes)
        assert "exec: MYEXEC" in notes
        assert "args: ARG1 ARG2" in notes

    def test_no_parm_graceful(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IRXJCL\n"
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert "no exec name" in results[0].summary

    def test_parenthesised_parm_list_does_not_crash(self):
        """PARM=(sub,parm,...) parses as a list, not a string — the profile
        must not call .split() on it directly."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IRXJCL,PARM=('MYEXEC','ARG1','ARG2')\n"
            "//SYSEXEC  DD DSN=PROD.EXEC.LIB,DISP=SHR\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        result = results[0]
        assert result.invoked_programs == ["MYEXEC"]
        notes = " | ".join(result.notes)
        assert "exec: MYEXEC" in notes
        assert "args: ARG1 ARG2" in notes


class TestFTP:
    def test_open_user_transfer_commands(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=FTP,PARM='REMOTE.HOST.COM (EXIT'\n"
            "//SYSIN    DD *\n"
            "  OPEN REMOTE.HOST.COM\n"
            "  USER FTPUSER FTPPASS\n"
            "  BINARY\n"
            "  PUT LOCAL.FILE REMOTE.FILE\n"
            "  QUIT\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        notes = " | ".join(results[0].notes)
        assert "OPEN REMOTE.HOST.COM" in notes
        assert "USER FTPUSER" in notes
        assert "BINARY" in notes
        assert "PUT LOCAL.FILE" in notes


class TestProgramAliases:
    """Alternate program names that route to an existing profile class."""

    def test_binder_aliases(self):
        for name in ("IEWBLINK", "LOADER", "IEWLDRGO", "HEWLDRGO"):
            assert get_profile(name).__class__.__name__ == "BinderProfile"

    def test_sort_alias(self):
        assert get_profile("SYNCSORT").__class__.__name__ == "SortProfile"

    def test_icetool_alias_reports_own_program_name(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=SYNCTOOL\n"
            "//TOOLIN   DD *\n"
            "  COUNT FROM(IN1)\n"
            "/*\n"
            "//IN1      DD DSN=IN.FILE,DISP=SHR\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].program == "SYNCTOOL"
        assert "SYNCTOOL" in results[0].summary

    def test_db2_batch_alias(self):
        assert get_profile("DSNTIAUL").__class__.__name__ == "DB2BatchProfile"

    def test_compiler_aliases(self):
        assert get_profile("CCNDRVR").__class__.__name__ == "CompilerProfile"
        assert get_profile("IKFCBL00").__class__.__name__ == "CompilerProfile"
        assert get_profile("IEV90").__class__.__name__ == "CompilerProfile"


class TestDSNUTILB:
    def test_reorg_and_runstats_against_tablespace(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=DSNUTILB,PARM='DSN1,UTILITY'\n"
            "//SYSIN    DD *\n"
            "UTIL1    REORG TABLESPACE DB1.TS1\n"
            "UTIL2    RUNSTATS TABLESPACE DB1.TS1\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].program == "DSNUTILB"
        notes = " | ".join(results[0].notes)
        assert "REORG TABLESPACE DB1.TS1" in notes
        assert "RUNSTATS TABLESPACE DB1.TS1" in notes

    def test_no_sysin_graceful(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=DSNUTILB\n"
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert "no recognised" in results[0].summary


class TestBPXBATCH:
    def test_pgm_mode_extracts_target_and_args(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=BPXBATCH,PARM='PGM /u/prod/bin/myprog arg1 arg2'\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        result = results[0]
        assert result.invoked_programs == ["MYPROG"]
        notes = " | ".join(result.notes)
        assert "PGM /u/prod/bin/myprog" in notes
        assert "args: arg1 arg2" in notes

    def test_sh_mode_reports_command(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=BPXBATCH,PARM='SH echo hello'\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].invoked_programs == []
        assert "SH echo hello" in " | ".join(results[0].notes)

    def test_no_parm_graceful(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=BPXBATCH\n"
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert "no PARM" in results[0].summary

    def test_parenthesised_parm_list_does_not_crash(self):
        """PARM=(sub,parm,...) parses as a list, not a string — the profile
        must not call .split() on it directly."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=BPXBATCH,PARM=('PGM','/bin/prog','arg1')\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert results[0].invoked_programs == ["PROG"]


class TestIEBCOMPR:
    def test_compares_sysut1_and_sysut2(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBCOMPR\n"
            "//SYSUT1   DD DSN=OLD.FILE,DISP=SHR\n"
            "//SYSUT2   DD DSN=NEW.FILE,DISP=SHR\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert "compares OLD.FILE vs NEW.FILE" in results[0].notes
        assert {e.dd_name for e in results[0].dataset_events} == {"SYSUT1", "SYSUT2"}
        assert all(e.action == "OPEN_SHARED" for e in results[0].dataset_events)

    def test_no_sysut_graceful(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IEBCOMPR\n"
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert "no SYSUT1/SYSUT2" in results[0].summary


class TestIEHINITT:
    def test_initt_with_vol_and_owner(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEHINITT\n"
            "//SYSIN    DD *\n"
            "  INITT VOL=SER=TAPE01,OWNER=SYS1,NUMBTAPE=1\n"
            "/*\n"
        )
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        notes = " | ".join(results[0].notes)
        assert "VOL=TAPE01" in notes
        assert "OWNER=SYS1" in notes

    def test_no_sysin_graceful(self):
        src = "//MYJOB    JOB  (ACCT)\n//STEP1    EXEC PGM=IEHINITT\n"
        job = jp.parse_jcl(src)
        results = analyze_job(job)
        assert len(results) == 1
        assert "no recognised" in results[0].summary


def test_unknown_program_still_returns_none():
    assert get_profile("SOMECUSTOMPGM") is None


class TestDDEventsFollowTheStatedDisposition:
    """A profile knows what its program does with a DD, not on what terms.

    ``DatasetEvent.action``/``disp_status`` used to be hardcoded per DD role
    — SYSUT1 ``OPEN_SHARED``, SYSUT2 ``ALLOCATE``/``NEW`` — regardless of the
    DISP the JCL actually stated. ``analyze_dataset_lifecycle`` branches on
    exactly those keywords, so a ``DISP=MOD`` append read as a fresh
    allocation and a ``DISP=OLD`` read read as a shared one.
    """

    def test_mod_output_is_an_extend_not_an_allocate(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD DSN=IN.FILE,DISP=OLD\n"
            "//SYSUT2   DD DSN=OUT.FILE,DISP=MOD\n"
        )
        events = {
            e.dd_name: e for e in analyze_job(jp.parse_jcl(src))[0].dataset_events
        }
        assert (events["SYSUT1"].action, events["SYSUT1"].disp_status) == (
            "OPEN_EXCLUSIVE",
            "OLD",
        )
        assert (events["SYSUT2"].action, events["SYSUT2"].disp_status) == (
            "EXTEND",
            "MOD",
        )

    def test_new_output_is_still_an_allocate(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD DSN=IN.FILE,DISP=SHR\n"
            "//SYSUT2   DD DSN=OUT.FILE,DISP=(NEW,CATLG,DELETE)\n"
        )
        events = {
            e.dd_name: e for e in analyze_job(jp.parse_jcl(src))[0].dataset_events
        }
        assert events["SYSUT1"].action == "OPEN_SHARED"
        assert (events["SYSUT2"].action, events["SYSUT2"].disp_status) == (
            "ALLOCATE",
            "NEW",
        )

    def test_a_dd_with_no_disp_falls_back_to_the_role_default(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBGENER\n"
            "//SYSUT1   DD DSN=IN.FILE\n"
            "//SYSUT2   DD DSN=OUT.FILE\n"
        )
        events = {
            e.dd_name: e for e in analyze_job(jp.parse_jcl(src))[0].dataset_events
        }
        assert (events["SYSUT1"].action, events["SYSUT1"].disp_status) == (
            "OPEN_SHARED",
            "SHR",
        )
        assert (events["SYSUT2"].action, events["SYSUT2"].disp_status) == (
            "ALLOCATE",
            "NEW",
        )

    def test_an_unsubstituted_symbolic_keeps_the_role_default_action(self):
        """``DISP=&STATUS`` is reported verbatim, not mapped to UNKNOWN."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=ICEGENER\n"
            "//SYSUT1   DD DSN=IN.FILE,DISP=(&STATUS,CATLG,DELETE)\n"
            "//SYSUT2   DD DSN=OUT.FILE,DISP=(NEW,CATLG,DELETE)\n"
        )
        events = {
            e.dd_name: e for e in analyze_job(jp.parse_jcl(src))[0].dataset_events
        }
        assert events["SYSUT1"].disp_status == "&STATUS"
        assert events["SYSUT1"].action == "OPEN_SHARED"

    def test_iebcompr_reads_exclusively_when_the_dd_says_old(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBCOMPR\n"
            "//SYSUT1   DD DSN=OLD.FILE,DISP=OLD\n"
            "//SYSUT2   DD DSN=NEW.FILE,DISP=SHR\n"
        )
        events = {
            e.dd_name: e for e in analyze_job(jp.parse_jcl(src))[0].dataset_events
        }
        assert events["SYSUT1"].action == "OPEN_EXCLUSIVE"
        assert events["SYSUT2"].action == "OPEN_SHARED"

    def test_iebupdte_update_in_place_is_an_extend(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEBUPDTE\n"
            "//SYSUT1   DD DSN=PROD.SRCLIB,DISP=SHR\n"
            "//SYSUT2   DD DSN=PROD.SRCLIB,DISP=MOD\n"
            "//SYSIN    DD *\n"
            "./ ADD NAME=MEMBER1\n"
            "/*\n"
        )
        events = {
            e.dd_name: e for e in analyze_job(jp.parse_jcl(src))[0].dataset_events
        }
        assert (events["SYSUT2"].action, events["SYSUT2"].disp_status) == (
            "EXTEND",
            "MOD",
        )


class TestIDCAMSContinuedCommands:
    """IDCAMS commands continued with ``-``, listed, or abbreviated."""

    def test_continued_delete_list_and_abbreviation(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IDCAMS\n"
            "//SYSPRINT DD SYSOUT=*\n"
            "//SYSIN    DD *\n"
            "  /* CLEAN UP -\n"
            "  DELETE -\n"
            "     MY.OLD.DSN PURGE\n"
            "  DELETE (A.B.C D.E(MEM)) NONVSAM\n"
            "  DEL X.Y.Z\n"
            "  ALTER -\n"
            "     MY.DSN NEWNAME(MY.NEW)\n"
            "/*\n"
        )
        result = analyze_job(jp.parse_jcl(src))[0]
        deletes = [n for n in result.notes if n.startswith("IDCAMS DELETE")]
        assert deletes == [
            "IDCAMS DELETE MY.OLD.DSN",
            "IDCAMS DELETE A.B.C",
            "IDCAMS DELETE D.E(MEM)",
            "IDCAMS DELETE X.Y.Z",
        ]
        assert "IDCAMS ALTER MY.DSN" in result.notes
        assert [e.action for e in result.dataset_events] == ["DELETE"] * 4
        # raw_control is still the SYSIN text as coded.
        assert result.raw_control is not None
        assert "DELETE -\n" in result.raw_control

    def test_abbreviated_define_commands(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IDCAMS\n"
            "//SYSIN    DD *\n"
            "  DEF CL (NAME(MY.KSDS) INDEXED KEYS(8 0))\n"
            "  DEF NVSAM (NAME(MY.NV) DEVT(3390) VOL(X))\n"
            "  DEFINE GENERATIONDATAGROUP (NAME(MY.GDG) LIMIT(5))\n"
            "  DEF UCAT (NAME(MY.CAT))\n"
            "/*\n"
        )
        result = analyze_job(jp.parse_jcl(src))[0]
        assert result.notes == [
            "IDCAMS DEFINE CLUSTER MY.KSDS",
            "IDCAMS DEFINE NONVSAM MY.NV",
            "IDCAMS DEFINE GDG MY.GDG",
            "IDCAMS DEFINE USERCATALOG MY.CAT",
        ]
        assert [e.action for e in result.dataset_events] == ["ALLOCATE"] * 4

    def test_define_name_stays_in_its_own_command(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IDCAMS\n"
            "//SYSIN    DD *\n"
            "  DEFINE CLUSTER (INDEXED KEYS(8 0))\n"
            "  DEFINE CLUSTER -\n"
            "     (NAME(LATER.KSDS) INDEXED)\n"
            "/*\n"
        )
        result = analyze_job(jp.parse_jcl(src))[0]
        assert result.notes == [
            "IDCAMS DEFINE CLUSTER (unknown)",
            "IDCAMS DEFINE CLUSTER LATER.KSDS",
        ]

    def test_define_name_with_generation_or_symbol(self):
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IDCAMS\n"
            "//SYSIN    DD *\n"
            "  DEFINE NONVSAM -\n"
            "     (NAME(BANK.TRAN.DAILY(+1)) -\n"
            "      VOLUMES(V1))\n"
            "  DEFINE GDG (NAME(&HLQ..GDG.BASE) LIMIT(5))\n"
            "  DEFINE CLUSTER (NAME('Q.QUOTED') INDEXED)\n"
            "/*\n"
        )
        result = analyze_job(jp.parse_jcl(src))[0]
        assert result.notes == [
            "IDCAMS DEFINE NONVSAM BANK.TRAN.DAILY(+1)",
            "IDCAMS DEFINE GDG &HLQ..GDG.BASE",
            "IDCAMS DEFINE CLUSTER Q.QUOTED",
        ]


class TestIKJEFT01ReadsCommandsNotComments:
    """DSN SYSTEM / BIND notes come from the commands, as RUN PROGRAM does."""

    def _notes(self, systsin: str) -> list[str]:
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IKJEFT01\n"
            "//SYSTSIN  DD *\n" + systsin + "/*\n"
        )
        return analyze_job(jp.parse_jcl(src))[0].notes

    def test_continued_dsn_command(self):
        notes = self._notes(
            " DSN -\n   SYSTEM(DB2P)\n RUN -\n   PROGRAM(PAYROLL) PLAN(PAYPLAN)\n END\n"
        )
        assert notes == ["DSN SYSTEM(DB2P)", "RUN PROGRAM(PAYROLL)"]

    def test_commented_out_commands_are_not_notes(self):
        notes = self._notes(
            " /* DSN SYSTEM(DB2T) BIND PLAN(OLDPLAN) */\n DSN SYSTEM(DB2P)\n END\n"
        )
        assert notes == ["DSN SYSTEM(DB2P)"]


class TestIDCAMSCommandBoundaries:
    """A command after THEN / ELSE or a ``;`` is a command too."""

    def _notes(self, sysin: str) -> list[str]:
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IDCAMS\n"
            "//SYSIN    DD *\n" + sysin + "/*\n"
        )
        return analyze_job(jp.parse_jcl(src))[0].notes

    def test_commands_in_then_and_else(self):
        notes = self._notes(
            "  LISTCAT ENTRIES(MY.KSDS)\n"
            "  IF LASTCC = 0 THEN DELETE MY.KSDS PURGE\n"
            "  ELSE DEFINE CLUSTER (NAME(MY.KSDS) INDEXED)\n"
            "  IF MAXCC = 0 THEN -\n"
            "     DELETE MY.OLD.DSN\n"
            "  IF MAXCC > 4 THEN ALTER MY.A NEWNAME(MY.B)\n"
        )
        assert notes == [
            "IDCAMS DELETE MY.KSDS",
            "IDCAMS DELETE MY.OLD.DSN",
            "IDCAMS DEFINE CLUSTER MY.KSDS",
            "IDCAMS ALTER MY.A",
            "IDCAMS LISTCAT",
        ]

    def test_commands_separated_by_semicolons(self):
        notes = self._notes(
            "  DELETE A.B PURGE; DELETE C.D PURGE\n"
            "  DEFINE GDG (NAME(E.F) LIMIT(5)); DEFINE GDG (LIMIT(3))\n"
        )
        assert notes == [
            "IDCAMS DELETE A.B",
            "IDCAMS DELETE C.D",
            "IDCAMS DEFINE GDG E.F",
            "IDCAMS DEFINE GDG (unknown)",
        ]

    def test_then_inside_a_dataset_name_is_not_a_keyword(self):
        assert self._notes("  DELETE MY.THEN.ELSE PURGE\n") == [
            "IDCAMS DELETE MY.THEN.ELSE"
        ]

    def test_delete_name_with_symbol(self):
        # DEFINE NAME(...) accepts a JCL symbol; DELETE reads the same names.
        assert self._notes("  DELETE &HLQ..WORK.FILE PURGE\n") == [
            "IDCAMS DELETE &HLQ..WORK.FILE"
        ]


class TestIEFBR14DeleteNotes:
    def test_mod_and_shr_delete_are_reported_as_deletes(self):
        """``DISP=(MOD,DELETE)`` is the "delete if it exists" idiom, and a
        normal DELETE with SHR deletes too; only ``OLD`` got a ``deletes``
        note (nightly 2026-10-14).  ``(NEW,DELETE)`` deletes nothing that
        existed, so it still gets none."""
        src = (
            "//MYJOB    JOB  (ACCT)\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//D1       DD DSN=PROD.A,DISP=(MOD,DELETE,DELETE),\n"
            "//            UNIT=SYSDA,SPACE=(TRK,0)\n"
            "//D2       DD DSN=PROD.B,DISP=(OLD,DELETE)\n"
            "//D3       DD DSN=PROD.C,DISP=(SHR,DELETE)\n"
            "//D4       DD DSN=PROD.D,DISP=(NEW,DELETE),UNIT=SYSDA\n"
            "//D5       DD DSN=PROD.E,DISP=(MOD,CATLG),UNIT=SYSDA\n"
        )
        result = analyze_job(jp.parse_jcl(src))[0]
        assert result.notes == [
            "deletes PROD.A",
            "deletes PROD.B",
            "deletes PROD.C",
        ]
        assert result.summary == "IEFBR14: 5 DD dispositions applied"
