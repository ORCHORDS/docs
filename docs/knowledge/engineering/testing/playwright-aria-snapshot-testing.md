# playwright-aria-snapshot-testing

**Issue:** UI tests can pass while the page's accessible structure silently regresses.
**Date:** 2026-08-26
**Status:** documented
**Source:** https://playwright.dev/docs/aria-snapshots

## Context
Playwright supports ARIA snapshot assertions that serialize the accessibility tree into a YAML-like representation of roles, accessible names, states, hierarchy, and selected attributes.

## Pattern
Use `toMatchAriaSnapshot()` for structural accessibility regression coverage where roles and relationships matter more than DOM implementation details.

```ts
await expect(page.getByRole('main')).toMatchAriaSnapshot(`
  - heading "Account" [level=1]
  - button "Save"
`)
```

Prefer focused snapshots around stable landmarks or components rather than huge whole-page snapshots that become noisy.

## Matching modes
Playwright supports partial child matching by default and stricter child modes when exact structure matters. Use strictness deliberately: over-broad snapshots miss regressions; over-strict snapshots create churn from harmless copy or ordering changes.

## Review rule
Never accept regenerated accessibility snapshots blindly. Treat snapshot changes like code changes:
- inspect the diff;
- confirm accessible names and roles are intentional;
- verify removed nodes are expected;
- review changed states such as `checked`, `disabled`, `expanded`, or `invalid`;
- combine snapshots with targeted behavioral assertions.

## Verification
Run ARIA snapshot tests across the supported browser matrix where relevant. Pair them with keyboard interaction, focus-order, form-validation, and screen-reader/manual checks for critical flows.

## Gotchas
- ARIA snapshots describe the accessibility tree, not full WCAG conformance.
- Partial matching can hide unexpected extra children unless stricter modes are chosen.
- Updating snapshots without reviewing the patch can normalize a regression.

## Related
- `playwright-accessibility-testing.md`
- `accessibility-regression-testing.md`
- `snapshot-testing.md`
