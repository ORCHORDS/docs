# ai-gateway-rate-limiting

**Issue:** Rate limiting LLM API calls at the gateway to prevent runaway costs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A bug or abuse pattern can exhaust monthly LLM budget in hours without rate limiting.

## Pattern / Solution
```python
from redis import Redis
import time

class TokenBucketLimiter:
    def __init__(self, redis: Redis, key: str, rate: int, capacity: int):
        self.redis = redis
        self.key = key
        self.rate = rate  # tokens/second
        self.capacity = capacity

    def consume(self, tokens: int = 1) -> bool:
        pipe = self.redis.pipeline()
        now = time.time()
        pipe.hgetall(self.key)
        pipe.expire(self.key, 3600)
        result, _ = pipe.execute()
        current = float(result.get(b"tokens", self.capacity))
        last = float(result.get(b"last_refill", now))
        refill = min(self.capacity, current + (now - last) * self.rate)
        if refill >= tokens:
            self.redis.hset(self.key, mapping={"tokens": refill - tokens, "last_refill": now})
            return True
        return False
```

## Gotchas
- Apply limits per user AND per API key to prevent both abuse and runaway jobs
- Return 429 with `Retry-After` header, not opaque errors
- Separate rate limits for cheap vs. expensive model tiers

## Related
- `ai-gateway-caching.md`
- `llm-rate-limit-handling.md`
