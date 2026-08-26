# ESLint bulk-suppression debt control

**Issue:** Large lint migrations can be blocked by legacy violations, but inline disables often become invisible permanent debt.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use ESLint bulk suppressions as a temporary baseline instead of scattering source comments. Commit the suppression file, review it like code, and require pruning so fixed violations disappear. Lock the file against casual regeneration, assign owners and expiry targets by rule, and keep new violations unsuppressed. A dependency or config upgrade must regenerate only in a reviewed migration change.

## Verification

Run lint with suppression pruning in CI and fail when the baseline grows outside an approved migration. Fix a known violation and verify its entry is removed; introduce a new violation and verify it is not automatically accepted.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://eslint.org/docs/latest/use/suppressions)
