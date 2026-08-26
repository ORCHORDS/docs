# end-to-end-test-strategy

**Issue:** Deciding what to cover with E2E tests and how to keep the suite maintainable
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
E2E suites grow until they are slow, flaky, and nobody trusts them. Teams either over-invest (covering every edge case E2E) or under-invest (no E2E at all).

## Pattern / Solution
Apply the "critical path" rule: E2E tests cover only journeys whose failure would block a user from the product's core value. Typical candidates:

- Sign-up → onboarding → first action
- Checkout / payment flow
- Primary CRUD workflow

Organise tests by journey, not by page:

```
e2e/
  journeys/
    signup.spec.ts
    checkout.spec.ts
  support/
    auth.ts       # shared login helper
    db-seed.ts    # seed & teardown
```

Keep each journey independent. Seed data programmatically rather than relying on prior test state. Run the suite against a staging environment with real external services behind a feature flag.

## Gotchas
- Do not duplicate unit/integration assertions in E2E — only verify observable UX outcomes.
- Long suites should be sharded across CI workers (see ci-test-parallelization).
- Avoid CSS-selector locators; prefer ARIA roles and `data-testid`.

## Related
- playwright-setup
- playwright-fixtures
- ci-test-parallelization
- test-environment-management
