# rate-limiter-design

**Issue:** Implementing a fair, accurate, and distributed rate limiter from scratch is error-prone
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A naive fixed-window counter allows double the intended rate at window boundaries (the boundary burst problem).

## Pattern / Solution
Use a sliding window log or sliding window counter for precision. Use a token bucket for burst tolerance. For distributed rate limiting, use Redis with atomic Lua scripts or the INCR and EXPIRE pattern. Return rate limit headers (X-RateLimit-Remaining, Retry-After).

## Gotchas
Redis cluster sharding splits the key space and requires ensuring the rate limit key lands on a single shard. Clock skew between nodes affects window boundaries in distributed sliding window implementations.

## Related
rate-limiting-architecture, throttling-patterns, api-security-architecture
