//ADVJOB01 JOB (ACCT123,DEPT456),'ADVANCED JOB EXAMPLES',
//             CLASS=A,
//             MSGCLASS=X,
//             MSGLEVEL=(1,1),
//             NOTIFY=&SYSUID,
//             REGION=4096K,
//             TIME=(1,30),
//             TYPRUN=SCAN,
//             USER=TESTUSER,
//             PASSWORD=SECRET,
//             RESTART=STEP3,
//             COND=(4,LT),
//             ADDRSPC=VIRT,
//             PERFORM=5,
//             PRTY=10,
//             RD=RNC,
//             SCHENV=PRODENV
//*----------------------------------------------------------------
//* Test various JOB statement parameters and edge cases
//*----------------------------------------------------------------
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DUMMY
//STEP2    EXEC PGM=IEFBR14
//DD2      DD DUMMY
