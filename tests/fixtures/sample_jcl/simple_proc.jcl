//*
//* Simple PROC without PROC/PEND keywords
//* Just contains EXEC and DD statements
//* Should be detected as FileType.PROC (no JOB card)
//*
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//STEP2    EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG)
//SYSIN    DD DUMMY
