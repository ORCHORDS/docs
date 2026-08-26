# llm-api-integration-patterns

**Issue:** Patterns for integrating LLM APIs reliably into production applications
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Integrating LLM APIs requires handling async calls, retries, streaming, and provider differences uniformly.

## Pattern / Solution
```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMClient:
    def __init__(self, provider: str, api_key: str, base_url: str):
        self.client = httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"})

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def complete(self, messages: list, model: str, **kwargs) -> dict:
        resp = await self.client.post("/chat/completions", json={"model": model, "messages": messages, **kwargs})
        resp.raise_for_status()
        return resp.json()
```

## Gotchas
- Always set explicit timeouts; LLMs can hang for 60+ seconds
- Normalize response shapes across providers before returning to callers
- Log token usage per request for cost tracking

## Related
- `llm-provider-abstraction.md`
- `llm-retry-patterns.md`
