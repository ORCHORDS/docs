# k6 Workers D1 Write Throughput Load Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

D1 is a SQLite-based database with per-database write concurrency limits. A Workers API that
accepts user-generated content can hit D1's serialised write bottleneck under burst traffic,
resulting in `SQLITE_BUSY` errors (HTTP 500 from the Worker) or elevated P99 latency that
doesn't appear in unit or integration tests. k6 load tests targeting the write path reveal the
exact request rate at which the Worker starts shedding requests and whether the retry/backoff
logic in the Worker holds up under real concurrency.

## Context

The example project platform's `apps/content-worker` persists articles, comments, and reactions to D1
(`example project_DB`). Under normal traffic the write rate is low, but marketing campaigns cause write
bursts. D1's current limit is one write transaction in-flight per database at a time; reads
are concurrent. This article shows how to structure k6 scenarios to measure:

1. Maximum sustainable write throughput (articles per second)
2. P95/P99 latency under steady-state vs. spike load
3. Error rate threshold beyond which the Worker's retry budget is exhausted

---

## k6 Script: Baseline Write Throughput

```javascript
// k6/d1-write-throughput.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";
import { randomString } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

const writeErrors   = new Rate("d1_write_errors");
const writeLatency  = new Trend("d1_write_latency_ms", true);
const writesTotal   = new Counter("d1_writes_total");
const busyErrors    = new Counter("d1_sqlite_busy_errors");

const BASE_URL = __ENV.WORKER_URL || "https://content.example project.example.com";
const API_TOKEN = <redacted-secret>  || "load-test-token";

export const options = {
  scenarios: {
    // Ramp up to find the saturation point
    ramp_writes: {
      executor: "ramping-arrival-rate",
      startRate: 10,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 200,
      stages: [
        { duration: "30s", target: 10  },   // warm-up
        { duration: "60s", target: 50  },   // ramp to moderate load
        { duration: "60s", target: 100 },   // push toward saturation
        { duration: "30s", target: 10  },   // cool-down
      ],
    },
  },
  thresholds: {
    d1_write_errors:     ["rate < 0.02"],          // < 2% error rate
    d1_write_latency_ms: ["p(95) < 1500", "p(99) < 3000"],
    http_req_duration:   ["p(95) < 2000"],
  },
};

export default function () {
  const payload = JSON.stringify({
    title: `Load Test Article ${randomString(8)}`,
    body:  `Body content ${randomString(64)}`,
    tags:  ["k6", "load-test"],
  });

  const start = Date.now();
  const res = http.post(`${BASE_URL}/v1/articles`, payload, {
    headers: {
      "Content-Type":  "application/json",
      "Authorization": `Bearer ${API_TOKEN}`,
    },
    timeout: "10s",
  });
  const elapsed = Date.now() - start;

  writeLatency.add(elapsed);
  writesTotal.add(1);

  const ok = check(res, {
    "status is 201": (r) => r.status === 201,
    "has article id": (r) => {
      try { return !!JSON.parse(r.body).id; } catch { return false; }
    },
  });

  if (!ok) {
    writeErrors.add(1);
    // Detect SQLITE_BUSY surfacing as 500
    if (res.status === 500 && res.body?.includes("SQLITE_BUSY")) {
      busyErrors.add(1);
    }
  }

  sleep(Math.random() * 0.2); // jitter 0–200 ms
}
```

---

## k6 Script: Spike Write Burst

```javascript
// k6/d1-write-spike.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";
import { randomString } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

const errorRate = new Rate("spike_errors");
const BASE_URL  = __ENV.WORKER_URL || "https://content.example project.example.com";

export const options = {
  scenarios: {
    spike: {
      executor: "constant-arrival-rate",
      rate: 200,
      timeUnit: "1s",
      duration: "20s",
      preAllocatedVUs: 300,
      maxVUs: 500,
    },
  },
  thresholds: {
    spike_errors:    ["rate < 0.10"],          // tolerate up to 10% during spike
    http_req_duration: ["p(99) < 5000"],
  },
};

export default function () {
  const res = http.post(
    `${BASE_URL}/v1/comments`,
    JSON.stringify({ articleId: "fixture-article-001", body: randomString(120) }),
    { headers: { "Content-Type": "application/json" }, timeout: "15s" }
  );
  errorRate.add(res.status >= 500 ? 1 : 0);
  check(res, { "not 500": (r) => r.status !== 500 });
}
```

---

## k6 Script: Read/Write Mixed Workload

```javascript
// k6/d1-mixed-workload.js
import http from "k6/http";
import { check, group, sleep } from "k6";
import { randomIntBetween } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

const BASE_URL = __ENV.WORKER_URL || "https://content.example project.example.com";

export const options = {
  scenarios: {
    readers: {
      executor: "constant-vus",
      vus: 80,
      duration: "2m",
      exec: "readScenario",
    },
    writers: {
      executor: "constant-arrival-rate",
      rate: 20,           // 20 writes/s
      timeUnit: "1s",
      duration: "2m",
      preAllocatedVUs: 40,
      maxVUs: 80,
      exec: "writeScenario",
    },
  },
  thresholds: {
    "http_req_duration{scenario:readers}": ["p(95) < 400"],
    "http_req_duration{scenario:writers}": ["p(95) < 2000"],
    http_req_failed: ["rate < 0.01"],
  },
};

export function readScenario() {
  group("list articles", () => {
    const res = http.get(`${BASE_URL}/v1/articles?limit=10&page=${randomIntBetween(1, 20)}`);
    check(res, { "list 200": (r) => r.status === 200 });
  });
  sleep(0.5);
}

export function writeScenario() {
  group("create comment", () => {
    const res = http.post(
      `${BASE_URL}/v1/comments`,
      JSON.stringify({ articleId: "fixture-article-001", body: "Load test comment" }),
      { headers: { "Content-Type": "application/json" } }
    );
    check(res, { "write 201 or 429": (r) => [201, 429].includes(r.status) });
  });
}
```

---

## Analysing Results for D1 Saturation

```bash
# Run the ramp test, output summary to JSON for CI gating
k6 run \
  --env WORKER_URL=https://content.example project.example.com \
  --env API_TOKEN=$example project_API_TOKEN \
  --out json=results/d1-write-ramp.json \
  k6/d1-write-throughput.js

# Summarise the JSON with jq
jq '
  [.[] | select(.type == "Point") | select(.metric == "d1_write_latency_ms")]
  | { count: length, p95: (map(.data.value) | sort | .[(length * 0.95) | floor]) }
' results/d1-write-ramp.json
```

Key metrics to watch in the summary output:

| Metric | Healthy | Warning | Critical |
|---|---|---|---|
| `d1_write_errors` rate | < 1% | 1–5% | > 5% |
| `d1_write_latency_ms` p95 | < 800 ms | 800–1500 ms | > 1500 ms |
| `d1_sqlite_busy_errors` count | 0 | 1–10 | > 10 |
| Throughput (req/s at saturation) | ≥ 40 | 20–40 | < 20 |

---

## Worker-Side Retry Pattern Under Test

```typescript
// apps/content-worker/src/lib/d1-retry.ts
export async function d1WriteWithRetry<T>(
  fn: () => Promise<T>,
  maxAttempts = 3,
  baseDelayMs = 50
): Promise<T> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      const isBusy =
        err instanceof Error && err.message.includes("SQLITE_BUSY");
      if (!isBusy || attempt === maxAttempts - 1) throw err;
      // Exponential backoff with jitter
      const delay = baseDelayMs * 2 ** attempt + Math.random() * baseDelayMs;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw new Error("unreachable");
}
```

The k6 ramp test validates that the Worker's retry budget keeps `d1_write_errors` below 2%
up to ~80 req/s; beyond that, errors rise sharply and indicate the retry budget needs tuning
or the write path needs a Durable Object write queue.

---

## CI Integration with Grafana Cloud k6

```yaml
# .github/workflows/d1-write-load.yml
name: D1 Write Throughput
on:
  schedule:
    - cron: "0 4 * * 3"   # Wednesday 04:00 UTC (low-traffic window)
  workflow_dispatch:

jobs:
  load:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup k6
        uses: grafana/setup-k6-action@v1
      - name: Run D1 write ramp
        env:
          WORKER_URL: ${{ secrets.STAGING_WORKER_URL }}
          API_TOKEN:  ${{ secrets.STAGING_API_TOKEN }}
          K6_CLOUD_TOKEN: ${{ secrets.K6_CLOUD_TOKEN }}
        run: |
          k6 run \
            --env WORKER_URL=$WORKER_URL \
            --env API_TOKEN=$API_TOKEN \
            --out cloud \
            k6/d1-write-throughput.js
```

---

## Anti-patterns

- **Running write load tests against production** – Always target staging with synthetic data.
  D1 write throughput tests will compete with live users and may cause `SQLITE_BUSY` for real
  writes.
- **Constant-VU executor for write throughput** – VU-based executors don't control arrival
  rate; use `ramping-arrival-rate` or `constant-arrival-rate` to measure throughput accurately.
- **No sleep / jitter** – All VUs hitting at the same millisecond creates artificial burst
  peaks that don't reflect real traffic. Add `sleep(Math.random() * 0.2)`.
- **Asserting only `status === 201`** – Also check `429 Too Many Requests` from the Worker's
  rate limiter; a well-implemented Worker should return 429 before 500.
- **Ignoring `d1_sqlite_busy_errors` count** – A zero error rate can mask BUSY errors if
  retries succeed silently. Track the counter separately to tune retry configuration.

---

## Gotchas

- D1 local (`wrangler dev --local`) uses SQLite WAL mode and does not reproduce the exact
  concurrency profile of production D1. Always run throughput tests against the deployed Worker.
- D1 write throughput limits are per-database, not per-Worker instance. Multiple Worker
  instances writing to the same D1 database share the serialisation bottleneck.
- `SQLITE_BUSY` from D1 surfaces as a generic 500 from the Worker unless the Worker
  explicitly catches and rethrows it with a recognisable body. Grep for "SQLITE" in the response
  body to distinguish it from other 500 causes.
- k6 `--out json` produces newline-delimited JSON (NDJSON), not a JSON array. Use `jq -s`
  or process line by line.
- Cloudflare rate limiting (Workers Rate Limiting binding) and D1 write limits are independent.
  The Worker may return 429 from the rate limiter before D1 is saturated; profile both limits
  separately.

---

## Verification

```bash
# Smoke: 5 VUs for 10 s to confirm the test script runs correctly
k6 run --vus 5 --duration 10s \
  --env WORKER_URL=http://localhost:8787 \
  k6/d1-write-throughput.js

# Full ramp against staging
k6 run \
  --env WORKER_URL=$STAGING_WORKER_URL \
  --env API_TOKEN=$STAGING_API_TOKEN \
  k6/d1-write-throughput.js

# Expected: thresholds pass, d1_sqlite_busy_errors = 0 at ≤ 50 req/s
```

---

## Related

- `k6-load-testing-cloudflare-workers-api.md`
- `d1-batch-transactions-vitest.md`
- `miniflare-d1-batch-transaction-testing.md`
- `workers-queues-retry-dlq-testing.md`
- `grafana-k6-cloud-workers-stress-test.md`

---

## Sources

- k6 arrival rate executors: https://k6.io/docs/using-k6/scenarios/executors/
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
- k6 custom metrics: https://k6.io/docs/using-k6/metrics/create-custom-metrics/
- Grafana k6 GitHub Action: https://github.com/grafana/setup-k6-action
- D1 SQLITE_BUSY handling: https://developers.cloudflare.com/d1/observability/debugging-d1/
