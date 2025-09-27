#!/usr/bin/env python3
"""
Basic JCL Parser Usage Examples

This script demonstrates the most common ways to use the jclparser module
for parsing and analyzing IBM JCL (Job Control Language) scripts.
"""

import sys
from pathlib import Path

# Add parent directory to Python path to import jclparser
sys.path.insert(0, str(Path(__file__).parent.parent))

import jclparser


def basic_parsing_example():
    """Demonstrate basic JCL parsing from string"""
    print("=== Basic JCL Parsing Example ===")
    
    # Sample JCL job (simplified - no continuation lines for now)
    jcl_content = """//EXAMPLE  JOB (12345),'JOHN DOE',CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD   SYSOUT=*
//DD1      DD   DSN=MY.INPUT.DATA,DISP=SHR
//DD2      DD   DSN=MY.OUTPUT.DATA,DISP=(NEW,CATLG)
//STEP2    EXEC PGM=SORT
//SORTIN   DD   DSN=MY.INPUT.DATA,DISP=SHR
//SORTOUT  DD   DSN=MY.SORTED.DATA,DISP=(NEW,CATLG)
//SYSOUT   DD   SYSOUT=*
//SYSIN    DD   *
  SORT FIELDS=(1,10,CH,A)
/*"""
    
    # Parse the JCL
    print("Parsing JCL content...")
    job = jclparser.parse_jcl(jcl_content)
    
    # Display job information
    print(f"Job Name: {job.name}")
    print(f"Job Parameters: {job.parameters}")
    print(f"Accounting Info: {job.accounting_info}")
    print(f"Number of Steps: {len(job.steps)}")
    
    # Display step information
    for i, step in enumerate(job.steps, 1):
        print(f"\nStep {i}: {step.name}")
        print(f"  Program: {step.program}")
        print(f"  Parameters: {step.parameters}")
        print(f"  DD Statements: {len(step.dd_statements)}")
        
        # Display DD information
        for dd in step.dd_statements:
            print(f"    DD {dd.name}: {dd.dataset_name or 'SYSOUT/INLINE'}")
            if dd.has_inline_data:
                print(f"      Inline Data: {len(dd.inline_data)} characters")
    
    print()


def validation_example():
    """Demonstrate JCL validation"""
    print("=== JCL Validation Example ===")
    
    # Valid JCL
    valid_jcl = "//GOOD JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14\n//DD1 DD DUMMY"
    
    # Invalid JCL  
    invalid_jcl = """
//BAD      JOB CLASS=
//STEP1    EXEC
//         DD   DSN=UNCLOSED.QUOTE'
"""
    
    # Validate good JCL
    print("Validating good JCL...")
    errors = jclparser.validate_jcl(valid_jcl)
    if not errors:
        print("✓ JCL is valid!")
    else:
        print("✗ Unexpected errors found")
    
    # Validate bad JCL
    print("\nValidating bad JCL...")
    errors = jclparser.validate_jcl(invalid_jcl)
    if errors:
        print(f"✗ Found {len(errors)} validation errors:")
        for error in errors:
            print(f"  Line {error.line_number}: {error.message}")
    else:
        print("✓ No errors found (unexpected)")
    
    print()


def error_handling_example():
    """Demonstrate error handling"""
    print("=== Error Handling Example ===")
    
    # JCL with syntax errors
    bad_jcl = "//BADJOB JOB CLASS=A\n//STEP1 EXEC\n//DD1 DD"
    
    try:
        job = jclparser.parse_jcl(bad_jcl)
        print(f"Parsed job: {job.name}")
    except jclparser.JCLSyntaxError as e:
        print(f"✓ Caught syntax error at line {e.line_number}: {e.message}")
    except jclparser.JCLValidationError as e:
        print(f"✓ Caught validation error: {e.message}")
    except Exception as e:
        print(f"✗ Unexpected error: {type(e).__name__}: {e}")
    
    # File not found error
    try:
        job = jclparser.parse_jcl("nonexistent_file.jcl")
    except FileNotFoundError as e:
        print(f"✓ Caught file not found error: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {type(e).__name__}: {e}")
    
    print()


def data_analysis_example():
    """Demonstrate JCL data flow analysis"""
    print("=== Data Flow Analysis Example ===")
    
    # JCL with data dependencies (simplified)
    jcl_with_flow = """//DATAFLOW JOB CLASS=A
//STEP1    EXEC PGM=IEBGENER
//SYSUT1   DD   DSN=SOURCE.DATA,DISP=SHR
//SYSUT2   DD   DSN=&&TEMP1,DISP=(NEW,PASS)
//SYSPRINT DD   SYSOUT=*
//SYSIN    DD   DUMMY
//STEP2    EXEC PGM=SORT
//SORTIN   DD   DSN=&&TEMP1,DISP=(OLD,DELETE)
//SORTOUT  DD   DSN=&&SORTED,DISP=(NEW,PASS)
//SYSOUT   DD   SYSOUT=*
//SYSIN    DD   *
  SORT FIELDS=(1,20,CH,A)
/*
//STEP3    EXEC PGM=IEBGENER  
//SYSUT1   DD   DSN=&&SORTED,DISP=(OLD,DELETE)
//SYSUT2   DD   DSN=FINAL.OUTPUT,DISP=(NEW,CATLG)
//SYSPRINT DD   SYSOUT=*
//SYSIN    DD   DUMMY"""
    
    print("Analyzing data flow...")
    job = jclparser.parse_jcl(jcl_with_flow)
    
    # Track temporary datasets
    temp_datasets = set()
    
    print("\nStep-by-step data flow:")
    for step in job.steps:
        inputs = step.get_input_datasets()
        outputs = step.get_output_datasets()
        
        print(f"\n{step.name} ({step.program}):")
        print(f"  Reads from: {inputs or 'None'}")
        print(f"  Writes to:  {outputs or 'None'}")
        
        # Track temporary datasets
        for ds in outputs:
            if ds.startswith('&&'):
                temp_datasets.add(ds)
    
    print(f"\nTemporary datasets created: {sorted(temp_datasets)}")
    
    # Find all DD statements and categorize
    all_dds = job.get_dd_statements()
    input_dds = [dd for dd in all_dds if dd.is_input()]
    output_dds = [dd for dd in all_dds if dd.is_output()]
    sysout_dds = [dd for dd in all_dds if 'SYSOUT' in dd.parameters]
    
    print(f"\nDataset summary:")
    print(f"  Total DD statements: {len(all_dds)}")
    print(f"  Input datasets: {len(input_dds)}")  
    print(f"  Output datasets: {len(output_dds)}")
    print(f"  SYSOUT statements: {len(sysout_dds)}")
    
    print()


def file_parsing_example():
    """Demonstrate parsing JCL from file"""
    print("=== File Parsing Example ===")
    
    # Create a sample JCL file
    sample_jcl = """//FILEJOB  JOB CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//DD1      DD   DUMMY
"""
    
    # Write to temporary file
    temp_file = Path("sample_job.jcl")
    try:
        with open(temp_file, "w") as f:
            f.write(sample_jcl)
        
        print(f"Created temporary file: {temp_file}")
        
        # Parse from file path (string)
        job1 = jclparser.parse_jcl(str(temp_file))
        print(f"Parsed from string path: {job1.name}")
        
        # Parse from Path object  
        job2 = jclparser.parse_jcl(temp_file)
        print(f"Parsed from Path object: {job2.name}")
        
        # Parse from file object
        with open(temp_file, "r") as f:
            job3 = jclparser.parse_jcl(f)
            print(f"Parsed from file object: {job3.name}")
        
    finally:
        # Clean up
        if temp_file.exists():
            temp_file.unlink()
            print(f"Cleaned up: {temp_file}")
    
    print()


def statement_parsing_example():
    """Demonstrate individual statement parsing"""
    print("=== Individual Statement Parsing Example ===")
    
    # Sample JCL statements
    statements = [
        "//MYJOB JOB (ACCOUNT),'USER NAME',CLASS=A",
        "//STEP1 EXEC PGM=IEFBR14,PARM='DEBUG=YES'", 
        "//SYSPRINT DD SYSOUT=*",
        "//INPUT DD DSN=MY.DATA,DISP=SHR,UNIT=SYSDA",
        "//* This is a comment",
        "",  # Empty line
        "//INVALID LINE WITHOUT PROPER FORMAT"
    ]
    
    print("Parsing individual statements:")
    for i, line in enumerate(statements, 1):
        print(f"\nLine {i}: {repr(line)}")
        try:
            stmt = jclparser.parse_statement(line, i)
            if stmt:
                print(f"  Type: {stmt.type}")
                print(f"  Name: {stmt.name}")  
                print(f"  Parameters: {stmt.parameters}")
            else:
                print("  Skipped (comment or empty)")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")
    
    print()


def plugin_example():
    """Demonstrate basic plugin usage"""
    print("=== Plugin System Example ===")
    
    # Get the global plugin registry
    registry = jclparser.get_plugin_registry()
    
    print(f"Current statement plugins: {len(registry.get_statement_plugins())}")
    print(f"Current validation plugins: {len(registry.get_validators())}")
    
    # Example of plugin configuration
    config = jclparser.ParserConfig(
        strict_mode=False,
        dialect="standard", 
        validation_level=jclparser.ValidationLevel.BASIC
    )
    
    print(f"Parser config: strict_mode={config.strict_mode}, dialect={config.dialect}")
    
    # Enable/disable plugins
    config.enable_plugin("CustomPlugin")
    print(f"Enabled plugins: {config.enabled_plugins}")
    
    config.disable_plugin("CustomPlugin")
    print(f"After disabling: {config.enabled_plugins}")
    
    print()


def main():
    """Run all examples"""
    print("JCL Parser - Usage Examples")
    print("=" * 40)
    print()
    
    try:
        basic_parsing_example()
        validation_example() 
        error_handling_example()
        data_analysis_example()
        file_parsing_example()
        statement_parsing_example()
        plugin_example()
        
        print("✓ All examples completed successfully!")
        
    except Exception as e:
        print(f"✗ Example failed with error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()