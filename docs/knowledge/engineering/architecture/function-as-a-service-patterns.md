# function-as-a-service-patterns

**Issue:** FaaS functions become tangled with infrastructure concerns and hard to test
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Lambda handlers mix business logic, SDK calls, and parsing. Unit testing requires mocking the entire AWS SDK.

## Pattern / Solution
Keep handlers thin: parse the event, call a pure business logic function, format the response. Extract business logic into a framework-independent core. Use dependency injection to swap infrastructure adapters in tests.

## Gotchas
Shared state between invocations via module-level variables is unreliable since instances may be recycled. Initialize connections outside the handler but validate them at the start of each invocation.

## Related
serverless-architecture, hexagonal-architecture, event-driven-architecture
