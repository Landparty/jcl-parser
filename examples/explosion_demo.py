"""
Example: JCL Procedure Explosion

Demonstrates the dynamic PROC explosion mechanism that automatically expands
procedure invocations with symbolic parameter substitution.
"""

from jclparser import parse_jcl

# Example JCL with procedure and symbolic parameters
jcl_content = """
//DEMOJOB  JOB (ACCT123),'EXPLOSION DEMO',CLASS=A,MSGCLASS=X
//         SET USERID=TESTUSER
//         SET ENVIRON=PROD
//*
//* Define a procedure with parameters
//*
//BACKUP   PROC DSN=DEFAULT.DATA,TYPE=FULL
//STEP1    EXEC PGM=IEBGENER
//SYSUT1   DD DSN=&DSN,DISP=SHR
//SYSUT2   DD DSN=&USERID..BACKUP.&TYPE,DISP=(NEW,CATLG),
//            SPACE=(TRK,(100,10)),UNIT=SYSDA
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//STEP2    EXEC PGM=IEFBR14
//LOG      DD DSN=&USERID..BACKUP.LOG,DISP=(MOD,KEEP)
//         PEND
//*
//* Call the procedure with overrides
//*
//BACKUP1  EXEC BACKUP,DSN=PROD.DATA.FILE1,TYPE=INCR
//BACKUP2  EXEC BACKUP,DSN=PROD.DATA.FILE2
//BACKUP3  EXEC BACKUP,DSN=TEST.DATA.FILE3,TYPE=DELTA
//"""

print("=" * 80)
print("JCL PROCEDURE EXPLOSION DEMO")
print("=" * 80)
print()

# Parse the JCL
print("1. Parsing JCL...")
job = parse_jcl(jcl_content)
print(f"   ✓ Parsed job: {job.name}")
print(f"   ✓ Found {len(job.procedures)} inline procedure(s)")
print(f"   ✓ Found {len(job.steps)} step(s) (before explosion)")
print(f"   ✓ SET statements: {job.set_statements}")
print()

# Explode procedures
print("2. Exploding procedures...")
exploded_job = job.explode(audit=True)
print(f"   ✓ Explosion complete!")
print(f"   ✓ Expanded to {len(exploded_job.steps)} step(s)")
print()

# Show expanded steps
print("3. Expanded Steps:")
print()
for i, step in enumerate(exploded_job.steps, 1):
    print(f"   Step {i}: {step.name}")
    print(f"      Program: {step.program}")
    print(f"      Exploded: {step.is_exploded}")
    if step.original_proc_call:
        print(f"      Original PROC call: {step.original_proc_call}")
    
    if step.dd_statements:
        print(f"      DD Statements:")
        for dd in step.dd_statements:
            if dd.dataset_name:
                print(f"         {dd.name}: DSN={dd.dataset_name}")
    print()

# Show audit trail
print("4. Explosion Audit Trail:")
print()
for record in exploded_job.explosion_audit:
    print(f"   Explosion Record:")
    print(f"      Step: {record.step_name}")
    print(f"      Procedure: {record.proc_name}")
    print(f"      Parameters: {record.parameters}")
    print(f"      Depth: {record.depth}")
    print(f"      Timestamp: {record.timestamp}")
    print(f"      Expanded to: {', '.join(record.expanded_steps)}")
    print()

# Show cross-reference map
print("5. Cross-Reference Map:")
print()
for step_name, expansion_info in exploded_job.explosion_map.items():
    print(f"   {step_name}:")
    print(f"      Original: {expansion_info.original_statement}")
    print(f"      Procedure: {expansion_info.proc_definition}")
    print(f"      Resolved Parameters: {expansion_info.resolved_parameters}")
    print(f"      Generated Steps: {', '.join(expansion_info.expanded_step_names)}")
    print()

# Demonstrate symbolic parameter substitution
print("6. Symbolic Parameter Substitution Examples:")
print()
print("   Original PROC parameter: DSN=&DSN")
print("   After explosion:")
for step in exploded_job.steps:
    if step.dd_statements and step.dd_statements[0].name == "SYSUT1":
        print(f"      {step.name} → {step.dd_statements[0].dataset_name}")
print()

print("   Original parameter with SET and PROC: DSN=&USERID..BACKUP.&TYPE")
print("   After explosion:")
for step in exploded_job.steps:
    if step.dd_statements:
        for dd in step.dd_statements:
            if dd.name == "SYSUT2":
                print(f"      {step.name} → {dd.dataset_name}")
print()

# Demonstrate error handling
print("7. Error Handling Examples:")
print()

# Example: Undefined symbol (non-strict mode)
try:
    jcl_with_undefined = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//STEP1    EXEC PGM=IEFBR14
//DD1      DD DSN=&UNDEFINED,DISP=SHR
//"""
    job2 = parse_jcl(jcl_with_undefined)
    exploded2 = job2.explode(strict_symbols=False)
    print("   ✓ Non-strict mode: Undefined symbols become empty strings")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Example: Circular reference detection
try:
    jcl_circular = """
//TESTJOB  JOB (ACCT),'TEST',CLASS=A
//PROC1    PROC
//STEP1    EXEC PROC1
//         PEND
//CALL     EXEC PROC1
//"""
    job3 = parse_jcl(jcl_circular)
    exploded3 = job3.explode()
    print("   ✗ Should have detected circular reference!")
except Exception as e:
    print(f"   ✓ Circular reference detected: {type(e).__name__}")

print()
print("=" * 80)
print("For more information, see the documentation in the README.")
print("=" * 80)
