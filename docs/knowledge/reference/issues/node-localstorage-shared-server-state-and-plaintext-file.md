# Node localStorage Shared Server State and Plaintext File

**Issue:** Node’s browser-compatible localStorage is process-wide server state, not per-user storage. It is unencrypted, file-backed when configured, and size-limited.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Do not use Node localStorage for tenant, session, credential, or request-isolated data.
- Provide --localstorage-file explicitly when the feature is intentionally used and protect that file with OS permissions.
- Treat the API’s release-candidate status and major-version behavior as an upgrade risk.
- Prefer an explicit datastore with concurrency, encryption, and tenancy controls for server state.

## Verification

- Issue requests for two users and confirm no state can cross identities.
- Fill storage to its limit and verify failure behavior.
- Restart and run multiple processes against the deployment design to test persistence and contention assumptions.

## Gotchas

- The data is shared across all users and requests.
- Behavior without --localstorage-file changed across Node major versions.

## Official sources

- https://nodejs.org/api/globals.html#localstorage
