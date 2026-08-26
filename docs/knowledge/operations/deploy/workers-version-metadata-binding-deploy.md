# Using the Workers Version Metadata Binding to Expose Deployment Context at Runtime

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker needs to know at runtime which deployed version is currently serving a request — without baking the version into environment variables — so that you can log deployment-aware analytics, implement gradual rollout guards, or surface version info in health-check endpoints. The Workers Version Metadata binding injects this context automatically on each request without any build-time configuration.

---

## Context

The Workers Version Metadata binding is a special binding type introduced alongside Workers Gradual Rollouts. When declared in `wrangler.toml`, it exposes a `VERSION` object on the `env` argument of every `fetch`, `scheduled`, and `queue` handler. The object carries three fields: `id` (a unique UUID per deployment version), `tag` (an optional string you supply at deploy time), and `timestamp` (the ISO 8601 time the version was uploaded). This makes it possible to correlate production incidents with specific deploys, emit per-version request counts to Analytics Engine, and assert in integration tests that the expected version is live. The binding is read-only and zero-cost — it adds no latency and requires no external service call. Version tags are set via `wrangler deploy --tag <tag>` and are typically the Git SHA or semantic version string from CI.

---

## Section 1 — wrangler.toml Configuration

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]

# Version Metadata binding — exposes id, tag, timestamp on env.VERSION
[version_metadata]
binding = "VERSION"

# Analytics Engine for per-version metrics
[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "worker_requests"

[vars]
SERVICE_NAME = "my-worker"

[env.staging]
name = "my-worker-staging"

[env.staging.version_metadata]
binding = "VERSION"

[env.staging.analytics_engine_datasets]
binding = "ANALYTICS"
dataset = "worker_requests_staging"
```

---

## Section 2 — Worker Implementation

```typescript
// src/index.ts
export interface Env {
  VERSION: {
    id: string;
    tag: string;
    timestamp: string;
  };
  ANALYTICS: AnalyticsEngineDataset;
  SERVICE_NAME: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Health check — expose version metadata to monitoring systems
    if (url.pathname === '/health') {
      return Response.json({
        status: 'ok',
        version: {
          id: env.VERSION.id,
          tag: env.VERSION.tag,
          timestamp: env.VERSION.timestamp,
        },
        service: env.SERVICE_NAME,
      });
    }

    // Log version info to Analytics Engine on every request (non-blocking)
    ctx.waitUntil(logVersionMetrics(request, env));

    return new Response('Hello from ' + env.VERSION.tag, {
      headers: {
        'X-Version-Id': env.VERSION.id,
        'X-Version-Tag': env.VERSION.tag,
        'Content-Type': 'text/plain',
      },
    });
  },

  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Version metadata available in cron handlers too
    console.log(JSON.stringify({
      type: 'cron',
      cron: event.cron,
      versionId: env.VERSION.id,
      versionTag: env.VERSION.tag,
    }));
  },
} satisfies ExportedHandler<Env>;

async function logVersionMetrics(request: Request, env: Env): Promise<void> {
  const url = new URL(request.url);
  try {
    env.ANALYTICS.writeDataPoint({
      blobs: [
        env.VERSION.id,
        env.VERSION.tag,
        request.method,
        url.pathname,
        request.headers.get('CF-Connecting-IP') ?? 'unknown',
      ],
      doubles: [Date.now()],
      indexes: [env.VERSION.id],
    });
  } catch (err) {
    // Analytics failures must never surface to the user
    console.error('analytics write failed', err);
  }
}
```

---

## Section 3 — CI Deploy with Version Tag and Verification

```yaml
# .github/workflows/deploy-versioned.yml
name: Deploy Versioned Worker

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm

      - run: npm ci

      - name: Deploy with version tag
        id: deploy
        run: |
          GIT_TAG="$(git rev-parse --short HEAD)"
          npx wrangler deploy --tag "$GIT_TAG"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Wait for propagation
        run: sleep 5

      - name: Verify deployed version via health endpoint
        run: |
          GIT_TAG="$(git rev-parse --short HEAD)"
          RESPONSE=$(curl -s https://my-worker.example.com/health)
          ACTUAL_TAG=$(echo "$RESPONSE" | jq -r '.version.tag')
          if [ "$ACTUAL_TAG" != "$GIT_TAG" ]; then
            echo "ERROR: expected tag $GIT_TAG but got $ACTUAL_TAG"
            echo "Response: $RESPONSE"
            exit 1
          fi
          echo "Version tag verified: $ACTUAL_TAG"
```

```typescript
// scripts/query-version-analytics.ts
// Query Analytics Engine for per-version request counts
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

const query = `
  SELECT
    blob1 AS version_id,
    blob2 AS version_tag,
    count() AS requests
  FROM worker_requests
  WHERE timestamp > NOW() - INTERVAL '1' HOUR
  GROUP BY version_id, version_tag
  ORDER BY requests DESC
`;

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
  {
    method: 'POST',
    headers: { Authorization: `Bearer ${API_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  }
);
const data = await res.json();
console.table((data as { data: unknown[] }).data);
```

---

## Anti-patterns
- **Reading `env.VERSION` in module-level code** — the binding is only populated inside a handler function; accessing it at module initialisation returns `undefined`.
- **Using version tag as the sole deployment identifier** — tags are optional strings and are not guaranteed unique; always use `env.VERSION.id` as the canonical key.
- **Logging version info synchronously in the hot path** — always wrap Analytics Engine writes in `ctx.waitUntil()` to avoid adding latency to the response.
- **Omitting the `[version_metadata]` block for each `[env.X]` stanza** — bindings do not inherit across environments; each named environment must redeclare the binding.

---

## Gotchas
- `env.VERSION.tag` is an empty string (`""`) if you deploy without `--tag`; add a guard in health-check responses to avoid misleading output.
- The binding name (`VERSION`) is configurable; choose a name that does not collide with your own environment variables.
- Workers Gradual Rollouts use the same version system — when a version is in a partial rollout, different requests may see different `env.VERSION.id` values across the same deployment.
- Analytics Engine SQL queries have a 25 MB response size limit; use `LIMIT` clauses when querying high-traffic datasets.

---

## Verification

```bash
# Deploy with a git-sha tag
npx wrangler deploy --tag "$(git rev-parse --short HEAD)"

# Check version metadata live
curl -s https://my-worker.example.com/health | jq .version

# Inspect response headers for version info
curl -I https://my-worker.example.com/ 2>&1 | grep -i x-version

# List all deployed versions
npx wrangler versions list
```

---

## Related
- `cloudflare-pages-deploy-hooks-external-ci.md`
- `wrangler-deploy-dry-run-schema-validation.md`

---

## Sources
- Workers Version Metadata binding — https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/
- Workers Gradual Rollouts — https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
