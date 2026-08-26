# API Rate Limiting Algorithms and Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your API has no rate limiting — a single misbehaving client can
overwhelm the service, degrading performance for everyone. Or you have
basic rate limiting (fixed window), but clients see unfair rejections at
window boundaries while abusive traffic slips through in bursts. Your
distributed API gateway does not share rate limit state, so limits are
inconsistent across instances. You cannot differentiate between
free-tier and premium API consumers.

## Context

Rate limiting controls how many requests a client can make to an API
within a time period. The choice of algorithm determines how limits
behave at boundaries, during bursts, and under sustained load. In 2026,
the standard practice is multi-layer rate limiting: global limits
protect shared infrastructure, per-IP limits prevent anonymous abuse,
per-user/key limits ensure fair sharing, and per-endpoint limits protect
expensive operations. Rate limiting state is typically stored in Redis
or a similar shared store for consistency across distributed gateway
instances. API gateways (Kong, APISIX, Envoy) and platforms (Cloudflare,
AWS API Gateway) provide built-in rate limiting with configurable
algorithms.

## Algorithm comparison

| Algorithm | Burst handling | Memory | Accuracy | Complexity |
|---|---|---|---|---|
| **Fixed window** | Allows 2× burst at boundary | Low (1 counter) | Low | Simple |
| **Sliding window log** | Exact, no bursts | High (per-request log) | Exact | Medium |
| **Sliding window counter** | Near-exact, minimal burst | Low (2 counters) | High | Medium |
| **Token bucket** | Controlled bursts allowed | Low (tokens + timestamp) | High | Medium |
| **Leaky bucket** | No bursts (queue-based) | Low (queue + rate) | High | Medium |

## Fixed window

```
Window: 60 seconds, Limit: 100 requests

Timeline:   |-------- window 1 --------|-------- window 2 --------|
Requests:   ||||||||| (50)              ||||||||||||||||||| (100)
                                        ^ window boundary

Problem: 50 requests at end of window 1 + 100 at start of window 2
= 150 requests in 60 seconds (exceeds intended 100/min limit)
```

```python
def fixed_window(key, limit, window_seconds):
    current_window = int(time.time() / window_seconds)
    cache_key = f"{key}:{current_window}"
    count = redis.incr(cache_key)
    if count == 1:
        redis.expire(cache_key, window_seconds)
    return count <= limit
```

## Sliding window counter

```
Combines two fixed windows with weighted overlap.
Current window weight = elapsed% of current window
Previous window weight = remaining% of current window

Example: 70% through current window
  Previous window: 80 requests × 0.30 = 24
  Current window:  50 requests × 1.00 = 50
  Estimated count: 74 (under 100 limit → allow)
```

```python
def sliding_window(key, limit, window_seconds):
    now = time.time()
    current_window = int(now / window_seconds)
    elapsed = (now % window_seconds) / window_seconds

    prev_count = int(redis.get(f"{key}:{current_window - 1}") or 0)
    curr_count = int(redis.get(f"{key}:{current_window}") or 0)

    weighted = prev_count * (1 - elapsed) + curr_count
    if weighted >= limit:
        return False

    redis.incr(f"{key}:{current_window}")
    redis.expire(f"{key}:{current_window}", window_seconds * 2)
    return True
```

## Token bucket

```
Bucket capacity: 100 tokens
Refill rate: 10 tokens/second
Each request consumes 1 token

Timeline:   |--burst--|--steady--|--burst--|
Tokens:     100→0     0→50→50    50→0
            (allowed) (10/s)     (allowed)

Allows controlled bursts up to bucket capacity while enforcing
a long-term average rate equal to the refill rate.
```

```python
def token_bucket(key, capacity, refill_rate):
    now = time.time()
    bucket = redis.hgetall(key)

    tokens = float(bucket.get("tokens", capacity))
    last_refill = float(bucket.get("last_refill", now))

    elapsed = now - last_refill
    tokens = min(capacity, tokens + elapsed * refill_rate)

    if tokens < 1:
        return False

    redis.hset(key, mapping={
        "tokens": tokens - 1,
        "last_refill": now,
    })
    redis.expire(key, int(capacity / refill_rate) + 1)
    return True
```

## Leaky bucket

```
Queue-based: requests enter a queue and are processed at a fixed rate.
If the queue is full, new requests are rejected.

Bucket size: 10 (queue depth)
Leak rate: 5 requests/second

Incoming:  ||||||||||||||||| (burst of 15)
Queue:     [1][2][3][4][5][6][7][8][9][10] → full
Rejected:  [11][12][13][14][15]
Processed: |----|----|----|----| (steady 5/s)
```

## Multi-layer rate limiting

```
Layer 1: Global        → 10,000 req/s total (protect infrastructure)
Layer 2: Per-IP        → 100 req/min (prevent anonymous abuse)
Layer 3: Per-API-key   → Tier-based (fair sharing)
Layer 4: Per-endpoint  → /search: 20/min, /export: 5/min
```

| Tier | Requests/min | Burst capacity | Concurrent |
|---|---|---|---|
| Free | 60 | 10 | 5 |
| Pro | 600 | 100 | 20 |
| Enterprise | 6,000 | 1,000 | 100 |

## Response headers

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1692230400

# IETF draft standard headers (RateLimit-*)
RateLimit-Limit: 100
RateLimit-Remaining: 0
RateLimit-Reset: 30
```

## Anti-patterns

- **No rate limiting** — an unprotected API is one misbehaving client
  away from a denial-of-service. Every public API needs at least
  per-IP rate limiting.
- **Fixed window only** — the boundary burst problem allows 2× the
  intended rate. Use sliding window counter or token bucket for
  accurate limiting.
- **Rate limiting after processing** — checking rate limits after
  the request has already consumed compute. Rate limiting must happen
  at the edge (gateway, load balancer) before requests reach services.
- **Silent rejection** — returning 429 without `Retry-After` or
  rate limit headers. Clients cannot implement proper backoff without
  knowing when they can retry or how many requests remain.

## Gotchas

- **Distributed state consistency** — rate limit counters in Redis
  must be shared across all gateway instances. Without shared state,
  each instance enforces limits independently, allowing N× the
  intended rate (where N is the number of instances).
- **Clock skew in sliding windows** — sliding window algorithms
  depend on consistent timestamps. Use Redis server time (`TIME`
  command) instead of application server clocks to avoid skew.
- **Rate limit key design** — using only IP address penalizes
  users behind NAT or corporate proxies. Combine IP with API key
  or authenticated user ID for fairer limiting.
- **Cost of exact algorithms** — sliding window log stores every
  request timestamp, consuming O(n) memory per client. Use the
  sliding window counter (O(1) memory) for high-volume APIs.

## Verification

- Every public API endpoint has rate limiting configured.
- Rate limit headers (`RateLimit-*`, `Retry-After`) are returned
  on every response, not just 429s.
- Rate limit state is shared across all gateway instances (Redis).
- Different API tiers have appropriate limits.
- Per-endpoint limits protect expensive operations.
- Rate limiting is tested under load with concurrent clients.

## Related

- `documentation/docs/policies/cloudflare/rate-limiting-dos-protection.md`
- `documentation/docs/policies/security/ddos-mitigation-strategies.md`
- `documentation/docs/policies/patterns/api-design-patterns.md`

## Source URLs (verified 2026-08-16)

- 10 API Rate Limiting Best Practices (2026) — https://zuplo.com/learning-center/10-best-practices-for-api-rate-limiting-in-2026
- Advanced API Rate Limiting: Sliding Windows, Token Buckets — https://dev.to/young_gao/advanced-api-rate-limiting-sliding-windows-token-buckets-and-distributed-counters-5afa
- Rate Limiting Algorithms Comparison — https://blog.arcjet.com/rate-limiting-algorithms-token-bucket-vs-sliding-window-vs-fixed-window/
- API Gateway Rate Limiting Strategies — https://medium.com/@udarasenarath/api-gateway-rate-limiting-strategies-building-reliable-and-protected-apis-16f0e51f26c2
