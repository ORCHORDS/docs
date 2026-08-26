# npm minimum-release-age dependency policy

**Issue**

Installing a package immediately after publication reduces time for ecosystem review and incident response.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `minimum-release-age` from an explicit freshness policy.
- Maintain a reviewed exclusion list for emergency packages.
- Combine age gates with lockfiles, integrity verification, provenance, and vulnerability response.

## Verification

1. Attempt installs just below and above the threshold.
2. Test transitive dependencies and exclusions.
3. Record resolver diagnostics without retry loops that bypass policy.

## Gotchas

- Age is not evidence of safety.
- Urgent security fixes may require approved exceptions.
- Different registries can expose different metadata.

## Official source

- [Official documentation](https://docs.npmjs.com/cli/v11/using-npm/config#minimum-release-age)
