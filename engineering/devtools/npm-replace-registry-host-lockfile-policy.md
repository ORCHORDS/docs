# npm lockfile registry-host replacement policy

**Issue**

Rewriting registry hosts from lockfiles can silently redirect dependency downloads and change provenance.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `replace-registry-host` explicitly and review mirrors as supply-chain infrastructure.
- Keep integrity fields mandatory and pin authentication by registry scope.
- Test public, private, and mixed lockfiles.

## Verification

1. Install with never, npmjs-only, and always policies in isolation.
2. Confirm resolved URLs and integrity.
3. Make mirror outage fail closed or follow an approved fallback.

## Gotchas

- Integrity does not authenticate registry metadata.
- Always replacement can redirect private packages.
- Lockfile diffs may hide systematic host rewriting.

## Official source

- [Official documentation](https://docs.npmjs.com/cli/v11/using-npm/config#replace-registry-host)
