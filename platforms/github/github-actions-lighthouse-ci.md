# github-actions-lighthouse-ci

**Issue:** Running Lighthouse performance audits in CI and failing on score regressions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Performance regressions slip in unnoticed. Lighthouse CI gates PRs on Core Web Vitals scores.

## Pattern / Solution
`.lighthouserc.yml`:
```yaml
ci:
  collect:
    url:
      - http://localhost:3000
    numberOfRuns: 3
  assert:
    assertions:
      categories:performance:
        - warn
        - minScore: 0.85
      categories:accessibility:
        - error
        - minScore: 0.95
  upload:
    target: temporary-public-storage
```
Workflow:
```yaml
      - run: npm run build && npm start &
      - run: npx @lhci/cli@0.14 autorun
        env:
          LHCI_GITHUB_APP_TOKEN: ${{ secrets.LHCI_GITHUB_APP_TOKEN }}
```

## Gotchas
- Run the server in the background (`&`) and wait for it to be ready before LHCI runs.
- `numberOfRuns: 3` reduces variance; take the median.
- `temporary-public-storage` uploads reports publicly — use an LHCI server for private storage.
- The GitHub App token posts status checks directly to the PR; without it, only the workflow step fails.

## Related
- `github-actions-e2e-playwright.md`
- `github-required-status-checks.md`
