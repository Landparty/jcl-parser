//TAPEJOB  JOB (ACCT),'TAPE OPERATIONS'
//*----------------------------------------------------------------
//* Test tape-related DD statements and operations
//*----------------------------------------------------------------
//*
//* Write to tape with standard labels
//*----------------------------------------------------------------
//WRITETAP EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=TAPE.DATA,
//             DISP=(NEW,KEEP,DELETE),
//             UNIT=TAPE,
//             VOL=SER=TAPE01,
//             LABEL=(1,SL),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000,DEN=3)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Read from tape
//*----------------------------------------------------------------
//READTAPE EXEC PGM=IEBGENER
//SYSUT1   DD DSN=TAPE.DATA,
//             DISP=OLD,
//             UNIT=TAPE,
//             VOL=SER=TAPE01,
//             LABEL=(1,SL)
//SYSUT2   DD DSN=OUTPUT.DATA,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(50,25)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Multi-volume tape
//*----------------------------------------------------------------
//MULTIVOL EXEC PGM=IEBGENER
//SYSUT1   DD DSN=LARGE.DATA,DISP=SHR
//SYSUT2   DD DSN=TAPE.DATA,
//             DISP=(NEW,KEEP),
//             UNIT=(TAPE,2),
//             VOL=SER=(TAPE01,TAPE02,TAPE03),
//             LABEL=(1,SL),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=32000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Non-labeled tape
//*----------------------------------------------------------------
//NOLABEL  EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=TAPE.DATA,
//             DISP=(NEW,KEEP),
//             UNIT=TAPE,
//             VOL=SER=TAPE04,
//             LABEL=(,NL),
//             DCB=(RECFM=U,BLKSIZE=32760)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Bypass label processing
//*----------------------------------------------------------------
//BYPLABEL EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=TAPE.DATA,
//             DISP=(NEW,KEEP),
//             UNIT=TAPE,
//             VOL=SER=TAPE05,
//             LABEL=(,BLP),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* American National Standard labels
//*----------------------------------------------------------------
//ANSLABEL EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=TAPE.DATA,
//             DISP=(NEW,KEEP),
//             UNIT=TAPE,
//             VOL=SER=TAPE06,
//             LABEL=(1,AL),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Tape with specific file position
//*----------------------------------------------------------------
//FILEPOS  EXEC PGM=IEBGENER
//SYSUT1   DD DSN=TAPE.DATA,
//             DISP=OLD,
//             UNIT=TAPE,
//             VOL=SER=TAPE01,
//             LABEL=(3,SL)
//SYSUT2   DD SYSOUT=*
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Tape with retention period
//*----------------------------------------------------------------
//RETAIN   EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=TAPE.DATA,
//             DISP=(NEW,KEEP),
//             UNIT=TAPE,
//             VOL=SER=TAPE07,
//             LABEL=(1,SL,RETPD=365),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Tape with expiration date
//*----------------------------------------------------------------
//EXPDATE  EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=TAPE.DATA,
//             DISP=(NEW,KEEP),
//             UNIT=TAPE,
//             VOL=SER=TAPE08,
//             LABEL=(1,SL,EXPDT=2026365),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Deferred mounting
//*----------------------------------------------------------------
//DEFER    EXEC PGM=TESTPGM
//TAPE1    DD DSN=TAPE.DATA1,
//             DISP=OLD,
//             UNIT=(TAPE,,DEFER),
//             VOL=SER=TAPE09,
//             LABEL=(1,SL)
//TAPE2    DD DSN=TAPE.DATA2,
//             DISP=OLD,
//             UNIT=(TAPE,,DEFER),
//             VOL=SER=TAPE10,
//             LABEL=(1,SL)
//*
//* Cartridge tape
//*----------------------------------------------------------------
//CART     EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=CART.DATA,
//             DISP=(NEW,KEEP),
//             UNIT=CART,
//             VOL=SER=CART01,
//             LABEL=(1,SL),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=32720)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
