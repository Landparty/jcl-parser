# Advanced Features

## Condition parsing

Parse `// IF` expressions into a typed AST:

```python
from jclparser.condition_parser import parse_condition

node = parse_condition("STEP1.RC = 0 AND NOT ABEND")
print(type(node).__name__)   # AndCondition
```

Conditions are also available on parsed jobs:

```python
jcl = """
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
// IF STEP1.RC = 0 THEN
//STEP2    EXEC PGM=CLEANUP
// ENDIF
"""

job = jclparser.parse_jcl(jcl)
# Conditional blocks are preserved in job.steps as ConditionalBlock objects
```

## SQL / DB2 detection

Detect whether a step embeds DB2 SQL:

```python
from jclparser import detect_sql_in_step, detect_sql_in_job

result = detect_sql_in_step(step)
if result.has_sql:
    print(f"SQL found — DB2 program: {result.is_db2_program}")

# Scan all steps at once
results = detect_sql_in_job(job)
for step_name, result in results.items():
    if result.has_sql:
        print(f"{step_name}: SQL detected")
```

## Plugin system

### Custom statement parser

```python
import jclparser
from jclparser.plugins import StatementPlugin

class MyPlugin(StatementPlugin):
    @property
    def statement_types(self):
        return ["MYTYPE"]

    def can_parse(self, line: str) -> bool:
        return "//MYTYPE" in line

    def parse_statement(self, line: str, line_number: int):
        return None  # return your custom Statement subclass here

registry = jclparser.get_plugin_registry()
registry.register_statement_plugin(MyPlugin())
```

### Custom validation rule

```python
from jclparser.plugins import ValidationPlugin
from jclparser.errors import ValidationError

class NoProdTestNames(ValidationPlugin):
    def validate_job(self, job):
        if job.name.startswith("TEST") and "PROD" in str(job.parameters):
            return [ValidationError("TEST jobs must not run in PROD")]
        return []

    def validate_step(self, step): return []
    def validate_dd(self, dd):     return []

registry.register_validation_plugin(NoProdTestNames())
```

## Structured DCB and SPACE parameters

```python
jcl = """
//TESTJOB  JOB (ACCT),'TEST'
//STEP1    EXEC PGM=IEFBR14
//DD1      DD  DSN=MY.DATA,DISP=(NEW,CATLG,DELETE),
//             SPACE=(CYL,(100,10),RLSE),
//             DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920)
"""

job = jclparser.parse_jcl(jcl)
dd  = job.steps[0].get_dd("DD1")

# DCB
print(dd.dcb.recfm)      # FB
print(dd.dcb.lrecl)      # 80
print(dd.dcb.blksize)    # 27920

# SPACE
print(dd.space.unit)     # CYL
print(dd.space.primary)  # 100
print(dd.space.rlse)     # True
```
