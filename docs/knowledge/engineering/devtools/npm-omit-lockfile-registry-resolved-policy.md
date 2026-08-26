# npm lockfile registry-resolved omission policy

**Issue**

Omitting registry-resolved URLs improves lockfile portability but changes provenance evidence and reinstall diagnostics.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `omit-lockfile-registry-resolved` explicitly.
- Retain integrity fields and approved registry policy.
- Test reproducibility against every supported registry.

## Verification

1. Generate lockfiles with both settings and diff semantics.
2. Perform clean offline and online installs.
3. Verify private scopes resolve correctly.

## Gotchas

- Portability can reduce source attribution.
- Integrity is not registry authentication.
- Older npm behavior may differ.

## Official source

- [Official documentation](https://docs.npmjs.com/cli/v11/using-npm/config#omit-lockfile-registry-resolved)
