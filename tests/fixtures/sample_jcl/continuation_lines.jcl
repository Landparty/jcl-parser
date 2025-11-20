//CONTTEST JOB (ACCT),'TEST CONTINUATION',
//             CLASS=A,
//             MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14,
//             PARM='OPTION1,OPTION2'
//DD1      DD DSN=MY.DATA.SET,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(10,5)),
//             DCB=(RECFM=FB,LRECL=80)
