# retry-with-jitter

**Issue:** Exponential backoff + jitter for vendor API retries
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your service calls a vendor API. The vendor has a 5-minute outage.
You retry every second. The vendor's service is hammered by
thousands of identical "is it back yet?" requests the moment it
recovers. The recovery is delayed by minutes. You're part of the
problem.

## Root cause
**Synchronous retries without jitter** create thundering herds.
When the vendor recovers, every client retries at roughly the
same moment. The vendor gets a 1000x spike in traffic, which
re-triggers the outage.

**Source:** AWS Builders Library — Timeouts, retries, and backoff
with jitter:
https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/

> "Adding a small amount of randomness to the backoff time, also
> known as jitter, ... can prevent thundering herd scenarios."

## Fix
Exponential backoff with **full jitter**:

```ts
async function fetchWithRetry(
  url: string,
  init: RequestInit,
  maxAttempts: number = 5
): Promise<Response> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const res = await fetch(url, init);
      // Don't retry 4xx (client error) — only 5xx and network errors
      if (res.status < 500) return res;
      if (attempt === maxAttempts - 1) return res;  // give up
    } catch (err) {
      if (attempt === maxAttempts - 1) throw err;
    }
    // Full jitter: random delay between 0 and exponential ceiling
    const ceiling = Math.min(1000 * Math.pow(2, attempt), 30_000);
    const delay = Math.random() * ceiling;
    await new Promise(r => setTimeout(r, delay));
  }
  // Unreachable
  throw new Error('Retry exhausted');
}
```

Delays: 0-1s, 0-2s, 0-4s, 0-8s, 0-16s, 0-30s (capped). Average
client retries at ~7.5s for the 4th attempt, spread over a wide
window. No thundering herd.

## When NOT to retry

- **4xx client errors** (400, 401, 403, 404, 422). The request is
  malformed; retrying won't help.
- **Idempotency-violating operations** (e.g. POST without an
  Idempotency-Key). See `idempotency-keys.md`.
- **Vendor explicitly says don't retry** (some return 429 with a
  `Retry-After` header that you should respect).
- **Time-sensitive operations** (live trading, urgent
  notifications). The cost of a delayed response is worse than
  the cost of a failed request.

## When to use circuit breaker

If the vendor is consistently failing, retrying every time wastes
your time + theirs. Use a circuit breaker (see
`circuit-breaker-pattern.md`) to short-circuit failed vendors for
a cooldown period.

## Verification
- **Test:** `test/retry.test.ts > exponential backoff with jitter`
  — verify delays are in [0, ceiling] range over 1000 iterations
- **Live:** Vendor's status page shows normal load during outages
  (no retry spike)

## Gotchas
- **Set a timeout per attempt** (5-10s). Don't let a slow request
  block a retry loop for 30 minutes.
- **Use `AbortController` to cancel pending requests on timeout.**
  Otherwise the in-flight request keeps running in the background.
- **Cap max attempts at 3-5.** More attempts = more wasted compute.
- **Log every retry** (with attempt #, delay, error). This is the
  data you need to debug vendor issues.
- **Full jitter vs decorrelated jitter:** Full jitter is
  `random(0, ceiling)`. Decorrelated jitter is
  `min(cap, random(base, prev * 3))`. Full jitter is simpler;
  decorrelated spreads better. For most cases, full jitter is
  fine.

## Related
- `circuit-breaker-pattern.md` (next step when retries fail too often)
- `idempotency-keys.md` (mandatory for retryable POSTs)
- AWS: https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
- Marc Brooker's post: https://brooker.co.za/blog/2015/03/21/backoff.html
