# contract-timeout-and-cancellation-tests

**Issue:** An outbound dependency timeout is tested only as a generic error, so callers cannot distinguish cancellation, deadline expiry, upstream rejection, and safe retry behavior.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Timeout is part of the API contract. If an abort signal, deadline, retry, public error shape, and protected diagnostic record are not tested together, implementations often leak internals, retry unsafe requests, or treat an unavailable dependency as a successful empty result.

**Source:** [MDN — AbortSignal.timeout()](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static) and [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).

## Fix

- define deadline and failure policy per dependency;
- test abort propagation to the actual client call;
- distinguish timeout, cancellation, upstream rejection, and validation failure internally;
- return stable public error contracts without sensitive diagnostics;
- test safe retry/idempotency behavior and fail-open/fail-closed choice;
- capture protected correlation data for operators.

## Verification

- A delayed dependency triggers the intended deadline and public response.
- Abort reaches the downstream client.
- Public responses do not contain credentials, stack traces, or provider internals.
- Retried requests follow the documented idempotency policy.

## Related

- `patterns/circuit-breaker-pattern.md`
- `testing/schema-driven-api-fuzzing-schemathesis.md`
