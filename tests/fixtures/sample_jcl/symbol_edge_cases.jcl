//SYMBTEST JOB (ACCT),'SYMBOL SUBSTITUTION TESTS'
//*----------------------------------------------------------------
//* Test complex symbol substitution patterns
//*----------------------------------------------------------------
//  SET SYM1='VALUE1'
//  SET SYM2='VALUE2'
//  SET SYM3='MY.DATA.SET'
//  SET SYM4=100
//  SET SYM5='OPTION1,OPTION2,OPTION3'
//*
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&SYM3,DISP=SHR
//*
//* System symbols
//STEP2    EXEC PGM=TESTPGM,
//             PARM='DATE=&SYSDATE,TIME=&SYSTIME'
//DD2      DD DSN=&SYSUID..MY.DATA,DISP=SHR
//*
//* Nested symbol references
//  SET BASEDS='MY.BASE'
//  SET QUAL1='QUAL1'
//  SET FULLDSN='&BASEDS..&QUAL1'
//STEP3    EXEC PGM=IEFBR14
//DD3      DD DSN=&FULLDSN,DISP=SHR
//*
//* Symbols in various positions
//  SET PGM='IEFBR14'
//  SET CLASS='A'
//  SET REGION='4096K'
//STEP4    EXEC PGM=&PGM,
//             REGION=&REGION
//DD4      DD DUMMY
//*
//* Undefined symbols (should be left as-is or error)
//STEP5    EXEC PGM=IEFBR14
//DD5      DD DSN=&UNDEFINED.DATA,DISP=SHR
//*
//* Symbols in quoted strings
//  SET MSG='HELLO WORLD'
//STEP6    EXEC PGM=TESTPGM,
//             PARM='MESSAGE=&MSG'
//*
//* Multiple symbols in one parameter
//  SET DSN1='PART1'
//  SET DSN2='PART2'
//  SET DSN3='PART3'
//STEP7    EXEC PGM=IEFBR14
//DD6      DD DSN=&DSN1..&DSN2..&DSN3,DISP=SHR
//*
//* Symbols with special characters
//  SET SPECIAL='DATA$ET'
//  SET NUMERIC='123'
//STEP8    EXEC PGM=IEFBR14
//DD7      DD DSN=MY.&SPECIAL..&NUMERIC,DISP=SHR
//*
//* Symbol in procedure override
//  SET PARM1='VALUE1'
//PROCSTEP EXEC PROC=MYPROC,
//             PARM.STEP1='&PARM1'
//*
//* Conditional SET
//  IF (&SYSUID = 'TESTUSER') THEN
//    SET ENV='TEST'
//  ELSE
//    SET ENV='PROD'
//  ENDIF
//STEP9    EXEC PGM=IEFBR14
//DD8      DD DSN=&ENV..DATA,DISP=SHR
//*
//* SET with expressions
//  SET COUNT=10
//  SET DOUBLED=&COUNT * 2
//STEP10   EXEC PGM=TESTPGM,
//             PARM='COUNT=&COUNT,DOUBLED=&DOUBLED'
//*
//* Very long symbol value
//  SET LONGVAL='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
//STEP11   EXEC PGM=IEFBR14
//DD9      DD DSN=&LONGVAL..DATA,DISP=SHR
//*
//* Symbol substitution in comments (should not occur)
//* This comment contains &SYM1 but it should not be substituted
//*
//STEP12   EXEC PGM=IEFBR14
//*
//* Ampersand without symbol name
//STEP13   EXEC PGM=TESTPGM,
//             PARM='SIGN=&'
//*
//* Double ampersand (temporary dataset)
//STEP14   EXEC PGM=IEFBR14
//DD10     DD DSN=&&TEMP,DISP=(NEW,PASS)
//*
//* Symbol in GDG
//  SET GDGBASE='MY.GDG'
//STEP15   EXEC PGM=IEFBR14
//DD11     DD DSN=&GDGBASE(+1),DISP=(NEW,CATLG)
//*
//* Symbols in SYSOUT
//  SET OUTCLASS='A'
//STEP16   EXEC PGM=TESTPGM
//DD12     DD SYSOUT=&OUTCLASS
//*
//* SET with no value (should default to empty string)
//  SET EMPTY=
//STEP17   EXEC PGM=IEFBR14
//DD13     DD DSN=PREFIX.&EMPTY.SUFFIX,DISP=SHR
