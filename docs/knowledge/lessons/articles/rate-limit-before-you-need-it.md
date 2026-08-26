# rate-limit-before-you-need-it

**Issue:** APIs without rate limits become attack vectors for abuse, accidental hammering, and runaway clients
**Date:** 2026-08-11
**Status:** documented

## What happened
A public API endpoint was launched without rate limiting because "we'll add it when we need it." A client deployed a polling loop with a one-second interval and no backoff. During a network blip, their retry logic produced a thundering herd that took the service down for 22 minutes. Adding rate limiting under an active incident required a hotfix deploy — which also required the database to be stable enough to write rate-limit counters. It was not.

## The lesson
Rate limiting must be in place before an API is public. Implement it at the gateway layer (not in application code) so it survives application failures. Define limits per client, per IP, and globally. Return 429 with a Retry-After header.

## Why it matters
Rate limiting prevents abuse, protects downstream services, and makes your SLAs enforceable. Retrofitting it during an incident is the worst possible time — you're fighting the fire and doing surgery simultaneously.

## How to apply
- [ ] Add rate limiting to the API gateway or load balancer before the first external client.
- [ ] Choose a limit strategy: fixed window, sliding window, or token bucket (token bucket is usually best).
- [ ] Set per-client, per-IP, and global limits independently.
- [ ] Return `429 Too Many Requests` with `Retry-After` and `X-RateLimit-*` headers.
- [ ] Test rate limit behavior in staging by running a load test that exceeds the limit.
- [ ] Alert when global limit is hit more than 1% of requests — it signals a client bug.

## Related
- `circuit-breaker-prevents-cascade-failure.md`
- `timeouts-everywhere-no-exceptions.md`
