# Workers Version Deployment Health Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A new Workers version rolls out via a gradual deployment (traffic split) and error rates
silently increase on the incoming version before 100% of traffic shifts. Without per-version
instrumentation you only see aggregate error rate and cannot tell whether the new version
or the stable version is the source. You need per-version error/latency breakdowns visible
within the first few percent of traffic so you can halt the rollout automatically.

## Context

Cloudflare Workers deployments expose `CF-Worker-Version` in the request metadata accessible
via `env.CF_VERSION_METADATA` (available in the Workers runtime since 2024-Q4) and via Tail
Workers' `TailEvent.scriptVersion`. Combining this with Analytics Engine lets you emit
per-version error and latency blobs that feed a GraphQL dashboard and burn-rate alert.

The pattern works for both gradual rollouts and Wrangler `--compatibility-date` bumps. A
companion Tail Worker is the recommended collection point because it runs outside the critical
path of the primary Worker and has access to the full event envelope including `outcome`.

---

## 1. Emitting Version Telemetry from the Primary Worker

```typescript
// src/index.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  CF_VERSION_METADATA: WorkerVersionMetadata;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    let statusCode = 200;

    try {
      const response = await handleRequest(request, env);
      statusCode = response.status;
      return response;
    } catch (err) {
      statusCode = 500;
      throw err;
    } finally {
      const latencyMs = Date.now() - start;
      const versionId = env.CF_VERSION_METADATA?.id ?? 'unknown';
      const versionTag = env.CF_VERSION_METADATA?.tag ?? 'untagged';

      ctx.waitUntil(
        Promise.resolve(
          env.ANALYTICS.writeDataPoint({
            blobs: [versionId, versionTag, request.method, String(statusCode)],
            doubles: [latencyMs, statusCode >= 500 ? 1 : 0],
            indexes: [versionId],
          })
        )
      );
    }
  },
};
```

## 2. Collecting Version Health via a Tail Worker

```typescript
// tail/index.ts  — wrangler.toml: services = [{ service = "my-worker", tail = true }]
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

interface ScriptVersion {
  id: string;
  tag?: string;
  message?: string;
}

export default {
  async tail(events: TailEvent[], env: Env): Promise<void> {
    for (const event of events) {
      const version = (event as any).scriptVersion as ScriptVersion | undefined;
      const versionId = version?.id ?? 'unknown';
      const versionTag = version?.tag ?? 'untagged';
      const isError = event.outcome !== 'ok';
      const cpuMs = event.cpuTime ?? 0;
      const wallMs = event.wallTime ?? 0;

      env.ANALYTICS.writeDataPoint({
        blobs: [
          versionId,
          versionTag,
          event.outcome,
          event.scriptName ?? '',
        ],
        doubles: [
          isError ? 1 : 0,   // index 0: error flag
          cpuMs,              // index 1: cpu time ms
          wallMs,             // index 2: wall time ms
        ],
        indexes: [versionId],
      });
    }
  },
};
```

## 3. Analytics Engine Schema and GraphQL Query

```graphql
# Blob layout (tail worker):
#   blob1 = version_id, blob2 = version_tag, blob3 = outcome, blob4 = script_name
# Double layout:
#   double1 = is_error (0|1), double2 = cpu_ms, double3 = wall_ms

query VersionHealthLast30Min($accountId: String!) {
  viewer {
    accounts(filter: { accountTag: $accountId }) {
      workersInvocationsAdaptive(
        filter: {
          datetime_geq: "2026-08-23T00:00:00Z"
          datetime_leq: "2026-08-23T00:30:00Z"
        }
        limit: 10000
      ) {
        sum { requests }
        avg { cpuTime }
        dimensions {
          scriptVersion
          outcome
        }
      }
      # Custom Analytics Engine dataset for version blobs:
      tailDeploymentHealth: analyticsEngineDataset(
        datasetName: "deployment_health"
      ) {
        sum { double1 }   # total errors
        count            # total requests
        dimensions { blob1 blob2 blob3 }
      }
    }
  }
}
```

## 4. Automated Rollout Halt via Scheduled Worker

```typescript
// monitor/rollout-guard.ts  — runs every 2 minutes via cron
export interface Env {
  ROLLOUT_KV: KVNamespace;
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  CF_WORKER_NAME: string;
  ANALYTICS_API_TOKEN: string;
}

const ERROR_RATE_THRESHOLD = 0.05; // 5% errors triggers halt

async function queryVersionErrorRate(env: Env, versionId: string): Promise<number> {
  const query = `
    SELECT
      SUM(_sample_interval * double1) AS errors,
      SUM(_sample_interval) AS total
    FROM deployment_health
    WHERE blob1 = '${versionId}'
      AND timestamp >= NOW() - INTERVAL '5' MINUTE
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.ANALYTICS_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    }
  );
  const json = (await res.json()) as { data: Array<{ errors: number; total: number }> };
  const row = json.data[0];
  if (!row || row.total === 0) return 0;
  return row.errors / row.total;
}

async function haltRollout(env: Env, versionId: string): Promise<void> {
  // Set traffic split back to 100% on the previous stable version via Wrangler API
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/workers/services/${env.CF_WORKER_NAME}/environments/production/traffic`,
    {
      method: 'PUT',
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ split: [{ version_id: versionId, percentage: 0 }] }),
    }
  );
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const incomingVersion = await env.ROLLOUT_KV.get('incoming_version_id');
    if (!incomingVersion) return;

    const errorRate = await queryVersionErrorRate(env, incomingVersion);
    if (errorRate > ERROR_RATE_THRESHOLD) {
      await haltRollout(env, incomingVersion);
      await env.ROLLOUT_KV.delete('incoming_version_id');
      console.error(`[rollout-guard] Halted version ${incomingVersion}: error_rate=${errorRate.toFixed(3)}`);
    }
  },
};
```

## 5. Version Tag Convention

```toml
# wrangler.toml — tag every deployment with a semver or git SHA
[version_metadata]
enabled = true

# In CI (GitHub Actions):
# wrangler deploy --tag "v1.4.2-$(git rev-parse --short HEAD)"
```

```typescript
// Read tag in the Worker for structured logging
const tag = env.CF_VERSION_METADATA?.tag ?? 'unknown';
// Expected format: "v1.4.2-abc1234"
const [semver, sha] = tag.split('-');
console.log(JSON.stringify({ version: semver, sha, route: new URL(request.url).pathname }));
```

## 6. Wrangler Gradual Rollout + Monitor Integration

```bash
# Deploy new version at 10% traffic
wrangler deploy --tag "v1.5.0-$(git rev-parse --short HEAD)" --no-bundle=false

# Set gradual split (requires Wrangler >=3.75)
wrangler versions upload
wrangler versions deploy --version-percentage 10

# Store incoming version ID in KV so the monitor can watch it
wrangler kv:key put --namespace-id=<KV_ID> incoming_version_id "<new-version-id>"
```

---

## Anti-patterns

- **Reading version inside the primary Worker for error counting**: adds latency on every
  request. Use a Tail Worker so version telemetry is off the critical path.
- **Using a single `outcome` counter without per-version dimensions**: masks whether the
  new or old version is misbehaving during a traffic split.
- **Halting rollout based on absolute error count**: use error *rate* so low-traffic
  canaries aren't falsely stable and high-traffic ones aren't falsely sensitive.
- **Not tagging deployments**: `CF_VERSION_METADATA.id` is a UUID; without a `tag` you
  cannot correlate a version to a git SHA or release in your dashboard.

## Gotchas

- `env.CF_VERSION_METADATA` is only populated when the binding is declared in `wrangler.toml`
  under `[version_metadata] enabled = true`. Omitting it yields `undefined` at runtime.
- Tail Workers receive `scriptVersion` as an unstable field; fall back to `'unknown'` defensively.
- The Analytics Engine SQL API enforces a 5-minute minimum `timestamp` filter floor for
  freshness; very recent points (< 1 minute) may not yet appear.
- `writeDataPoint` is fire-and-forget but silently drops blobs if the dataset binding is
  missing — test with `wrangler tail` first to confirm blobs are emitted.

## Verification

```bash
# Confirm version metadata binding is active
wrangler tail my-worker --format pretty | grep version_id

# Query error rate for the last 10 minutes
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"SELECT blob1, SUM(_sample_interval*double1)/SUM(_sample_interval) AS error_rate FROM deployment_health WHERE timestamp >= NOW() - INTERVAL '\''10'\'' MINUTE GROUP BY blob1"}'
```

## Related

- `workers-ai-inference-cost-analytics-engine-tracking.md`
- `performance-regression-ci-workers-baseline.md`
- `canary-deployment-metric-baseline-comparison.md`
- `tail-worker-structured-error-classification-d1.md`
- `workers-error-rate-anomaly-detection-d1.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/
