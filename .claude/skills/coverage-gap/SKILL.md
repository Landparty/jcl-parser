---
name: coverage-gap
description: Find jclparser modules with lowest test coverage and suggest which tests to add
disable-model-invocation: true
---

Run the following command and report the results:

```bash
python -m pytest -q 2>/dev/null; python -m coverage report --sort=cover
```

Then:
1. List the modules below 95% coverage, sorted from lowest to highest.
2. For each under-covered module, name the corresponding test file in `tests/unit/` and suggest 2-3 specific scenarios that are likely missing (based on the module's purpose from CLAUDE.md).
3. Remind the user they can run `/gen-test jclparser/<module>.py` to generate tests for any of these modules.
