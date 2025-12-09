//CONTEDGE JOB (ACCT),'CONTINUATION EDGE CASES',
//             CLASS=A,MSGCLASS=X,
//             NOTIFY=&SYSUID
//*----------------------------------------------------------------
//* Test complex continuation line patterns
//*----------------------------------------------------------------
//STEP1    EXEC PGM=TESTPGM,
//             PARM='OPTION1,OPTION2,OPTION3,OPTION4,OPTION5,OPTION6,-
//             OPTION7,OPTION8,OPTION9,OPTION10,OPTION11,OPTION12,-
//             OPTION13,OPTION14,OPTION15,OPTION16,OPTION17'
//*
//* Test continuation with non-continuation character
//STEP2    EXEC PGM=TESTPGM,
//             PARM='THIS STRING HAS A DASH-IN-THE-MIDDLE BUT CONTINUES
//             ON THE NEXT LINE'
//*
//* Test multiple continuations
//STEP3    EXEC PGM=LONGPARM,
//             PARM='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA-
//             BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB-
//             CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC-
//             DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD-
//             EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE'
//*
//* Test continuation in middle of parameter
//DD1      DD DSN=MY.VERY.LONG.DATASET.NAME.THAT.NEEDS.TO.BE.SPLIT.A-
//             CROSS.MULTIPLE.LINES.FOR.READABILITY,
//             DISP=SHR
//*
//* Test continuation with special characters
//DD2      DD DSN='MY.DATA.SET(MEMBER)',
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(TRK,(100,50,20),RLSE),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=8000,
//             OPTCD=(Q,C,B),
//             BUFNO=20,
//             NCP=5)
//*
//* Test continuation with commas
//DD3      DD DSN=MY.DATA,
//             DISP=SHR,
//             VOL=SER=(VOL001,VOL002,VOL003,VOL004,VOL005,
//             VOL006,VOL007,VOL008,VOL009,VOL010,
//             VOL011,VOL012,VOL013,VOL014,VOL015)
//*
//* Test continuation with nested parentheses
//STEP4    EXEC PGM=COMPLEX,
//             PARM=((OUTER1,(INNER1,INNER2,(DEEP1,DEEP2)),OUTER2),
//             (OUTER3,OUTER4,(INNER3,(DEEP3,DEEP4),INNER4)))
//*
//* Test continuation with quotes across lines
//STEP5    EXEC PGM=TESTPGM,
//             PARM='THIS IS A STRING THAT STARTS ON ONE LINE AND-
//             CONTINUES ON THE NEXT LINE WITHOUT BREAKING THE QUOTE'
