//EDGECASE JOB (9999),'EDGE CASES',CLASS=Z
//*
//* Testing parsing edge cases
//*
//STEP1    EXEC PGM=IEFBR14
//*
//* 1. Tricky continuation with comments
//DD1      DD DSN=MY.LONG.DATASET.NAME,
//            DISP=SHR
//*
//* 2. Concatenated DDs (empty DD names)
//DD2      DD DSN=DATA.SET.ONE,DISP=SHR
//         DD DSN=DATA.SET.TWO,DISP=SHR
//         DD DSN=DATA.SET.THREE,DISP=SHR
//*
//* 3. DD * with delimiter (Inline Data)
//DD3      DD *,DLM=$$
Data line 1
Data line 2 with // in it
$$
//*
//* 4. Parameter values with special characters
//STEP2    EXEC PGM=UTILITY,PARM='A/B*C+D=E'
//DD4      DD DSN=QUOTED.NAME.TEST,DISP=(OLD,KEEP)
