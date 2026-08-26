# Git bundle prerequisite verification

**Problem**

A thin or incremental bundle can be syntactically valid yet unusable because the destination lacks prerequisite commits.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use before offline transfer, disaster recovery, or bundle-based bootstrap.

## Controls

- Run `git bundle verify` against the intended destination repository.
- Record advertised refs, prerequisites, and object IDs.
- Authenticate the bundle transport separately.

## Implementation

- Generate the bundle from reviewed refs.
- Verify at destination before changing refs.
- Import into a quarantine namespace first.

## Tests

- Test full, thin, missing-prerequisite, corrupt, and wrong-repository bundles.

## Gotchas

- Verification uses destination object availability.
- Bundles can expose history beyond one branch.
- Validity is not publisher authenticity.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-bundle)
