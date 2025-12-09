//REALTEST JOB (ACCT),'REALISTIC PRODUCTION JCL'
//*----------------------------------------------------------------
//* Realistic production-like JCL with multiple complex scenarios
//*----------------------------------------------------------------
//         JCLLIB ORDER=(PROD.PROCLIB,SYS1.PROCLIB)
//  SET ENV='PROD'
//  SET DATE=&SYSDATE
//  SET USER=&SYSUID
//  SET BACKUP='BACKUP.&DATE..DATA'
//*
//*----------------------------------------------------------------
//* Step 1: Backup existing data
//*----------------------------------------------------------------
//BACKUP   EXEC PGM=IEBGENER,REGION=4096K,
//             COND=(0,NE)
//SYSUT1   DD DSN=PROD.MASTER.FILE,
//             DISP=SHR,
//             DCB=*.SYSUT2
//SYSUT2   DD DSN=&BACKUP,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(CYL,(100,50),RLSE),
//             UNIT=SYSDA,
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//*----------------------------------------------------------------
//* Step 2: Sort and merge multiple input files
//*----------------------------------------------------------------
//SORTMERG EXEC PGM=SORT,REGION=8M,
//             COND=(4,LT,BACKUP),
//             TIME=(0,30)
//SORTIN01 DD DSN=INPUT.FILE.ONE,DISP=SHR
//         DD DSN=INPUT.FILE.TWO,DISP=SHR
//         DD DSN=INPUT.FILE.THREE,DISP=SHR
//SORTOUT  DD DSN=&&SORTED,
//             DISP=(NEW,PASS),
//             SPACE=(CYL,(50,25)),
//             DCB=(RECFM=FB,LRECL=200,BLKSIZE=27800)
//SORTWORK DD UNIT=SYSDA,SPACE=(CYL,(10,10))
//SYSIN    DD *
  SORT FIELDS=(1,20,CH,A,21,10,CH,D),
       FORMAT=CH
  SUM FIELDS=NONE
  OUTREC FIELDS=(1,200)
/*
//SYSOUT   DD SYSOUT=*
//*
//*----------------------------------------------------------------
//* Step 3: IDCAMS - Define VSAM cluster and load data
//*----------------------------------------------------------------
//IDCAMS   EXEC PGM=IDCAMS,REGION=4096K,
//             COND=((4,LT,BACKUP),(4,LT,SORTMERG))
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  DELETE PROD.VSAM.CLUSTER PURGE CLUSTER
  SET MAXCC=0
  DEFINE CLUSTER(NAME(PROD.VSAM.CLUSTER) -
         VOLUMES(PRODV1 PRODV2) -
         RECORDSIZE(200 200) -
         KEYS(20 0) -
         INDEXED -
         FREESPACE(10 10) -
         SHAREOPTIONS(2 3) -
         SPEED -
         REUSE) -
         DATA(NAME(PROD.VSAM.CLUSTER.DATA) -
              CYLINDERS(500 100)) -
         INDEX(NAME(PROD.VSAM.CLUSTER.INDEX) -
               CYLINDERS(50 10))
  REPRO INFILE(INPUT) -
        OUTFILE(OUTPUT) -
        REUSE
/*
//INPUT    DD DSN=&&SORTED,DISP=(OLD,DELETE)
//OUTPUT   DD DSN=PROD.VSAM.CLUSTER,DISP=OLD
//*
//*----------------------------------------------------------------
//* Step 4: Run custom COBOL program
//*----------------------------------------------------------------
//COBOLPGM EXEC PGM=CUSTPROG,REGION=0M,
//             COND=((4,LT,BACKUP),(4,LT,SORTMERG),(4,LT,IDCAMS)),
//             PARM='MODE=PROD,DEBUG=NO,TRACE=ERROR'
//STEPLIB  DD DSN=PROD.LOADLIB,DISP=SHR
//         DD DSN=SYS1.COBLIB,DISP=SHR
//VSAMFILE DD DSN=PROD.VSAM.CLUSTER,DISP=SHR
//REFFILE  DD DSN=PROD.REFERENCE.DATA,DISP=SHR
//OUTFILE  DD DSN=PROD.OUTPUT.&DATE,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(CYL,(200,100,50),RLSE),
//             DCB=(RECFM=FB,LRECL=133,BLKSIZE=27930),
//             UNIT=(SYSDA,3),
//             VOL=SER=PRODV3
//ERRFILE  DD DSN=PROD.ERRORS.&DATE,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(CYL,(10,5),RLSE),
//             DCB=(RECFM=VB,LRECL=255,BLKSIZE=27998)
//SYSOUT   DD SYSOUT=*
//SYSPRINT DD SYSOUT=*
//SYSABEND DD SYSOUT=*
//SYSUDUMP DD SYSOUT=*
//*
//*----------------------------------------------------------------
//* Step 5: Generate report
//*----------------------------------------------------------------
//REPORT   EXEC PGM=RPTGEN,REGION=4096K,
//             COND=((4,LT,COBOLPGM),EVEN)
//INPUT    DD DSN=PROD.OUTPUT.&DATE,DISP=SHR
//OUTPUT   DD SYSOUT=(A,INTRDR),
//             DEST=CENTRAL,
//             COPIES=3,
//             OUTLIM=50000,
//             FORMS=STANDARD,
//             FCB=STD1
//CONTROL  DD *
TITLE 'PRODUCTION PROCESSING REPORT'
DATE &DATE
USER &USER
ENVIRONMENT &ENV
PAGE SIZE 60
FONT COURIER 10
/*
//SYSPRINT DD SYSOUT=*
//*
//*----------------------------------------------------------------
//* Step 6: Send notification
//*----------------------------------------------------------------
//NOTIFY   EXEC PGM=IEBGENER,
//             COND=(4,GT,COBOLPGM)
//SYSUT1   DD *
Processing completed successfully for &DATE
User: &USER
Environment: &ENV
Output file: PROD.OUTPUT.&DATE
/*
//SYSUT2   DD SYSOUT=(A,INTRDR)
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//*
//*----------------------------------------------------------------
//* Step 7: Cleanup temporary files
//*----------------------------------------------------------------
//CLEANUP  EXEC PGM=IDCAMS,
//             COND=EVEN
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  DELETE TEMP.WORK.FILES
  SET MAXCC=0
/*
