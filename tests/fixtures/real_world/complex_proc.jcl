//COMPLEX JOB (1234),'COMPLEX PROC TEST',CLASS=A,MSGCLASS=X
//*
//* A complex job defining and using an inline procedure
//* with symbolic parameters and conditional logic.
//*
//MYPROC   PROC DSN='DEFAULT.DATA',UNIT=SYSDA,SPACE='(CYL,(10,5))',
//             VOL=SER=123456
//*
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN,DISP=(NEW,CATLG,DELETE),
//            UNIT=&UNIT,SPACE=&SPACE,VOL=&VOL
//*
// IF (&DSN = 'PRODUCTION.DATA') THEN
//STEP2    EXEC PGM=PRODPROG
// ELSE
//STEP2    EXEC PGM=TESTPROG
// ENDIF
//*
//         PEND
//*
//* Execute the procedure with default values
//RUN1     EXEC MYPROC
//*
//* Execute with overrides
//RUN2     EXEC MYPROC,DSN='PRODUCTION.DATA',UNIT=VIO
