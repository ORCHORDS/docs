# github-actions-e2e-playwright

**Issue:** Running Playwright end-to-end tests in GitHub Actions with trace and video artefacts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
E2E tests need a real browser; the official Playwright Docker image or `playwright install` is required on the runner.

## Pattern / Solution
```yaml
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test
        env:
          CI: "true"
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
          retention-days: 7
```

## Gotchas
- `--with-deps` installs OS-level browser dependencies (libglib, etc.) — required on Ubuntu runners.
- `CI=true` causes Playwright to use the `ci` reporter and disable interactive output.
- Shard tests across jobs with `--shard=1/4` to parallelise: use a matrix `shard: [1, 2, 3, 4]`.
- Traces and videos balloon artefact size — only upload `if: failure()`.

## Related
- `github-actions-lighthouse-ci.md`
- `github-actions-timeout-jobs.md`
