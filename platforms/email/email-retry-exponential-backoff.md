# email-retry-exponential-backoff

**Issue:** Implementing exponential backoff for failed email send retries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ESP rate limits and transient failures require smart retry strategies to avoid hammering APIs while ensuring delivery.

## Pattern / Solution
Exponential backoff formula: `delay = base * (2^attempt) + jitter`

```js
function getRetryDelay(attempt, baseMs = 1000, maxMs = 300000) {
  const exponential = baseMs * Math.pow(2, attempt);
  const jitter = Math.random() * 1000;
  return Math.min(exponential + jitter, maxMs);
}
// attempt 0: ~1s, 1: ~2s, 2: ~4s, 3: ~8s, 4: ~16s, ...
```

Retry rules:
- **Retry:** 429 (rate limit), 5xx server errors, connection timeouts.
- **Do not retry:** 4xx client errors (400, 401, 403), permanent bounce (invalid address).
- **Max retries:** 5-7 attempts over 72 hours for transient failures.

## Gotchas
- Jitter prevents thundering herd when many jobs fail simultaneously.
- 429 responses may include `Retry-After` header; use that delay if provided.
- Permanent bounces (hard bounces) must never be retried; suppress the address.
- Dead-letter after final retry; alert on-call if DLQ depth exceeds threshold.

## Related
- email-queue-architecture, bounce-handling-hard-soft, email-batch-sending
