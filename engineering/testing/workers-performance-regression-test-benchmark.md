# Performance Regression Testing for Workers Using Vitest Benchmarks

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A Workers deployment passes all functional tests but a recent change doubled response latency under load. Without automated performance regression tests, this type of regression is caught only after users complain or after observing elevated P95 latency in production dashboards. You need CI tests that measure actual response times, compare against a stored baseline, and fail the build when performance degrades beyond an acceptable threshold.

---

## Context
Vitest's `SELF.fetch()` provides an in-process way to call your Worker handler and measure round-trip time accurately. By running 50 requests per endpoint, collecting individual timings, and computing P95, you get a meaningful latency distribution rather than a single noisy sample. Baselines are stored in Cloudflare KV so they persist across CI runs and can be updated intentionally when performance characteristics change. A regression threshold of 20% over baseline triggers a test failure with a diagnostic table written to the GitHub Actions job summary.

---

## Configuration

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "PERF_BASELINES"
id = "YOUR_KV_NAMESPACE_ID"

[env.test.kv_namespaces]
binding = "PERF_BASELINES"
id = "YOUR_KV_NAMESPACE_ID"
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wranglerConfigPath: './wrangler.toml',
        miniflare: {
          kvNamespaces: ['PERF_BASELINES'],
        },
      },
    },
    // Performance tests can take longer — raise the timeout
    testTimeout: 60_000,
  },
});
```

---

## Benchmark Utility

```typescript
// test/perf/bench-utils.ts
import { SELF } from 'cloudflare:test';

export interface TimingResult {
  samples: number[];
  p50: number;
  p95: number;
  p99: number;
  min: number;
  max: number;
  mean: number;
}

function percentile(sorted: number[], p: number): number {
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, idx)];
}

/**
 * Runs `runs` sequential SELF.fetch() calls to `url` and returns timing stats.
 * Sequential (not parallel) to avoid saturating the Miniflare event loop
 * and to get per-request latency rather than throughput.
 */
export async function measureFetchTiming(
  url: string,
  options: RequestInit = {},
  runs = 50,
): Promise<TimingResult> {
  const samples: number[] = [];

  // Warm-up: one un-timed request to populate any caches
  await SELF.fetch(url, options);

  for (let i = 0; i < runs; i++) {
    const start = performance.now();
    const res = await SELF.fetch(url, options);
    const end = performance.now();
    // Only count successful responses in timing samples
    if (res.status < 500) {
      samples.push(end - start);
    }
  }

  const sorted = [...samples].sort((a, b) => a - b);
  const mean = samples.reduce((a, b) => a + b, 0) / samples.length;

  return {
    samples,
    p50: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    p99: percentile(sorted, 99),
    min: sorted[0],
    max: sorted[sorted.length - 1],
    mean,
  };
}

export function formatTimingTable(
  results: Record<string, TimingResult>,
  baselines: Record<string, number>,
): string {
  const rows = Object.entries(results).map(([endpoint, t]) => {
    const baseline = baselines[endpoint] ?? null;
    const regression = baseline ? ((t.p95 - baseline) / baseline) * 100 : null;
    const regressionStr = regression !== null
      ? `${regression >= 0 ? '+' : ''}${regression.toFixed(1)}%`
      : 'no baseline';
    const status = regression !== null && regression > 20 ? 'FAIL' : 'PASS';
    return `| ${endpoint} | ${t.p95.toFixed(2)}ms | ${baseline?.toFixed(2) ?? '-'}ms | ${regressionStr} | ${status} |`;
  });

  return [
    '## Performance Regression Report',
    '',
    '| Endpoint | P95 | Baseline P95 | Regression | Status |',
    '|----------|-----|-------------|------------|--------|',
    ...rows,
  ].join('\n');
}
```

---

## Performance Regression Tests

```typescript
// test/perf/response-time.perf.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, afterAll } from 'vitest';
import { appendFileSync } from 'fs';
import { measureFetchTiming, formatTimingTable, type TimingResult } from './bench-utils';

const REGRESSION_THRESHOLD = 0.20; // 20%
const RUNS = 50;
const P95_HARD_LIMIT_MS = 100; // absolute ceiling regardless of baseline

const endpoints: Array<{ name: string; url: string; init?: RequestInit }> = [
  { name: 'GET /api/users', url: 'http://localhost/api/users' },
  { name: 'GET /api/users/:id', url: 'http://localhost/api/users/00000000-0000-0000-0000-000000000001' },
  {
    name: 'POST /api/users',
    url: 'http://localhost/api/users',
    init: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Bench User', email: 'bench@example.com', role: 'viewer' }),
    },
  },
];

describe('Performance regression tests', () => {
  const results: Record<string, TimingResult> = {};
  const baselines: Record<string, number> = {};

  it.each(endpoints)('$name P95 < baseline + 20% and < 100ms', async ({ name, url, init }) => {
    // Load baseline from KV (set during a separate CI baseline-update job)
    const baselineRaw = await env.PERF_BASELINES.get(`p95:${name}`);
    const baseline = baselineRaw ? parseFloat(baselineRaw) : null;
    if (baseline !== null) {
      baselines[name] = baseline;
    }

    const timing = await measureFetchTiming(url, init ?? {}, RUNS);
    results[name] = timing;

    console.log(`[${name}] P95=${timing.p95.toFixed(2)}ms P50=${timing.p50.toFixed(2)}ms baseline=${baseline?.toFixed(2) ?? 'none'}ms`);

    // Assert absolute ceiling
    expect(
      timing.p95,
      `${name}: P95 ${timing.p95.toFixed(2)}ms exceeds hard limit of ${P95_HARD_LIMIT_MS}ms`,
    ).toBeLessThan(P95_HARD_LIMIT_MS);

    // Assert regression threshold (only when baseline exists)
    if (baseline !== null) {
      const regressionFactor = (timing.p95 - baseline) / baseline;
      expect(
        regressionFactor,
        `${name}: P95 regressed ${(regressionFactor * 100).toFixed(1)}% over baseline (${baseline.toFixed(2)}ms → ${timing.p95.toFixed(2)}ms). Threshold: ${REGRESSION_THRESHOLD * 100}%`,
      ).toBeLessThanOrEqual(REGRESSION_THRESHOLD);
    }
  });

  afterAll(() => {
    // Write timing table to GitHub Actions Job Summary
    const summaryPath = process.env.GITHUB_STEP_SUMMARY;
    if (summaryPath && Object.keys(results).length > 0) {
      const table = formatTimingTable(results, baselines);
      appendFileSync(summaryPath, `\n${table}\n`);
    }
  });
});
```

---

## CI Pipeline

```yaml
# .github/workflows/perf.yml
name: Performance Regression

on:
  push:
    branches: [main]
  pull_request:

jobs:
  perf-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci

      # On main branch: update baseline after tests pass
      - name: Run performance tests
        run: npx vitest run test/perf --reporter=verbose
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

      # Update baselines in KV only when merging to main
      - name: Update performance baselines
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: node scripts/update-perf-baselines.mjs
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          KV_NAMESPACE_ID: ${{ secrets.PERF_BASELINES_KV_ID }}
```

```javascript
// scripts/update-perf-baselines.mjs
// Reads timing output from the last test run and updates KV baselines
// Run after tests pass on main branch
import { execSync } from 'child_process';

const results = JSON.parse(process.env.PERF_RESULTS_JSON ?? '{}');
const namespaceId = process.env.KV_NAMESPACE_ID;
const token = process.env.CLOUDFLARE_API_TOKEN;
const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;

for (const [endpoint, p95] of Object.entries(results)) {
  const key = encodeURIComponent(`p95:${endpoint}`);
  execSync(
    `curl -s -X PUT "https://api.cloudflare.com/client/v4/accounts/${accountId}/storage/kv/namespaces/${namespaceId}/values/${key}" \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: text/plain" \
      --data "${p95}"`,
  );
  console.log(`Updated baseline for ${endpoint}: ${p95}ms`);
}
```

---

## Anti-patterns
- **Measuring time with `Date.now()`** — `Date.now()` has millisecond resolution and is affected by system clock adjustments. Use `performance.now()` for sub-millisecond precision.
- **Running timing measurements in parallel** — Parallel `SELF.fetch()` calls in Miniflare contend for the same event loop, producing artificially inflated and inconsistent latencies. Always run timing samples sequentially.
- **Storing baselines only in the repo** — Baselines committed to git require a PR to update, which creates friction. KV allows automated updates on main-branch merges without requiring a code change PR.
- **Using only mean latency** — Mean hides tail latency spikes. P95 represents the experience of 1 in 20 users and is the right metric for catching regressions that affect real users under load.

---

## Gotchas
- `performance.now()` in the Miniflare environment measures wall-clock time on the test runner host, not CPU time inside the Worker isolate. It includes serialization overhead from the worker pool boundary.
- The first request to a Worker in Miniflare may incur JIT warm-up overhead. Always discard a warm-up request before collecting timing samples.
- GitHub Actions runners have variable CPU availability. Use `self-hosted` runners or add a ±30% baseline tolerance for hosted runners to avoid flaky failures due to infrastructure noise.
- KV writes from the `update-perf-baselines` script take up to 60 seconds to propagate globally. If your CI jobs run in rapid succession, a PR job may read a stale baseline from a just-updated main merge.

---

## Verification

```bash
# Run performance tests locally
npx vitest run test/perf --reporter=verbose

# View timing output
npx vitest run test/perf 2>&1 | grep '\[GET\|\[POST'

# Check what baselines are stored in KV
wrangler kv key list --namespace-id=YOUR_KV_NAMESPACE_ID
wrangler kv key get "p95:GET /api/users" --namespace-id=YOUR_KV_NAMESPACE_ID

# Update a single baseline manually
wrangler kv key put "p95:GET /api/users" "12.5" --namespace-id=YOUR_KV_NAMESPACE_ID
```

---

## Related
- `workers-test-coverage-c8-vitest.md`
- `workers-api-contract-testing-zod.md`
- `workers-golden-file-testing-api-responses.md`

---

## Sources
- Cloudflare Workers Vitest integration — https://developers.cloudflare.com/workers/testing/vitest-integration/
- performance.now() in Workers — https://developers.cloudflare.com/workers/runtime-apis/performance/
- GitHub Actions Job Summary — https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#adding-a-job-summary
- Cloudflare KV API — https://developers.cloudflare.com/kv/api/
