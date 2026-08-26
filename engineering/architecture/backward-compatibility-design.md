# backward-compatibility-design

**Issue:** API changes break existing clients silently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Clients running older versions start failing after a server deploy. No formal compatibility contract existed.

## Pattern / Solution
Never remove or rename fields in responses. Add-only changes are safe. Use field deprecation notices and sunset headers. Maintain parallel field names during transitions. Semantic versioning gates breaking changes behind major version bumps.

## Gotchas
Default values for new required fields must be sensible. Enums are particularly dangerous adding values can break exhaustive switches on the client.

## Related
api-versioning-strategy, contract-first-api-design, openapi-spec-driven-development
