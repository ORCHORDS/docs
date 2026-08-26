# github-actions-cache-dependencies

**Issue:** Caching build tool dependencies efficiently with actions/cache
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cold builds download hundreds of MB on every run. Proper caching can cut CI time by 60-90%.

## Pattern / Solution
```yaml
      - uses: actions/cache@v4
        with:
          path: |
            ~/.npm
            ~/.cache/Cypress
          key: ${{ runner.os }}-npm-${{ hashFiles('**/package-lock.json') }}
          restore-keys: |
            ${{ runner.os }}-npm-
```
Tool-specific shortcuts (auto-integrated into setup actions):
```yaml
      # Node
      - uses: actions/setup-node@v4
        with:
          cache: npm           # or pnpm / yarn

      # Python
      - uses: actions/setup-python@v5
        with:
          cache: pip

      # Go
      - uses: actions/setup-go@v5
        with:
          cache: true
```

## Gotchas
- Cache keys are immutable; a matching key is never updated. Use `restore-keys` as a fallback prefix.
- Cache size limit is 10 GB per repository; older entries are evicted after 7 days of no access.
- Cross-OS cache sharing does not work — always include `runner.os` in the key.
- Post-job cache saving fails silently if the runner runs out of disk space.

## Related
- `github-actions-monorepo-caching.md`
- `github-actions-caching-2026.md`
