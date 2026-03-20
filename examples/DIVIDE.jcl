//* ---------------------------------------------------------------
//* DIVIDE.JCL  –  Split an input dataset into two output streams
//* ---------------------------------------------------------------
//DIVIDE   JOB (ACCT),'DIVIDE EXAMPLE',
//             CLASS=A,
//             MSGCLASS=X,
//             NOTIFY=&SYSUID
//*
//STEP1    EXEC PGM=IEBGENER
//*
//SYSPRINT DD SYSOUT=*
//SYSIN    DD DUMMY
//*
//* Input dataset
//SYSUT1   DD DSN=INPUT.DATA,
//             DISP=SHR
//*
//* Output dataset – parameters split across continuation lines
//SYSUT2   DD DSN=OUTPUT.DATA,
//             DISP=(NEW,CATLG,DELETE),
//             UNIT=SYSDA,
//             SPACE=(TRK,(1,1)),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=800)
//
