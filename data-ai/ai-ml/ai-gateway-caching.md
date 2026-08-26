# ai-gateway-caching

**Issue:** Caching LLM responses at the gateway level to reduce cost and latency
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Identical or near-identical prompts are sent repeatedly, wasting tokens and adding latency.

## Pattern / Solution
```python
# Exact match caching (Redis)
import hashlib, redis, json

cache = redis.Redis()

def cache_key(model: str, messages: list) -> str:
    payload = json.dumps({"model": model, "messages": messages}, sort_keys=True)
    return f"llm:{hashlib.sha256(payload.encode()).hexdigest()}"

async def cached_llm(model: str, messages: list, ttl: int = 3600) -> str:
    key = cache_key(model, messages)
    if cached := cache.get(key):
        return json.loads(cached)
    result = await llm_call(model, messages)
    cache.setex(key, ttl, json.dumps(result))
    return result
```
Use Cloudflare AI Gateway or Portkey for managed caching with semantic match.

## Gotchas
- Exact match caching only helps for truly repeated prompts
- Semantic caching requires embedding similarity check — see `semantic-caching-patterns.md`
- Cache invalidation on prompt changes is a common footgun

## Related
- `semantic-caching-patterns.md`
- `ai-gateway-rate-limiting.md`
