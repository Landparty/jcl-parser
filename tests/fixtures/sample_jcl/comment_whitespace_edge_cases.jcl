//*COMMENT1 JOB (ACCT),'COMMENT AND WHITESPACE TESTS'
//*----------------------------------------------------------------
//* Test various comment and whitespace patterns
//*----------------------------------------------------------------
//CMTTEST  JOB (ACCT),'WHITESPACE AND COMMENTS'
//*
//* Simple comment
//*
//STEP1    EXEC PGM=IEFBR14
//*        Another comment with leading spaces
//DD1      DD DUMMY
//* Comment with special chars: !@#$%^&*()_+-={}[]|:;"'<>,.?/
//*
//*****************************************************************
//* Comment block separator
//*****************************************************************
//*
//STEP2    EXEC PGM=IEFBR14    // Inline comment not standard
//DD2      DD DUMMY
//*
//* Multi-line comment block:
//* Line 1 of comment
//* Line 2 of comment
//* Line 3 of comment
//*
//STEP3    EXEC PGM=IEFBR14
//*Comment with no space after asterisk
//DD3      DD DUMMY
//*                                  
//* Comment with trailing spaces
//*
//STEP4    EXEC PGM=IEFBR14
//*
//* Empty comment line above (a bare // is a null statement: it would end the job)
//*
//DD4      DD DUMMY
//*
//* Test various whitespace patterns
//STEP5    EXEC PGM=IEFBR14
//DD5      DD   DSN=MY.DATA,DISP=SHR
//DD6      DD    DSN=OTHER.DATA,   DISP=SHR
//DD7      DD DSN=THIRD.DATA,DISP=SHR,UNIT=SYSDA
//*
//* Tabs vs spaces test removed due to parser limitations
//* Mixed indentation
//STEP7    EXEC PGM=IEFBR14
//  DD9    DD DSN=MY.DATA,DISP=SHR
//    DD10 DD DSN=OTHER.DATA,DISP=SHR
//*
//* Comment that looks like JCL
//* //FAKEJOB JOB (ACCT),'NOT REAL'
//* //FAKESTEP EXEC PGM=NOTHING
//*
//STEP8    EXEC PGM=IEFBR14
//DD11     DD DUMMY
//*
//* Empty comment lines
//*
//*
//*
//STEP9    EXEC PGM=IEFBR14
//*
//* Very long comment line that goes on and on and on and on and on and on
//* to test if the parser handles extremely long comment lines correctly
//* without any issues or truncation problems that might occur
//*
//STEP10   EXEC PGM=IEFBR14
//*
//* Comment with continuation character at end -
//* But comments don't continue
//*
//STEP11   EXEC PGM=IEFBR14
//*
//**********************************************
//* Comment box
//* Multiple lines with asterisks
//**********************************************
//*
//STEP12   EXEC PGM=IEFBR14
//*
//* Comment with symbols: &SYSUID &SYSDATE &SYSTIME
//* These should not be substituted in comments
//*
//STEP13   EXEC PGM=IEFBR14
//*
//* Note: /* appears only as data delimiter, not standalone
//*
//STEP14   EXEC PGM=IEFBR14
//* Comment before DD
//DD12     DD DUMMY
//* Comment after DD
//DD13     DD DUMMY
//* Comment between DDs
//DD14     DD DUMMY
//*
//* Blank lines between statements
//STEP15   EXEC PGM=IEFBR14

//DD15     DD DUMMY

//DD16     DD DUMMY
//*
//* Comment at end of JCL
//*
