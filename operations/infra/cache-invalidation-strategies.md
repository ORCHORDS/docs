# cache-invalidation-strategies

**Issue:** Keeping caches consistent with the source of truth without full cache flushes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stale data served from cache after DB updates. Full cache flushes on every deploy cause thundering herd. Cache and database drifting silently.

## Pattern / Solution
Cache-aside (lazy loading):
```python
def get_user(user_id: str) -> dict:
    cache_key = f"user:{user_id}"
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    user = db.query("SELECT * FROM users WHERE id = %s", user_id)
    redis.setex(cache_key, 300, json.dumps(user))  # TTL 5 min
    return user

def update_user(user_id: str, data: dict):
    db.execute("UPDATE users SET ... WHERE id = %s", user_id)
    redis.delete(f"user:{user_id}")   # invalidate, not update
```

Write-through (update cache on write):
```python
def update_user(user_id: str, data: dict):
    db.execute("UPDATE users ...", user_id)
    redis.setex(f"user:{user_id}", 300, json.dumps(data))
    # Risk: write failure leaves cache stale — use transactions or accept eventual consistency
```

Tag-based invalidation (invalidate groups of keys):
```python
# Store keys in a set per entity
def cache_product(product_id, category_id, data):
    key = f"product:{product_id}"
    redis.setex(key, 600, json.dumps(data))
    redis.sadd(f"category:{category_id}:products", key)

def invalidate_category(category_id):
    keys = redis.smembers(f"category:{category_id}:products")
    if keys:
        redis.delete(*keys)
    redis.delete(f"category:{category_id}:products")
```

Versioned cache keys (deploy invalidation):
```python
VERSION = os.environ.get("CACHE_VERSION", "v1")

def cache_key(entity: str, id: str) -> str:
    return f"{VERSION}:{entity}:{id}"
```

## Gotchas
- Delete-on-write (cache-aside) causes thundering herd if many readers hit DB simultaneously — add jitter to TTL
- Write-through with transaction: if DB write succeeds but cache write fails, reads serve stale data for up to TTL
- Redis `KEYS` for bulk invalidation is O(N) and blocks — use `SCAN` with pattern matching instead
- Cache stampede prevention: use Redis `SET NX EX` mutex or Lua script to prevent parallel DB fetches on cold key

## Related
- `aws-elasticache-redis.md`
- `redis-eviction-policies.md`
- `cdn-origin-shield-patterns.md`
