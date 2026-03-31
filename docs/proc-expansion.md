# PROC Expansion

## Inline PROC definition and explosion

```python
import jclparser

jcl = """
//TESTJOB  JOB (ACCT),'TEST'
//MYPROC   PROC DSN=DEFAULT.DATA
//STEP1    EXEC PGM=IEFBR14
//DD1      DD  DSN=&DSN,DISP=SHR
//         PEND
//RUN1     EXEC PROC=MYPROC,DSN='PROD.DATA'
//RUN2     EXEC PROC=MYPROC
"""

job = jclparser.parse_jcl(jcl)
print(len(job.steps))        # 2  (RUN1, RUN2 — unexpanded EXEC calls)

exploded = job.explode()
# Each EXEC PROC is replaced by the steps it contains, with symbols resolved

step = exploded.steps[0]     # RUN1.STEP1
dd   = step.get_dd("DD1")
print(dd.dataset_name)       # PROD.DATA  (override applied)
```

## External PROC loading

The parser can load PROCs from the file system using `JCLLIB ORDER`:

```python
jcl = """
//MYJOB  JOB (ACCT),'TEST'
// JCLLIB ORDER=SYS1.PROCLIB
//STEP1  EXEC SORTPROC
"""

job = jclparser.parse_jcl(jcl, proc_base_path="/path/to/proclibs")
```

Directory layout mirrors mainframe dataset naming:

```
/path/to/proclibs/
    SYS1.PROCLIB/
        SORTPROC.jcl
        TESTPROC.jcl
    USER.PROCLIB/
        MYPROC.jcl
```

Multiple libraries are searched in declaration order:

```python
jcl = """
//MYJOB  JOB (ACCT),'TEST'
// JCLLIB ORDER=(SYS1.PROCLIB,USER.PROCLIB)
//STEP1  EXEC MYPROC
"""
job = jclparser.parse_jcl(jcl, proc_base_path="/path/to/proclibs")
```

Set `JCL_PROCLIB_PATH` to avoid specifying `proc_base_path` at every call:

```bash
export JCL_PROCLIB_PATH=/path/to/proclibs
```

## Error cases

```python
from jclparser.errors import CircularProcedureError, ProcedureNotFoundError

# Circular reference — detected at explosion time
try:
    job.explode()
except CircularProcedureError as e:
    print(e)   # Circular procedure reference detected: PROCA. Call chain: PROCA -> PROCB -> PROCA

# Missing PROC — detected at explosion time
try:
    job.explode()
except ProcedureNotFoundError as e:
    print(e)   # Procedure not found: NONEXIST
```

## File-type detection

Use `detect_file_type` to tell JCL jobs apart from standalone PROC files:

```python
from jclparser.jcl_file_type import detect_file_type, FileType

ft = detect_file_type("tests/fixtures/sample_jcl/standalone_proc.jcl")
print(ft)   # FileType.PROC

ft = detect_file_type("examples/DIVIDE.jcl")
print(ft)   # FileType.JCL
```
