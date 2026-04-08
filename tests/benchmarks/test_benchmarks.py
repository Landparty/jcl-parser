"""
Benchmark tests for the JCL parser library.

Run with: pytest tests/benchmarks/ --benchmark-only
"""

import pytest
from jclparser import parse_jcl, validate_jcl
from jclparser.explosion import explode_job, substitute_symbols, SymbolScope
from jclparser.parameter_ast import ParameterParser

# ---------------------------------------------------------------------------
# Fixture JCL strings
# ---------------------------------------------------------------------------

_SMALL_JCL = """\
//SMALLJOB JOB CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//SYSOUT   DD   SYSOUT=*
"""

_MEDIUM_JCL = """\
//MEDJOB   JOB (ACCT),'MEDIUM JOB',CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//STEP1    EXEC PGM=SORT
//SORTIN   DD   DSN=MY.INPUT.FILE,DISP=SHR
//SORTOUT  DD   DSN=MY.OUTPUT.FILE,DISP=(NEW,CATLG,DELETE),
//              SPACE=(CYL,(10,5),RLSE),
//              DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920)
//SYSIN    DD   *
  SORT FIELDS=(1,10,CH,A)
/*
//SYSOUT   DD   SYSOUT=*
//STEP2    EXEC PGM=IEBGENER
//SYSUT1   DD   DSN=MY.OUTPUT.FILE,DISP=SHR
//SYSUT2   DD   SYSOUT=*
//SYSIN    DD   DUMMY
//SYSPRINT DD   SYSOUT=*
"""

_LARGE_JCL = """\
//LARGEJOB JOB (ACCT001),'LARGE JOB',CLASS=A,MSGCLASS=X,
//              NOTIFY=&SYSUID,REGION=0M
//SET1     SET  INDSN=MY.INPUT,OUTDSN=MY.OUTPUT,WRKDSN=MY.WORK
""" + "".join(
    f"""\
//STEP{i:02d}    EXEC PGM=IEFBR14,PARM='STEP{i:02d}'
//INPUT{i:02d}  DD   DSN=&INDSN..STEP{i:02d},DISP=SHR
//OUTPUT{i:02d} DD   DSN=&OUTDSN..STEP{i:02d},DISP=(NEW,CATLG,DELETE),
//              SPACE=(TRK,(100,50)),DCB=(RECFM=FB,LRECL=80)
//WORK{i:02d}   DD   DSN=&&TEMP{i:02d},DISP=(NEW,PASS,DELETE),
//              SPACE=(CYL,(5,2),RLSE)
//SYSOUT{i:02d} DD   SYSOUT=*
"""
    for i in range(1, 21)
)

_PROC_JCL = """\
//PROCJOB  JOB CLASS=A,MSGCLASS=X
//MYPROC   PROC INFILE=DEFAULT.INPUT,OUTFILE=DEFAULT.OUTPUT
//PSTEP1   EXEC PGM=IEFBR14
//PINPUT   DD   DSN=&INFILE,DISP=SHR
//POUTPUT  DD   DSN=&OUTFILE,DISP=(NEW,CATLG,DELETE),SPACE=(TRK,(10,5))
//PEND
//STEP1    EXEC MYPROC,INFILE=REAL.INPUT,OUTFILE=REAL.OUTPUT
//STEP2    EXEC MYPROC,INFILE=ANOTHER.INPUT
"""

_COMPLEX_PARAM = "RECFM=FB,LRECL=80,BLKSIZE=27920,BUFNO=10,DSORG=PS,OPTCD=W"

_SYMBOL_HEAVY = (
    "DSN=&HLQ..&SYSDATE..&SYSUID..DATA.FILE,DISP=SHR,"
    "DCB=(RECFM=&RECFM,LRECL=&LRECL,BLKSIZE=&BLKSIZE),"
    "UNIT=&UNIT,VOL=SER=&VOLSER"
)


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_parse_jcl_small(benchmark):
    """Benchmark parse_jcl() on a small JCL string."""
    benchmark(parse_jcl, _SMALL_JCL)


@pytest.mark.benchmark
def test_parse_jcl_medium(benchmark):
    """Benchmark parse_jcl() on a medium JCL string."""
    benchmark(parse_jcl, _MEDIUM_JCL)


@pytest.mark.benchmark
def test_parse_jcl_large(benchmark):
    """Benchmark parse_jcl() on a large JCL string (20 steps)."""
    benchmark(parse_jcl, _LARGE_JCL)


@pytest.mark.benchmark
def test_validate_jcl(benchmark):
    """Benchmark validate_jcl() on a typical job."""
    benchmark(validate_jcl, _MEDIUM_JCL)


@pytest.mark.benchmark
def test_explode_job(benchmark):
    """Benchmark explode_job() on a PROC-heavy job."""
    job = parse_jcl(_PROC_JCL)
    benchmark(explode_job, job)


@pytest.mark.benchmark
def test_parameter_parser_parse(benchmark):
    """Benchmark ParameterParser on a complex parameter string."""
    parser = ParameterParser()
    benchmark(parser._split_parameters, _COMPLEX_PARAM)


@pytest.mark.benchmark
def test_substitute_symbols(benchmark):
    """Benchmark substitute_symbols() on symbol-heavy text."""
    scope = SymbolScope(
        set_symbols={
            "HLQ": "MY.HLQ",
            "RECFM": "FB",
            "LRECL": "80",
            "BLKSIZE": "27920",
            "UNIT": "SYSDA",
            "VOLSER": "VOL001",
        }
    )
    benchmark(substitute_symbols, _SYMBOL_HEAVY, scope, False, True)


# ---------------------------------------------------------------------------
# Algorithmic-fix benchmark fixtures
# ---------------------------------------------------------------------------

_LARGE_DD_JCL = "//DDJOB    JOB CLASS=A\n" + "".join(
    f"//STEP{i:02d}   EXEC PGM=IEFBR14\n//DD{i:02d}     DD   *\nDATA LINE {i}\n/*\n"
    for i in range(1, 51)
)

_HEAVY_CONTINUATION_JCL = "//CONTJOB  JOB CLASS=A\n" + "".join(
    f"//STEP{i:02d}   EXEC PGM=IEFBR14\n"
    f"//DD{i:02d}     DD   DSN=MY.DATASET.{i:02d},\n"
    f"//             DISP=(NEW,CATLG,DELETE),\n"
    f"//             SPACE=(CYL,(10,5),RLSE),\n"
    f"//             DCB=(RECFM=FB,\n"
    f"//             LRECL=80,\n"
    f"//             BLKSIZE=27920,\n"
    f"//             BUFNO=10,\n"
    f"//             DSORG=PS),\n"
    f"//             UNIT=SYSDA\n"
    for i in range(1, 51)
)

_COMPLEX_PARAMS_JCL = "//PARAMJOB  JOB CLASS=A\n" + "".join(
    f"//STEP{i:03d}  EXEC PGM=IEFBR14\n"
    f"//DD{i:03d}    DD   DSN=MY.DS.{i:03d},\n"
    f"//             DISP=(NEW,CATLG,DELETE),\n"
    f"//             SPACE=(CYL,(10,5),RLSE),\n"
    f"//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920),\n"
    f"//             UNIT=SYSDA,LABEL=(1,SL),RETPD=30\n"
    for i in range(1, 101)
)


@pytest.mark.benchmark
def test_parse_large_dd_job(benchmark):
    """Benchmark: 50 DD * inline data blocks (targets inline data scan)."""
    benchmark(parse_jcl, _LARGE_DD_JCL)


@pytest.mark.benchmark
def test_parse_heavy_continuation_job(benchmark):
    """Benchmark: 50 steps x 9 continuation lines each (targets context re-analysis)."""
    benchmark(parse_jcl, _HEAVY_CONTINUATION_JCL)


@pytest.mark.benchmark
def test_parse_complex_params_job(benchmark):
    """Benchmark: 100 steps x 7 keyword parameters each (targets join overhead)."""
    benchmark(parse_jcl, _COMPLEX_PARAMS_JCL)
