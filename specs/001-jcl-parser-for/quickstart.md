# Quickstart: JCL Parser Testing & Validation

**Purpose**: Test scenarios to validate JCL Parser implementation against acceptance criteria  
**Status**: Ready for implementation  
**Prerequisites**: JCL Parser library installed and importable

## Test Scenario 1: Basic JCL Parsing

**Validates**: FR-001, FR-003, FR-007 (core parsing, object model, job metadata)

### Setup
```python
import jclparser

# Sample JCL script
jcl_content = """
//MYJOB    JOB (12345),'DEVELOPER',CLASS=A,MSGCLASS=X
//STEP1    EXEC PGM=IEFBR14
//SYSPRINT DD   SYSOUT=*
//SYSIN    DD   *
This is inline data
for the SYSIN DD
/*
//STEP2    EXEC PGM=SORT
//SORTIN   DD   DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD   DSN=OUTPUT.DATA,DISP=(NEW,CATLG)
//SYSOUT   DD   SYSOUT=*
"""
```

### Expected Behavior
```python
# Parse the JCL
job = jclparser.parse_jcl(jcl_content)

# Validate job structure
assert job.name == "MYJOB"
assert job.accounting_info == "12345"
assert job.parameters["CLASS"] == "A"
assert job.parameters["MSGCLASS"] == "X"

# Validate steps
assert len(job.steps) == 2
assert job.steps[0].name == "STEP1"
assert job.steps[0].program == "IEFBR14"
assert job.steps[1].name == "STEP2"
assert job.steps[1].program == "SORT"

# Validate DD statements
step1_dds = job.steps[0].dd_statements
assert len(step1_dds) == 2
assert step1_dds[0].name == "SYSPRINT"
assert step1_dds[1].name == "SYSIN"
assert step1_dds[1].has_inline_data == True
assert "This is inline data" in step1_dds[1].inline_data

step2_dds = job.steps[1].dd_statements
assert len(step2_dds) == 3
assert step2_dds[0].dataset_name == "INPUT.DATA"
assert step2_dds[1].dataset_name == "OUTPUT.DATA"
```

---

## Test Scenario 2: Error Handling & Validation

**Validates**: FR-004, FR-009 (syntax validation, error reporting)

### Setup
```python
# Invalid JCL with syntax errors
invalid_jcl = """
//BADJOB   JOB CLASS=A
//STEP1    EXEC PGM=TEST
//DD1      DD   DSN=UNCLOSED.QUOTE'
//         DD   DSN=MISSING.NAME
//STEP2    EXEC 
"""
```

### Expected Behavior
```python
# Validation should catch errors
errors = jclparser.validate_jcl(invalid_jcl)

# Should find multiple errors
assert len(errors) > 0

# Check specific error types
syntax_errors = [e for e in errors if e.error_type == ErrorType.SYNTAX_ERROR]
assert len(syntax_errors) >= 2  # Unclosed quote, missing DD name

# Parsing should raise exception
try:
    job = jclparser.parse_jcl(invalid_jcl)
    assert False, "Should have raised JCLSyntaxError"
except jclparser.JCLSyntaxError as e:
    assert e.line_number > 0
    assert "quote" in e.message.lower() or "name" in e.message.lower()
```

---

## Test Scenario 3: Complex JCL Features

**Validates**: FR-002, FR-005, FR-008 (comments, parameters, step relationships)

### Setup
```python
# Complex JCL with various features
complex_jcl = """
//* This is a job comment
//COMPLEX  JOB (ACCT,1234),'USER NAME',
//             CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//*
//PROC1    EXEC MYPROC,PARM='OPTION1,OPTION2'
//SYSIN    DD   DSN=&&TEMP,UNIT=SYSDA,
//             SPACE=(TRK,(5,2)),DISP=(NEW,PASS)
//*
//STEP2    EXEC PGM=MYPROG,
//             PARM='DEBUG=YES,TRACE=ON'
//INPUT    DD   DSN=&&TEMP,DISP=(OLD,DELETE)
//OUTPUT   DD   DSN=FINAL.OUTPUT,
//             DISP=(NEW,CATLG,DELETE),
//             UNIT=DISK,SPACE=(CYL,(10,5,5)),
//             DCB=(LRECL=80,BLKSIZE=800,RECFM=FB)
"""
```

### Expected Behavior
```python
job = jclparser.parse_jcl(complex_jcl)

# Validate job-level continuation and parameters
assert job.name == "COMPLEX"
assert "NOTIFY" in job.parameters
assert job.parameters["NOTIFY"] == "&SYSUID"

# Validate procedure call
proc_step = job.get_step("PROC1")
assert proc_step.is_procedure == True
assert "PARM" in proc_step.parameters
assert "OPTION1" in proc_step.parameters["PARM"]

# Validate temporary datasets
sysin_dd = proc_step.get_dd("SYSIN")
assert sysin_dd.is_temporary() == True
assert sysin_dd.dataset_name == "&&TEMP"

# Validate parameter parsing complexity
input_dd = job.steps[1].get_dd("INPUT")
assert input_dd.dataset_name == "&&TEMP"
assert input_dd.disposition == "(OLD,DELETE)"

output_dd = job.steps[1].get_dd("OUTPUT")
assert "LRECL" in output_dd.parameters["DCB"]
assert output_dd.parameters["DCB"]["LRECL"] == "80"
```

---

## Test Scenario 4: Plugin Extensibility

**Validates**: FR-010 (extensible architecture)

### Setup
```python
# Custom statement plugin for hypothetical MYSTAT statement
class MyStatementPlugin(jclparser.StatementPlugin):
    def can_parse(self, line: str) -> bool:
        return line.strip().startswith("//") and "MYSTAT" in line
    
    def parse_statement(self, line: str, line_number: int):
        # Custom parsing logic
        return CustomStatement(line, line_number)
    
    @property
    def statement_types(self) -> List[str]:
        return ["MYSTAT"]

# Register plugin
registry = jclparser.get_plugin_registry()
registry.register_statement_plugin(MyStatementPlugin())
```

### Expected Behavior
```python
# JCL with custom statement
custom_jcl = """
//TESTJOB  JOB CLASS=A
//MYSTAT   CUSTOM PARAM1=VALUE1,PARAM2=VALUE2
//STEP1    EXEC PGM=TEST
"""

# Parser should handle custom statement
job = jclparser.parse_jcl(custom_jcl)
# Custom statement handling depends on plugin implementation

# Verify plugin registration
plugins = registry.get_statement_plugins()
assert any(isinstance(p, MyStatementPlugin) for p in plugins)
```

---

## Performance Validation

**Validates**: FR-012 (batch processing performance)

### Setup
```python
import time
from pathlib import Path

# Generate large JCL file for testing
def generate_large_jcl(num_steps: int) -> str:
    jcl_parts = ["//BIGJOB JOB CLASS=A"]
    
    for i in range(num_steps):
        jcl_parts.extend([
            f"//STEP{i:04d} EXEC PGM=TEST{i % 10}",
            f"//INPUT{i:04d} DD DSN=INPUT.DATA{i},DISP=SHR", 
            f"//OUTPUT{i:04d} DD DSN=OUTPUT.DATA{i},DISP=(NEW,CATLG)"
        ])
    
    return "\n".join(jcl_parts)
```

### Expected Behavior
```python
# Test with 1000 steps (3000+ lines)
large_jcl = generate_large_jcl(1000)

start_time = time.time()
job = jclparser.parse_jcl(large_jcl)
parse_time = time.time() - start_time

# Performance expectations
assert parse_time < 5.0  # Should parse 3000+ lines in under 5 seconds
assert len(job.steps) == 1000
assert len(job.get_dd_statements()) == 2000  # 2 DDs per step

print(f"Parsed {len(large_jcl.splitlines())} lines in {parse_time:.3f} seconds")
```

---

## Integration Test Checklist

**Before considering implementation complete, verify:**

- [ ] All quickstart scenarios pass without modification
- [ ] Error messages are clear and include line numbers
- [ ] Memory usage remains reasonable for large JCL files
- [ ] Plugin system works with custom implementations
- [ ] Parser handles real-world JCL variations (comments, continuations, nested quotes)
- [ ] Object model provides intuitive access to all parsed data
- [ ] Validation catches common JCL syntax errors
- [ ] Performance meets batch processing requirements

**Success Criteria**: All test scenarios execute successfully and demonstrate the functional requirements from the specification are met.

---

**Next Step**: Run `/tasks` to generate implementation tasks based on these acceptance tests.