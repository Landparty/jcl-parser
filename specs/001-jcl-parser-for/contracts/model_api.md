# Job Model API Contract

**Module**: `jclparser.model`  
**Purpose**: Data model classes for representing parsed JCL structures

## Job Class Interface

**Description**: Represents a complete JCL job with all execution steps.

### Properties
```python
@property
def name(self) -> str:
    """Job name from JOB statement"""

@property  
def parameters(self) -> Dict[str, Any]:
    """Job-level parameters (CLASS, MSGCLASS, etc.)"""

@property
def steps(self) -> List[Step]:
    """Execution steps in order"""

@property
def accounting_info(self) -> Optional[str]:
    """Accounting information from JOB statement"""
```

### Methods
```python
def get_step(self, name: str) -> Optional[Step]:
    """Find step by name"""

def get_dd_statements(self) -> List[DDStatement]:
    """Get all DD statements from all steps"""

def validate(self) -> List[ValidationError]:
    """Validate job structure and dependencies"""
```

---

## Step Class Interface

**Description**: Represents an execution step within a job.

### Properties
```python
@property
def name(self) -> Optional[str]:
    """Step name (may be auto-generated)"""

@property
def program(self) -> str:
    """Program name from EXEC statement"""

@property
def dd_statements(self) -> List[DDStatement]:
    """Data definitions for this step"""

@property
def is_procedure(self) -> bool:
    """True if step executes a procedure"""
```

### Methods
```python
def get_dd(self, name: str) -> Optional[DDStatement]:
    """Find DD statement by name"""

def get_input_datasets(self) -> List[str]:
    """Get all input dataset names"""

def get_output_datasets(self) -> List[str]:
    """Get all output dataset names"""
```

---

## DDStatement Class Interface

**Description**: Represents a data definition statement.

### Properties
```python
@property
def name(self) -> str:
    """DD name"""

@property
def dataset_name(self) -> Optional[str]:
    """DSN parameter value if present"""

@property
def disposition(self) -> Optional[str]:
    """DISP parameter value"""

@property
def has_inline_data(self) -> bool:
    """True for DD * statements"""

@property
def inline_data(self) -> Optional[str]:
    """In-stream data content"""
```

### Methods
```python
def is_input(self) -> bool:
    """True if DD defines input data"""

def is_output(self) -> bool:
    """True if DD defines output data"""

def is_temporary(self) -> bool:
    """True if dataset is temporary (&&name)"""
```

## Contract Tests Required

### test_job_creation()
- GIVEN job name and parameters
- WHEN Job() constructed
- THEN properties accessible and correct

### test_job_add_step()
- GIVEN Job instance and Step
- WHEN step added to job
- THEN step appears in job.steps list

### test_job_get_step()
- GIVEN Job with named steps
- WHEN get_step() called with valid name
- THEN returns correct Step object

### test_job_get_step_not_found()
- GIVEN Job with steps
- WHEN get_step() called with invalid name  
- THEN returns None

### test_step_creation()
- GIVEN step name and program
- WHEN Step() constructed
- THEN properties accessible and correct

### test_step_add_dd()
- GIVEN Step instance and DDStatement
- WHEN DD added to step
- THEN DD appears in step.dd_statements

### test_dd_statement_dataset()
- GIVEN DD with DSN parameter
- WHEN DDStatement created
- THEN dataset_name property returns DSN value

### test_dd_statement_inline_data()
- GIVEN DD * with inline data
- WHEN DDStatement created with inline content
- THEN has_inline_data is True and data accessible

### test_dd_disposition_parsing()
- GIVEN DD with DISP parameter
- WHEN DDStatement created
- THEN disposition property parsed correctly

### test_job_validation()
- GIVEN Job with invalid structure
- WHEN validate() called
- THEN returns list of validation errors