//EXECTEST JOB (ACCT),'EXEC STATEMENT TESTS'
//*----------------------------------------------------------------
//* Test various EXEC statement types and parameters
//*----------------------------------------------------------------
//STEP1    EXEC PGM=IEFBR14
//STEP2    EXEC PGM=IDCAMS,REGION=2048K,TIME=5
//STEP3    EXEC PGM=SORT,
//             PARM='MSGPRT=CRITICAL,LIST,EQUALS',
//             REGION=4096K,
//             TIME=(0,30),
//             COND=(4,LT,STEP1),
//             DYNAMNBR=50,
//             ACCT=(1234,'PROJ-A')
//STEP4    EXEC PGM=MYPROGRAM,
//             PARM=('OPTION1','OPTION2,WITH,COMMAS','OPTION3'),
//             REGION=0M,
//             TIME=NOLIMIT,
//             COND=((0,NE,STEP1),(4,LT,STEP2),(8,LE,STEP3))
//STEP5    EXEC PGM=TEST,
//             PARM='STRING WITH QUOTES'', EMBEDDED QUOTES, AND SPACES',
//             REGION=8M
//PROCSTEP EXEC PROC=MYPROC,
//             COND=(4,LT),
//             PARM.STEP1='VALUE1',
//             DSN.STEP2='MY.DATASET'
//PGMSTEP  EXEC PGM=LOADER,
//             PARM='/OPTION=VALUE,DEBUG=YES,TRACE=ALL',
//             TIME=MAXIMUM,
//             RD=R,
//             DPRTY=(10,15)
//CONDJOB  EXEC PGM=TESTPGM,
//             COND=EVEN
//CONDJOB2 EXEC PGM=TESTPGM,
//             COND=ONLY
//LONGPARM EXEC PGM=TESTPGM,
//             PARM='THIS IS A VERY LONG PARAMETER STRING THAT CONTINUES -
//             ON THE NEXT LINE WITH EVEN MORE TEXT TO TEST CONTINUATION-
//             AND MAKE SURE THE PARSER HANDLES IT CORRECTLY'
