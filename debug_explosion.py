from jclparser import parse_jcl
from jclparser.parser import parse_statement

jcl = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//MYPROC   PROC
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=TEST.DATA,DISP=SHR
//         PEND
//CALL     EXEC MYPROC
//"""

print("Lines in JCL:")
for i, line in enumerate(jcl.strip().split('\n'), 1):
    print(f"  {i}: {repr(line)}")

print("\nParsing each line:")
for i, line in enumerate(jcl.strip().split('\n'), 1):
    if line.strip() and not line.strip().startswith("//*"):
        try:
            stmt = parse_statement(line, i)
            print(f"  Line {i} ({stmt.type:6}): name={stmt.name:10} params={stmt.parameters}")
        except Exception as e:
            print(f"  Line {i}: ERROR - {e}")

job = parse_jcl(jcl, strict_mode=False)
print(f"\nJob steps: {len(job.steps)}")
print(f"Job procedures: {len(job.procedures)}")

if job.procedures:
    proc = job.procedures[0]
    print(f"  Procedure '{proc.name}' has {len(proc.steps)} steps")
    for s in proc.steps:
        print(f"    Step: {s.name}, prog: {s.program}, proc: {s.procedure}")

for s in job.steps:
    print(f"  Job Step: {s.name}, prog: {s.program}, proc: {s.procedure}")
