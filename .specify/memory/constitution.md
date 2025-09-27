<!--
Sync Impact Report:
Version: 1.0.0 (initial constitution creation)
Modified principles: None (new constitution)
Added sections: All sections created from template
Removed sections: None
Templates requiring updates: 
  ✅ plan-template.md - Constitution Check section needs principle alignment
  ✅ spec-template.md - Reviewed for scope/requirements alignment
  ✅ tasks-template.md - Reviewed for task categorization alignment
Follow-up TODOs: None - all placeholders filled
-->

# JCL Parser Constitution

## Core Principles

### I. Library-First Architecture
The JCL parser MUST be implemented as a standalone, self-contained library with clear separation of concerns. The core parsing functionality MUST be independent of CLI, web interfaces, or other delivery mechanisms. All features start as library functions before any interface implementation.

Rationale: Enables maximum reusability for mainframe modernization tools, migration systems, and third-party integrations while maintaining testability and modularity.

### II. Test-First Development (NON-NEGOTIABLE)
Automated tests MUST be written and MUST pass for every release. All core functionality MUST be covered by tests. Tests MUST be written before implementation using TDD methodology: Tests written → Tests fail → Implement → Tests pass → Refactor.

Code coverage MUST be tracked and maintained above 90%. Releases are blocked if required tests fail. No feature is complete without corresponding tests.

Rationale: JCL parsing involves complex syntax variations and edge cases. Test-first approach ensures correctness and prevents regressions in this critical parsing functionality.

### III. Comprehensive JCL Coverage
Tests and examples MUST cover most current and commonly used JCL syntax including statement variations, parameters, edge cases, and real-world script samples. The parser MUST handle JOB, EXEC, DD statements, comments, parameters, quoted values, lists, and positional arguments.

Error handling MUST be comprehensive with clear reporting of syntax errors, missing statements, and unsupported features. Validation MUST verify JCL structure and parameter correctness.

Rationale: JCL has numerous syntactic variations and legacy patterns. Comprehensive coverage ensures the parser works reliably with real mainframe workloads.

### IV. Clean API Design  
The Python API MUST be Pythonic, intuitive, and simple. Object model MUST expose parsed JCL as a tree of meaningful objects (Job, Step, DD). Method names MUST follow Python conventions. Error handling MUST use standard Python exceptions.

Public interfaces MUST be documented with docstrings. Breaking changes MUST follow semantic versioning. API design MUST prioritize ease of use over implementation convenience.

Rationale: The parser will be used by developers with varying mainframe knowledge. A clean, well-documented API reduces learning curve and integration friction.

### V. Extensibility & Modularity
The parser MUST support extensibility through plugins or hooks for new statement types and validation rules. Core parsing logic MUST be separated from validation, formatting, and transformation features.

Optional advanced features (syntax highlighting, static analysis, transformations) MUST be implemented as separate modules that don't impact core parsing performance or complexity.

Rationale: JCL dialects vary across mainframe vendors and organizations. Extensibility allows customization without modifying core parser logic.

## Python Standards

**Technology Stack**: Python 3.13+, pytest for testing, coverage.py for coverage tracking. Use pyproject.toml (PEP 621) for build configuration and metadata.

**Distribution**: Publish on PyPI as `jclparser`. Provide both wheel and source distributions. Follow semantic versioning (MAJOR.MINOR.PATCH) for releases.

**Code Quality**: Follow PEP 8 style guidelines. Use type hints for public APIs. Maintain consistent code formatting and documentation standards.

## Quality Gates

**Testing Requirements**: All tests MUST pass before merging PRs or publishing releases. Integration tests MUST include real JCL script samples. Performance tests MUST verify parsing speed for large JCL files.

**Review Process**: All code changes require review for adherence to constitution principles. Complex parsing logic requires additional review for edge case handling and performance impact.

**Release Criteria**: Version increments require passing test suite, documentation updates, and changelog entries. Breaking API changes require MAJOR version increment and migration guidance.

## Governance

This constitution supersedes all other development practices and guidelines. All pull requests and code reviews MUST verify compliance with these principles.

Amendments require documentation of rationale, impact assessment, and migration plan for existing code. Constitution violations MUST be justified in writing or the approach MUST be simplified to comply.

**Version**: 1.0.0 | **Ratified**: 2025-09-27 | **Last Amended**: 2025-09-27