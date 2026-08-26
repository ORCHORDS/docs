# lighthouse-ci-integration

**Issue:** Running Lighthouse audits automatically on every PR to prevent performance and accessibility regressions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Performance scores and accessibility grades drift downward release by release because no one is watching them between manual audits.

## Pattern / Solution
Use `@lhci/cli` (Lighthouse CI) to run audits in CI and assert against configurable thresholds:

```yaml
# .github/workflows/lhci.yml
- name: Run Lighthouse CI
  run: |
    npm install -g @lhci/cli
    lhci autorun
```

```js
// lighthouserc.js
module.exports = {
  ci: {
    collect: { url: ["http://localhost:3000/", "http://localhost:3000/checkout"] },
    assert: {
      assertions: {
        "categories:performance": ["warn", { minScore: 0.8 }],
        "categories:accessibility": ["error", { minScore: 0.9 }],
        "categories:best-practices": ["warn", { minScore: 0.85 }],
      },
    },
    upload: { target: "temporary-public-storage" },
  },
};
```

Store results in Lighthouse CI server or `temporary-public-storage` for link-in-PR comments.

## Gotchas
- Lighthouse scores are variable across runs; use `--runs=3` and compare the median.
- Run against a production-like build (`NODE_ENV=production`), not the dev server.
- Score comparisons are only meaningful between the same device/CPU throttling settings.

## Related
- a11y-automated-testing-axe
- performance-testing-k6
- visual-regression-testing-percy
