//*----------------------------------------------------------------
//* SYNTAX ERRORS - Invalid JCL for testing error handling
//*----------------------------------------------------------------
//* Note: This file contains intentional syntax errors for testing
//* the parser's error detection and reporting capabilities
//*----------------------------------------------------------------
//*
//* Missing JOB statement
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DUMMY
