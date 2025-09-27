#!/usr/bin/env python3
"""
Quick Start - JCL Parser

The fastest way to get started with the jclparser module.
"""

import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import jclparser


def main():
    """Quick demonstration of JCL parsing"""
    
    # Sample JCL
    jcl = """//QUICKJOB JOB CLASS=A
//STEP1    EXEC PGM=IEFBR14
//DD1      DD   DSN=MY.DATA,DISP=SHR
//DD2      DD   SYSOUT=*
"""
    
    print("Quick JCL Parser Demo")
    print("=" * 30)
    print()
    print("JCL Content:")
    print(jcl)
    
    # Parse it
    print("Parsing...")
    job = jclparser.parse_jcl(jcl)
    
    # Show results
    print(f"✓ Job: {job.name}")
    print(f"✓ Steps: {len(job.steps)}")
    print(f"✓ DD Statements: {len(job.get_dd_statements())}")
    
    # Show job structure
    print("\nJob Structure:")
    for step in job.steps:
        print(f"  {step.name} -> {step.program}")
        for dd in step.dd_statements:
            if dd.dataset_name:
                print(f"    {dd.name}: {dd.dataset_name}")
            else:
                print(f"    {dd.name}: SYSOUT")
    
    print("\n✓ Done! See examples/basic_parsing.py for more details.")


if __name__ == "__main__":
    main()