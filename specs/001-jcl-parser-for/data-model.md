# Data Model: JCL Parser Entities

**Feature**: JCL Parser for Python 3.13  
**Date**: 2025-09-27  
**Based on**: Feature specification requirements and research decisions

## Entity Overview

The JCL Parser data model represents parsed JCL scripts as a hierarchical tree of Python objects, following the natural structure of JCL: Jobs contain Steps, Steps contain DD statements.

## Core Entities

### Job
Represents a complete JCL job definition.

**Fields**:
- `name: str` - Job name from JOB statement
- `parameters: Dict[str, Any]` - Job parameters (accounting, class, etc.)
- `steps: List[Step]` - Execution steps in order
- `comments: List[str]` - Job-level comments
- `line_number: int` - Source line number for error reporting

**Validation Rules**:
- Name must be valid JCL identifier (1-8 characters, alphanumeric + @, #, $)
- Must contain at least one execution step
- Parameters must include required accounting information

**Relationships**:
- One-to-many with Step entities
- Root entity in the object hierarchy

### Step
Represents a single execution step within a job.

**Fields**:
- `name: str` - Step name (optional, generated if not provided)
- `program: str` - Program name from EXEC statement
- `parameters: Dict[str, Any]` - EXEC parameters (PARM, COND, etc.)
- `dd_statements: List[DDStatement]` - Data definitions for this step
- `procedure_name: Optional[str]` - Procedure name if EXEC references procedure
- `comments: List[str]` - Step-level comments
- `line_number: int` - Source line number

**Validation Rules**:
- Program or procedure name is required
- Step name must be unique within job (if provided)
- DD statement names must be unique within step

**Relationships**:
- Many-to-one with Job
- One-to-many with DDStatement

### DDStatement
Represents a data definition (DD) statement.

**Fields**:
- `name: str` - DD name (e.g., "SYSOUT", "INPUT")
- `parameters: Dict[str, Any]` - DD parameters (DSN, DISP, UNIT, etc.)
- `in_stream_data: Optional[str]` - In-stream data content (for DD *)
- `comments: List[str]` - DD-level comments
- `line_number: int` - Source line number

**Validation Rules**:
- Name must be valid JCL identifier
- Either dataset name (DSN) or special assignment (* for in-stream, DUMMY, etc.)
- DISP parameter validation for dataset handling

**Relationships**:
- Many-to-one with Step
- Contains inline data for DD * statements

### Parameter
Represents parsed parameter values with type awareness.

**Fields**:
- `name: str` - Parameter name
- `value: Union[str, List[str], Dict[str, str]]` - Parameter value (supports strings, lists, keyword=value)
- `quoted: bool` - Whether original value was quoted
- `line_number: int` - Source line for error reporting

**Validation Rules**:
- Name follows JCL parameter naming conventions
- Value parsing handles quoted strings, parameter lists, positional arguments
- Nested quotes and escaped characters preserved

### ParseError
Represents syntax or validation errors with detailed context.

**Fields**:
- `error_type: ErrorType` - Type of error (syntax, validation, structure)
- `message: str` - Human-readable error description
- `line_number: int` - Source line where error occurred
- `column_number: Optional[int]` - Character position if available
- `context: str` - Surrounding text context
- `severity: ErrorSeverity` - Error, Warning, or Info

**Error Types**:
- `SYNTAX_ERROR`: Invalid JCL syntax
- `VALIDATION_ERROR`: Valid syntax but invalid semantics
- `STRUCTURE_ERROR`: Missing required statements or invalid organization

## Entity Relationships

```
Job (1) ────┬──── Step (*)
            │
            └──── Parameter (*)
            │
            └──── Comment (*)

Step (1) ───┬──── DDStatement (*)
            │
            └──── Parameter (*)
            │
            └──── Comment (*)

DDStatement (1) ──┬── Parameter (*)
                  │
                  └── Comment (*)
```

## State Transitions

### Job Parsing States
1. **INITIAL** → JOB statement parsed → **JOB_DEFINED**
2. **JOB_DEFINED** → First EXEC found → **STEPS_PARSING**
3. **STEPS_PARSING** → End of input → **COMPLETE**
4. Any state → Parse error → **ERROR**

### Validation Sequencing
1. Syntax validation during parsing
2. Structure validation after complete parsing
3. Semantic validation (cross-references, dependencies)
4. Custom validation via plugin system

## Implementation Notes

### Immutability
- Entities are immutable after creation (using dataclasses with frozen=True)
- Changes require creating new instances
- Supports functional programming patterns and thread safety

### Type Safety
- All entities use type hints for IDE support
- Runtime type checking for critical paths
- Optional mypy compatibility for static analysis

### Extensibility Points
- Plugin hooks for custom entity types
- Validator registration for new parameter types
- Custom error types via inheritance

### Performance Considerations
- Lazy loading of in-stream data for memory efficiency
- Iterator patterns for large job collections
- Optional detailed parsing vs. quick structure extraction

---

**Status**: ✅ Complete - Ready for contract generation