"""Bundled IBM-supplied cataloged procedures.

Customers ``EXEC`` standard IBM-supplied cataloged procedures (IMS region
controllers, DB2 utilities, COBOL compile/link procs) but almost never store
their definitions alongside their own JCL — the definitions live in vendor
PROCLIBs (IMS ``SDFSPROC``, DB2 ``SDSNSAMP``, COBOL ``SIGYPROC``) on the
mainframe.  Without those definitions the explosion engine raises
``ProcedureNotFoundError`` and the invoking step is never expanded.

This module ships a curated set of authentic IBM cataloged procedures as plain
JCL text so they can always be resolved.  The definitions are intentionally
faithful to the IBM-shipped originals but trimmed to the steps, symbolic
parameters, and DD statements that matter for static analysis.

The bundled procedures are exposed as a ``dict`` and as a ready-made loader.
They are designed to be the *last* fallback in a loader chain so inline PROCs
and customer/site PROCs of the same name always take precedence.
"""

from __future__ import annotations

from .proc_loader import DictProcedureLoader, ProcedureLoader

# ---------------------------------------------------------------------------
# IMS region controllers (all invoke PGM=DFSRRC00; see program_profiles.dfsrrc00)
#
# The first PARM sub-parameter selects the region type:
#   BMP = batch message processing, DLI = DL/I batch, DBB = DBB batch,
#   MPP = message processing region.
# ---------------------------------------------------------------------------

_IMSBATCH = """\
//IMSBATCH PROC MBR=TEMPNAME,PSB=,BUF=7,SPIE=0,TEST=0,EXCPVR=0,
//         RST=0,PRLD=,SRCH=0,CKPTID=,MON=N,LOGA=0,FMTO=T,
//         IMSID=IMS1,SWAP=,DBRC=,IRLM=N,IRLMNM=IRLM,BKO=,
//         IOB=,SOUT=A,RGN=512K,SYS2=,ALTID=,APARM=,LOCKMAX=
//G       EXEC PGM=DFSRRC00,REGION=&RGN,
//         PARM=(BMP,&MBR,&PSB,&BUF,&SPIE&TEST&EXCPVR&RST,&PRLD,
//         &SRCH,&CKPTID,&MON,&LOGA,&FMTO,&IMSID,&SWAP,&DBRC,
//         &IRLM,&IRLMNM,&BKO,&IOB,&APARM,&LOCKMAX)
//STEPLIB  DD DSN=IMS.&SYS2.SDFSRESL,DISP=SHR
//         DD DSN=IMS.&SYS2.PGMLIB,DISP=SHR
//PROCLIB  DD DSN=IMS.&SYS2.PROCLIB,DISP=SHR
//SYSUDUMP DD SYSOUT=&SOUT
//IEFRDER  DD DSN=IMS.&SYS2.SLDS,DISP=SHR
//SYSPRINT DD SYSOUT=&SOUT
// PEND
"""

_DLIBATCH = """\
//DLIBATCH PROC MBR=TEMPNAME,PSB=,BUF=7,SPIE=0,TEST=0,EXCPVR=0,
//         RST=0,PRLD=,SRCH=0,CKPTID=,MON=N,LOGA=0,FMTO=T,
//         IMSID=IMS1,SWAP=,DBRC=,IRLM=N,IRLMNM=IRLM,BKO=,
//         IOB=,SOUT=A,RGN=512K,SYS2=,ALTID=,APARM=,LOCKMAX=
//G       EXEC PGM=DFSRRC00,REGION=&RGN,
//         PARM=(DLI,&MBR,&PSB,&BUF,&SPIE&TEST&EXCPVR&RST,&PRLD,
//         &SRCH,&CKPTID,&MON,&LOGA,&FMTO,&IMSID,&SWAP,&DBRC,
//         &IRLM,&IRLMNM,&BKO,&IOB,&APARM,&LOCKMAX)
//STEPLIB  DD DSN=IMS.&SYS2.SDFSRESL,DISP=SHR
//         DD DSN=IMS.&SYS2.PGMLIB,DISP=SHR
//PROCLIB  DD DSN=IMS.&SYS2.PROCLIB,DISP=SHR
//SYSUDUMP DD SYSOUT=&SOUT
//IEFRDER  DD DSN=IMS.&SYS2.SLDS,DISP=SHR
//SYSPRINT DD SYSOUT=&SOUT
// PEND
"""

_DBBBATCH = """\
//DBBBATCH PROC MBR=TEMPNAME,PSB=,BUF=7,SPIE=0,TEST=0,EXCPVR=0,
//         RST=0,PRLD=,SRCH=0,CKPTID=,MON=N,LOGA=0,FMTO=T,
//         IMSID=IMS1,SWAP=,DBRC=,IRLM=N,IRLMNM=IRLM,BKO=,
//         IOB=,SOUT=A,RGN=512K,SYS2=,APARM=,LOCKMAX=
//G       EXEC PGM=DFSRRC00,REGION=&RGN,
//         PARM=(DBB,&MBR,&PSB,&BUF,&SPIE&TEST&EXCPVR&RST,&PRLD,
//         &SRCH,&CKPTID,&MON,&LOGA,&FMTO,&IMSID,&SWAP,&DBRC,
//         &IRLM,&IRLMNM,&BKO,&IOB,&APARM,&LOCKMAX)
//STEPLIB  DD DSN=IMS.&SYS2.SDFSRESL,DISP=SHR
//         DD DSN=IMS.&SYS2.PGMLIB,DISP=SHR
//PROCLIB  DD DSN=IMS.&SYS2.PROCLIB,DISP=SHR
//SYSUDUMP DD SYSOUT=&SOUT
//IEFRDER  DD DSN=IMS.&SYS2.SLDS,DISP=SHR
//SYSPRINT DD SYSOUT=&SOUT
// PEND
"""

# Message processing region. IBM ships this as DFSMPR; IMSMSG is the classic
# alias many sites use, so both spellings resolve to the same definition.
_MPR_BODY = """\
//{name} PROC RGN=512K,SOUT=A,CL1=001,CL2=000,CL3=000,CL4=000,
//         SPIE=0,VALCK=0,TLIM=00,PCB=000,PRLD=,STIMER=,
//         SOD=,DBLDL=,NBA=,OBA=,IMSID=IMS1,SWAP=,SYS2=,
//         AGN=,VSFX=,VFREE=,SSM=,PREINIT=,ALTID=,PWFI=N
//REGION   EXEC PGM=DFSRRC00,REGION=&RGN,
//         PARM=(MSG,&CL1&CL2&CL3&CL4,&SPIE&VALCK&TLIM&PCB,
//         &PRLD,&STIMER,&SOD,&DBLDL,&NBA,&OBA,&IMSID,&SWAP,
//         &AGN,&VSFX,&VFREE,&SSM,&PREINIT,&ALTID,&PWFI)
//STEPLIB  DD DSN=IMS.&SYS2.SDFSRESL,DISP=SHR
//PROCLIB  DD DSN=IMS.&SYS2.PROCLIB,DISP=SHR
//SYSUDUMP DD SYSOUT=&SOUT
//SYSPRINT DD SYSOUT=&SOUT
// PEND
"""

_IMSMSG = _MPR_BODY.format(name="IMSMSG  ")
_DFSMPR = _MPR_BODY.format(name="DFSMPR  ")

# ---------------------------------------------------------------------------
# DB2
# ---------------------------------------------------------------------------

# DB2 online utilities (LOAD, UNLOAD, REORG, RUNSTATS, COPY, ...) via DSNUTILB.
_DSNUPROC = """\
//DSNUPROC PROC LIB='DSN!!0.SDSNLOAD',SYSTEM=DSN,UID='',UTPROC=''
//DSNUPROC EXEC PGM=DSNUTILB,REGION=0M,PARM='&SYSTEM,&UID,&UTPROC'
//STEPLIB  DD DSN=&LIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//UTPRINT  DD SYSOUT=*
//SYSUDUMP DD SYSOUT=*
//SYSREC   DD DUMMY
// PEND
"""

# DB2 precompile + COBOL compile + link-edit (DSNHPC -> IGYCRCTL -> IEWL).
_DSNHICOB = """\
//DSNHICOB PROC WSPC=500,MEM=TEMPNAME,USER=USER,
//         LIB='DSN!!0.RUNLIB.LOAD',
//         SQLLIB='DSN!!0.SDSNLOAD',
//         COBLIB='IGY.SIGYCOMP'
//PC      EXEC PGM=DSNHPC,PARM='HOST(IBMCOB),SOURCE,XREF',REGION=0M
//STEPLIB  DD DSN=&SQLLIB,DISP=SHR
//DBRMLIB  DD DSN=&USER..DBRMLIB.DATA(&MEM),DISP=SHR
//SYSCIN   DD DSN=&&DSNHOUT,DISP=(MOD,PASS),UNIT=SYSDA,
//            SPACE=(800,(&WSPC,&WSPC))
//SYSLIB   DD DSN=&USER..SRCLIB.DATA,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSUDUMP DD SYSOUT=*
//COB     EXEC PGM=IGYCRCTL,REGION=0M,
//         PARM='APOST,LIB,RENT,RES,NODYNAM,LIST,XREF',COND=(4,LT,PC)
//STEPLIB  DD DSN=&COBLIB,DISP=SHR
//SYSIN    DD DSN=&&DSNHOUT,DISP=(OLD,DELETE)
//SYSLIN   DD DSN=&&LOADSET,DISP=(MOD,PASS),UNIT=SYSDA,
//            SPACE=(800,(&WSPC,&WSPC))
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD SPACE=(800,(&WSPC,&WSPC)),UNIT=SYSDA
//LKED    EXEC PGM=IEWL,PARM='LIST,XREF',REGION=0M,COND=(4,LT,COB)
//SYSLIB   DD DSN=&SQLLIB,DISP=SHR
//SYSLIN   DD DSN=&&LOADSET,DISP=(OLD,DELETE)
//SYSLMOD  DD DSN=&LIB(&MEM),DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD SPACE=(1024,(50,50)),UNIT=SYSDA
// PEND
"""

# ---------------------------------------------------------------------------
# COBOL compile / link / go (Enterprise COBOL SIGYPROC procs)
# ---------------------------------------------------------------------------

_IGYWCL = """\
//IGYWCL   PROC LNGPRFX='IGY.V6R3M0',LIBPRFX='CEE',
//         PGMLIB='&&GOSET',GOPGM=GO
//COBOL   EXEC PGM=IGYCRCTL,REGION=0M
//STEPLIB  DD DSN=&LNGPRFX..SIGYCOMP,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSLIN   DD DSN=&&LOADSET,DISP=(MOD,PASS),UNIT=SYSDA,
//            SPACE=(80,(10,10))
//SYSUT1   DD UNIT=SYSDA,SPACE=(80,(10,10))
//LKED    EXEC PGM=IEWBLINK,COND=(8,LT,COBOL),REGION=0M
//SYSLIB   DD DSN=&LIBPRFX..SCEELKED,DISP=SHR
//SYSLIN   DD DSN=&&LOADSET,DISP=(OLD,DELETE)
//SYSLMOD  DD DSN=&PGMLIB(&GOPGM),DISP=(MOD,PASS),UNIT=SYSDA,
//            SPACE=(1024,(50,20,1))
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD UNIT=SYSDA,SPACE=(1024,(50,20))
// PEND
"""

_IGYWCLG = """\
//IGYWCLG  PROC LNGPRFX='IGY.V6R3M0',LIBPRFX='CEE',
//         PGMLIB='&&GOSET',GOPGM=GO
//COBOL   EXEC PGM=IGYCRCTL,REGION=0M
//STEPLIB  DD DSN=&LNGPRFX..SIGYCOMP,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSLIN   DD DSN=&&LOADSET,DISP=(MOD,PASS),UNIT=SYSDA,
//            SPACE=(80,(10,10))
//SYSUT1   DD UNIT=SYSDA,SPACE=(80,(10,10))
//LKED    EXEC PGM=IEWBLINK,COND=(8,LT,COBOL),REGION=0M
//SYSLIB   DD DSN=&LIBPRFX..SCEELKED,DISP=SHR
//SYSLIN   DD DSN=&&LOADSET,DISP=(OLD,DELETE)
//SYSLMOD  DD DSN=&PGMLIB(&GOPGM),DISP=(MOD,PASS),UNIT=SYSDA,
//            SPACE=(1024,(50,20,1))
//SYSPRINT DD SYSOUT=*
//GO      EXEC PGM=*.LKED.SYSLMOD,COND=((8,LT,COBOL),(8,LT,LKED)),
//         REGION=0M
//STEPLIB  DD DSN=&LIBPRFX..SCEERUN,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
// PEND
"""

_COBUCL = """\
//COBUCL   PROC
//COB     EXEC PGM=IGYCRCTL,REGION=0M
//SYSPRINT DD SYSOUT=*
//SYSLIN   DD DSN=&&LOADSET,DISP=(MOD,PASS),UNIT=SYSDA,
//            SPACE=(80,(10,10))
//SYSUT1   DD UNIT=SYSDA,SPACE=(80,(10,10))
//LKED    EXEC PGM=IEWL,REGION=0M,COND=(5,LT,COB)
//SYSLIN   DD DSN=&&LOADSET,DISP=(OLD,DELETE)
//SYSLMOD  DD DSN=&&GOSET(GO),DISP=(MOD,PASS),UNIT=SYSDA,
//            SPACE=(1024,(50,20,1))
//SYSUT1   DD UNIT=SYSDA,SPACE=(1024,(50,20))
//SYSPRINT DD SYSOUT=*
// PEND
"""


BUILTIN_UTILITY_PROCS: dict[str, str] = {
    # IMS region controllers
    "IMSBATCH": _IMSBATCH,
    "DLIBATCH": _DLIBATCH,
    "DBBBATCH": _DBBBATCH,
    "IMSMSG": _IMSMSG,
    "DFSMPR": _DFSMPR,  # IBM-shipped name for the message processing region
    # DB2
    "DSNUPROC": _DSNUPROC,
    "DSNHICOB": _DSNHICOB,
    # COBOL compile / link / go
    "IGYWCL": _IGYWCL,
    "IGYWCLG": _IGYWCLG,
    "COBUCL": _COBUCL,
}


def create_builtin_proc_loader() -> ProcedureLoader:
    """Return a loader serving the bundled IBM-supplied utility procedures.

    The loader is a plain :class:`DictProcedureLoader`; place it last in a
    :class:`CompositeProcedureLoader` chain so inline and site PROCs override
    these defaults.
    """
    return DictProcedureLoader(BUILTIN_UTILITY_PROCS)
