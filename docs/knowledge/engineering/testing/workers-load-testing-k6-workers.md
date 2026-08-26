# Load Testing Cloudflare Workers with k6

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker handles spiky traffic — flash sales, cron-driven batch jobs, webhook fan-outs. Functional tests pass but you have no signal on how the Worker behaves at 500 concurrent requests. You need latency percentiles, error rates, and throughput numbers before promoting to production, not after a postmortem.

## Context

k6 is an open-source load testing tool written in Go with a JavaScript scripting API. Scripts define virtual users (VUs), ramping profiles, and pass/fail thresholds. k6 runs entirely outside the Worker — it hits your Worker's HTTP endpoint as a real HTTP client. This makes it suitable for both `wrangler dev --remote` (testing against a preview deployment) and a fully deployed Worker URL.

Key concepts:
- **VU (Virtual User)** — a single concurrent executor of the script.
- **Stage** — a time window with a target VU count; multiple stages define a ramp-up/soak/ramp-down profile.
- **Threshold** — a pass/fail assertion on a metric (e.g. `p(95)<200`).
- **Check** — an inline assertion counted as a metric (does not abort the test).

## Solution

```javascript
// k6/load-test-worker.js
// Run: k6 run --env BASE_URL=https://api.example.com k6/load-test-worker.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { randomItem, randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// --- Custom metrics ---
const errorRate = new Rate('worker_errors');
const queueEnqueueDuration = new Trend('queue_enqueue_duration_ms', true);

// --- Options ---
export const options = {
  stages: [
    { duration: '30s', target: 10 },   // ramp up
    { duration: '1m',  target: 50 },   // ramp to normal load
    { duration: '2m',  target: 50 },   // soak at normal load
    { duration: '30s', target: 200 },  // spike
    { duration: '1m',  target: 200 },  // hold spike
    { duration: '30s', target: 0 },    // ramp down
  ],
  thresholds: {
    // 95th-percentile latency under 250 ms at all times
    'http_req_duration{expected_response:true}': ['p(95)<250'],
    // Overall error rate below 0.5 %
    'worker_errors': ['rate<0.005'],
    // Queue enqueue calls (subset) also within budget
    'queue_enqueue_duration_ms': ['p(95)<300'],
    // At least 99 % of checks must pass
    'checks': ['rate>0.99'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8787';
const API_TOKEN = <redacted-secret> || 'test-token';

const PRODUCT_IDS = ['abc-123', 'def-456', 'ghi-789', 'jkl-012', 'mno-345'];

// --- Default scenario: mixed read/write traffic ---
export default function () {
  const headers = {
    Authorization: `Bearer ${API_TOKEN}`,
    'Content-Type': 'application/json',
    'X-Request-ID': `k6-${__VU}-${__ITER}`,
  };

  // 70 % read path
  if (Math.random() < 0.7) {
    const productId = randomItem(PRODUCT_IDS);
    const res = http.get(`${BASE_URL}/v1/products/${productId}`, { headers });

    const ok = check(res, {
      'GET product status 200': (r) => r.status === 200,
      'GET product has id field': (r) => {
        try { return JSON.parse(r.body).id === productId; }
        catch { return false; }
      },
      'GET product response time < 200ms': (r) => r.timings.duration < 200,
    });
    errorRate.add(!ok);
  } else {
    // 30 % write path — enqueue an order event
    const payload = JSON.stringify({
      productId: randomItem(PRODUCT_IDS),
      quantity: randomIntBetween(1, 10),
      customerId: `cust-${randomIntBetween(1, 1000)}`,
    });

    const start = Date.now();
    const res = http.post(`${BASE_URL}/v1/orders`, payload, { headers });
    queueEnqueueDuration.add(Date.now() - start);

    const ok = check(res, {
      'POST order status 202': (r) => r.status === 202,
      'POST order returns orderId': (r) => {
        try { return !!JSON.parse(r.body).orderId; }
        catch { return false; }
      },
    });
    errorRate.add(!ok);
  }

  sleep(randomIntBetween(1, 3));
}

// --- Queue consumer load test scenario ---
export function queueConsumerScenario() {
  // Flood the queue endpoint to back-pressure the consumer Worker
  for (let i = 0; i < 5; i++) {
    const res = http.post(
      `${BASE_URL}/v1/orders`,
      JSON.stringify({ productId: 'abc-123', quantity: 1, customerId: 'cust-flood' }),
      { headers: { Authorization: `Bearer ${API_TOKEN}`, 'Content-Type': 'application/json' } }
    );
    check(res, { 'queue flood accepted': (r) => r.status === 202 || r.status === 429 });
  }
  sleep(0.1);
}
```

```typescript
// scripts/correlate-k6-analytics.ts
// Fetch Workers Analytics Engine data for the same time window as the k6 run
// and print a side-by-side comparison.

interface AnalyticsResult {
  p50: number;
  p95: number;
  p99: number;
  errorRate: number;
  requestCount: number;
}

async function queryAnalyticsEngine(
  accountId: string,
  apiToken: string,
  workerName: string,
  from: string,
  to: string
): Promise<AnalyticsResult> {
  const query = `
    SELECT
      quantilesMerge(0.50)(latency_quantiles)[1] AS p50,
      quantilesMerge(0.95)(latency_quantiles)[1] AS p95,
      quantilesMerge(0.99)(latency_quantiles)[1] AS p99,
      sumMerge(errors) / sumMerge(requests) AS error_rate,
      sumMerge(requests) AS total_requests
    FROM workers_analytics
    WHERE worker_name = '${workerName}'
      AND timestamp >= '${from}'
      AND timestamp <= '${to}'
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    }
  );

  if (!res.ok) throw new Error(`Analytics Engine query failed: ${res.status}`);
  const { data } = await res.json<{ data: Array<Record<string, number>> }>();
  const row = data[0];

  return {
    p50: Math.round(row.p50),
    p95: Math.round(row.p95),
    p99: Math.round(row.p99),
    errorRate: row.error_rate,
    requestCount: row.total_requests,
  };
}

async function main() {
  const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
  const API_TOKEN  = process.env.CF_API_TOKEN!;
  const WORKER     = process.env.WORKER_NAME ?? 'catalogue-worker';
  // These are passed from the k6 run wrapper script
  const FROM = process.env.TEST_START_TIME!;
  const TO   = process.env.TEST_END_TIME!;

  const analytics = await queryAnalyticsEngine(ACCOUNT_ID, API_TOKEN, WORKER, FROM, TO);

  console.log('=== Workers Analytics Engine (same window) ===');
  console.log(`  Requests : ${analytics.requestCount}`);
  console.log(`  p50      : ${analytics.p50} ms`);
  console.log(`  p95      : ${analytics.p95} ms`);
  console.log(`  p99      : ${analytics.p99} ms`);
  console.log(`  Error %  : ${(analytics.errorRate * 100).toFixed(3)}%`);
}

main().catch(console.error);
```

## Implementation Details

**Running against `wrangler dev --remote`** — start wrangler in remote mode to hit a preview deployment of the real Worker with real KV, D1, and Queue bindings:

```bash
npx wrangler dev --remote --env preview &
WRANGLER_PID=$!
sleep 5  # allow cold start
TEST_START_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
k6 run --env BASE_URL=http://localhost:8787 --env API_TOKEN=$PREVIEW_TOKEN k6/load-test-worker.js
TEST_END_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
kill $WRANGLER_PID
```

**k6 Cloud vs local runner** — use the local runner for PR-level checks and k6 Cloud (`k6 cloud`) for scheduled capacity runs. k6 Cloud distributes load from multiple regions; local is single-origin. Set `ext.loadimpact.distribution` in the script options to specify regions.

**Queue consumer load** — Cloudflare Queues deliver batches; a Queue consumer Worker processes messages asynchronously. Flood the producer endpoint (as in `queueConsumerScenario`) and then poll a `/v1/queue/depth` diagnostic endpoint to measure lag. Chart queue depth vs enqueue rate to find the consumer throughput ceiling.

## Anti-patterns

- **Setting `vus` without stages** — a flat VU count ignores ramp-up, which hides cold-start latency spikes that users actually experience.
- **Assertions with hard-coded IDs from a test database** — load tests hit real preview deployments. Seed data must exist and be stable, or use data-driven VU scripts that pick from a known pool.
- **Ignoring `sleep()`** — removing think-time makes the test unrealistically aggressive. Real users pause between actions; open-loop tests without sleep can exhaust CPU on the k6 runner before the Worker.
- **Targeting production directly** — load tests should target preview or staging deployments. Target production only with explicit approval and reduced VU counts.

## Gotchas

- Workers have a **per-account request rate limit** in preview mode; sustained k6 runs can trigger 429s that look like Worker errors. Use `--remote` rate-limiting awareness and set appropriate thresholds.
- The k6 `jslib` import (`https://jslib.k6.io/...`) requires outbound network access from the k6 runner. In air-gapped CI, vendor the module locally.
- `http_req_duration` in k6 measures time from first byte sent to last byte received. Workers Analytics Engine measures CPU time. They will not match; expect k6 p95 to be 10–40 ms higher due to TLS and network overhead.
- k6 does not follow redirects by default. Set `redirects: 5` in the request params if your Worker redirects on auth flows.

## Verification

```bash
# Dry run with 1 VU, 10 s to validate the script
k6 run --vus 1 --duration 10s \
  --env BASE_URL=http://localhost:8787 \
  --env API_TOKEN=test-token \
  k6/load-test-worker.js

# Full ramp as defined in options
k6 run \
  --env BASE_URL=https://preview.example.com \
  --env API_TOKEN=$PREVIEW_TOKEN \
  --out json=k6-results.json \
  k6/load-test-worker.js

# Correlate with Workers Analytics
TEST_START_TIME=2026-08-24T10:00:00Z \
TEST_END_TIME=2026-08-24T10:07:00Z \
WORKER_NAME=catalogue-worker \
npx ts-node scripts/correlate-k6-analytics.ts
```

## Related

- `documentation/docs/policies/testing/workers-golden-path-test-suite.md`
- `documentation/docs/policies/testing/workers-mutation-testing-stryker.md`
- k6 docs: https://grafana.com/docs/k6/latest/
- Cloudflare Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Queues: https://developers.cloudflare.com/queues/

## Sources

- Grafana k6 — Getting Started (2025)
- Cloudflare Workers — Analytics Engine SQL API (2025)
- example.com internal runbook: load-testing-workers (2026-06)
