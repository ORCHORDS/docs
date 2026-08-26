# bruno-api-client

**Issue:** API collections stored in Postman cloud, not version-controlled
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Postman collections drift, are not in git, and require account login to access.

## Pattern / Solution
Bruno stores API collections as plain text files (.bru format) in a folder — commit alongside code. Open source, no account required. Import from Postman/Insomnia. Environments stored as environments/*.bru. Run via CLI: bru run --env local.

## Gotchas
- .bru files contain environment variable names but not values — store values in local env file
- Bruno scripting uses JavaScript in script blocks

## Related
- httpie-patterns, curl-advanced-usage, postman-collections
