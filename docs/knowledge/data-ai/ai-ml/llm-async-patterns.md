# llm-async-patterns

**Issue:** Synchronous LLM call patterns block threads and scale poorly under concurrent load
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A FastAPI or Node.js service makes synchronous LLM calls. Under load, threads block waiting for responses, memory grows, and p99 latency spikes. The service handles far fewer concurrent users than expected.

## Pattern / Solution
Use async LLM clients (httpx async, openai async client). Fire multiple independent LLM calls concurrently with `asyncio.gather`. For dependent chains, use async generators for streaming. Use a task queue (Celery, ARQ, BullMQ) for long-running or background LLM jobs.

```python
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI()

async def parallel_calls(prompts: list[str]):
    tasks = [client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": p}]
    ) for p in prompts]
    return await asyncio.gather(*tasks)
```

## Gotchas
- `asyncio.gather` with many requests still hits rate limits — add semaphore or rate limiter
- Mixing sync and async code (e.g., calling sync SDK in async context) blocks the event loop; use `asyncio.to_thread`
- Streaming async generators must be fully consumed or explicitly closed to avoid resource leaks

## Related
- llm-streaming-responses
- llm-batch-processing
- llm-rate-limit-handling
