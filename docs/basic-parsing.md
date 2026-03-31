# Basic Parsing

## Parse from a string

```python
import jclparser

jcl = """
//MYJOB    JOB (ACCT),'My Job',CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD  SYSOUT=*
//STEP2    EXEC PGM=SORT
//SORTIN   DD  DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD  DSN=OUTPUT.DATA,DISP=(NEW,CATLG,DELETE)
//SYSIN    DD  *
  SORT FIELDS=(1,10,CH,A)
/*
"""

job = jclparser.parse_jcl(jcl)

print(job.name)                        # MYJOB
print(job.parameters["CLASS"])         # A
print(len(job.steps))                  # 2
```

## Parse from a file

```python
from pathlib import Path

job = jclparser.parse_jcl(Path("my_job.jcl"))
# or
job = jclparser.parse_jcl("my_job.jcl")
```

## Navigate the job structure

```python
for step in job.steps:
    print(f"{step.name}  PGM={step.program}")
    for dd in step.dd_statements:
        print(f"  {dd.name}  DSN={dd.dataset_name}  DISP={dd.disposition}")
```

## Find a specific step or DD

```python
step = job.get_step("STEP2")
dd   = step.get_dd("SORTIN")
print(dd.dataset_name)   # INPUT.DATA
print(dd.disposition)    # SHR
```

## Read inline data

```python
step  = job.get_step("STEP2")
sysin = step.get_dd("SYSIN")

if sysin.has_inline_data:
    print(sysin.inline_data)   # SORT FIELDS=(1,10,CH,A)
```

## JES2/JES3 control statements

```python
jcl = """
//JESJOB   JOB (1234),'TEST',CLASS=A
/*JOBPARM ROOM=123,TIME=60
/*ROUTE   PRINT LOCAL
//STEP1   EXEC PGM=IEFBR14
"""

job = jclparser.parse_jcl(jcl)
for stmt in job.jes_statements:
    print(stmt)
# /*JOBPARM ROOM=123,TIME=60
# /*ROUTE   PRINT LOCAL
```

## Real-world example — `examples/DIVIDE.jcl`

```python
job   = jclparser.parse_jcl("examples/DIVIDE.jcl")
step  = job.get_step("STEP1")          # IEBGENER
sysut2 = step.get_dd("SYSUT2")

print(sysut2.dataset_name)             # OUTPUT.DATA
print(sysut2.disposition)              # ['NEW', 'CATLG', 'DELETE']
print(sysut2.parameters["UNIT"])       # SYSDA
```
