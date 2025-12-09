//BADJOB   JOB (ACCT),'MISSING DELIMITER TEST'
//STEP1    EXEC PGM=TESTPGM
//DD1      DD *
This is inline data
But there's no delimiter to end it
//STEP2    EXEC PGM=IEFBR14
