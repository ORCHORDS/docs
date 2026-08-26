# retry-pattern

**Issue:** Transient failures cause unnecessary user-visible errors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A brief network blip causes 5xx errors to surface to users even though the downstream service recovers within milliseconds.

## Pattern / Solution
Retry idempotent operations with exponential backoff and jitter. Set a maximum retry count and total timeout budget. Only retry on retriable status codes (429, 502, 503, 504). Do not retry non-idempotent writes unless the operation is explicitly idempotent.

## Gotchas
Retries without jitter cause thundering herd problems. Always cap total retry duration, not just per-attempt count. Log retry attempts for observability.

## Related
circuit-breaker-design, timeout-pattern, idempotency-design
