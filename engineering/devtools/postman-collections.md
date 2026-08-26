# postman-collections

**Issue:** API collections not shared or version-controlled across team
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every developer creates their own Postman collection; no canonical set of test requests.

## Pattern / Solution
Export collection as JSON v2.1 and commit to repo. Use newman CLI to run collections in CI. Postman Workspaces for team collaboration. Collection variables for base URL and auth tokens.

## Gotchas
- Postman environment files contain secrets — commit variable names only, not values
- newman requires Node; use docker run postman/newman for CI without Node install

## Related
- bruno-api-client, httpie-patterns, insomnia-patterns
