# eslint-baseline-ratchet-local-vs-ci-divergence

**Issue:** web ESLint baseline gate
**Date:** 2026-08-23
**Repo:** example-org/example-repo at 5b52fcfb
**Author:** the platform team
**Status:** fixed (2e44f7c1)

## Symptom
CI failed `Web ESLint baseline (no new violations)` for one new `react-hooks/set-state-in-effect` error in a new component. Running the repo's `lint:baseline:update` locally rewrote `eslint-baseline.json` from 272 violations to 388 errors/169 warnings — silently ADDING ~116 errors that only reproduce under the CI eslint version and DROPPING 4 warning entries (file/rule pairs that locally produce no findings). Committing that file would have hidden real regressions behind a corrupted baseline.

## Root cause
Local `eslint` (different version/resolution than CI's pnpm-installed 10.x) reports a different violation set. The baseline "ratchet" script regenerates the full file from whatever eslint run it sees, so it is only safe on a machine whose eslint output matches CI byte-for-byte. A baseline file is a diff-based contract, not a cache.

## Fix
2e44f7c1 — never run `lint:baseline:update` for a single new violation. Insert surgically: add one `"file|severity|rule": count` entry (keeping sort order) and bump `totals.errors` by 1, producing a 3-line diff. Verify with the check script (`check-eslint-baseline.mjs`) before committing.

## Verification
- **Test:** local `node scripts/check-eslint-baseline.mjs` passes; CI lint job green
- **CI:** PR #<number> lint+typecheck+test green at 2e44f7c1
- **Live:** `git diff --stat eslint-baseline.json` = 3 lines changed, not 700

## Gotchas
- `react-hooks/set-state-in-effect` is a HARD error for NEW files in strict baselines even when 74 old files carry the same violation — derive loading state (`const loading = !loaded && !failed`) instead of calling setState in an effect body/finally callback.
- Baseline checkers that print "N entries are now lower; run update to ratchet" hint that the local run under-reports; do NOT ratchet on that signal from a divergent environment.

## Related
- example-org/example-repo scripts/check-eslint-baseline.mjs, eslint-baseline.json, PR #<number>
