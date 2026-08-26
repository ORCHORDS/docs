# Performance Regression Detection in CI Using Workers Analytics Engine Baselines

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Workers deployment that increases p99 handler latency by 40 ms goes undetected because smoke tests only check for error-free responses, not response time. By querying a rolling production baseline from Analytics Engine at deploy time, a CI gate can compare the candidate build's benchmark results against the real-world p99 and block the release automatically when the regression exceeds a configurable threshold.

## Context

Cloudflare Workers Analytics Engine stores per-request duration, status, and route data written by a tracing Worker binding. During CI, a benchmark script exercises the new Worker build against a preview deployment and then pulls the last 24-hour p75/p99 baseline for the same routes from the production dataset. The comparison is run as a final gate step in a GitHub Actions workflow before `wrangler deploy` is allowed to continue. Regressions above the threshold produce a structured JSON diff that is posted as a PR check annotation.

## Analytics Engine Baseline Query Helper

```typescript
// scripts/fetch-baseline.ts — run with `tsx` in CI
import { z } from "zod";

const RowSchema = z.object({
  route: z.string(),
  p75_ms: z.number(),
  p99_ms: z.number(),
  samples: z.number(),
});

export type BaselineRow = z.infer<typeof RowSchema>;

const QUERY = `
  SELECT
    blob1                              AS route,
    quantileWeighted(0.75)(double1, 1) AS p75_ms,
    quantileWeighted(0.99)(double1, 1) AS p99_ms,
    count()                            AS samples
  FROM worker_requests
  WHERE timestamp >= now() - INTERVAL '24' HOUR
    AND double2 < 500               -- exclude 5xx (double2 = status code)
  GROUP BY route
  HAVING samples >= 100
`;

export async function fetchBaseline(
  accountId: string,
  apiToken: string,
): Promise<Map<string, BaselineRow>> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: QUERY }),
    },
  );

  if (!res.ok) {
    throw new Error(`Analytics Engine query failed: ${res.status} ${await res.text()}`);
  }

  const json = await res.json() as { data: unknown[] };
  const rows = json.data.map((r) => RowSchema.parse(r));
  return new Map(rows.map((r) => [r.route, r]));
}
```

## Benchmark Runner Against Preview Deployment

```typescript
// scripts/benchmark.ts
interface BenchmarkResult {
  route: string;
  p75_ms: number;
  p99_ms: number;
  samples: number;
}

export async function runBenchmark(
  previewUrl: string,
  routes: { path: string; method?: string }[],
  iterations = 200,
): Promise<Map<string, BenchmarkResult>> {
  const results = new Map<string, number[]>();

  for (const { path, method = "GET" } of routes) {
    const latencies: number[] = [];
    // Serial requests to avoid preview CPU over-subscription skewing results
    for (let i = 0; i < iterations; i++) {
      const start = performance.now();
      const res = await fetch(`${previewUrl}${path}`, { method });
      await res.arrayBuffer();
      if (res.ok) latencies.push(performance.now() - start);
    }
    results.set(path, latencies.sort((a, b) => a - b));
  }

  const out = new Map<string, BenchmarkResult>();
  for (const [route, latencies] of results) {
    const p = (pct: number) => latencies[Math.floor((latencies.length - 1) * pct)] ?? 0;
    out.set(route, { route, p75_ms: p(0.75), p99_ms: p(0.99), samples: latencies.length });
  }
  return out;
}
```

## CI Gate Script

```typescript
// scripts/perf-gate.ts — called from GitHub Actions after wrangler deploy --dry-run
import { fetchBaseline } from "./fetch-baseline.js";
import { runBenchmark } from "./benchmark.js";

const P99_THRESHOLD = 0.20;  // block if candidate p99 > baseline p99 × 1.20
const P75_THRESHOLD = 0.15;

const accountId = process.env.CF_ACCOUNT_ID!;
const apiToken = process.env.CF_API_TOKEN!;
const previewUrl = process.env.PREVIEW_URL!;

const ROUTES = [
  { path: "/api/v1/products" },
  { path: "/api/v1/search?q=test" },
  { path: "/api/v1/user/me" },
];

const [baseline, candidate] = await Promise.all([
  fetchBaseline(accountId, apiToken),
  runBenchmark(previewUrl, ROUTES),
]);

let failed = false;
const findings: object[] = [];

for (const [route, cand] of candidate) {
  const base = baseline.get(route);
  if (!base || base.samples < 100) continue;  // not enough production data to gate

  const p99Delta = (cand.p99_ms - base.p99_ms) / base.p99_ms;
  const p75Delta = (cand.p75_ms - base.p75_ms) / base.p75_ms;

  if (p99Delta > P99_THRESHOLD || p75Delta > P75_THRESHOLD) {
    failed = true;
    findings.push({
      route,
      baseline_p75: base.p75_ms.toFixed(1),
      candidate_p75: cand.p75_ms.toFixed(1),
      delta_p75_pct: (p75Delta * 100).toFixed(1),
      baseline_p99: base.p99_ms.toFixed(1),
      candidate_p99: cand.p99_ms.toFixed(1),
      delta_p99_pct: (p99Delta * 100).toFixed(1),
    });
  }
}

if (findings.length) {
  console.log("::error::Performance regression detected");
  console.log(JSON.stringify(findings, null, 2));
}

process.exit(failed ? 1 : 0);
```

## GitHub Actions Integration

```yaml
# .github/workflows/deploy.yml (relevant steps only)
- name: Run perf gate
  env:
    CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
    CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    PREVIEW_URL: ${{ steps.deploy-preview.outputs.url }}
  run: npx tsx scripts/perf-gate.ts

- name: Deploy to production
  if: success()
  run: wrangler deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Anti-patterns

- Gating on mean latency instead of p99 — a bimodal distribution can have a stable mean while the tail regresses 3×, masking real user impact.
- Pulling a 5-minute baseline window — too short to be statistically stable; use 24 hours minimum, or 7 days for low-traffic routes.
- Running benchmark requests in parallel against a preview deployment that cold-starts each isolate — serialise warm-up requests first, then measure.

## Gotchas

- Analytics Engine SQL queries have a 1 000 000 row scan limit per query — add a `HAVING samples >= 100` clause to drop low-traffic routes before they bloat the result set.
- Preview deployments share the same Workers platform but have different KV and D1 bindings by default; ensure the preview environment points to staging data stores, not production, to avoid test pollution.

## Verification

```bash
# Dry-run the gate locally against a deployed preview
PREVIEW_URL=https://my-worker.preview.workers.dev \
CF_ACCOUNT_ID=abc123 \
CF_API_TOKEN=your_token \
npx tsx scripts/perf-gate.ts

# Inspect the last 24-hour baseline interactively
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"query":"SELECT blob1, quantileWeighted(0.99)(double1,1) AS p99 FROM worker_requests WHERE timestamp > now() - INTERVAL '\''24'\'' HOUR GROUP BY blob1 ORDER BY p99 DESC LIMIT 20"}' \
  | jq '.data'
```

## Related

- `monitoring/analytics-engine-sql-api-programmatic-querying.md`
- `monitoring/cloudflare-analytics-engine.md`
- `monitoring/query-performance-regression-detection.md`
- `monitoring/slo-error-budget-workers-pages.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/testing/integration-testing/
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions
