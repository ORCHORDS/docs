# llm-rate-limit-handling

**Issue:** Hitting provider rate limits (RPM/TPM) causes request failures and unpredictable throughput
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Batch jobs or high-traffic services hit 429 errors from token-per-minute or request-per-minute limits. Naive retries amplify the problem by sending bursts on top of existing traffic.

## Pattern / Solution
Implement a token bucket or sliding window rate limiter on the client side, below provider limits. Parse `Retry-After` from 429 responses. Use a queue with concurrency control for batch workloads. Track both RPM and TPM — TPM is often the binding constraint for long-context work.

```python
from asyncio import Semaphore

sem = Semaphore(10)  # max 10 concurrent requests

async def rate_limited_call(prompt):
    async with sem:
        return await llm_client.complete(prompt)
```

For TPM limiting, count tokens before sending and pre-throttle using a sliding window counter.

## Gotchas
- Different tiers of the same provider have wildly different limits — check after every billing upgrade
- Limits are per-model, not per-account globally on some providers
- Headers like `x-ratelimit-remaining-tokens` let you proactively slow down before hitting 429

## Related
- llm-retry-patterns
- llm-batch-processing
- llm-cost-optimization
