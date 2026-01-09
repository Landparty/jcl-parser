//NESTED JOB (5678),'NESTED PROC TEST',CLASS=B
//*
//* A job simulating nested procedure calls.
//* Note: The parser's explosion logic handles the nesting.
//* For this test, we define two inline PROCs where one calls the other.
//*
//INNER    PROC P=DEFAULT
//INSTEP   EXEC PGM=IEFBR14,PARM='&P'
//         PEND
//*
//OUTER    PROC VAL=TEST
//STEP1    EXEC INNER,P=&VAL
//         PEND
//*
//RUNNEST  EXEC OUTER,VAL=FINAL
