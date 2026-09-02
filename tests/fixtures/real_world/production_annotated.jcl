//*MAIN CLASS=BATCH,LINES=(100,W)                                       PAY00001
//PRDPAY01 JOB (55001,DEPT),'MONTHLY PAYROLL',CLASS=A,MSGCLASS=X,      XPAY00002
//             MSGLEVEL=(1,1),NOTIFY=&SYSUID,REGION=0M                  PAY00003
//*                                                                     PAY00004
//*        MONTHLY PAYROLL EXTRACT AND REPORT                           PAY00005
//*                                                                     PAY00006
//        JCLLIB ORDER=(PROD.PROCLIB,SYS1.PROCLIB)    LIBRARIES         PAY00007
//        SET HLQ=PROD.PAYROLL             HIGH LEVEL QUALIFIER         PAY00008
//        SET CYCLE=M01                    PROCESSING CYCLE             PAY00009
//*                                                                     PAY00010
//STEP010  EXEC PGM=SORT,REGION=4M          SORT THE EXTRACT            PAY00011
//SORTIN   DD DSN=&HLQ..EXTRACT.&CYCLE,DISP=SHR                         PAY00012
//SORTOUT  DD DSN=&HLQ..SORTED.&CYCLE,                                 XPAY00013
//            DISP=(NEW,CATLG,DELETE),                 NEW FILE         PAY00014
//            UNIT=SYSDA,SPACE=(CYL,(50,10),RLSE),                      PAY00015
//            DCB=(RECFM=FB,LRECL=200,BLKSIZE=27800)                    PAY00016
//SYSOUT   DD SYSOUT=*                                                  PAY00017
//SYSIN    DD *                                                         PAY00018
  SORT FIELDS=(1,9,CH,A)                                                PAY00019
  INCLUDE COND=(10,2,CH,EQ,C'01')                                       PAY00020
/*                                                                      PAY00021
//*                                                                     PAY00022
//STEP020  EXEC PGM=IEBGENER                PRINT THE REPORT            PAY00023
//SYSPRINT DD SYSOUT=*                                                  PAY00024
//SYSUT1   DD DSN=&HLQ..SORTED.&CYCLE,DISP=SHR                          PAY00025
//SYSUT2   DD SYSOUT=A,OUTPUT=*.RPTOUT                                  PAY00026
//OUTPUT   DD SYSOUT=*                      DDNAME IS OUTPUT            PAY00027
//SYSIN    DD DUMMY                                                     PAY00028
//RPTOUT   OUTPUT DEST=RMT10,COPIES=2,FORMS=STD                         PAY00029
//*                                                                     PAY00030
// IF (STEP020.RC = 0) THEN                                             PAY00031
//STEP030  EXEC PAYPROC,CYCLE=&CYCLE        CATALOGED PROC              PAY00032
//PS1.AUDIT DD DSN=&HLQ..AUDIT.&CYCLE,DISP=MOD                          PAY00033
// ELSE                                                                 PAY00034
//STEP040  EXEC PGM=IEFBR14                 NOTHING TO DO               PAY00035
// ENDIF                                                                PAY00036
//*                                                                     PAY00037
//STEP050  EXEC PGM=IEFBR14                                             PAY00038
//CTL1     CNTL                                                         PAY00039
//         PRINTDEV BUFNO=20                                            PAY00040
//         ENDCNTL                                                      PAY00041
//DELETE   DD DSN=&HLQ..OLD.&CYCLE,DISP=(OLD,DELETE,DELETE)             PAY00042
//                                                                      PAY00043
