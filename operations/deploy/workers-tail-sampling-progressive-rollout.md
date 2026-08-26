# Workers Tail Sampling for Progressive Rollout Observability

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

During a progressive (canary) rollout of a new Worker version, engineering teams need real-time visibility into error rates, latency distributions, and specific failing requests on the new version — without drowning in logs from the existing 95% of traffic still on the old version. The standard `wrangler tail` command streams all events from a Worker, but does not distinguish between versions and does not support structured sampling rules that vary by version weight.

Tail sampling with a dedicated tail Worker solves this: the tail Worker receives every event from the main Worker, applies version-aware sampling, and forwards only a statistically valid sample to an observability sink (Logpush, Analytics Engine, or a third-party platform). This gives accurate signal on the canary version without log storage costs proportional to total traffic.

## Context

Cloudflare Workers support a `tail` consumer: a second Worker configured to receive `TraceItem` objects for every invocation of the main Worker. The tail Worker runs asynchronously, does not affect the main Worker's response time, and receives metadata including the `scriptVersion` field that identifies which deployed version handled each request.

Workers Versions (the versioned deploy system behind `wrangler versions upload` and `wrangler versions deploy`) gives each uploaded bundle a unique `versionId`. The tail Worker can read this `versionId` from the `TraceItem` and apply different sampling rates per version — for example, 100% of canary traffic and 0.1% of stable traffic.

## Configuring the Tail Worker Consumer

```toml
# wrangler.toml (main Worker)
name = "my-api"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[tail_consumers]]
service = "my-api-tail-sampler"
```

```toml
# workers/tail-sampler/wrangler.toml
name = "my-api-tail-sampler"
main = "src/index.ts"
compatibility_date = "2026-01-01"

# Analytics Engine for storing sampled events
[[analytics_engine_datasets]]
binding = "TRACE_AE"
dataset = "worker_traces"

[vars]
# Version IDs are injected by CI after wrangler versions upload
CANARY_VERSION_ID = ""        # overridden at deploy time
CANARY_SAMPLE_RATE = "1.0"   # 100% of canary traffic
STABLE_SAMPLE_RATE = "0.001" # 0.1% of stable traffic
```

## Tail Worker Implementation

```typescript
// workers/tail-sampler/src/index.ts
import type { TraceItem, AnalyticsEngineDataset } from "@cloudflare/workers-types";

export interface Env {
  TRACE_AE: AnalyticsEngineDataset;
  CANARY_VERSION_ID: string;
  CANARY_SAMPLE_RATE: string;
  STABLE_SAMPLE_RATE: string;
}

function shouldSample(versionId: string, env: Env): boolean {
  const isCanary = versionId === env.CANARY_VERSION_ID;
  const rate = isCanary
    ? parseFloat(env.CANARY_SAMPLE_RATE)
    : parseFloat(env.STABLE_SAMPLE_RATE);
  return Math.random() < rate;
}

function extractTraceFields(event: TraceItem) {
  const req = event.logs[0] ?? null;
  return {
    version_id: event.scriptVersion?.id ?? "unknown",
    version_tag: event.scriptVersion?.tag ?? "",
    outcome: event.outcome,
    cpu_ms: event.cpuTime ?? 0,
    wall_ms: event.wallTime ?? 0,
    status: event.response?.status ?? 0,
    url: event.request?.url ?? "",
    method: event.request?.method ?? "",
    cf_ray: event.request?.headers?.["cf-ray"] ?? "",
    error: event.outcome !== "ok"
      ? (event.exceptions?.[0]?.message ?? "")
      : "",
    timestamp: new Date(event.eventTimestamp ?? Date.now()).toISOString(),
  };
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const versionId = event.scriptVersion?.id ?? "unknown";

      if (!shouldSample(versionId, env)) continue;

      const fields = extractTraceFields(event);
      const isCanary = versionId === env.CANARY_VERSION_ID;

      // Write to Analytics Engine
      env.TRACE_AE.writeDataPoint({
        blobs: [
          fields.version_id,
          fields.version_tag,
          fields.outcome,
          fields.url,
          fields.method,
          fields.cf_ray,
          fields.error,
          isCanary ? "canary" : "stable",
        ],
        doubles: [
          fields.cpu_ms,
          fields.wall_ms,
          fields.status,
          isCanary ? 1 : 0,
        ],
        indexes: [fields.version_id],
      });
    }
  },
};
```

## CI Integration: Injecting the Canary Version ID

After uploading the canary version, the CI pipeline captures the new `versionId` and updates the tail Worker's `CANARY_VERSION_ID` binding so sampling targets the correct version.

```yaml
# .github/workflows/canary-deploy.yml
name: Canary Deploy with Tail Sampling

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      - name: Upload new Worker version (canary)
        id: upload
        run: |
          OUTPUT=$(npx wrangler versions upload \
            --tag "canary-${{ github.sha }}" \
            --message "Canary: ${{ github.sha }}" 2>&1)
          echo "$OUTPUT"
          VERSION_ID=$(echo "$OUTPUT" | grep -oP 'Version ID:\s+\K[a-f0-9-]+')
          echo "version_id=$VERSION_ID" >> $GITHUB_OUTPUT
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Update tail sampler with canary version ID
        run: |
          npx wrangler secret put CANARY_VERSION_ID \
            --name my-api-tail-sampler \
            <<< "${{ steps.upload.outputs.version_id }}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy canary at 10% traffic
        run: |
          npx wrangler versions deploy \
            --version-id ${{ steps.upload.outputs.version_id }} \
            --percentage 10
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Monitor canary for 10 minutes
        run: |
          sleep 600
          # Query Analytics Engine for canary error rate
          node scripts/check-canary-error-rate.mjs \
            --version-id "${{ steps.upload.outputs.version_id }}" \
            --threshold 0.01  # 1% max error rate
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## Querying Sampled Traces from Analytics Engine

```typescript
// scripts/check-canary-error-rate.mjs
import { parseArgs } from "util";

const { values } = parseArgs({
  args: process.argv.slice(2),
  options: {
    "version-id": { type: "string" },
    threshold: { type: "string", default: "0.01" },
  },
});

const versionId = values["version-id"];
const threshold = parseFloat(values.threshold);

const query = `
  SELECT
    SUM(IF(blob3 = 'ok', 1, 0)) as ok_count,
    SUM(IF(blob3 != 'ok', 1, 0)) as error_count,
    COUNT() as total
  FROM worker_traces
  WHERE blob1 = '${versionId}'
    AND timestamp > NOW() - INTERVAL '10' MINUTE
`;

const resp = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${process.env.CF_ACCOUNT_ID}/analytics_engine/sql`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.CF_API_TOKEN}`,
      "Content-Type": "text/plain",
    },
    body: query,
  }
);

const data = await resp.json();
const row = data.data[0];

if (!row) {
  console.warn("No trace data for version yet — may be too early");
  process.exit(0);
}

const errorRate = row.error_count / row.total;
console.log(`Canary error rate: ${(errorRate * 100).toFixed(2)}% (${row.error_count}/${row.total})`);

if (errorRate > threshold) {
  console.error(`Error rate ${(errorRate * 100).toFixed(2)}% exceeds threshold ${(threshold * 100).toFixed(2)}%`);
  process.exit(1);
}
```

## Anti-patterns

- Setting `CANARY_SAMPLE_RATE = "1.0"` on a high-traffic Worker without estimating Analytics Engine write costs — 100% sampling on millions of requests per minute will exhaust your AE budget
- Forgetting to update `CANARY_VERSION_ID` when the canary version changes — the sampler will continue tagging the old canary, making version attribution wrong
- Using `wrangler tail` (streaming CLI) as the only observability tool during a canary — it disconnects on network interruptions and loses events
- Storing sensitive request data (authorization headers, PII in URLs) in the trace blobs without redaction
- Deploying the tail Worker to the same script as the main Worker — tail consumers must be separate Worker scripts

## Gotchas

- The `tail` export handler receives a batch of `TraceItem` objects, not individual events — process all items in the array
- Tail Workers have a 30-second CPU time limit per invocation; avoid synchronous HTTP calls inside the tail handler
- `event.scriptVersion` is `undefined` for Workers deployed before the Versions system was enabled for the account — handle gracefully
- Analytics Engine SQL queries have eventual consistency; recent traces (< 1 minute old) may not appear in query results
- `wrangler versions deploy` with `--percentage` requires that the Worker was already deployed at least once with `wrangler deploy` — first-time deploys must use `wrangler deploy`
- The tail consumer binding in `wrangler.toml` (`[[tail_consumers]]`) must reference the tail Worker by its `name`, not its URL

## Verification

1. Deploy the tail sampler, then make a test request to the main Worker. Run: `npx wrangler tail --name my-api-tail-sampler` and confirm you see a `TraceItem` within 30 seconds.
2. Query Analytics Engine after 5 minutes of canary traffic: `SELECT blob8 as variant, COUNT() as n, AVG(double2) as avg_wall_ms FROM worker_traces GROUP BY blob8` — you should see separate rows for `canary` and `stable`.
3. Verify `CANARY_VERSION_ID` is set correctly: compare it against `npx wrangler versions list` output.
4. Confirm sampling rates by checking the ratio of `n` in Analytics Engine vs. total requests in the Cloudflare dashboard — canary should be ~100% sampled, stable ~0.1%.

## Related

- `worker-versioning-gradual-rollout.md` — gradual traffic splitting with Workers Versions
- `workers-tail-worker-deploy-validation.md` — using tail Workers for deploy validation
- `cloudflare-analytics-engine-deploy-observability.md` — Analytics Engine setup for observability
- `canary-workers-gradual-traffic-split.md` — canary traffic split patterns

## Sources

- Cloudflare Workers: Tail Workers: https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- Cloudflare Workers: Workers Versions: https://developers.cloudflare.com/workers/configuration/versions-and-gradual-deployments/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
