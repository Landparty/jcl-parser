from jclparser.parser import parse_jcl
from jclparser.errors import JCLSyntaxError, JCLValidationError
import sys

print("Running repro script...")

jcl = "//TESTJOB\tJOB\tCLASS=A\n//STEP1\tEXEC\tPGM=PROG\n//"
print(f"JCL content:\n{jcl}")

try:
    print("Calling parse_jcl...")
    job = parse_jcl(jcl, strict_mode=False)
    print(f"Result job: {job}")
    
    if job is None:
        print("ERROR: job is None!")
    else:
        print(f"Job name: {job.name}")

except Exception as e:
    print(f"Caught exception: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("Done.")
