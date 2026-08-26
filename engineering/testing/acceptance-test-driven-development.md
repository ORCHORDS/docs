# acceptance-test-driven-development

**Issue:** Using acceptance tests to drive feature development and prevent scope creep
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Features ship but stakeholders discover they do not match the original intent. Unit tests pass but the user journey is broken.

## Pattern / Solution
ATDD makes acceptance criteria executable before writing any production code:

1. **Three Amigos** — developer, tester, and product owner co-author the acceptance criteria.
2. Translate criteria into runnable tests (Gherkin, Playwright, or plain integration tests).
3. Run the tests — they all fail. This is the shared definition of "done".
4. Implement until the acceptance tests pass without modifying them.
5. Demo against the running acceptance tests.

Acceptance tests live in the repo alongside unit tests:

```
tests/
  acceptance/   # ATDD scenarios
  unit/
  integration/
```

## Gotchas
- Acceptance tests should be written in domain language, not in UI-click language.
- Keep acceptance tests fast by testing at the API/service layer rather than through a browser where possible.
- If the feature changes, the acceptance test must change first — it is the spec, not the implementation.

## Related
- bdd-cucumber-gherkin
- outside-in-tdd
- end-to-end-test-strategy
