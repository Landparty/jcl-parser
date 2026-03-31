---
name: gen-test
description: Generate pytest unit tests for a jclparser module following project conventions. Usage: /gen-test <module_path> e.g. /gen-test jclparser/condition_parser.py
---

Generate unit tests for the module specified in the arguments (or ask the user if not provided).

## Steps

1. Read the target module to understand its public API, classes, and functions.
2. Check for an existing test file at `tests/unit/test_<module_name>.py`. If it exists, read it to avoid duplicating tests — only generate tests for gaps.
3. Look at `tests/unit/test_condition_parser.py` as a style reference if needed.

## Conventions to follow

- File: `tests/unit/test_<module_name>.py`
- Class names: `Test<ClassName>` or `Test<FunctionName>`
- Method names: `test_<what>_<scenario>_<expected_outcome>`
- Every test method gets `@pytest.mark.unit`
- Import the relevant classes/functions from `jclparser.<module>`
- Test both success paths and error cases — use `pytest.raises(JCLSyntaxError)`, `pytest.raises(JCLValidationError)`, etc.
- No mocking unless unavoidable — this codebase is pure Python with no external I/O in unit tests
- Keep tests focused and independent (no shared state between methods)

## Output

Write the complete test file to `tests/unit/test_<module_name>.py`. If the file already exists, add only the new test classes/methods at the bottom or within the appropriate class.
