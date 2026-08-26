# openapi-spec-driven-development

**Issue:** REST API documentation goes stale immediately after publication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers rely on outdated Postman collections. Spec and implementation diverge within weeks of a launch.

## Pattern / Solution
Treat the OpenAPI YAML as the primary artifact. Validate the running service against the spec in CI using tools like schemathesis or Dredd. Generate mock servers from the spec for frontend development.

## Gotchas
Large specs become hard to review. Split into components and use refs liberally. Security schemes must be defined in the spec or consumers cannot authenticate.

## Related
contract-first-api-design, backward-compatibility-design, api-versioning-strategy
