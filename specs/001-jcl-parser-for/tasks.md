# Tasks: JCL Parser for Python 3.13

**Input**: Design documents from `C:\Users\sam94\workspace\jcl-parser\specs\001-jcl-parser-for\`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → ✓ Found: Python 3.13+, pytest, single package structure
2. Load optional design documents:
   → ✓ data-model.md: 5 entities (Job, Step, DDStatement, Parameter, ParseError)
   → ✓ contracts/: 3 files (parser_api, model_api, plugin_api)
   → ✓ research.md: Technology decisions for setup
   → ✓ quickstart.md: 4 integration scenarios
3. Generate tasks by category:
   → ✓ Setup: project structure, dependencies, linting
   → ✓ Tests: 21 contract tests, 4 integration tests
   → ✓ Core: 5 entity models, parser, validators, plugins
   → ✓ Integration: package initialization, error handling
   → ✓ Polish: unit tests, performance validation, docs
4. Apply task rules:
   → ✓ Different files marked [P] for parallel
   → ✓ Same file tasks sequential (no [P])
   → ✓ Tests before implementation (TDD)
5. Number tasks sequentially (T001-T042)
6. Generate dependency graph
7. Create parallel execution examples
8. Validate task completeness:
   → ✓ All 3 contracts have test tasks
   → ✓ All 5 entities have model tasks
   → ✓ All 4 scenarios have integration tasks
9. Return: SUCCESS (tasks ready for execution)
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
Based on plan.md structure: Single Python package at repository root
```
jclparser/           # Main package
tests/              # Test suite
examples/           # Usage examples
docs/               # Documentation
```

## Phase 3.1: Setup
- [x] T001 Create jclparser package directory structure with __init__.py, parser.py, model.py, errors.py, validators.py, utils.py, plugins/__init__.py, plugins/base.py
- [x] T002 Initialize Python 3.13+ project with pyproject.toml including pytest and coverage.py dependencies
- [x] T003 [P] Configure pytest.ini and .coveragerc for 90%+ coverage requirement
- [x] T004 [P] Create tests/ directory structure with contract/, integration/, unit/, fixtures/sample_jcl/ subdirectories

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

### Contract Tests (Parser API) - ✅ FAILING AS EXPECTED
- [x] T005 Contract tests for parse_jcl(), validate_jcl(), parse_statement() in tests/test_parser_api.py

### Contract Tests (Model API) - ✅ FAILING AS EXPECTED
- [x] T006 Contract tests for Job, Step, DDStatement classes and methods in tests/test_model_api.py

### Contract Tests (Plugin API) - ✅ FAILING AS EXPECTED
- [x] T007 Contract tests for StatementPlugin, ValidationPlugin, PluginRegistry, ParserConfig in tests/test_plugin_api.py

### Integration Tests (Quickstart Scenarios) - ✅ FAILING AS EXPECTED
- [x] T008 Integration tests for all quickstart scenarios in tests/test_integration.py
- [ ] T022 [P] Integration test error handling and validation scenario in tests/integration/test_quickstart_error_handling.py
- [ ] T023 [P] Integration test complex JCL features scenario in tests/integration/test_quickstart_complex_jcl.py
- [ ] T024 [P] Integration test plugin extensibility scenario in tests/integration/test_quickstart_plugin_system.py
- [ ] T025 [P] Performance validation test for large JCL files in tests/integration/test_quickstart_performance.py

## Phase 3.3: Core Implementation (ONLY after tests are failing)

### Data Model Entities
- [ ] T026 [P] Job entity dataclass in jclparser/model.py (Job class only)
- [ ] T027 Step entity dataclass in jclparser/model.py (Step class, same file as Job)
- [ ] T028 DDStatement entity dataclass in jclparser/model.py (DDStatement class, same file)
- [ ] T029 Parameter entity dataclass in jclparser/model.py (Parameter class, same file)
- [ ] T030 [P] ParseError and enum classes in jclparser/errors.py

### Core Parser Logic
- [ ] T031 Core JCL statement parsing logic in jclparser/parser.py (parse_statement function)
- [ ] T032 Main parse_jcl() function implementation in jclparser/parser.py (same file as T031)
- [ ] T033 JCL validation functions in jclparser/validators.py
- [ ] T034 Helper utilities for JCL syntax handling in jclparser/utils.py

### Plugin System
- [ ] T035 [P] StatementPlugin and ValidationPlugin base classes in jclparser/plugins/base.py
- [ ] T036 PluginRegistry implementation in jclparser/plugins/__init__.py
- [ ] T037 ParserConfig class with plugin support in jclparser/parser.py (same file as parsing logic)

## Phase 3.4: Integration
- [ ] T038 Package __init__.py with main API exports and plugin registry initialization in jclparser/__init__.py
- [ ] T039 Error handling integration and custom exception hierarchy completion in jclparser/errors.py (same file as T030)
- [ ] T040 Plugin system integration with core parser in jclparser/parser.py (same file as parsing)

## Phase 3.5: Polish
- [ ] T041 [P] Unit tests for edge cases and utilities in tests/unit/test_utils.py
- [ ] T042 [P] Performance benchmarks and memory usage validation in tests/unit/test_performance.py
- [ ] T043 [P] Create example usage scripts in examples/basic_parsing.py
- [ ] T044 [P] Sample JCL files for testing in tests/fixtures/sample_jcl/
- [ ] T045 [P] API documentation generation in docs/api/
- [ ] T046 Code coverage verification (90%+ requirement) and test execution
- [ ] T047 Integration test execution against quickstart scenarios

## Dependencies

### Setup Dependencies
- T001 → T002 → T003, T004 (project structure before config)

### Test Dependencies (TDD Critical Path)
- T004 → T005-T025 (test directories before test files)
- All T005-T025 MUST complete and FAIL before any T026+ implementation

### Implementation Dependencies  
- T026-T030 (models) → T031-T034 (parser logic)
- T035-T036 (plugin base) → T037 (plugin integration)
- T031-T034 (core logic) → T038-T040 (integration)

### Validation Dependencies
- T038-T040 (integration) → T041-T047 (polish and validation)

## Parallel Execution Examples

### Phase 3.2 Contract Tests (Launch together after T004)
```bash
# All contract tests can run in parallel (different files)
Task: "Contract test parse_jcl(string) in tests/contract/test_parser_api_parse_string.py"
Task: "Contract test Job class creation in tests/contract/test_model_api_job.py"  
Task: "Contract test StatementPlugin registration in tests/contract/test_plugin_api_statement.py"
Task: "Integration test basic parsing in tests/integration/test_quickstart_basic_parsing.py"
# Continue with T006-T025 all in parallel
```

### Phase 3.3 Entity Models (After tests failing)
```bash
# T026 can run in parallel with T030 (different files)
# T027-T029 must run sequentially after T026 (same file jclparser/model.py)
Task: "Job entity dataclass in jclparser/model.py"
Task: "ParseError classes in jclparser/errors.py"  # Can run parallel with T026
# Then T027 → T028 → T029 sequentially after T026
```

### Phase 3.5 Polish Tasks
```bash
# Different files can run in parallel
Task: "Unit tests for utilities in tests/unit/test_utils.py"
Task: "Performance benchmarks in tests/unit/test_performance.py" 
Task: "Example scripts in examples/basic_parsing.py"
Task: "Sample JCL files in tests/fixtures/sample_jcl/"
Task: "API documentation in docs/api/"
```

## Task Validation Results

✅ **All contracts have tests**: 3 contract files → 16 contract test tasks (T005-T020)  
✅ **All entities have models**: 5 entities → 5 model tasks (T026-T030)  
✅ **All scenarios have integration tests**: 4 scenarios + performance → 5 integration tasks (T021-T025)  
✅ **TDD ordering**: All test tasks (T005-T025) before implementation (T026+)  
✅ **Parallel tasks independent**: [P] tasks use different files  
✅ **File path specificity**: Each task specifies exact file location  
✅ **No file conflicts**: Same-file tasks sequential, different-file tasks marked [P]

## Notes
- [P] tasks = different files, no dependencies between them
- Verify ALL tests T005-T025 fail before implementing ANY T026+ tasks
- Commit after each task completion
- Focus on TDD: Red → Green → Refactor cycle
- Plugin system tests (T016-T020) may need custom plugin implementations
- Performance tests (T042, T025) should validate <5 second parsing for 3000+ line files
- Coverage validation (T046) must achieve 90%+ as per constitutional requirement

---

**Status**: Ready for execution - 47 tasks generated following constitutional TDD requirements