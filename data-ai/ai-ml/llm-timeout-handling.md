# llm-timeout-handling

**Issue:** LLM requests hang indefinitely under load, blocking threads and exhausting connection pools
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Under high concurrency or provider degradation, LLM API requests take 30-120 seconds or never complete. Without explicit timeouts, thread pools fill up and the entire service becomes unresponsive.

## Pattern / Solution
Set timeouts at two levels: connect timeout (5-10 s) and read timeout (60-120 s depending on expected output length). Use streaming to detect stalled streams via chunk-level timeouts. Implement a circuit breaker that opens after N consecutive timeouts.

```python
import httpx

client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0)
)

async def call_with_timeout(prompt):
    async with asyncio.timeout(100):  # hard ceiling
        return await client.post("/v1/chat/completions", json={"messages": [...]})
```

For streaming: track time of last chunk received and abort if it exceeds 10 s.

## Gotchas
- Read timeout must be longer than the expected generation time — a 30 s read timeout kills long completions legitimately
- Async frameworks need both the HTTP client timeout AND an outer asyncio timeout
- Log timeout events with full context (model, prompt length, attempt) for debugging provider SLA violations

## Related
- llm-retry-patterns
- llm-rate-limit-handling
- llm-async-patterns
