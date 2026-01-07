//IFTEST   JOB (ACCT),'CONDITIONAL IF/THEN/ELSE TESTS'
//*----------------------------------------------------------------
//* Test various IF/THEN/ELSE/ENDIF conditional constructs
//*----------------------------------------------------------------
//  SET VAR1=10
//  SET VAR2=20
//  SET ENV='TEST'
//*
//* Simple IF condition
//  IF &VAR1 = 10 THEN
//    SET RESULT='TRUE'
//  ENDIF
//*
//* IF with ELSE
//  IF &VAR1 > &VAR2 THEN
//    SET BIGGER='VAR1'
//  ELSE
//    SET BIGGER='VAR2'
//  ENDIF
//*
//* Nested IF statements
//  IF &ENV = 'TEST' THEN
//    IF &VAR1 < 100 THEN
//      SET LEVEL='LOW'
//    ELSE
//      SET LEVEL='HIGH'
//    ENDIF
//  ELSE
//    SET LEVEL='PROD'
//  ENDIF
//*
//* IF with string comparison
//  IF &SYSUID = 'TESTUSER' THEN
//    SET ACCESS='GRANTED'
//  ELSE
//    SET ACCESS='DENIED'
//  ENDIF
//*
//* Complex boolean expressions
//  IF (&VAR1 > 5) AND (&VAR2 < 30) THEN
//    SET RANGE='VALID'
//  ENDIF
//*
//  IF (&ENV = 'TEST') OR (&ENV = 'DEV') THEN
//    SET DEBUG='YES'
//  ELSE
//    SET DEBUG='NO'
//  ENDIF
//*
//* IF with NOT
//  IF NOT &VAR1 = 0 THEN
//    SET NONZERO='TRUE'
//  ENDIF
//*
//* Multiple ELSE IF (if supported)
//  IF &VAR1 < 10 THEN
//    SET CATEGORY='SMALL'
//  ELSE
//    IF &VAR1 < 50 THEN
//      SET CATEGORY='MEDIUM'
//    ELSE
//      SET CATEGORY='LARGE'
//    ENDIF
//  ENDIF
//*
//STEP1    EXEC PGM=TESTPGM,
//             PARM='RESULT=&RESULT,LEVEL=&LEVEL'
//DD1      DD DUMMY
//*
//* Conditional EXEC
//  IF &ENV = 'PROD' THEN
//STEP2    EXEC PGM=PRODPGM
//  ELSE
//STEP2    EXEC PGM=TESTPGM
//  ENDIF
//DD2      DD DUMMY
//*
//* Conditional DD
//STEP3    EXEC PGM=IEFBR14
//  IF &ENV = 'TEST' THEN
//DD3      DD DSN=TEST.DATA,DISP=SHR
//  ELSE
//DD3      DD DSN=PROD.DATA,DISP=SHR
//  ENDIF
//*
//* IF with expressions
//  SET TOTAL=&VAR1 + &VAR2
//  IF &TOTAL > 25 THEN
//    SET STATUS='OVER'
//  ELSE
//    SET STATUS='UNDER'
//  ENDIF
//STEP4    EXEC PGM=TESTPGM,
//             PARM='STATUS=&STATUS'
//*
//* IF with system symbols
//  IF &SYSDATE > '2025/01/01' THEN
//    SET YEAR='CURRENT'
//  ELSE
//    SET YEAR='OLD'
//  ENDIF
//*
//* Complex nested conditions
//  IF &ENV = 'PROD' THEN
//    IF &VAR1 > 50 THEN
//      IF &VAR2 < 10 THEN
//        SET COMPLEXITY='HIGH'
//      ELSE
//        SET COMPLEXITY='MEDIUM'
//      ENDIF
//    ELSE
//      SET COMPLEXITY='LOW'
//    ENDIF
//  ELSE
//    SET COMPLEXITY='TEST'
//  ENDIF
//STEP5    EXEC PGM=TESTPGM,
//             PARM='COMPLEXITY=&COMPLEXITY'
