# contract-first-api-design

**Issue:** Client and server drift when the API is defined in code rather than a shared spec
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams discover integration mismatches in QA. Each side's understanding of field names, types, and optionality diverges over sprint cycles.

## Pattern / Solution
Write the OpenAPI or Protobuf schema before writing any implementation. Generate server stubs and client SDKs from the single source of truth. CI validates that implementation conforms to the schema.

## Gotchas
Avoid spec drift by linting the schema on every PR. Do not let code-first generation tools write the canonical spec.

## Related
openapi-spec-driven-development, backward-compatibility-design, grpc-vs-rest-vs-graphql
