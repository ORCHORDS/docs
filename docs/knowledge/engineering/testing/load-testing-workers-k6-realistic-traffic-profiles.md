# Load Testing Cloudflare Workers with k6 Realistic Traffic Profiles

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to verify that a Cloudflare Workers endpoint meets response-time SLOs under realistic traffic (ramp-up, steady state, spike, ramp-down) before promoting a release, and you want per-request reporting of Worker-specific headers such as `cf-cache-status` and `x-request-id` in the k6 summary.

## Context

k6 is a JavaScript-based load testing tool that models traffic with `stages` (VU ramp curves), supports CSV data files for parameterised payloads, and exposes a custom metrics API for tracking arbitrary values. Cloudflare Workers return diagnostic headers on every response; capturing them as custom metrics gives you cache hit rates and request tracing data alongside standard latency percentiles.

The tests here target a deployed Workers endpoint (staging or production). For pre-deploy load tests targeting `wrangler dev --local`, replace `TARGET_URL` with `http://localhost:8787`.

## k6 Load Test Script

```javascript
// load-tests/workers-traffic.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Counter, Rate } from "k6/metrics";
import { SharedArray } from "k6/data";
import papaparse from "https://jslib.k6.io/papaparse/5.1.1/index.js";

// ---------------------------------------------------------------------------
// Custom metrics for Worker-specific headers
// ---------------------------------------------------------------------------

const cfCacheHits = new Counter("cf_cache_hits");
const cfCacheMisses = new Counter("cf_cache_misses");
const workerResponseTime = new Trend("worker_response_ms", true); // percentiles
const errorRate = new Rate("error_rate");

// ---------------------------------------------------------------------------
// Parameterised payloads from CSV
// ---------------------------------------------------------------------------

// CSV format: productId,userId,quantity
// Example row: prod-001,user-alice,3
const payloads = new SharedArray("order-payloads", () => {
  const raw = open("./data/order-payloads.csv");
  return papaparse.parse(raw, { header: true, skipEmptyLines: true }).data;
});

// ---------------------------------------------------------------------------
// Traffic profile: ramp-up -> steady state -> spike -> ramp-down
// ---------------------------------------------------------------------------

export const options = {
  stages: [
    { duration: "1m", target: 20 },   // Ramp-up to 20 VUs
    { duration: "5m", target: 20 },   // Steady state at 20 VUs
    { duration: "30s", target: 100 }, // Spike to 100 VUs
    { duration: "1m", target: 20 },   // Recover to 20 VUs
    { duration: "1m", target: 0 },    // Ramp-down
  ],

  // SLO thresholds — test FAILS if these are breached
  thresholds: {
    http_req_duration: [
      "p(95)<200",   // 95th percentile under 200 ms
      "p(99)<500",   // 99th percentile under 500 ms
    ],
    worker_response_ms: ["p(95)<200"],
    error_rate: ["rate<0.01"],         // Less than 1% errors
    http_req_failed: ["rate<0.01"],
  },
};

// ---------------------------------------------------------------------------
// Main VU function
// ---------------------------------------------------------------------------

export default function main() {
  const TARGET_URL =
    __ENV.TARGET_URL ?? "https://workers-api.staging.example.com";

  // Pick a random payload row from the CSV
  const row = payloads[Math.floor(Math.random() * payloads.length)];

  const payload = JSON.stringify({
    productId: row.productId,
    userId: row.userId,
    quantity: parseInt(row.quantity, 10),
  });

  const params = {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      // Propagate a synthetic trace ID so k6 requests are identifiable in logs
      "x-load-test-id": `k6-${__VU}-${__ITER}`,
    },
    tags: { endpoint: "POST /orders" },
  };

  const start = Date.now();
  const res = http.post(`${TARGET_URL}/orders`, payload, params);
  const elapsed = Date.now() - start;

  // Record custom Worker-specific metrics
  workerResponseTime.add(elapsed);

  const cacheStatus = res.headers["Cf-Cache-Status"] ?? "";
  if (cacheStatus === "HIT") {
    cfCacheHits.add(1);
  } else {
    cfCacheMisses.add(1);
  }

  // Track the x-request-id for debugging slow samples
  const requestId = res.headers["X-Request-Id"] ?? "(none)";

  // Checks — failures increment error_rate
  const ok = check(res, {
    "status is 201 or 202": (r) =>
      r.status === 201 || r.status === 202,
    "response has request ID": () => requestId !== "(none)",
    "response body is JSON": (r) => {
      try {
        JSON.parse(r.body);
        return true;
      } catch {
        return false;
      }
    },
  });

  errorRate.add(!ok);

  // Realistic think time between requests (100-300 ms)
  sleep(Math.random() * 0.2 + 0.1);
}

// ---------------------------------------------------------------------------
// Custom end-of-test summary
// ---------------------------------------------------------------------------

export function handleSummary(data) {
  const p95 = data.metrics["worker_response_ms"]?.values["p(95)"] ?? 0;
  const hits = data.metrics["cf_cache_hits"]?.values?.count ?? 0;
  const misses = data.metrics["cf_cache_misses"]?.values?.count ?? 0;
  const total = hits + misses;
  const hitRate = total > 0 ? ((hits / total) * 100).toFixed(1) : "N/A";

  const summary = [
    "=== Workers Load Test Summary ===",
    `p(95) response time : ${p95.toFixed(0)} ms`,
    `Cache hit rate      : ${hitRate}%`,
    `Total requests      : ${total}`,
    `Error rate          : ${(
      (data.metrics["error_rate"]?.values?.rate ?? 0) * 100
    ).toFixed(2)}%`,
  ].join("\n");

  console.log(summary);

  return {
    "stdout": summary + "\n",
    "load-test-summary.json": JSON.stringify(data, null, 2),
  };
}
```

## Sample CSV Data File

```csv
# load-tests/data/order-payloads.csv
productId,userId,quantity
prod-001,user-alice,1
prod-002,user-bob,3
prod-003,user-carol,2
prod-001,user-dave,5
prod-004,user-eve,1
```

## Running k6 in CI (GitHub Actions)

```yaml
# .github/workflows/load-test.yml
name: Load Test Workers

on:
  workflow_dispatch:
    inputs:
      target_url:
        description: Workers endpoint to test
        required: true
        default: https://workers-api.staging.example.com

jobs:
  k6-load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install k6
        run: |
          sudo gpg -k
          sudo gpg --no-default-keyring \
            --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
            --keyserver hkp://keyserver.ubuntu.com:80 \
            --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] \
            https://dl.k6.io/deb stable main" \
            | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update && sudo apt-get install k6 -y

      - name: Run load test
        env:
          TARGET_URL: ${{ inputs.target_url }}
        run: |
          k6 run \
            --env TARGET_URL=$TARGET_URL \
            --out json=load-test-results.json \
            load-tests/workers-traffic.js

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: k6-results
          path: |
            load-test-results.json
            load-test-summary.json
```

## Anti-patterns

- **Running the spike stage first** — Workers cold-start under a sudden VU spike without a ramp-up inflates p99 latency figures that don't reflect real traffic.
- **Using a single static payload** — Workers that cache aggressively will serve 100% cache hits, masking origin latency. Vary inputs via a CSV data file.
- **Setting thresholds but ignoring exit codes** — k6 exits with code 99 when thresholds are breached; CI pipelines must check the exit code to gate deploys.
- **Not propagating a test trace header** — without `x-load-test-id`, k6 requests are indistinguishable from real traffic in Workers logs, making post-mortem analysis harder.

## Gotchas

- `SharedArray` is evaluated once in the init context (before VUs start); `open()` is only available in the init context. Do not call `open()` inside the main VU function.
- Cloudflare strips or renames some headers on the way out; `Cf-Cache-Status` is only present on responses served from the Cloudflare cache tier, not on Worker-computed responses.
- `papaparse` imported from `jslib.k6.io` requires an internet connection at test start. For air-gapped CI, bundle the library locally and import it as a relative path.
- k6's `Trend` metric with `true` as the second argument enables percentile calculation; without it, `p(95)` is not available in the summary.

## Verification

```bash
# Quick smoke run (1 VU, 10 iterations, no threshold gating)
k6 run --vus 1 --iterations 10 load-tests/workers-traffic.js

# Full profile against local wrangler dev
k6 run --env TARGET_URL=http://localhost:8787 load-tests/workers-traffic.js

# Check exit code for CI gate
k6 run load-tests/workers-traffic.js; echo "Exit: $?"
# Exit: 0 = pass, Exit: 99 = threshold breach
```

## Related

- `contract-testing-workers-pact-provider-verification.md`
- `playwright-workers-authenticated-session-testing.md`
- k6 documentation — `https://grafana.com/docs/k6/latest/`

## Sources

- k6 official documentation — stages, thresholds, custom metrics
- Cloudflare Workers response headers reference
- k6 `SharedArray` and CSV parameterisation guide
