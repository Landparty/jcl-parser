# Core Parser API Contract

**Module**: `jclparser.parser`  
**Purpose**: Main parsing functionality for JCL scripts

## parse_jcl(source: Union[str, Path, IO]) -> Job

**Description**: Parse JCL script from various input sources into structured Job object.

**Parameters**:
- `source`: JCL script content as string, file path, or file-like object
- `options`: Optional parsing configuration (strict mode, dialect settings)

**Returns**: 
- `Job` object representing parsed JCL structure

**Raises**:
- `JCLSyntaxError`: Invalid JCL syntax encountered
- `JCLValidationError`: Valid syntax but semantic errors
- `FileNotFoundError`: When source is path to non-existent file

**Examples**:
```python
# Parse from string
jcl_text = "//MYJOB JOB CLASS=A\n//STEP1 EXEC PGM=IEFBR14"
job = parse_jcl(jcl_text)

# Parse from file
job = parse_jcl(Path("job.jcl"))

# Parse with options
job = parse_jcl(jcl_text, strict_mode=True)
```

---

## validate_jcl(source: Union[str, Path, IO]) -> List[ParseError]

**Description**: Validate JCL syntax and structure without full parsing.

**Parameters**:
- `source`: JCL script to validate
- `level`: Validation level (syntax_only, structure, semantic)

**Returns**: 
- List of `ParseError` objects (empty if valid)

**Examples**:
```python
errors = validate_jcl("//INVALID JOB")
if errors:
    for error in errors:
        print(f"Line {error.line_number}: {error.message}")
```

---

## parse_statement(line: str) -> Optional[Statement]

**Description**: Parse individual JCL statement for syntax analysis.

**Parameters**:
- `line`: Single line of JCL text
- `line_number`: Line number for error context

**Returns**: 
- Parsed statement object or None if comment/empty

**Examples**:
```python
stmt = parse_statement("//DD1 DD DSN=MY.DATA,DISP=SHR")
print(stmt.type)  # "DD"
print(stmt.name)  # "DD1" 
print(stmt.parameters["DSN"])  # "MY.DATA"
```

## Contract Tests Required

### test_parse_jcl_string()
- GIVEN valid JCL string
- WHEN parse_jcl() called
- THEN returns Job with correct name, steps, parameters

### test_parse_jcl_file()
- GIVEN JCL file path
- WHEN parse_jcl() called  
- THEN reads file and parses content correctly

### test_parse_jcl_syntax_error()
- GIVEN invalid JCL syntax
- WHEN parse_jcl() called
- THEN raises JCLSyntaxError with line number

### test_validate_jcl_success()
- GIVEN valid JCL
- WHEN validate_jcl() called
- THEN returns empty error list

### test_validate_jcl_errors()
- GIVEN invalid JCL
- WHEN validate_jcl() called
- THEN returns list of specific errors

### test_parse_statement_job()
- GIVEN JOB statement string
- WHEN parse_statement() called
- THEN returns JobStatement with parsed parameters

### test_parse_statement_dd()
- GIVEN DD statement string
- WHEN parse_statement() called
- THEN returns DDStatement with parsed parameters

### test_parse_statement_comment()
- GIVEN comment line
- WHEN parse_statement() called
- THEN returns None (comments not parsed as statements)