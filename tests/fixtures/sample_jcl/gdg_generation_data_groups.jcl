//GDGTEST  JOB (ACCT),'GENERATION DATA GROUP TESTS'
//*----------------------------------------------------------------
//* Test GDG (Generation Data Group) handling
//*----------------------------------------------------------------
//*
//* Define a new GDG base
//*----------------------------------------------------------------
//DEFGDG   EXEC PGM=IDCAMS
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  DEFINE GDG(NAME(MY.GDG.BASE) -
         LIMIT(10) -
         SCRATCH -
         NOEMPTY)
/*
//*
//* Create new generation (+1)
//*----------------------------------------------------------------
//CREATE   EXEC PGM=IEBGENER
//SYSUT1   DD *
This is generation +1 data
Line 2
Line 3
/*
//SYSUT2   DD DSN=MY.GDG.BASE(+1),
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(10,5)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Read current generation (0)
//*----------------------------------------------------------------
//READCURR EXEC PGM=IEBGENER
//SYSUT1   DD DSN=MY.GDG.BASE(0),DISP=SHR
//SYSUT2   DD SYSOUT=*
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Read previous generation (-1)
//*----------------------------------------------------------------
//READPREV EXEC PGM=IEBGENER
//SYSUT1   DD DSN=MY.GDG.BASE(-1),DISP=SHR
//SYSUT2   DD SYSOUT=*
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Create multiple generations in same job
//*----------------------------------------------------------------
//MULTI1   EXEC PGM=IEBGENER
//SYSUT1   DD *
Generation 1
/*
//SYSUT2   DD DSN=MY.GDG.BASE(+1),
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(5,2)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//MULTI2   EXEC PGM=IEBGENER
//SYSUT1   DD *
Generation 2
/*
//SYSUT2   DD DSN=MY.GDG.BASE(+1),
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(5,2)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//MULTI3   EXEC PGM=IEBGENER
//SYSUT1   DD *
Generation 3
/*
//SYSUT2   DD DSN=MY.GDG.BASE(+1),
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(5,2)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Use generation as input and create new one
//*----------------------------------------------------------------
//COPYINCR EXEC PGM=IEBGENER
//SYSUT1   DD DSN=MY.GDG.BASE(0),DISP=SHR
//SYSUT2   DD DSN=MY.GDG.BASE(+1),
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(10,5)),
//             DCB=(*.SYSUT1)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Delete old generations
//*----------------------------------------------------------------
//DELGDG   EXEC PGM=IDCAMS
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  DELETE MY.GDG.BASE(-5) -
         PURGE -
         GDG
  DELETE MY.GDG.BASE(-6) -
         PURGE -
         GDG
/*
//*
//* List GDG entries
//*----------------------------------------------------------------
//LISTGDG  EXEC PGM=IDCAMS
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  LISTCAT ENTRIES(MY.GDG.BASE) -
          GDG -
          ALL
/*
//*
//* Modify GDG base
//*----------------------------------------------------------------
//MODGDG   EXEC PGM=IDCAMS
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  ALTER MY.GDG.BASE -
        LIMIT(20) -
        SCRATCH
/*
//*
//* GDG with symbols
//*----------------------------------------------------------------
//  SET GDGBASE='MY.GDG.BASE'
//SYMBGDG  EXEC PGM=IEBGENER
//SYSUT1   DD *
Data with symbolic GDG
/*
//SYSUT2   DD DSN=&GDGBASE(+1),
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(5,2)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//* Absolute generation number
//*----------------------------------------------------------------
//ABSGDG   EXEC PGM=IEBGENER
//SYSUT1   DD DSN=MY.GDG.BASE.G0001V00,DISP=SHR
//SYSUT2   DD SYSOUT=*
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
