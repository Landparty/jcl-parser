# JCL Parser Test Fixtures

This directory contains comprehensive JCL test fixtures designed to cover all edge cases and ensure robust parsing capabilities.

## Fixture Categories

### Basic Examples (Original)
- **basic_job.jcl** - Simple JCL job structure
- **complex_params.jcl** - Complex parameter examples
- **continuation_lines.jcl** - Basic continuation line handling
- **instream_data.jcl** - Inline data sections
- **procedure.jcl** - Basic procedure definition and execution
- **set_symbols.jcl** - Symbol definitions
- **symbol_resolution.jcl** - Symbol substitution examples

### Advanced Statement Tests
- **advanced_job_statements.jcl** - Complex JOB statements with:
  - Multiple accounting parameters
  - Special characters in job names
  - All JOB parameters (REGION, TIME, TYPRUN, RESTART, etc.)
  - Long job names and complex accounting
  
- **advanced_exec_statements.jcl** - Complex EXEC statements with:
  - Various PARM formats (simple, complex, quoted, lists)
  - COND parameter variations (EVEN, ONLY, complex conditions)
  - REGION, TIME, DYNAMNBR specifications
  - Procedure execution with overrides
  - Long parameter strings with continuations

- **advanced_dd_statements.jcl** - Complex DD statements with:
  - All DISP parameter combinations
  - SPACE parameters (TRK, CYL, with RLSE, CONTIG, ROUND)
  - DCB subparameters (RECFM, LRECL, BLKSIZE, OPTCD, etc.)
  - Concatenated datasets
  - SYSOUT variations
  - GDG references (+1, -1, 0)
  - PDS member references
  - Temporary datasets (&&TEMP)
  - Referbacks (*.STEP.DD)
  - Unix PATH specifications
  - SMS parameters (DATACLAS, MGMTCLAS, STORCLAS)
  - AMP and SUBSYS parameters

### Continuation Line Edge Cases
- **continuation_edge_cases.jcl** - Complex continuation patterns:
  - Multiple levels of continuation
  - Continuation in middle of parameters
  - Continuation with special characters
  - Very long parameter strings
  - Nested parentheses with continuation
  - Blank continuation lines
  - Quotes across continuation lines
  - Continuation in JOB statements

### Parameter Parsing Edge Cases
- **parameter_edge_cases.jcl** - Complex parameter parsing:
  - Nested quotes and apostrophes
  - Doubled quotes ('') for escaping
  - Complex list parameters
  - Nested lists
  - Empty parameters
  - Keywords with special characters
  - Mixed positional and keyword parameters
  - Parameters with equals signs in values
  - Special characters in dataset names ($, #, @)
  - Referbacks with qualifiers
  - GDG relative generations
  - Unix paths
  - Very long parameter values
  - Commas in quoted strings
  - Boolean-like parameters
  - COND parameter variations
  - SYSOUT variations

### Inline Data Edge Cases
- **inline_data_edge_cases.jcl** - Inline data scenarios:
  - Simple inline data (DD *)
  - Custom delimiters (DLM=)
  - Data with JCL-like lines
  - Special delimiters (##, @@, !)
  - Multiple inline data sections
  - Continuation-like characters in data
  - Empty inline data
  - Nested delimiters
  - Long inline data sections
  - Special characters in data
  - DD DATA without DLM
  - IDCAMS with continuation characters
  - Mixed inline and regular DD statements
  - Numbered lines (COBOL source)
  - Delimiters that look like JCL (//)

### Comment and Whitespace Edge Cases
- **comment_whitespace_edge_cases.jcl** - Comment patterns:
  - Simple comments
  - Comment blocks
  - Comments with special characters
  - Empty comment lines
  - Inline comments (non-standard)
  - Multi-line comment blocks
  - Comment with no space after asterisk
  - Comments with trailing spaces
  - Empty lines (just //)
  - Various whitespace patterns
  - Tabs vs spaces
  - Mixed indentation
  - Comments that look like JCL
  - Very long comment lines
  - Comments with continuation characters
  - Comment boxes with asterisks
  - Comments with symbols
  - Delimiter vs comment distinction
  - Comments between statements

### Symbol and Procedure Edge Cases
- **symbol_edge_cases.jcl** - Symbol substitution:
  - SET statement variations
  - System symbols (&SYSUID, &SYSDATE, &SYSTIME)
  - Nested symbol references
  - Symbols in various positions
  - Undefined symbols
  - Symbols in quoted strings
  - Multiple symbols in one parameter
  - Symbols with special characters
  - Conditional SET (IF/THEN/ELSE)
  - SET with expressions
  - Very long symbol values
  - Ampersand without symbol name
  - Double ampersand (&&TEMP)
  - Symbols in GDG
  - Symbols in SYSOUT
  - SET with no value
  - Symbolic parameters in JOB statement

- **procedure_edge_cases.jcl** - Procedure scenarios:
  - Simple inline procedures (PROC/PEND)
  - Procedures with parameters
  - Procedure overrides
  - Multiple step procedures
  - Step-specific DD overrides
  - Conditional execution in procedures
  - Nested procedure calls
  - Complex parameter passing
  - ADD statements
  - Override with concatenation
  - Symbolic parameters and SET in procedures
  - JCLLIB ORDER
  - Procedures with defaults
  - Long procedure names
  - Procedures with inline data
  - Override inline data
  - Procedure invocation with continuation

### Conditional Statements
- **conditional_if.jcl** - Basic IF statement (original)
- **conditional_if_then_else.jcl** - Comprehensive IF/THEN/ELSE:
  - Simple IF conditions
  - IF with ELSE
  - Nested IF statements
  - String comparisons
  - Boolean expressions (AND, OR, NOT)
  - Multiple ELSE IF
  - Conditional EXEC
  - Conditional DD
  - IF with expressions
  - IF with system symbols
  - Complex nested conditions

### Special Characters and Encoding
- **special_characters.jcl** - Character handling:
  - National characters (ÄÖÜ)
  - All valid special characters ($, #, @)
  - Ampersands in various contexts
  - Maximum length names
  - Single character names
  - Numbers in names
  - Underscores and hyphens
  - Very long dataset names (44 chars)
  - Empty parameters
  - Null statements
  - Multiple spaces
  - Space before/after comma
  - Trailing commas
  - Parameters with no value
  - Zero values
  - Very large numbers
  - Negative numbers
  - Decimal numbers
  - Scientific notation
  - Binary/hex values
  - Unicode in comments
  - Case sensitivity tests
  - Reserved words as names
  - Special JCL characters in strings
  - Blank parameter values

### Realistic Production Examples
- **realistic_production_job.jcl** - Complete production workflow:
  - JCLLIB ORDER
  - Multiple SET statements
  - Backup step with IEBGENER
  - Sort and merge with concatenated inputs
  - IDCAMS VSAM operations
  - Custom COBOL program execution
  - Report generation
  - Notification step
  - Cleanup with COND=EVEN
  - Complex COND parameters across steps
  - Multiple DD concatenations
  - Temporary datasets (&&TEMP)
  - Referback DCB parameters
  - GDG with symbols
  - SYSOUT with INTRDR

### Utility Programs
- **utility_programs.jcl** - IBM utility examples:
  - IEBGENER - Sequential copy
  - IEBCOPY - PDS copy/compress
  - IEBCOMPR - Compare datasets
  - IEBUPDTE - Maintain source libraries
  - IEFBR14 - Dummy program
  - DFSORT - Advanced sorting
  - ICETOOL - Advanced data manipulation
  - IEBPTPCH - Print/punch utility
  - IEBIMAGE - Character set management
  - IEHINITT - Tape initialization
  - FTP - File transfer

### Generation Data Groups (GDG)
- **gdg_generation_data_groups.jcl** - GDG operations:
  - Define GDG base
  - Create new generation (+1)
  - Read current generation (0)
  - Read previous generation (-1)
  - Multiple generations in same job
  - Copy between generations
  - Delete old generations
  - List GDG entries
  - Modify GDG base
  - GDG with symbols
  - Absolute generation numbers

### Tape Operations
- **tape_operations.jcl** - Tape handling:
  - Write to tape with standard labels
  - Read from tape
  - Multi-volume tape
  - Non-labeled tape (NL)
  - Bypass label processing (BLP)
  - American National Standard labels (AL)
  - Tape with specific file position
  - Retention period (RETPD)
  - Expiration date (EXPDT)
  - Deferred mounting
  - Cartridge tape

### Error Handling Test Cases
These fixtures contain intentional errors for testing parser error detection:

- **error_no_job_statement.jcl** - Missing JOB statement
- **error_dd_without_exec.jcl** - DD without preceding EXEC
- **error_unclosed_quote.jcl** - Unclosed quotation mark
- **error_unclosed_paren.jcl** - Unclosed parenthesis
- **error_invalid_name.jcl** - Invalid name with hyphens
- **error_missing_pgm_param.jcl** - EXEC without PGM parameter
- **error_invalid_disp.jcl** - Invalid DISP values
- **error_duplicate_dd_name.jcl** - Duplicate DD names in same step
- **error_name_too_long.jcl** - Name exceeds 8 characters
- **error_invalid_continuation.jcl** - Continuation line without //
- **error_missing_delimiter.jcl** - Inline data without delimiter
- **error_circular_proc.jcl** - Circular procedure references
- **error_undefined_proc.jcl** - Reference to non-existent procedure
- **error_invalid_proc_override.jcl** - Override for non-existent step
- **error_mismatched_brackets.jcl** - Mismatched parentheses

### Legacy Test Files
- **circular_proc.jcl** - Circular procedure reference test
- **dd_override.jcl** - DD override examples
- **jcllib_include.jcl** - JCLLIB ORDER examples
- **multiline_strings.jcl** - Multi-line string handling
- **nested_proc.jcl** - Nested procedure examples

## Coverage Areas

These fixtures are designed to test:

1. **Statement Types**: JOB, EXEC, DD, PROC, PEND, SET, IF, THEN, ELSE, ENDIF, JCLLIB
2. **Parameters**: All standard and advanced parameters for each statement type
3. **Continuation Lines**: Various patterns and edge cases
4. **Comments**: All comment styles and edge cases
5. **Inline Data**: All delimiter types and data patterns
6. **Symbols**: System and user-defined symbols, substitution patterns
7. **Procedures**: Definition, invocation, overrides, nesting
8. **Conditionals**: IF/THEN/ELSE constructs
9. **Special Characters**: All valid JCL special characters
10. **Error Conditions**: Syntax errors, validation errors, semantic errors
11. **Real-world Scenarios**: Production-like JCL with complex workflows

## Usage in Tests

These fixtures can be used for:

- Unit tests for individual parser components
- Integration tests for end-to-end parsing
- Regression tests to prevent bugs
- Performance tests with complex JCL
- Error handling and validation tests
- Documentation and examples

## Adding New Fixtures

When adding new fixtures:

1. Use descriptive names indicating what is being tested
2. Include comments explaining the test purpose
3. Group related tests in the same file
4. For error tests, prefix with `error_`
5. Update this README with the new fixture description
6. Ensure the fixture tests a unique edge case not already covered
