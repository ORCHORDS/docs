# performance-budget-setup

**Issue:** Performance degrades gradually without guardrails
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A performance budget defines maximum values for metrics (LCP < 2.5s, JS bundle < 200 KB). CI checks enforce budgets, preventing regressions before they reach production.

## Pattern / Solution
1. Define budgets in budget.json or Lighthouse config.\n2. Run Lighthouse CI with budget assertions in your CI pipeline.\n3. Set budgets slightly tighter than current values to allow headroom for dependencies.\n4. Alert on budget violations as build failures, not just warnings.\n5. Review and update budgets quarterly as the product grows.

## Gotchas
- Budgets that are too strict cause constant failures and are ignored; set realistic targets.\n- Lab budgets don't enforce field performance; complement with CrUX monitoring.\n- Bundle size budgets in webpack: performance: { maxAssetSize: 250000 }.

## Related
lighthouse-scoring, performance-regression-detection, javascript-bundle-size
