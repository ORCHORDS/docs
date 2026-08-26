# Load Testing Cloudflare Workers with k6

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Worker handles order creation and KV-backed session lookups. After a traffic spike the team sees elevated p95 latency and sporadic 522 errors reported by Cloudflare Analytics. The deployment pipeline has unit and integration tests but no load tests, so there is no baseline to compare against and no automated gate to catch regressions before they reach production.

---

## Context

k6 (by Grafana Labs) is a TypeScript-native load testing tool that runs test scripts written in JavaScript/TypeScript outside the browser. It sends real HTTP requests to a deployed (or `wrangler dev`-served) Worker endpoint, measures response times and error rates, and can fail CI when thresholds are breached.

Cloudflare Workers are stateless compute at the edge, but backing services (D1, KV, R2, Queues) can become bottlenecks under load. k6 is used to find the saturation point before it affects production users.

Stack:
- `k6` v0.52+ (binary, not npm)
- TypeScript transpiled to k6-compatible JS via `k6-bundle` or `esbuild`
- Cloudflare Analytics Engine (for result cross-referencing)
- `wrangler` (for deploying and `wrangler dev`)

---

## Solution

### 1. Install k6

```bash
# macOS
brew install k6

# Linux
sudo apt-get install k6

# Docker
docker pull grafana/k6
```

### 2. Basic k6 script for a Workers endpoint

```typescript
// load-tests/orders.k6.ts
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate    = new Rate('error_rate');
const orderLatency = new Trend('order_latency_ms', true);

// Load profile: ramp up -> steady -> ramp down
export const options = {
  stages: [
    { duration: '30s', target: 50  },  // ramp up to 50 VUs
    { duration: '2m',  target: 50  },  // hold at 50 VUs
    { duration: '30s', target: 100 },  // ramp up to 100 VUs
    { duration: '2m',  target: 100 },  // hold at 100 VUs
    { duration: '30s', target: 0   },  // ramp down
  ],
  thresholds: {
    // p95 latency must stay under 300 ms
    'http_req_duration{status:200}': ['p(95)<300'],
    // custom latency metric
    order_latency_ms: ['p(95)<300', 'p(99)<500'],
    // error rate must stay below 1%
    error_rate: ['rate<0.01'],
    // fewer than 1% of requests fail HTTP checks
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL ?? 'https://orders.example.workers.dev';
const API_KEY  = <redacted-secret>  ?? '';

export default function (): void {
  const headers = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${API_KEY}`,
  };

  // --- Create order ---
  const payload = JSON.stringify({
    items: [{ sku: 'WIDGET-001', qty: 2 }],
  });

  const start    = Date.now();
  const createRes = http.post(`${BASE_URL}/orders`, payload, { headers });
  const elapsed  = Date.now() - start;

  orderLatency.add(elapsed);
  errorRate.add(createRes.status !== 201);

  check(createRes, {
    'create order status 201':    (r) => r.status === 201,
    'response has id':            (r) => (r.json() as any)?.id !== undefined,
    'content-type is json':       (r) => r.headers['Content-Type']?.includes('application/json') ?? false,
  });

  if (createRes.status === 201) {
    const { id } = createRes.json() as { id: number };

    // --- Fetch created order ---
    const getRes = http.get(`${BASE_URL}/orders/${id}`, { headers });
    check(getRes, {
      'get order status 200':      (r) => r.status === 200,
      'order id matches':          (r) => (r.json() as any)?.id === id,
    });
  }

  sleep(0.5); // think time between iterations
}
```

### 3. Ramping VU patterns

```typescript
// load-tests/ramp-patterns.k6.ts
export const options = {
  scenarios: {
    // Scenario A: steady ramp (baseline characterization)
    baseline: {
      executor: 'ramping-vus',
      stages: [
        { duration: '1m', target: 10 },
        { duration: '3m', target: 10 },
        { duration: '1m', target: 0  },
      ],
      gracefulRampDown: '30s',
    },

    // Scenario B: spike test (sudden traffic surge)
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 500,
      stages: [
        { duration: '10s', target: 10  },
        { duration: '5s',  target: 500 },  // spike
        { duration: '30s', target: 500 },
        { duration: '10s', target: 10  },
      ],
      startTime: '5m', // start after baseline completes
    },
  },
};
```

### 4. KV saturation test

```typescript
// load-tests/kv-saturation.k6.ts
import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const kvReadLatency  = new Trend('kv_read_latency_ms',  true);
const kvWriteLatency = new Trend('kv_write_latency_ms', true);

export const options = {
  vus: 200,
  duration: '2m',
  thresholds: {
    kv_read_latency_ms:  ['p(95)<50'],   // KV reads should be fast from edge
    kv_write_latency_ms: ['p(95)<150'],  // Writes go to central store
    http_req_failed:     ['rate<0.001'], // near-zero errors
  },
};

const BASE_URL = __ENV.BASE_URL ?? 'https://session.example.workers.dev';

export default function (): void {
  const sessionId = `sess_${Math.random().toString(36).slice(2)}`;

  // Write a session key via Worker endpoint that internally calls KV.put()
  const writeStart = Date.now();
  const writeRes = http.post(
    `${BASE_URL}/sessions`,
    JSON.stringify({ sessionId, userId: 123, expiresIn: 3600 }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  kvWriteLatency.add(Date.now() - writeStart);

  check(writeRes, { 'session created': (r) => r.status === 201 });

  // Read back via a Worker endpoint that calls KV.get()
  const readStart = Date.now();
  const readRes   = http.get(`${BASE_URL}/sessions/${sessionId}`);
  kvReadLatency.add(Date.now() - readStart);

  check(readRes, { 'session found': (r) => r.status === 200 });
}
```

### 5. D1 saturation test

```typescript
// load-tests/d1-saturation.k6.ts
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const d1WriteLatency = new Trend('d1_write_latency_ms', true);
const d1ReadLatency  = new Trend('d1_read_latency_ms',  true);
const writeErrors    = new Rate('d1_write_errors');

export const options = {
  stages: [
    { duration: '1m', target: 50  },
    { duration: '3m', target: 50  },
    { duration: '1m', target: 0   },
  ],
  thresholds: {
    // D1 is single-region; writes can be slower than KV
    d1_write_latency_ms: ['p(95)<600'],
    d1_read_latency_ms:  ['p(95)<200'],
    d1_write_errors:     ['rate<0.005'],
  },
};

const BASE_URL = __ENV.BASE_URL ?? 'https://orders.example.workers.dev';

export default function (): void {
  const ws = Date.now();
  const r  = http.post(
    `${BASE_URL}/orders`,
    JSON.stringify({ items: [{ sku: 'TEST', qty: 1 }] }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  d1WriteLatency.add(Date.now() - ws);
  writeErrors.add(r.status >= 500);
  check(r, { 'order created': (r) => r.status === 201 });

  if (r.status === 201) {
    const { id } = r.json() as { id: number };
    const rs = Date.now();
    const g  = http.get(`${BASE_URL}/orders/${id}`);
    d1ReadLatency.add(Date.now() - rs);
    check(g, { 'order fetched': (g) => g.status === 200 });
  }

  sleep(0.2);
}
```

### 6. Cross-referencing with Cloudflare Analytics Engine

After a k6 run, compare k6-measured latency with Cloudflare's own edge-side measurements:

```typescript
// scripts/compare-analytics.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN  = process.env.CF_API_TOKEN!;

async function queryAnalyticsEngine(since: string, until: string) {
  const query = `
    SELECT
      quantilesMerge(0.95)(durationMsQuantiles) AS p95_ms,
      quantilesMerge(0.99)(durationMsQuantiles) AS p99_ms,
      countMerge(requests)                      AS total_requests,
      sumMerge(errors)                          AS total_errors
    FROM workers_analytics
    WHERE timestamp BETWEEN '${since}' AND '${until}'
      AND scriptName = 'orders-worker'
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    },
  );

  return res.json();
}

(async () => {
  const since = new Date(Date.now() - 10 * 60 * 1000).toISOString();
  const until = new Date().toISOString();
  const data  = await queryAnalyticsEngine(since, until);
  console.log('Cloudflare edge analytics:', JSON.stringify(data, null, 2));
})();
```

### 7. CI integration

```yaml
# .github/workflows/load-test.yml
name: Load Test
on:
  workflow_dispatch:
    inputs:
      base_url:
        description: 'Worker URL to test'
        required: true
        default: 'https://orders.example.workers.dev'

jobs:
  k6-load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install k6
        run: |
          sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
          echo 'deb https://dl.k6.io/deb stable main' | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update && sudo apt-get install k6

      - name: Run load test
        run: |
          k6 run \
            --out json=results.json \
            --env BASE_URL=${{ github.event.inputs.base_url }} \
            --env API_KEY=${{ secrets.LOAD_TEST_API_KEY }} \
            load-tests/orders.k6.ts

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: k6-results
          path: results.json
```

---

## Implementation Details

- k6 uses a **goroutine-per-VU** model, not a thread-per-VU model, so 500 VUs is feasible on a standard CI runner without OOM issues.
- `ramping-arrival-rate` executor is preferred for production-realistic tests because it controls **requests per second**, not concurrent users. Use `ramping-vus` for characterizing concurrency limits.
- k6 `check()` does not halt execution on failure - it records the failure and increments the `http_req_failed` metric. Thresholds are evaluated at the end of the run.
- `__ENV.BASE_URL` passes environment variables from the CLI (`--env KEY=VALUE`) into the k6 script.
- The Analytics Engine SQL API accepts standard SQL against Cloudflare's telemetry data and is the authoritative source of edge-side latency (vs. k6's client-side measurement which includes network RTT).

---

## Anti-patterns

- **Running load tests against `wrangler dev` for performance benchmarking**: Local Miniflare does not replicate Cloudflare's edge network, V8 isolate recycling, or global PoP routing. Always run performance load tests against a deployed staging environment.
- **Using `sleep(0)` or no sleep**: Zero think time creates an artificial CPU-bound loop that does not resemble real user behavior and can saturate the load generator itself.
- **Ignoring the `wrangler tail` output during tests**: Tail logs reveal Worker errors (exceptions, D1 errors) that manifest as 500s but may not surface in k6 check failures if the error body is still valid JSON.
- **Setting thresholds too loose**: `p(95)<10000` is not a useful threshold. Start from your SLA (e.g., 300 ms p95) and tighten from there.
- **Load testing on shared production KV namespaces**: KV writes during load tests pollute production data. Use dedicated staging namespaces.

---

## Gotchas

- Cloudflare Workers have a **CPU time limit** (50 ms on the free plan, 30 s on paid) per request. A Worker that passes unit tests may timeout under real load if it does multiple sequential D1 queries. Batch with `db.batch()` and parallelize with `Promise.all()`.
- k6 TypeScript support requires transpilation via `k6-bundle` or `esbuild` before running - k6 does not natively run `.ts` files. Some k6 versions accept `--experimental-compat-mode=v2` for limited TS support.
- The `--out json` flag writes a JSONL file (one JSON object per line), not a single JSON array. Parse with `jq -s '.'` if you need an array.
- Cloudflare applies rate limiting at the account level. Very high RPS load tests from a single IP may trigger Cloudflare's bot protection before hitting Worker limits.
- The Analytics Engine SQL API has a 1-minute data delay. Wait at least 90 seconds after a k6 run before querying for results.

---

## Verification

```bash
# Dry run - check script syntax without sending requests
k6 run --dry-run load-tests/orders.k6.ts

# Quick smoke test (1 VU, 10 iterations)
k6 run --vus 1 --iterations 10 \
  --env BASE_URL=https://orders.example.workers.dev \
  load-tests/orders.k6.ts

# Full ramp test
k6 run \
  --out json=results.json \
  --env BASE_URL=https://orders.example.workers.dev \
  --env API_KEY=$LOAD_TEST_API_KEY \
  load-tests/orders.k6.ts

# Inspect p95 from results
jq -rs '[.[] | select(.type == "Point" and .metric == "http_req_duration")] | map(.data.value) | sort | .[length * 0.95 | floor]' results.json
```

---

## Related

- `documentation/categories/testing/workers-vitest-d1-fixtures.md`
- `documentation/categories/testing/workers-visual-regression-playwright-r2.md`
- `documentation/workers/d1-query-patterns.md`
- `documentation/workers/kv-caching-strategy.md`

---

## Sources

- https://k6.io/docs/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/observability/
- https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/
