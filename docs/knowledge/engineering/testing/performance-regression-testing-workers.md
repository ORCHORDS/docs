# performance-regression-testing-workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

A example project Workers API pull request that refactors a D1 query
silently increases the p99 response latency from 180 ms to 420 ms.
No CI gate catches it because load tests are only run manually.
By the time the regression reaches production, mobile clients on
3G networks start timing out. The team needs a reproducible
baseline, automated trend detection, and a CI gate that fails
the build when a percentile crosses its budget.

## Context

Performance regression testing for Cloudflare Workers requires
three layers:

1. **Baseline benchmarking** — establish the p50/p95/p99 latency
   profile of a known-good revision using k6.
2. **Comparison runs** — run the same k6 scenario against the new
   revision and compare the percentile distributions.
3. **Trend analysis** — use Cloudflare Analytics Engine to track
   percentile drift across every deployment, giving visibility
   beyond what a single run captures.

Workers have no guaranteed CPU affinity across requests, so
always run benchmarks against a staging environment with a
warm cache and fixed KV/D1 schema. Never run regression
benchmarks against a cold Worker — include a warm-up stage.

## Project Structure

```
scripts/
  k6/
    regression-baseline.js    # steady-state benchmark scenario
    regression-compare.js     # same scenario with compare thresholds
    lib/
      percentiles.js          # shared metric extraction helpers
  perf/
    baselines/
      main.json               # committed baseline summary
    compare.ts                # Node script: compare two k6 summaries
workers/
  analytics/
    src/
      latency-tracker.ts      # writes p99 samples to Analytics Engine
.github/
  workflows/
    perf-regression.yml
```

## Baseline Benchmark

The baseline scenario uses a `constant-arrival-rate` executor
to decouple request rate from VU count, giving a stable RPS
regardless of how long individual requests take:

```js
// scripts/k6/regression-baseline.js
import http            from 'k6/http';
import { check }       from 'k6';
import { Trend, Rate } from 'k6/metrics';

const p99Duration = new Trend('custom_p99', true);
const errorRate   = new Rate('error_rate');
const BASE = __ENV.WORKER_URL || 'https://staging.example project.workers.dev';

export const options = {
  scenarios: {
    warm_up: {
      executor:         'constant-arrival-rate',
      rate:             10,
      timeUnit:         '1s',
      duration:         '30s',
      preAllocatedVUs:  5,
      maxVUs:           20,
      tags: { phase: 'warmup' },
    },
    steady_state: {
      executor:         'constant-arrival-rate',
      rate:             50,
      timeUnit:         '1s',
      duration:         '2m',
      preAllocatedVUs:  20,
      maxVUs:           80,
      startTime:        '30s',   // after warm_up
      tags: { phase: 'steady' },
    },
  },

  thresholds: {
    // Evaluated only on the steady-state phase
    'http_req_duration{phase:steady}': [
      { threshold: 'p(95)<300', abortOnFail: false },
      { threshold: 'p(99)<500', abortOnFail: false },
    ],
    'error_rate{phase:steady}': [
      { threshold: 'rate<0.01', abortOnFail: true },
    ],
  },
};

export default function () {
  const res = http.get(`${BASE}/api/events`, {
    headers: { Accept: 'application/json' },
  });

  const ok = res.status === 200;
  errorRate.add(!ok);
  if (ok) p99Duration.add(res.timings.duration);

  check(res, { 'status 200': (r) => r.status === 200 });
}
```

Capture the summary JSON for baseline storage:

```bash
k6 run \
  --summary-export scripts/perf/baselines/main.json \
  --env WORKER_URL=https://staging.example project.workers.dev \
  scripts/k6/regression-baseline.js
```

## Percentile Extraction and Comparison

```ts
// scripts/perf/compare.ts
import fs from 'node:fs';

interface K6Summary {
  metrics: {
    http_req_duration: {
      values: Record<string, number>;
    };

  };
}

interface Thresholds {
  p95MaxRegressionMs: number;
  p99MaxRegressionMs: number;
}

function loadSummary(filePath: string): K6Summary {
  return JSON.parse(fs.readFileSync(filePath, 'utf8')) as K6Summary;
}

function extractPercentiles(summary: K6Summary) {
  const v = summary.metrics.http_req_duration.values;
  return {
    p50: v['p(50)'] ?? 0,
    p95: v['p(95)'] ?? 0,
    p99: v['p(99)'] ?? 0,
  };
}

export function compareBaselines(
  baselinePath: string,
  candidatePath: string,
  thresholds: Thresholds = {
    p95MaxRegressionMs: 50,
    p99MaxRegressionMs: 100,
  }
): void {
  const baseline  = extractPercentiles(loadSummary(baselinePath));
  const candidate = extractPercentiles(loadSummary(candidatePath));

  const delta = {
    p50: candidate.p50 - baseline.p50,
    p95: candidate.p95 - baseline.p95,
    p99: candidate.p99 - baseline.p99,
  };

  console.table({ baseline, candidate, delta });

  const failures: string[] = [];

  if (delta.p95 > thresholds.p95MaxRegressionMs) {
    failures.push(
      `p95 regressed by ${delta.p95.toFixed(1)} ms `
      + `(limit: ${thresholds.p95MaxRegressionMs} ms)`
    );
  }
  if (delta.p99 > thresholds.p99MaxRegressionMs) {
    failures.push(
      `p99 regressed by ${delta.p99.toFixed(1)} ms `
      + `(limit: ${thresholds.p99MaxRegressionMs} ms)`
    );
  }

  if (failures.length > 0) {
    console.error('\nPerformance regression detected:');
    failures.forEach((f) => console.error('  ✗', f));
    process.exit(1);
  }

  console.log('\nNo regression detected. All percentiles within budget.');
}

// CLI entry point
const [, , baseline, candidate] = process.argv;
if (baseline && candidate) {
  compareBaselines(baseline, candidate);
}
```

## Cloudflare Analytics Engine Trend Tracking

Write p99 latency samples from within the Worker to Analytics
Engine so that every deployment's latency is visible in a
Cloudflare dashboard query:

```ts
// workers/analytics/src/latency-tracker.ts

export function recordLatency(
  dataset: AnalyticsEngineDataset,
  endpointTag: string,
  durationMs: number,
  platform: 'mobile' | 'desktop'
): void {
  dataset.writeDataPoint({
    blobs:   [endpointTag, platform],
    doubles: [durationMs],
    indexes: [endpointTag],
  });
}
```

Use it in the Worker fetch handler:

```ts
// workers/api/src/index.ts (excerpt)
import { recordLatency } from '../../analytics/src/latency-tracker.js';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const start = Date.now();
    const platform = request.headers.get('x-client-platform') === 'mobile'
      ? 'mobile' : 'desktop';

    try {
      const response = await router.handle(request, env);
      const durationMs = Date.now() - start;

      ctx.waitUntil(
        Promise.resolve(
          recordLatency(
            env.PERF_DATASET,
            new URL(request.url).pathname,
            durationMs,
            platform
          )
        )
      );

      return response;
    } catch (err) {
      return new Response('Internal Server Error', { status: 500 });
    }
  },
};
```

Query the Analytics Engine via Cloudflare's GraphQL API to
retrieve p99 per endpoint per day:

```graphql
{
  viewer {
    accounts(filter: { accountTag: $accountId }) {
      workersAnalyticsEngineAdaptiveGroups(
        filter: {
          date_geq: "2026-08-15"
          blob1: "/api/events"
        }
        limit: 30
        orderBy: [date_ASC]
      ) {
        avg { double1 }
        quantiles { double1P99 }
        dimensions { date blob1 blob2 }
      }
    }
  }
}
```

| Field | Meaning |
|-------|---------|
| `blob1` | Endpoint path |
| `blob2` | Platform (`mobile` / `desktop`) |
| `double1` | Duration in ms |
| `double1P99` | p99 latency for that day/endpoint |

## GitHub Actions CI Gate

```yaml
# .github/workflows/perf-regression.yml
name: Performance regression gate
on:
  pull_request:
    branches: [main]

jobs:
  perf:
    runs-on: ubuntu-latest
    env:
      WORKER_URL: ${{ vars.STAGING_WORKER_URL }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: '22' }

      - run: npm ci

      - name: Install k6
        run: |
          sudo gpg --dearmor -o /usr/share/keyrings/k6.gpg \
            < <(curl -sfL https://dl.k6.io/key.gpg)
          echo "deb [signed-by=/usr/share/keyrings/k6.gpg] \
            https://dl.k6.io/deb stable main" \
            | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update && sudo apt-get install -y k6

      - name: Run performance benchmark (PR branch)
        run: |
          k6 run \
            --summary-export /tmp/candidate.json \
            --env WORKER_URL="$WORKER_URL" \
            scripts/k6/regression-baseline.js

      - name: Compare against committed baseline
        run: |
          npx tsx scripts/perf/compare.ts \
            scripts/perf/baselines/main.json \
            /tmp/candidate.json

      - name: Upload candidate summary
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: perf-candidate-${{ github.sha }}
          path: /tmp/candidate.json
```

## Regression Budget Reference

| Percentile | Mobile budget | Desktop budget | Max regression vs baseline |
|------------|---------------|----------------|---------------------------|
| p50 | 150 ms | 80 ms | +30 ms |
| p95 | 400 ms | 200 ms | +50 ms |
| p99 | 800 ms | 400 ms | +100 ms |

Budgets are measured from the Cloudflare edge to the Worker
response, excluding TCP/TLS handshake time on the client side.

## Anti-patterns

- Running the regression benchmark against the production Worker —
  a benchmark that generates 50 RPS for two minutes will appear in
  production traffic metrics and may trip rate limits.
- Using `ramping-vus` instead of `constant-arrival-rate` for
  regression benchmarks — a ramping VU scenario does not hold RPS
  constant, so a slower Worker appears to have lower throughput
  rather than higher latency, masking the regression.
- Comparing a warm baseline against a cold candidate run — always
  include a warm-up stage in both runs and compare only the
  steady-state phase metrics.
- Setting p99 regression thresholds tighter than the natural
  measurement variance — p99 has high variance at low RPS. At
  50 RPS over 2 minutes the p99 sample size is ~6000 requests;
  a 5 ms threshold will produce spurious failures.
- Storing the baseline JSON in the repository without a clear
  update process — engineers will not know when to update it
  and it will drift out of sync with the real Worker performance.

## Gotchas

- Cloudflare Analytics Engine data is eventually consistent with
  a ~1-minute lag. Do not query it immediately after a deploy and
  expect to see that deploy's data.
- The `constant-arrival-rate` executor adjusts VU count to hit
  the target RPS; if the Worker is slow, k6 will spin up more
  VUs. Set `maxVUs` high enough that the target RPS is achievable.
- `--summary-export` writes a flat JSON; nested tag-based metrics
  (e.g., `http_req_duration{phase:steady}`) appear as separate
  keys in the `metrics` object with the tag selector as a suffix.
  The compare script must match this key format.
- Workers cold-start latency appears in p99 tails on the first
  few requests. The warm-up stage isolates this effect; discard
  warm-up phase metrics in the comparison.

## Verification

```bash
# Run benchmark locally against staging
k6 run \
  --summary-export /tmp/local-candidate.json \
  --env WORKER_URL=https://staging.example project.workers.dev \
  scripts/k6/regression-baseline.js

# Compare against committed baseline
npx tsx scripts/perf/compare.ts \
  scripts/perf/baselines/main.json \
  /tmp/local-candidate.json

# Update the baseline after intentional performance improvements
cp /tmp/local-candidate.json scripts/perf/baselines/main.json
git add scripts/perf/baselines/main.json
```

## Related

- `testing/k6-load-testing-cloudflare-workers-api.md`
- `testing/k6-performance-regression-testing.md`
- `testing/performance-testing-k6.md`
- `testing/performance-regression-gates-ci.md`
- `testing/chaos-engineering-cloudflare-workers.md`

## Source URLs (verified 2026-08-22)

- https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/
- https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/graphql-api/
