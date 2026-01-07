from jclparser import parse_jcl

content = """//TESTPROC PROC DSN=DEFAULT.DATA
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&DSN,DISP=SHR
//         PEND
//"""

try:
    job = parse_jcl(content, strict_mode=False)
    print(f"Procedures: {len(job.procedures)}")
    print(f"Steps: {len(job.steps)}")
    for p in job.procedures:
        print(f"Proc name: {p.name}, steps: {len(p.steps)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
