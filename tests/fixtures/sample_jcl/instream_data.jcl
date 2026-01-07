//DATATEST JOB (ACCT),'INSTREAM DATA TEST'
//STEP1    EXEC PGM=IEBGENER
//SYSIN    DD *
This is inline data
Line 2 of data
Line 3 of data
/*
//SYSPRINT DD SYSOUT=*
//STEP2    EXEC PGM=SORT
//SORTIN   DD DATA,DLM=@@
Sorted data line 1
Sorted data line 2
@@
//SORTOUT  DD SYSOUT=*
