# legacy-code-testing

**Issue:** Adding tests to existing code that was written without testability in mind
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A large codebase has no tests. Every attempt to add a test requires restructuring half the module because of hard-coded dependencies, static calls, and global state.

## Pattern / Solution
Apply Michael Feathers' "safe refactoring to seams":

1. **Find a seam** — a place where you can change behaviour without editing the code under test (constructor injection, extracted interface, function parameter).
2. **Extract and inject dependencies** one at a time rather than rewriting the whole module.
3. **Write a characterization test first** to pin current (possibly buggy) behaviour before changing anything.

Practical techniques:
- Wrap static/global calls behind a thin adapter that can be swapped in tests.
- Use `jest.spyOn` / `vi.spyOn` to intercept hard-coded module imports without restructuring.
- Break circular dependencies by extracting shared types to a separate module.

Start with the highest-risk code (payment, auth, data migration) rather than the most convenient code.

## Gotchas
- Do not aim for 100% coverage immediately — focus on stabilising the riskiest paths first.
- Approval tests (golden master) are useful for complex legacy output where desired behaviour is unknown.
- Legacy tests that pass do not mean the code is correct — they mean the code does what it currently does.

## Related
- characterization-tests
- golden-master-testing
- approval-testing
- refactoring-with-tests
