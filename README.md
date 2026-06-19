# jcl-parser

A Python library for parsing IBM JCL (Job Control Language) into structured objects.

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![Coverage](https://img.shields.io/badge/coverage-90%25+-green.svg)](#testing)
[![License](https://img.shields.io/badge/license-EULA-blue.svg)](LICENSE)
[![Changelog](https://img.shields.io/badge/changelog-1.0.0-blue.svg)](CHANGELOG.md)

## Install

```bash
git clone https://github.com/Landparty/jcl-parser.git
cd jcl-parser
pip install -e .[dev]
```

## Quick start

```python
import jclparser

jcl = """
//MYJOB    JOB (ACCT),'My Job',CLASS=A
//STEP1    EXEC PGM=SORT
//SORTIN   DD  DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD  DSN=OUTPUT.DATA,DISP=(NEW,CATLG,DELETE)
//SYSIN    DD  *
  SORT FIELDS=(1,10,CH,A)
/*
"""

job = jclparser.parse_jcl(jcl)

print(job.name)                                    # MYJOB
print(job.steps[0].program)                        # SORT
print(job.steps[0].get_dd("SORTIN").dataset_name)  # INPUT.DATA
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Basic parsing](docs/basic-parsing.md) | Parse from string, file, or file object; navigate Job / Step / DD |
| [Validation & errors](docs/validation.md) | `validate_jcl`, strict mode, error types, error fixtures |
| [PROC expansion](docs/proc-expansion.md) | Inline and external PROCs, `explode_job()`, file-type detection |
| [Advanced features](docs/advanced-features.md) | Condition parsing, SQL detection, plugins, structured DCB/SPACE |

## CLI

The package installs a `jcl-parser` command:

```bash
jcl-parser FILE                              # Job summary
jcl-parser FILE steps                        # List all steps
jcl-parser FILE STEPNAME                     # Step detail
jcl-parser FILE STEPNAME.DDNAME             # Single DD statement
jcl-parser FILE DDNAME                       # All DDs with that name across steps
jcl-parser FILE procs                        # List inline PROC definitions
jcl-parser FILE procs PROCNAME              # Single PROC detail
jcl-parser FILE procs --explode             # PROC expansion audit
jcl-parser FILE procs --list-available      # List PROCs in --proc-path libraries
jcl-parser FILE detect                       # Detect file type (JCL/PROC/UNKNOWN)
jcl-parser FILE --validate                   # Validate and report errors
jcl-parser FILE --json                       # Full parse result as JSON
jcl-parser FILE metrics                      # Structural metrics (steps, nesting depth, cyclomatic score)
jcl-parser FILE lint                         # Run lint rules
jcl-parser FILE datasets                     # Dataset lifecycle analysis
jcl-parser FILE sql                          # SQL/DB2 usage detection
jcl-parser FILE analyze [STEPNAME]           # Program profile analysis
jcl-parser FILE paths                        # RC feasibility path analysis
jcl-parser --lint-list                       # List all available lint rule codes
jcl-parser FILE --explode                    # Expand PROCs before displaying
jcl-parser FILE --proc-path PATH             # Base path for external PROC libraries
jcl-parser FILE --profile                    # Include parse timing/memory metrics
```

## Testing

```bash
pytest                        # run all tests (coverage enforced at 90%)
pytest -m unit                # unit tests only
pytest -m integration         # integration tests only
pytest -m contract            # API contract tests
pytest -m performance         # benchmarks
ruff check . && ruff format . # lint and format
```

Test fixtures live in `tests/fixtures/` — see the [fixtures README](tests/fixtures/sample_jcl/README.md) for a full catalogue including error cases and real-world examples.

## Public API

```
Tier 1 (stable)    parse_jcl · validate_jcl · parse_statement · parse
                   Job · Step · DDStatement · Parameter · Statement · OutputStatement
                   JCLSyntaxError · JCLValidationError · JCLStructureError
                   ParseError · ValidationError · ErrorType · ErrorSeverity
                   UndefinedSymbolError · CircularProcedureError
                   ExplosionDepthError · ProcedureNotFoundError

Tier 2 (advanced)  explode_job · SymbolScope
                   detect_file_type · detect_file_type_from_content · is_jcl_file · is_proc_file · FileType
                   parse_condition · ConditionNode · ReturnCodeCondition · AbendCondition
                   RunCondition · NotCondition · AndCondition · OrCondition
                   detect_sql_in_job · detect_sql_in_step · detect_sql_in_dd · detect_sql_in_text
                   SQLDetectionResult · is_db2_program · DB2_PROGRAMS
                   resolve_includes · IncludeMemberLoader · DictMemberLoader · JCLLIBMemberLoader
                   analyze_dataset_lifecycle · validate_dataset_lifecycle · DatasetEvent
                   parse_jes_control · JESControlStatement · JobParmStatement · RouteStatement
                   XmitStatement · SignonStatement · MessageStatement · NetacctStatement
                   NotifyStatement · PriorityStatement · Jes3RouteXeqStatement
                   compute_metrics · JobMetrics
                   compute_feasible_paths · FeasibilityReport · DEFAULT_RC_DOMAIN
                   analyze_job · analyze_step · ProgramProfile · ProgramAnalysis
                   register_profile · analyze_step · analyze_job
                   lint_job · lint_to_sarif · register_lint_rule · LintRule · LintConfig
                   ProcedureLoader · CompositeProcedureLoader · DictProcedureLoader · create_default_loader
                   ParserConfig · ValidationLevel · StatementPlugin · ValidationPlugin
                   PluginRegistry · get_plugin_registry
                   validate_jcl_identifier · validate_dataset_name
                   validate_job_structure · validate_step_structure · validate_dd_statement
                   SystemSymbolProvider

Tier 3 (internal)  MockSystemSymbolProvider · InlineProcedureLoader · ProfilingResult · FunctionProfile
                   (may be removed in a future major version)
```

## License

Proprietary EULA — see [LICENSE](LICENSE).
