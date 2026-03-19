# JCL Parser Constitution

**This file is a reference to the LegacyLens Platform Constitution.**

## Master Constitution

All development in this project MUST comply with the **LegacyLens Platform Constitution** defined at:
   
   📄 [`../../backend/.specify/memory/constitution.md`](../../backend/.specify/memory/constitution.md)

The seven universal principles (Type Safety, TDD, Modular Architecture, Performance, Observability, Security, Reliability) apply equally to all projects.

---

## Project-Specific Stack & Guidance

This project is **JCL Parser** — a Python 3.13+ lexer/parser pipeline for Job Control Language.

### Technology Stack

- **Language**: Python 3.13+
- **Testing**: pytest + coverage.py
- **Type checking**: type hints on all public APIs
- **Architecture**: Two-stage pipeline (Lexer → Tokens → Parser → AST)
- **Export**: JSON serialization via consistent AST node structure
- **Coverage minimum**: 81%+ line coverage required

### Mandatory Rules

**Type Safety (Principle I)**:
- Type hints on all public functions and class methods.
- No `Any` types without documented justification.

**TDD (Principle II)**:
- All new features MUST have tests written first (red-green-refactor).
- Minimum 81% line coverage required for all new code.
- Test layers: unit (isolated), integration (real JCL samples), contract (API stability).

**Modular Architecture (Principle III)**:
- Lexer and Parser as separate stages.
- Clear separation of concerns: tokenization vs. parsing vs. AST construction.
- Consistent `to_dict()` interface on all AST nodes for JSON export.

**Performance (Principle IV)**:
- Efficient token processing for large JCL files.
- No unnecessary re-scanning or AST re-construction.
- Memory-efficient data structures.

**Observability (Principle V)**:
- Structured logging via Python's logging module.
- Parse statistics collected and reported.
- Error types and recovery strategies documented.

**Security (Principle VI)**:
- Input validation for JCL source (encoding, length).
- Safe handling of external file references.
- No arbitrary code execution via included files.

**Reliability (Principle VII)**:
- Graceful error handling with detailed error messages.
- Idempotent parsing (same input → same AST).
- All edge cases tested and handled.

### Key Patterns

**AST Node Serialization**:
All AST nodes MUST support JSON export via consistent structure:
```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "node_type": self.node_type,
        "value": self.value,
        "location": self.location.to_dict() if self.location else None,
    }
```

**Type Hints Everywhere**:
```python
def parse_jcl(source: str, strict: bool = True) -> JCLProgram:
    """Parse JCL source code.
    
    Args:
        source: JCL source code as string
        strict: if True, fail on first error; if False, collect all errors
        
    Returns:
        JCLProgram AST node
    """
    ...
```

### Code Review Gates (JCL Parser-Specific)

- [ ] Type hints on all new/modified public methods.
- [ ] 81%+ coverage for new code (unit + integration + contract).
- [ ] All AST nodes serialize to/from JSON correctly.
- [ ] No `Any` types or `type: ignore` without documented reason.
- [ ] Contract tests validate API stability.
- [ ] Error handling verified for all edge cases.

### Development Workflow

1. **Write test** (red) — failing unit test for the feature.
2. **Implement** (green) — minimal code to make test pass.
3. **Verify JSON export** — ensure AST nodes serialize to JSON.
4. **Integration test** — end-to-end with real JCL samples.
5. **Contract test** — API stability and backward compatibility.
6. **Refactor** — improve clarity while tests pass.

### Testing Commands

```bash
# All tests
cd jclparser; pytest

# Coverage check
pytest --cov=jclparser --cov-fail-under=81

# Code quality
ruff check . ; black . ; mypy jclparser/
```

### Additional Resources

- **Main Platform Constitution**: [`../../backend/.specify/memory/constitution.md`](../../backend/.specify/memory/constitution.md)
- **Project Instructions**: [`.github/copilot-instructions.md`](.github/copilot-instructions.md)
- **Development Guide**: [`README.md`](README.md)

---

**Version**: 2.0.0 (follows platform v2.0.0) | **Synced**: 2026-03-16
