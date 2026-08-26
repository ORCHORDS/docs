# insomnia-patterns

**Issue:** Postman alternative needed for teams preferring local-first tool
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams want API client with git sync, local storage, and no required cloud account.

## Pattern / Solution
Insomnia stores collections as files, syncs via git. inso CLI for running requests in CI. Design mode for OpenAPI spec editing. Plugin ecosystem for custom auth and scripting. Export/import from Postman, HAR, cURL.

## Gotchas
- Insomnia 2023+ requires account for some features — check version for cloud requirement
- inso run test for running API test suites in CI pipeline

## Related
- postman-collections, bruno-api-client
