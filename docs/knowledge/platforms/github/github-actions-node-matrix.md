# github-actions-node-matrix

**Issue:** Running CI across multiple Node.js versions in a matrix strategy
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You want to ensure your Node.js package works on LTS versions (18, 20, 22) and optionally the current release without duplicating workflow steps.

## Pattern / Solution
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        node-version: [18, 20, 22]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: npm
      - run: npm ci
      - run: npm test
```
Add `include` to test an extra combo without adding a full matrix dimension:
```yaml
        include:
          - node-version: 23
            experimental: true
```

## Gotchas
- `fail-fast: false` prevents one failing version from cancelling the rest.
- Always pin `actions/setup-node` to a major tag; patch updates can shift default behaviour.
- `cache: npm` only caches `~/.npm`; use `cache-dependency-path` when `package-lock.json` lives in a subdirectory.
- `npm ci` requires a lockfile; `npm install` does not — choose deliberately.

## Related
- `github-actions-cache-dependencies.md`
- `github-actions-matrix-2026.md`
