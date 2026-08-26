# Outbound dependency deadlines and error contracts

**Issue:** An API call to a dependency waits indefinitely or returns provider-specific errors directly to callers, exhausting capacity and turning a partial outage into a system outage.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

Set a bounded deadline for every outbound dependency call. Classify timeout, cancellation, and upstream rejection separately; decide fail-open versus fail-closed per operation before implementation.

**Source:** [MDN AbortSignal.timeout()](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static)

## Pattern

```ts
const response = await fetch(url, {
  signal: AbortSignal.timeout(3_000),
});
```

Use a deadline derived from the caller’s remaining budget where possible. Do not create retries that outlive the request or repeat unsafe side effects without idempotency.

## Decision matrix

| Operation | Timeout outcome |
|---|---|
| Authorization, payment capture, destructive change | fail closed with a stable retryable response |
| Optional enrichment, recommendations, non-critical analytics | degrade explicitly and record the dependency failure |
| Idempotent read | bounded retry only when remaining deadline and provider policy allow |

## Verification

- simulated timeout releases resources and produces the documented public error;
- timeout is distinguishable from a user/client abort and upstream 4xx/5xx;
- logs retain sanitized provider diagnostics while public responses do not expose internals;
- retry tests prove no duplicate side effect;
- dependency SLO dashboards show timeout rate and deadline exhaustion.

## Gotchas

- `AbortSignal.timeout()` uses active time; suspended environments can affect wall-clock assumptions.
- A long default timeout is not a resilience strategy.
- Circuit breakers and retries complement deadlines; they do not replace them.
- Never fail open for a security or payment decision merely to make latency look better.

## Related

- `testing/contract-timeout-and-cancellation-tests.md`
- `patterns/idempotency-keys.md`
- `monitoring/slo-error-budget-2026.md`
