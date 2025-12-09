//UTILJOBS JOB (ACCT),'UTILITY PROGRAM EXAMPLES'
//*----------------------------------------------------------------
//* Examples of common IBM utility programs
//*----------------------------------------------------------------
//*
//* IEBGENER - Sequential copy
//*----------------------------------------------------------------
//IEBGEN   EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=OUTPUT.DATA,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(100,50),RLSE),
//             DCB=(*.SYSUT1)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* IEBCOPY - PDS copy/compress
//*----------------------------------------------------------------
//IEBCOPY  EXEC PGM=IEBCOPY
//SYSPRINT DD SYSOUT=*
//INPDS    DD DSN=SOURCE.PDS,DISP=SHR
//OUTPDS   DD DSN=TARGET.PDS,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(100,50,50)),
//             DCB=(DSORG=PO,RECFM=FB,LRECL=80,BLKSIZE=27920)
//SYSIN    DD *
  COPY INDD=INPDS,OUTDD=OUTPDS
  SELECT MEMBER=((MEMBER1,NEWNAME1),(MEMBER2))
  EXCLUDE MEMBER=(EXCLUDE1,EXCLUDE2)
/*
//*
//* IEBCOMPR - Compare datasets
//*----------------------------------------------------------------
//IEBCOMPR EXEC PGM=IEBCOMPR
//SYSPRINT DD SYSOUT=*
//DD1      DD DSN=FIRST.DATA,DISP=SHR
//DD2      DD DSN=SECOND.DATA,DISP=SHR
//SYSIN    DD *
  COMPARE TYPORG=PS
/*
//*
//* IEBUPDTE - Maintain source libraries
//*----------------------------------------------------------------
//IEBUPDTE EXEC PGM=IEBUPDTE,PARM=NEW
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD DSN=OLD.SOURCE.LIB,DISP=SHR
//SYSUT2   DD DSN=NEW.SOURCE.LIB,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(50,25,25)),
//             DCB=(DSORG=PO,RECFM=FB,LRECL=80,BLKSIZE=27920)
//SYSIN    DD *
./ ADD NAME=MEMBER1,LIST=ALL
SOURCE CODE LINE 1
SOURCE CODE LINE 2
./ ENDUP
/*
//*
//* IEFBR14 - Dummy program for dataset operations
//*----------------------------------------------------------------
//IEFBR14  EXEC PGM=IEFBR14
//DELETE   DD DSN=OLD.DATA,DISP=(OLD,DELETE)
//CREATE   DD DSN=NEW.DATA,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(10,5)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//*
//* DFSORT - Advanced sorting
//*----------------------------------------------------------------
//DFSORT   EXEC PGM=SORT,REGION=8M
//SORTIN   DD DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD DSN=OUTPUT.DATA,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(CYL,(50,25)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920)
//SORTWORK DD UNIT=SYSDA,SPACE=(CYL,(20,10))
//SYSIN    DD *
  SORT FIELDS=(1,10,CH,A,11,5,ZD,D),
       EQUALS,
       SKIPREC=1
  INCLUDE COND=(15,2,CH,EQ,C'OK')
  OUTREC FIELDS=(1,10,15,50,80:X)
/*
//SYSOUT   DD SYSOUT=*
//*
//* ICETOOL - Advanced data manipulation
//*----------------------------------------------------------------
//ICETOOL  EXEC PGM=ICETOOL
//TOOLMSG  DD SYSOUT=*
//DFSMSG   DD SYSOUT=*
//IN1      DD DSN=INPUT.DATA,DISP=SHR
//OUT1     DD DSN=OUTPUT.DATA,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(CYL,(50,25)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920)
//TOOLIN   DD *
  SORT FROM(IN1) TO(OUT1) USING(CTL1)
/*
//CTL1CNTL DD *
  SORT FIELDS=(1,10,CH,A)
  INCLUDE COND=(20,3,CH,EQ,C'ABC')
/*
//*
//* IEBPTPCH - Print/punch utility
//*----------------------------------------------------------------
//IEBPTPCH EXEC PGM=IEBPTPCH
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD SYSOUT=*
//SYSIN    DD *
  PRINT MAXFLDS=1
  RECORD FIELD=(80)
/*
//*
//* IEBIMAGE - Manage character sets
//*----------------------------------------------------------------
//IEBIMAGE EXEC PGM=IEBIMAGE
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD DSN=IMAGE.LIB,DISP=OLD
//SYSIN    DD *
  INCLUDE NAME=CHARSET1
  INCLUDE NAME=CHARSET2
/*
//*
//* IEHINITT - Initialize tape
//*----------------------------------------------------------------
//IEHINITT EXEC PGM=IEHINITT
//SYSPRINT DD SYSOUT=*
//TAPE     DD UNIT=TAPE,
//             VOL=SER=TAPE01,
//             DISP=(NEW,KEEP),
//             LABEL=(1,SL)
//SYSIN    DD *
  INITT TAPE,SER=TAPE01,NUMBTAPE=1
/*
//*
//* FTP file transfer
//*----------------------------------------------------------------
//FTP      EXEC PGM=FTP,PARM='(EXIT=8'
//SYSPRINT DD SYSOUT=*
//OUTPUT   DD SYSOUT=*
//INPUT    DD *
server.example.com
userid
password
bin
put LOCAL.FILE REMOTE.FILE
quit
/*
