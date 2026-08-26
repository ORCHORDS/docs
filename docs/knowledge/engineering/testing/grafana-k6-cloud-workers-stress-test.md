# Grafana k6 Cloud Distributed Stress Testing for Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Running k6 stress tests from a single local machine caps achievable request rate at what one host can generate, masking how a Cloudflare Worker performs under genuine multi-region, high-concurrency load. Grafana k6 Cloud distributes test execution across cloud load zones, surfaces per-region latency breakdowns in real time, and stores results for trend comparison — without requiring self-managed infrastructure or a fleet of EC2 instances.

## Context

Cloudflare Workers execute at the edge in dozens of regions simultaneously. A stress test hammering a Worker from one geographic origin cannot reproduce the fan-out pattern real users create across PoPs. Grafana k6 Cloud (formerly k6 Cloud by Load Impact) allocates virtual users across AWS load zones that mirror Cloudflare's PoP footprint and streams metrics back to a hosted Grafana dashboard. Test scripts are plain k6 JavaScript; the same script runs locally against `wrangler dev` for development iteration, then on k6 Cloud for CI gate runs. Billing is by VUh (virtual user hours), so CI runs should be scoped to a defined threshold pass/fail gate and not run on every PR.

## Stress Test Script

```javascript
// tests/stress/workers-api-stress.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate   = new Rate("worker_errors");
const p99Latency  = new Trend("worker_p99_latency", true);

export const options = {
  ext: {
    loadimpact: {
      projectID: __ENV.K6_CLOUD_PROJECT_ID,
      name: `Workers API Stress — ${__ENV.GIT_SHA ?? "local"}`,
      distribution: {
        "amazon:us:ashburn":    { loadZone: "amazon:us:ashburn",   percent: 30 },
        "amazon:eu:frankfurt":  { loadZone: "amazon:eu:frankfurt", percent: 30 },
        "amazon:ap:singapore":  { loadZone: "amazon:ap:singapore", percent: 20 },
        "amazon:us:portland":   { loadZone: "amazon:us:portland",  percent: 20 },
      },
    },
  },
  stages: [
    { duration: "2m",  target: 200  },   // ramp up
    { duration: "5m",  target: 200  },   // steady state
    { duration: "3m",  target: 1000 },   // stress spike
    { duration: "2m",  target: 200  },   // recovery
    { duration: "2m",  target: 0    },   // ramp down
  ],
  thresholds: {
    http_req_duration:   ["p(95)<500", "p(99)<1500"],
    http_req_failed:     ["rate<0.01"],
    worker_errors:       ["rate<0.005"],
  },
};

const BASE_URL = __ENV.WORKERS_URL ?? "https://api.example.workers.dev";
const API_KEY  = __ENV.STRESS_TEST_API_KEY;

const ENDPOINTS = [
  { path: "/api/v1/items",    weight: 0.60 },
  { path: "/api/v1/items/42", weight: 0.30 },
  { path: "/api/v1/health",   weight: 0.10 },
];

function pickEndpoint() {
  const r = Math.random();
  let cumulative = 0;
  for (const ep of ENDPOINTS) {
    cumulative += ep.weight;
    if (r < cumulative) return ep.path;
  }
  return ENDPOINTS[0].path;
}

export default function () {
  const params = {
    headers: {
      Authorization:   `Bearer ${API_KEY}`,
      Accept:          "application/json",
      "CF-Cache-Tag":  "stress-test",  // tag for post-run cache purge
    },
    timeout: "10s",
  };

  const res = http.get(`${BASE_URL}${pickEndpoint()}`, params);

  const ok = check(res, {
    "status is 2xx":          (r) => r.status >= 200 && r.status < 300,
    "response time < 500ms":  (r) => r.timings.duration < 500,
    "cf-ray header present":  (r) => Boolean(r.headers["Cf-Ray"]),
  });

  errorRate.add(!ok);
  p99Latency.add(res.timings.duration);

  sleep(Math.random() * 0.5 + 0.1); // 100–600 ms think time
}

export function handleSummary(data) {
  return {
    "results/stress-summary.json": JSON.stringify(data, null, 2),
  };
}
```

## CI Pipeline Integration

```yaml
# .github/workflows/stress.yml
name: Workers Stress Test
on:
  workflow_dispatch:
  schedule:
    - cron: "0 3 * * 1"   # Monday 03:00 UTC

jobs:
  stress:
    runs-on: ubuntu-latest
    environment: stress
    steps:
      - uses: actions/checkout@v4

      - uses: grafana/setup-k6-action@v1
        with:
          cloud-api-token: ${{ secrets.K6_CLOUD_TOKEN }}

      - name: Run k6 Cloud stress test
        env:
          K6_CLOUD_PROJECT_ID: ${{ vars.K6_CLOUD_PROJECT_ID }}
          WORKERS_URL:         ${{ vars.WORKERS_STRESS_URL }}
          STRESS_TEST_API_KEY: ${{ secrets.STRESS_TEST_API_KEY }}
          GIT_SHA:             ${{ github.sha }}
        run: |
          k6 cloud --exit-on-running \
            --env K6_CLOUD_PROJECT_ID="$K6_CLOUD_PROJECT_ID" \
            --env WORKERS_URL="$WORKERS_URL" \
            --env STRESS_TEST_API_KEY="$STRESS_TEST_API_KEY" \
            --env GIT_SHA="$GIT_SHA" \
            tests/stress/workers-api-stress.js

      - name: Upload summary
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: stress-summary
          path: results/stress-summary.json
```

## Threshold Comparison Across Runs

```typescript
// scripts/compare-stress-results.ts
import { readFileSync } from "fs";

interface K6Summary {
  metrics: {
    http_req_duration: { values: { "p(99)": number } };
    http_req_failed:   { values: { rate: number } };
  };
}

function compare(baselinePath: string, currentPath: string) {
  const baseline: K6Summary = JSON.parse(readFileSync(baselinePath, "utf-8"));
  const current:  K6Summary = JSON.parse(readFileSync(currentPath,  "utf-8"));

  const baseP99    = baseline.metrics.http_req_duration.values["p(99)"];
  const currentP99 = current.metrics.http_req_duration.values["p(99)"];
  const regression = ((currentP99 - baseP99) / baseP99) * 100;

  if (regression > 20) {
    console.error(`P99 regression: +${regression.toFixed(1)}% (${baseP99}ms → ${currentP99}ms)`);
    process.exit(1);
  }
  console.log(`P99 within budget: ${currentP99}ms (baseline ${baseP99}ms, ${regression.toFixed(1)}%)`);
}

compare(process.argv[2], process.argv[3]);
```

## Anti-patterns

- Running stress tests against the production Worker deployment with real user API keys — stress traffic skews analytics and may trigger rate limits for legitimate users
- Using a flat `vus` + `duration` config instead of `stages` — misses ramp-up cost that reveals memory pressure at the Worker isolate level during cold start
- Omitting `ext.loadimpact.distribution` — k6 Cloud silently picks a single default load zone, negating the multi-region value and producing misleadingly low latency numbers

## Gotchas

- `__ENV.K6_CLOUD_PROJECT_ID` must be a numeric string matching a project in your Grafana k6 Cloud org; a string mismatch silently runs under the account default project with no error
- Cloudflare's CDN may serve cached responses during the stress run; append `Cache-Control: no-store` to requests or use a cache-busting query param when measuring cold-path Worker latency specifically
- k6 Cloud charges by VUh; a 14-minute test at 1 000 VUs costs roughly 233 VUh — configure a spend alert in the k6 Cloud project settings before scheduling weekly runs

## Verification

```bash
# Dry-run locally before committing to k6 Cloud spend
k6 run --vus 10 --duration 30s \
  --env WORKERS_URL=http://localhost:8787 \
  --env STRESS_TEST_API_KEY=dev-key \
  tests/stress/workers-api-stress.js

# Execute on k6 Cloud (requires K6_CLOUD_TOKEN in environment)
k6 cloud tests/stress/workers-api-stress.js

# Compare two summary files for regression
npx ts-node scripts/compare-stress-results.ts results/baseline.json results/stress-summary.json
```

## Related

- `testing/k6-load-testing-cloudflare-workers-api.md`
- `testing/k6-performance-regression-testing.md`
- `testing/performance-regression-gates-ci.md`

## Sources

- https://grafana.com/docs/k6/latest/results-output/real-time/cloud/
- https://grafana.com/docs/k6/latest/testing-guides/load-testing-websites/
- https://developers.cloudflare.com/workers/observability/
