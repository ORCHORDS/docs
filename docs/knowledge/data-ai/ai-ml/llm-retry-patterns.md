# llm-retry-patterns

**Issue:** Transient LLM API failures cause request loss without a consistent retry strategy
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LLM API calls fail with 429, 500, or 503 errors. Naive immediate retries hammer the API and worsen rate-limit situations. No retry means lost work on long pipelines.

## Pattern / Solution
Implement exponential backoff with jitter. Distinguish retryable errors (429, 500, 503, network timeout) from non-retryable ones (400 bad request, 401 auth). Cap total retry time. For streaming responses, restart from scratch — you cannot resume a partial stream.

```python
import time, random

def retry_llm(fn, max_attempts=4, base_delay=1.0):
    retryable = {429, 500, 502, 503, 504}
    for attempt in range(max_attempts):
        try:
            return fn()
        except APIError as e:
            if e.status_code not in retryable or attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(delay)
```

## Gotchas
- 429 responses often include a `Retry-After` header — respect it instead of using your own backoff
- Retrying idempotent reads is safe; retrying writes/actions may cause duplicates — use idempotency keys
- Add circuit breaker logic so a degraded provider does not block the entire pipeline

## Related
- llm-rate-limit-handling
- llm-timeout-handling
- llm-fallback-provider-rotation
