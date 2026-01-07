//PARAMEDG JOB (ACCT),'PARAMETER EDGE CASES'
//*----------------------------------------------------------------
//* Test complex parameter parsing scenarios
//*----------------------------------------------------------------
//STEP1    EXEC PGM=TESTPGM,
//             PARM='SIMPLE STRING'
//*
//* Nested quotes and apostrophes
//STEP2    EXEC PGM=TESTPGM,
//             PARM='STRING WITH ''DOUBLED QUOTES'' INSIDE'
//*
//STEP3    EXEC PGM=TESTPGM,
//             PARM='CAN''T STOP WON''T STOP'
//*
//* Complex list parameters
//DD1      DD DSN=MY.DATA,
//             DISP=SHR,
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000,OPTCD=(Q,C))
//*
//* Nested lists
//DD2      DD DSN=MY.DATA,
//             DISP=SHR,
//             AMP=('AMORG',('BUFND=10','BUFNI=5'),'BUFSP=32768')
//*
//* Empty parameters
//DD3      DD DSN=MY.DATA,
//             DISP=(,CATLG),
//             SPACE=(TRK,(10,))
//*
//* Keywords with special characters
//DD4      DD DSN=MY.DATA,
//             DISP=SHR,
//             DCB=(RECFM=F-B,LRECL=80)
//*
//* Mixed positional and keyword parameters
//STEP4    EXEC PGM=TESTPGM,
//             PARM=(POS1,POS2,KEY1=VAL1,POS3,KEY2=VAL2)
//*
//* Numeric parameters
//DD5      DD DSN=MY.DATA,
//             DISP=SHR,
//             SPACE=(CYL,(100,50,25),,,ROUND),
//             LABEL=(2,SL,EXPDT=99365,RETPD=0030)
//*
//* Parameters with equals in values
//STEP5    EXEC PGM=TESTPGM,
//             PARM='OPTION=VALUE,OTHER=X=Y,THIRD=A=B=C'
//*
//* Complex DCB with all subparameters
//DD6      DD DSN=MY.DATA,
//             DISP=SHR,
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000,BUFNO=20,
//             EROPT=ABE,FUNC=I,MODE=C,OPTCD=(C,Q),
//             NCP=5,PRTSP=3,STACK=2,TRTCH=C)
//*
//* Special characters in dataset names
//DD7      DD DSN='MY.$PECIAL.DATA$ET.#NAME',
//             DISP=SHR
//*
//DD8      DD DSN='SYS1.MACRO#LIB',
//             DISP=SHR
//*
//* Referback with qualifiers
//DD9      DD DSN=*.STEP1.DD1,
//             DISP=SHR
//*
//DD10     DD DSN=*.*.DD2,
//             DISP=SHR
//*
//* GDG with relative generation
//DD11     DD DSN=MY.GDG.DATA(+1),
//             DISP=(NEW,CATLG)
//*
//DD12     DD DSN=MY.GDG.DATA(-1),
//             DISP=SHR
//*
//DD13     DD DSN=MY.GDG.DATA(0),
//             DISP=OLD
//*
//* Unix paths
//DD14     DD PATH='/u/user/data/file.txt',
//             PATHOPTS=(ORDWR,OCREAT,OTRUNC),
//             PATHMODE=SIRUSR
//*
//* Very long parameter values
//DD15     DD DSN=MY.DATA,
//             DISP=SHR,
//             DCB=(RECFM=VBS,LRECL=32760,BLKSIZE=32764)
//*
//* Parameters with spaces in quoted strings
//STEP6    EXEC PGM=TESTPGM,
//             PARM='OPTION WITH SPACES, ANOTHER OPTION, THIRD OPTION'
//*
//* Commas in quoted strings
//STEP7    EXEC PGM=TESTPGM,
//             PARM='VALUE1,VALUE2,VALUE3'
//*
//* Boolean-like parameters
//DD16     DD DSN=MY.DATA,
//             DISP=SHR,
//             FREE=CLOSE,
//             HOLD=YES,
//             PROTECT=YES
//*
//* COND parameter variations
//STEP8    EXEC PGM=TESTPGM,
//             COND=(4,LT)
//*
//STEP9    EXEC PGM=TESTPGM,
//             COND=((0,NE),(4,LT,STEP1),(8,LE,STEP2))
//*
//STEP10   EXEC PGM=TESTPGM,
//             COND=EVEN
//*
//STEP11   EXEC PGM=TESTPGM,
//             COND=ONLY
//*
//* SYSOUT variations
//DD17     DD SYSOUT=*
//DD18     DD SYSOUT=A
//DD19     DD SYSOUT=(A,INTRDR)
//DD20     DD SYSOUT=(,INTRDR)
