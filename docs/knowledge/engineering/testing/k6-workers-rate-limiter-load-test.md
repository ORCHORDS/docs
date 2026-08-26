# k6 Workers Rate Limiter Load Test Threshold Validation
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You have implemented a rate limiter in a Cloudflare Worker (backed by Durable Objects or KV) and
need to prove under load that: (1) requests within the allowed rate succeed, (2) excess requests
receive HTTP 429 with the correct `Retry-After` header, and (3) the limiter resets correctly after
the window expires. A unit test can validate the logic in isolation, but a k6 load test validates
the end-to-end behaviour at real concurrency levels.

## Context
Rate limiters are inherently concurrent. The only way to trust them is to hammer the Worker from
multiple virtual users simultaneously and assert on the distribution of 200 vs 429 responses via
k6 thresholds. k6's `check` + `Counter` metrics let you bucket responses by status and fail the
run if the ratio is outside the expected envelope. Combining `ramping-arrival-rate` executors with
per-VU tags gives fine-grained visibility into which VU hit the limit first.

## Worker Implementation Under Test
```typescript
// src/rate-limiter.ts – Durable Object
import { DurableObject } from 'cloudflare:workers';

interface State { count: number; windowStart: number }

export class RateLimiter extends DurableObject {
  private readonly LIMIT = 10;
  private readonly WINDOW_MS = 60_000;

  async check(clientId: string): Promise<{ allowed: boolean; retryAfter?: number }> {
    const stored = await this.ctx.storage.get<State>(clientId);
    const now = Date.now();

    if (!stored || now - stored.windowStart > this.WINDOW_MS) {
      await this.ctx.storage.put<State>(clientId, { count: 1, windowStart: now });
      return { allowed: true };
    }

    if (stored.count < this.LIMIT) {
      await this.ctx.storage.put<State>(clientId, { ...stored, count: stored.count + 1 });
      return { allowed: true };
    }

    const retryAfter = Math.ceil((this.WINDOW_MS - (now - stored.windowStart)) / 1000);
    return { allowed: false, retryAfter };
  }
}

// src/index.ts
export { RateLimiter } from './rate-limiter';

export default {
  async fetch(req: Request, env: { RATE_LIMITER: DurableObjectNamespace }): Promise<Response> {
    const clientId = req.headers.get('x-client-id') ?? req.headers.get('cf-connecting-ip') ?? 'anonymous';
    const shardId = env.RATE_LIMITER.idFromName('global');
    const limiter = env.RATE_LIMITER.get(shardId);

    const result: { allowed: boolean; retryAfter?: number } = await limiter.check(clientId);
    if (!result.allowed) {
      return new Response('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(result.retryAfter ?? 60) },
      });
    }

    return new Response('OK', { status: 200 });
  },
};
```

## k6 Load Test Script
`k6/rate-limiter-load-test.js`:
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate } from 'k6/metrics';

// Custom metrics
const successCount = new Counter('rate_allowed');
const throttledCount = new Counter('rate_throttled');
const successRate = new Rate('rate_allowed_rate');

const BASE_URL = __ENV.WORKER_URL ?? 'http://localhost:8787';
/** Each VU gets a stable client ID so the limiter tracks per-client quotas. */
const clientId = () => `client-${__VU}`;

export const options = {
  scenarios: {
    // Phase 1 – warm up: 5 VUs, each sending exactly 10 requests (at the limit).
    // All should succeed.
    within_limit: {
      executor: 'per-vu-iterations',
      vus: 5,
      iterations: 10,
      maxDuration: '30s',
      tags: { scenario: 'within_limit' },
    },
    // Phase 2 – breach: same 5 VUs send 5 MORE requests (over the limit).
    // All should be throttled.
    over_limit: {
      executor: 'per-vu-iterations',
      vus: 5,
      iterations: 5,
      maxDuration: '30s',
      startTime: '35s',   // after within_limit window
      tags: { scenario: 'over_limit' },
    },
  },
  thresholds: {
    // All within-limit requests must succeed
    'rate_allowed{scenario:within_limit}': ['count>=50'],
    // All over-limit requests must be throttled
    'rate_throttled{scenario:over_limit}': ['count>=25'],
    // Overall p95 latency must stay under 300 ms
    'http_req_duration': ['p(95)<300'],
    // No unexpected errors
    'http_req_failed': ['rate<0.01'],
  },
};

export default function () {
  const res = http.get(BASE_URL, {
    headers: { 'x-client-id': clientId() },
    tags: { scenario: __ENV.K6_SCENARIO_NAME ?? 'unknown' },
  });

  const allowed = check(res, {
    'status is 200': (r) => r.status === 200,
    'status is 429': (r) => r.status === 429,
    '429 has Retry-After header': (r) =>
      r.status !== 429 || (r.headers['Retry-After'] !== undefined && parseInt(r.headers['Retry-After']) > 0),
  });

  if (res.status === 200) {
    successCount.add(1);
    successRate.add(true);
  } else if (res.status === 429) {
    throttledCount.add(1);
    successRate.add(false);
  }
}
```

## CI Integration
`.github/workflows/rate-limiter-load-test.yml`:
```yaml
name: Rate Limiter Load Test

on:
  pull_request:
    paths:
      - 'src/rate-limiter.ts'
      - 'k6/rate-limiter-load-test.js'

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Wrangler
        run: npm ci

      - name: Start Worker (background)
        run: npx wrangler dev --local --port 8787 &
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Wait for Worker to be ready
        run: |
          for i in $(seq 1 20); do
            curl -sf http://localhost:8787 && break
            sleep 1
          done

      - name: Run k6 load test
        uses: grafana/k6-action@v0.3.1
        with:
          filename: k6/rate-limiter-load-test.js
        env:
          WORKER_URL: http://localhost:8787
          K6_OUT: json=k6-results.json

      - name: Upload k6 results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: k6-results
          path: k6-results.json
```

## Interpreting Results
Key columns in the k6 summary to check:

| Metric | Expected |
|---|---|
| `rate_allowed{scenario:within_limit}` count | ≥ 50 (5 VUs × 10 requests) |
| `rate_throttled{scenario:over_limit}` count | ≥ 25 (5 VUs × 5 requests) |
| `http_req_duration` p95 | < 300 ms |
| `http_req_failed` rate | < 1 % |

If `rate_allowed` count < 50 in `within_limit`, the limiter is rejecting requests prematurely
(off-by-one in the window boundary or counter initialisation).

## Anti-patterns
- **Using a single shared `x-client-id` across all VUs** – every VU competes for the same bucket,
  making the within-limit and over-limit counts unpredictable. Use per-VU IDs.
- **Running within-limit and over-limit phases in the same time window** – the DO counter carries
  over; stagger phases with `startTime` so the window resets between them, or use distinct
  `x-client-id` prefixes per phase.
- **Asserting HTTP status with `check` only** – `check` failures don't abort the run; always back
  them with a threshold on a `Counter` metric that will fail the k6 exit code.
- **Omitting `Retry-After` header validation** – a 429 without a `Retry-After` value breaks
  well-behaved API clients that back off automatically.

## Gotchas
- Durable Objects in local `wrangler dev` mode are in-memory; if `wrangler dev` restarts between
  phases, the counter resets. Use `reuseExistingServer` or pin the wrangler process.
- k6's `per-vu-iterations` executor does not guarantee all VUs start at the exact same millisecond;
  use `ramping-arrival-rate` if you need a precise burst at T=0.
- The DO write-on-every-request pattern is expensive; in production you would use Cloudflare's
  native Rate Limiting API (`env.RATE_LIMITER.limit()`), but that requires a paid plan and is not
  testable with `wrangler dev --local` as of 2025.

## Verification
```bash
# Quick smoke test locally
WORKER_URL=http://localhost:8787 k6 run k6/rate-limiter-load-test.js --vus 5 --duration 30s

# Full dual-phase test (CI equivalent)
WORKER_URL=http://localhost:8787 k6 run k6/rate-limiter-load-test.js
echo "Exit code: $?"   # 0 = all thresholds passed
```

## Related
- `k6-load-testing-cloudflare-workers-api.md`
- `k6-workers-auth-bearer-token-load-test.md`
- `durable-objects-storage-snapshot-testing.md`
- `rate-limit-testing-strategies.md`
- `chaos-engineering-cloudflare-workers.md`

## Sources
- https://grafana.com/docs/k6/latest/using-k6/thresholds/
- https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/per-vu-iterations/
- https://developers.cloudflare.com/durable-objects/api/storage-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
