//SPECIAL  JOB (ACCT),'SPECIAL CHARACTERS AND ENCODING'
//*----------------------------------------------------------------
//* Test special characters, encoding, and boundary cases
//*----------------------------------------------------------------
//STEP1    EXEC PGM=IEFBR14
//* Test national characters (if supported)
//DD1      DD DSN='MY.DATA.ÄÖÜ',DISP=SHR
//*
//* Dataset names with all valid special characters
//DD2      DD DSN='MY.$DATA.#SET.@FILE',DISP=SHR
//*
//* Ampersands in various contexts
//DD3      DD DSN='DATA.&VAR',DISP=SHR
//DD4      DD DSN='DATA.&&TEMP',DISP=SHR
//*
//* Maximum length names (8 chars for steps/DDs in standard JCL)
//MAXNAME8 EXEC PGM=IEFBR14
//MAXDDNAM DD DUMMY
//*
//* Single character names
//A        EXEC PGM=IEFBR14
//B        DD DUMMY
//*
//* Numbers in names (valid positions)
//STEP2    EXEC PGM=IEFBR14
//DD1      DD DUMMY
//DD2A3B4C DD DUMMY
//*
//* All numeric name (if valid)
//STEP3    EXEC PGM=IEFBR14
//DD12345  DD DUMMY
//*
//* Underscores and hyphens in dataset names
//DD5      DD DSN='MY_DATA-SET',DISP=SHR
//*
//* Very long dataset name (44 chars is max)
//DD6      DD DSN='A.VERY.LONG.DATASET.NAME.WITH.MANY.QUALIFIERS',
//             DISP=SHR
//*
//* Empty parameters
//DD7      DD DSN=,DISP=SHR
//*
//* Null statement (just //) left out: it would end the job here
//*
//STEP4    EXEC PGM=IEFBR14
//*
//* Multiple spaces between elements
//STEP5    EXEC    PGM=IEFBR14
//DD8      DD      DSN=MY.DATA,    DISP=SHR
//*
//* No space after comma
//DD9      DD DSN=MY.DATA,DISP=SHR,UNIT=SYSDA
//*
//* Space before comma
//DD10     DD DSN=MY.DATA ,DISP=SHR ,UNIT=SYSDA
//*
//* Trailing comma (may be invalid)
//DD11     DD DSN=MY.DATA,DISP=SHR,
//*
//* Parameters with no value
//DD12     DD DSN=MY.DATA,DISP
//*
//* Zero values
//DD13     DD DSN=MY.DATA,
//             DISP=SHR,
//             SPACE=(TRK,(0,0))
//*
//* Very large numbers
//STEP6    EXEC PGM=TESTPGM,
//             REGION=2147483647
//DD14     DD DSN=MY.DATA,
//             SPACE=(TRK,(999999,999999))
//*
//* Negative numbers (may be invalid in some contexts)
//STEP7    EXEC PGM=TESTPGM,
//             PARM='-100'
//*
//* Decimal numbers
//DD15     DD DSN=MY.DATA,
//             SPACE=(TRK,(10.5,5.5))
//*
//* Scientific notation (may not be supported)
//STEP8    EXEC PGM=TESTPGM,
//             PARM='1E6'
//*
//* Binary/hex values (if supported)
//STEP9    EXEC PGM=TESTPGM,
//             PARM=X'FF'
//*
//* Unicode or extended characters in comments
//* Test: ©®™€£¥§¶†‡•…‰′″‹›♠♣♥♦
//*
//STEP10   EXEC PGM=IEFBR14
//*
//* Case sensitivity tests - parser expects uppercase keywords
//STEP11   EXEC PGM=IEFBR14
//dd16     DD DUMMY
//*
//* Mixed case in dataset names
//DD17     DD DSN='My.Mixed.Case.Data',DISP=SHR
//*
//* Reserved words as names (if allowed)
//DATA     EXEC PGM=IEFBR14
//SET      DD DUMMY
//IF       DD DUMMY
//*
//* Special JCL characters in strings
//STEP12   EXEC PGM=TESTPGM,
//             PARM='/,=()''&*'
//*
//* Blank parameter values
//DD18     DD DSN=MY.DATA,
//             DISP=(' ',' ')
