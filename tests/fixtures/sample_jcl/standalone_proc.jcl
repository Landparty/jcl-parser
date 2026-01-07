//*
//* Sample standalone PROC file (no JOB card)
//* This file should be detected as FileType.PROC
//*
//SORTPROC PROC DSN=DEFAULT.DATA,MEMBER=DEFMEM
//SORT1    EXEC PGM=SORT,REGION=4M
//SORTIN   DD DSN=&DSN,DISP=SHR
//SORTOUT  DD DSN=&DSN..SORTED,DISP=(NEW,CATLG,DELETE),
//            UNIT=SYSDA,SPACE=(CYL,(10,5),RLSE)
//SYSOUT   DD SYSOUT=*
//SYSIN    DD *
  SORT FIELDS=(1,10,CH,A)
/*
//         PEND
