
# Implementation Plan: JCL Parser for Python 3.13

**Branch**: `001-jcl-parser-for` | **Date**: 2025-09-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `C:\Users\sam94\workspace\jcl-parser\specs\001-jcl-parser-for\spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from file system structure or context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Parse IBM JCL scripts into Python objects (Job, Step, DD) with comprehensive syntax coverage, error handling, and extensible architecture. Provides clean Pythonic API for mainframe modernization tools and migration systems.

## Technical Context
**Language/Version**: Python 3.13+  
**Primary Dependencies**: pytest (testing), coverage.py (coverage tracking), type hints for APIs  
**Storage**: N/A (in-memory parsing, file I/O for JCL scripts)  
**Testing**: pytest with 90%+ code coverage requirement  
**Target Platform**: Cross-platform (Windows, Linux, macOS) - pure Python library
**Project Type**: Single library package - determines source structure  
**Performance Goals**: Parse large JCL files (thousands of lines) efficiently for batch operations  
**Constraints**: Pure Python implementation, no external parsing dependencies, extensible plugin architecture  
**Scale/Scope**: Handle complex JCL with multiple steps, nested procedures, comprehensive syntax variations

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**I. Library-First Architecture**: Design MUST start with standalone library functions before any CLI/interface implementation.

**II. Test-First Development (NON-NEGOTIABLE)**: Tests MUST be written and failing before any implementation begins. TDD cycle MUST be followed strictly.

**III. Comprehensive JCL Coverage**: Implementation MUST handle core JCL statements (JOB, EXEC, DD), parameters, comments, and error cases. Real JCL samples required for testing.

**IV. Clean API Design**: Python interfaces MUST follow Pythonic conventions, use clear object models (Job, Step, DD), and include proper docstrings.

**V. Extensibility & Modularity**: Core parsing MUST be separate from optional features. Plugin/hook architecture MUST be considered for extensions.

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
jclparser/                    # Main package directory
├── __init__.py              # Package initialization and main API
├── parser.py                # Core JCL parsing logic
├── model.py                 # Data classes (Job, Step, DD, Parameter)
├── errors.py                # Custom exception classes
├── validators.py            # JCL syntax and structure validation
├── utils.py                 # Helper functions and utilities
└── plugins/                 # Extension/plugin architecture
    ├── __init__.py
    └── base.py              # Base plugin interface

tests/
├── contract/                # Contract tests for core functionality
├── integration/             # End-to-end integration tests with real JCL
├── unit/                    # Unit tests for individual components
└── fixtures/                # Test JCL files and sample data
    └── sample_jcl/

examples/                    # Example scripts and usage demos
├── basic_parsing.py
└── sample_jcl/

docs/                        # Documentation
└── api/                     # API documentation

pyproject.toml               # Build configuration and metadata
README.md                    # Installation and usage guide
LICENSE                      # License file
```

**Structure Decision**: Single Python package structure selected. This is a standalone library focusing on JCL parsing with clear separation between core parsing (parser.py), data models (model.py), validation (validators.py), and extensibility (plugins/). The structure supports the constitutional requirements for modularity and extensibility while maintaining simplicity.

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType copilot`
     **IMPORTANT**: Execute it exactly as specified above. Do not add or remove any arguments.
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs:
  * 3 contract files → 9 contract test tasks [P] (parser_api, model_api, plugin_api)
  * 5 entities → 5 model creation tasks [P] (Job, Step, DDStatement, Parameter, ParseError)
  * 4 quickstart scenarios → 4 integration test tasks
  * Core implementation tasks for parser.py, validators.py, plugins/
- TDD approach: All tests written first, then implementation to make tests pass

**Ordering Strategy**:
- Phase 1: Setup and project structure
- Phase 2: Contract tests (all failing tests first) [P]
- Phase 3: Data model implementation [P] 
- Phase 4: Core parser implementation (sequential dependencies)
- Phase 5: Plugin system and validation
- Phase 6: Integration and performance validation

**Estimated Output**: 35-40 numbered, ordered tasks in tasks.md covering:
- Project setup and dependencies (3-4 tasks)
- Contract tests for all APIs (12-15 tasks) [P]
- Entity model implementations (8-10 tasks) [P]
- Parser core logic (8-10 tasks)
- Plugin system and validation (5-6 tasks)
- Performance and integration validation (4-5 tasks)

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none required)

---
*Based on Constitution v2.1.1 - See `/memory/constitution.md`*
