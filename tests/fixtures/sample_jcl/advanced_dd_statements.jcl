//DDTEST   JOB (ACCT),'DD STATEMENT TESTS'
//*----------------------------------------------------------------
//* Test various DD statement types and parameters
//*----------------------------------------------------------------
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=MY.DATA.SET,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(10,5,2),RLSE,CONTIG),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000,DSORG=PS),
//             UNIT=(SYSDA,3),
//             VOL=SER=VOL123,
//             LABEL=(1,SL,EXPDT=98000)
//DD2      DD DSN=&&TEMP,
//             DISP=(NEW,PASS),
//             SPACE=(CYL,(5,1),,,ROUND),
//             DCB=(RECFM=VB,LRECL=255,BLKSIZE=27998)
//DD3      DD DSN=MY.GDG(+1),
//             DISP=(NEW,CATLG),
//             SPACE=(CYL,(10,10,10),RLSE),
//             DCB=*.DD1
//DD4      DD DSN=MY.PDS(MEMBER),
//             DISP=SHR
//DD5      DD DSN=CONCAT.ONE,DISP=SHR
//         DD DSN=CONCAT.TWO,DISP=SHR
//         DD DSN=CONCAT.THREE,DISP=SHR,
//            VOL=SER=(VOL001,VOL002,VOL003)
//DD6      DD SYSOUT=*,
//             DEST=LOCAL,
//             OUTLIM=10000,
//             HOLD=YES,
//             FREE=CLOSE
//DD7      DD SYSOUT=(A,INTRDR),
//             COPIES=3,
//             FLASH=(LOGO,2),
//             FORMS=SPECIAL,
//             FCB=STD1
//DD8      DD DUMMY
//DD9      DD DSN=*.STEP1.DD1,
//             DISP=SHR
//DD10     DD DSN=MY.DATA,
//             DISP=MOD,
//             DCB=(RECFM=FB,LRECL=133,BLKSIZE=13300,OPTCD=Q)
//DD11     DD PATH='/u/mydir/myfile.txt',
//             PATHOPTS=(ORDONLY,OCREAT),
//             PATHMODE=SIRWXU,
//             FILEDATA=TEXT
//DD12     DD DSN=NULLFILE,
//             DISP=(OLD,DELETE),
//             SPACE=(TRK,0),
//             DCB=(RECFM=F,LRECL=0,BLKSIZE=0)
//DD13     DD DSN=MY.DATA.SET,
//             AMP=('AMORG','BUFND=10','BUFNI=5','BUFSP=32768'),
//             DISP=SHR
//DD14     DD SUBSYS=(MYJSS,'OPTION1,OPTION2'),
//             DISP=SHR
//DD15     DD DSN=MY.SMS.DATA,
//             DISP=(NEW,CATLG),
//             DATACLAS=DCPROD,
//             MGMTCLAS=MCPROD,
//             STORCLAS=SCPROD,
//             RECORG=KS,
//             KEYOFF=0,
//             KEYLEN=8,
//             SPACE=(CYL,(100,10))
//DD16     DD DSN=MY.VSAM.KSDS,
//             DISP=SHR,
//             AMP='BUFND=20'
