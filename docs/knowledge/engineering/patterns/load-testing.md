# load-testing

**Issue:** Load test before you ship — k6, wrk, Gatling
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a feature. It works for the 100 beta users. You go
to production. The first 10k users see 5xx errors. The D1
is overwhelmed. The Workers are at the subrequest cap. You
panic.

## Root cause
**Production traffic is not beta traffic.** Production has:
- Higher RPS
- More concurrent users
- More diverse data
- More edge cases

A feature that works at 100 RPS may break at 10k RPS.

**Source:** k6 docs:
https://k6.io/docs/

> "Load testing is the process of putting simulated demand
> on a system and measuring its response."

## The tools

### k6 (Grafana)
JavaScript-based load test. Easy to write, good for HTTP
load.
```js
// load-test.js
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 100 },  // ramp up to 100 RPS
    { duration: '1m', target: 1000 },  // ramp up to 1k RPS
    { duration: '5m', target: 1000 },  // hold at 1k RPS
    { duration: '30s', target: 0 },    // ramp down
  ],
};

export default function () {
  const res = http.get('https://example.com/api/users/u_123');
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 200ms': (r) => r.timings.duration < 200,
  });
}
```

### wrk (GitHub)
C-based, super fast. Good for measuring raw throughput.
```bash
wrk -t12 -c400 -d30s https://example.com/api/users/u_123
# 12 threads, 400 connections, 30 seconds
```

### Apache Bench (ab)
Simple, included with most Linux distros.
```bash
ab -n 1000 -c 100 https://example.com/api/users/u_123
# 1000 requests, 100 concurrent
```

### Vegeta (Go)
Good for rate-limited scenarios + complex flows.
```bash
echo "GET https://example.com/api/users/u_123" | vegeta attack -rate=1000 -duration=30s | tee results.bin | vegeta report
```

## What to test

### 1. The critical path
- **Homepage load:** First impression, must be fast
- **Login:** Most common user action
- **Create content:** The core value proposition
- **Search:** High-volume, may hit rate limits

### 2. The database-bound paths
- **List endpoints:** `GET /api/posts` may be slow
- **Aggregation queries:** `GET /api/stats` may time out

### 3. The vendor-bound paths
- **Payment:** Stripe may rate-limit you
- **Email:** SendGrid may throttle
- **AI inference:** OpenAI has rate limits

### 4. The rate-limit boundaries
- **Per-user limit:** What happens at exactly N req/sec?
- **Per-tenant limit:** A noisy tenant shouldn't starve others
- **Per-IP limit:** What's the bot threshold?

## The load test scenarios

### Smoke test
- 1-10 RPS, 1 minute
- Verifies the test setup works
- Catches basic issues

### Stress test
- 100-1000 RPS, 5-10 minutes
- Verifies the system handles expected load
- Catches N+1 queries, slow paths

### Spike test
- 1 RPS → 1000 RPS instantly
- Verifies the system handles traffic spikes
- Catches cache misses, cold starts

### Soak test
- Expected RPS, 1-24 hours
- Verifies the system doesn't degrade over time
- Catches memory leaks, connection leaks

### Breakpoint test
- Keep increasing RPS until the system breaks
- Verifies the upper limit
- Catches capacity planning issues

## The metrics to track

- **Throughput:** RPS the system handles
- **Latency:** p50, p95, p99 response time
- **Error rate:** % of requests that fail
- **Resource usage:** CPU, memory, DB queries
- **Saturation:** How "full" the system is

## The "production parity" environment

For meaningful load tests, the test environment must match
production:
- **Same data volume:** 1M+ rows in the test DB
- **Same data shape:** Real-shaped data, not synthetic
- **Same traffic shape:** Real user flows, not random GETs
- **Same infra:** Same CF region, same DB tier

A load test on a 100-row SQLite that says "10k RPS works" is
a lie.

## Verification
- **Test:** Load test in CI for every deploy (smoke + stress)
- **Live:** Pre-prod load test (spike + breakpoint) for every
  major release
- **Audit:** Quarterly load test (soak) for capacity planning

## Gotchas
- **The test environment is not production.** A test that
  passes on a 1k-row DB may fail on a 1M-row DB. Always
  load test with production-scale data.
- **The test is not the production code path.** A synthetic
  GET to `/api/users/u_123` is not the same as a real user
  flow (login, navigate, search, click). Test the real
  flows.
- **k6 can lie.** A test that "passes" with all 200s may have
  50% errors on the third-party calls. Check the response
  body, not just the status.
- **The test itself is a load source.** A load test from 1
  source IP may trip your WAF. Use a load test profile that
  looks like real users (different IPs, different UAs).
- **The "max RPS" is not the answer.** The right question is
  "at what RPS does p99 latency exceed 500ms?" That's your
  real capacity.

## Related
- `scaling-cf-workers.md`
- `error-budget-slo.md` (SLOs guide load test targets)
- `feature-rollout-strategies.md`
- k6: https://k6.io/
- wrk: https://github.com/wg/wrk
