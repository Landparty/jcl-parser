//INLNDATA JOB (ACCT),'INLINE DATA EDGE CASES'
//*----------------------------------------------------------------
//* Test various inline data scenarios and delimiters
//*----------------------------------------------------------------
//STEP1    EXEC PGM=IEBGENER
//SYSUT1   DD *
This is simple inline data.
Line 2 of data.
Line 3 of data.
/*
//SYSUT2   DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG)
//SYSIN    DD DUMMY
//*
//* Custom delimiter
//STEP2    EXEC PGM=SORT
//SORTIN   DD *
Record 1
Record 2
Record 3
/*
//SORTOUT  DD SYSOUT=*
//SYSIN    DD DATA,DLM=$$
  SORT FIELDS=(1,10,CH,A)
$$
//*
//* Data with JCL-like lines (DD DATA so // records are kept as data)
//STEP3    EXEC PGM=IDCAMS
//SYSIN    DD DATA
//THIS LOOKS LIKE JCL BUT IT'S DATA
//ANOTHER  FAKE JCL LINE
  DELETE MY.OLD.FILE
  SET MAXCC=0
/*
//SYSPRINT DD SYSOUT=*
//*
//* Data with special delimiter
//STEP4    EXEC PGM=TESTPGM
//INPUT    DD DATA,DLM=##
Line 1 of data
/* This is not the end
// Neither is this
More data here
##
//OUTPUT   DD SYSOUT=*
//*
//* Multiple inline data sections
//STEP5    EXEC PGM=TESTPGM
//DATA1    DD *
First dataset content
Line 2
/*
//DATA2    DD *
Second dataset content
More lines
/*
//DATA3    DD *
Third dataset content
/*
//*
//* Inline data with continuation-like characters
//STEP6    EXEC PGM=TESTPGM
//INPUT    DD *
This line has a dash at end -
But it's still data, not continuation
/*
//*
//* Empty inline data
//STEP7    EXEC PGM=TESTPGM
//EMPTY    DD *
/*
//*
//* Inline data with nested delimiters
//STEP8    EXEC PGM=TESTPGM
//INPUT    DD DATA,DLM=@@
This data contains /* which looks like delimiter
But it's not because we're using @@
/*
More data here
@@
//*
//* Long inline data section
//STEP9    EXEC PGM=TESTPGM
//LONGDATA DD *
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC
DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD
EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG
HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH
/*
//*
//* Inline data with special characters
//STEP10   EXEC PGM=TESTPGM
//SPECDATA DD *
!@#$%^&*()_+-={}[]|:;"'<>,.?/~`
Data with 'quotes' and "double quotes"
Data with symbols: $VAR, &SYM, &&TEMP
/*
//*
//* DD DATA without DLM (uses default /*)
//STEP11   EXEC PGM=TESTPGM
//INPUT    DD DATA
  CONTROL CARD 1
  CONTROL CARD 2
  CONTROL CARD 3
/*
//*
//* Inline data in IDCAMS with continuation characters
//STEP12   EXEC PGM=IDCAMS
//SYSIN    DD *
  DEFINE CLUSTER(NAME(MY.CLUSTER) -
         VOLUMES(VOL001 VOL002) -
         RECORDSIZE(80 80) -
         KEYS(8 0) -
         INDEXED) -
         DATA(NAME(MY.CLUSTER.DATA)) -
         INDEX(NAME(MY.CLUSTER.INDEX))
/*
//*
//* Mixed inline data and DD statements
//STEP13   EXEC PGM=TESTPGM
//DD1      DD DSN=MY.DATA,DISP=SHR
//DD2      DD *
Inline data between regular DD statements
/*
//DD3      DD DSN=OTHER.DATA,DISP=SHR
//DD4      DD *
More inline data
/*
//DD5      DD DUMMY
//*
//* Inline data with numbered lines (like COBOL source)
//STEP14   EXEC PGM=TESTPGM
//SOURCE   DD *
000100 IDENTIFICATION DIVISION.
000200 PROGRAM-ID. TESTPROG.
000300 PROCEDURE DIVISION.
000400     DISPLAY 'HELLO WORLD'.
000500     STOP RUN.
/*
//*
//* Very short custom delimiter
//STEP15   EXEC PGM=TESTPGM
//INPUT    DD DATA,DLM=!
Data line 1
Data line 2
!
//*
//* Delimiter that could be confused with JCL
//STEP16   EXEC PGM=TESTPGM
//INPUT    DD DATA,DLM=//*
Data line 1
Data line 2
//*
