//PROCTEST JOB (ACCT),'PROCEDURE EDGE CASES'
//*----------------------------------------------------------------
//* Test complex procedure scenarios
//*----------------------------------------------------------------
//* Define a simple inline procedure
//SIMPLEPR PROC
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DUMMY
//         PEND
//*
//* Execute the simple procedure
//EXEC1    EXEC PROC=SIMPLEPR
//*
//* Define procedure with parameters
//PARMPROC PROC DSN=DEFAULT.DATA,DISP=SHR,PGM=IEFBR14
//STEP1    EXEC PGM=&PGM
//DD1      DD DSN=&DSN,DISP=&DISP
//         PEND
//*
//* Execute with overrides
//EXEC2    EXEC PROC=PARMPROC,
//             DSN='MY.DATA',
//             DISP='OLD',
//             PGM='TESTPGM'
//*
//* Procedure with multiple steps
//MULTIPR  PROC
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DUMMY
//STEP2    EXEC PGM=IEBGENER
//SYSUT1   DD DUMMY
//SYSUT2   DD DUMMY
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//STEP3    EXEC PGM=IEFBR14
//DD2      DD DUMMY
//         PEND
//*
//EXEC3    EXEC PROC=MULTIPR
//*
//* Override specific step DD
//EXEC4    EXEC PROC=MULTIPR
//STEP2.SYSUT1 DD DSN=INPUT.DATA,DISP=SHR
//STEP2.SYSUT2 DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG)
//*
//* Procedure with conditional execution
//CONDPROC PROC
//STEP1    EXEC PGM=TESTPGM,
//             COND=(4,LT)
//DD1      DD DUMMY
//STEP2    EXEC PGM=TESTPGM,
//             COND=EVEN
//DD2      DD DUMMY
//         PEND
//*
//EXEC5    EXEC PROC=CONDPROC
//*
//* Nested procedure calls (if supported)
//OUTER    PROC
//STEP1    EXEC PROC=SIMPLEPR
//STEP2    EXEC PGM=IEFBR14
//         PEND
//*
//EXEC6    EXEC PROC=OUTER
//*
//* Procedure with complex parameters
//COMPLEX  PROC DSN=,SPACE='(TRK,(10,5))',
//             DCB='(RECFM=FB,LRECL=80)'
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN,
//             DISP=(NEW,CATLG),
//             SPACE=&SPACE,
//             DCB=&DCB
//         PEND
//*
//EXEC7    EXEC PROC=COMPLEX,
//             DSN='MY.NEW.DATA',
//             SPACE='(CYL,(100,50))',
//             DCB='(RECFM=VB,LRECL=255)'
//*
//* ADD statement to add DD after proc execution
//EXEC8    EXEC PROC=SIMPLEPR
//STEP1.DD2 DD DSN=ADDED.DATA,DISP=SHR
//*
//* Override with concatenation
//EXEC9    EXEC PROC=SIMPLEPR
//STEP1.DD1 DD DSN=CONCAT1.DATA,DISP=SHR
//         DD DSN=CONCAT2.DATA,DISP=SHR
//         DD DSN=CONCAT3.DATA,DISP=SHR
//*
//* Procedure with symbolic parameters and SET
//SETPROC  PROC DSN=
//  SET QUAL='TEST'
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN..&QUAL,DISP=SHR
//         PEND
//*
//EXEC10   EXEC PROC=SETPROC,DSN='MY.BASE'
//*
//* Procedure with JCLLIB
//         JCLLIB ORDER=(SYS1.PROCLIB,USER.PROCLIB)
//EXEC11   EXEC PROC=EXTPROC
//*
//* Procedure with defaults and nulls
//NULLPROC PROC DSN=,SPACE=,UNIT=SYSDA
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN,
//             SPACE=&SPACE,
//             UNIT=&UNIT,
//             DISP=SHR
//         PEND
//*
//EXEC12   EXEC PROC=NULLPROC,
//             DSN='MY.DATA',
//             SPACE='(TRK,10)'
//*
//* Very long procedure name (max 8 chars in real JCL)
//LONGNAME PROC
//STEP1    EXEC PGM=IEFBR14
//         PEND
//*
//EXEC13   EXEC PROC=LONGNAME
//*
//* Procedure with inline data
//DATAPROC PROC
//STEP1    EXEC PGM=SORT
//SORTIN   DD *
DATA1
DATA2
DATA3
/*
//SORTOUT  DD SYSOUT=*
//SYSIN    DD *
  SORT FIELDS=(1,10,CH,A)
/*
//         PEND
//*
//EXEC14   EXEC PROC=DATAPROC
//*
//* Override inline data (if possible)
//EXEC15   EXEC PROC=DATAPROC
//STEP1.SORTIN DD DSN=INPUT.DATA,DISP=SHR
//*
//* Procedure invocation with continuation
//EXEC16   EXEC PROC=COMPLEX,
//             DSN='VERY.LONG.DATASET.NAME.THAT.NEEDS.CONTINUATION',
//             SPACE='(CYL,(100,50,20))',
//             DCB='(RECFM=FB,LRECL=80,BLKSIZE=8000)'
