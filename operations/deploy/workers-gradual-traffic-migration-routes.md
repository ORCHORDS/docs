# Gradual Traffic Migration Between Worker Versions Using Routes

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to shift production traffic from an old Worker version to a new one without a hard cutover. A full swap risks exposing all users to a regression at once. You want to ramp traffic 5% → 25% → 50% → 100% while watching error rates, and to roll back automatically if errors spike.

## Context

Cloudflare Workers routes are evaluated in priority order (lower `priority` number wins). The platform does not natively support weighted traffic split, but you can implement percentage-based routing with a short KV read on every request. The KV operation adds ~1 ms and can be eliminated by encoding the sample threshold directly in the Worker code as a constant during the ramp.

Two Workers exist: `api-worker-stable` (the current version) and `api-worker-canary` (the new version). Both are fully deployed; the migration only changes which Worker handles a given request.

## Solution

### Route priority ordering

Create two routes for the same pattern, one per Worker:

```toml
# wrangler.toml — api-worker-canary
name = "api-worker-canary"
routes = [
  { pattern = "api.example.com/*", zone_name = "example.com", priority = 1 }
]

# wrangler.toml — api-worker-stable
name = "api-worker-stable"
routes = [
  { pattern = "api.example.com/*", zone_name = "example.com", priority = 2 }
]
```

Priority 1 wins, so every request hits the canary by default. The canary Worker proxies a configurable percentage back to the stable Worker using a Service Binding.

### KV-controlled traffic split

```typescript
// src/canary-router.ts
export interface Env {
  MIGRATION_KV: KVNamespace;
  STABLE_WORKER: Fetcher; // Service Binding to api-worker-stable
}

const MIGRATION_KEY = "migration:canary_pct";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const pctRaw = await env.MIGRATION_KV.get(MIGRATION_KEY);
    const canaryPct = pctRaw ? parseFloat(pctRaw) : 0; // 0–100

    const rand = Math.random() * 100;
    if (rand >= canaryPct) {
      // Route to stable
      return env.STABLE_WORKER.fetch(request);
    }

    // Handle with canary logic
    return handleCanary(request, env);
  },
};

async function handleCanary(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  // ... new business logic ...
  return new Response(JSON.stringify({ version: "canary", path: url.pathname }), {
    headers: { "Content-Type": "application/json", "X-Worker-Version": "canary" },
  });
}
```

### Ramp script (run from CI)

```typescript
// scripts/ramp-canary.ts
import Cloudflare from "cloudflare";

const cf = new Cloudflare({ apiToken: process.env.CF_API_TOKEN });
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const NAMESPACE_ID = process.env.MIGRATION_KV_ID!;
const STEPS = [5, 25, 50, 75, 100];
const ERROR_THRESHOLD_PCT = 1.0; // abort if canary error rate exceeds this

async function setCanaryPct(pct: number): Promise<void> {
  await cf.kv.namespaces.values.update(NAMESPACE_ID, "migration:canary_pct", {
    account_id: ACCOUNT_ID,
    value: String(pct),
    metadata: JSON.stringify({ updated: new Date().toISOString() }),
  });
  console.log(`Canary traffic set to ${pct}%`);
}

async function fetchErrorRate(version: "canary" | "stable"): Promise<number> {
  // Query your observability platform (e.g., Workers Analytics Engine)
  // Returns error percentage over the last 5 minutes
  const endpoint = `https://analytics.example.com/workers/error-rate?version=${version}&window=5m`;
  const res = await fetch(endpoint, {
    headers: { Authorization: `Bearer ${process.env.ANALYTICS_TOKEN}` },
  });
  const data = (await res.json()) as { error_rate: number };
  return data.error_rate;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function main(): Promise<void> {
  for (const step of STEPS) {
    await setCanaryPct(step);
    console.log(`Waiting 5 minutes to observe metrics at ${step}%...`);
    await sleep(5 * 60 * 1000);

    const errorRate = await fetchErrorRate("canary");
    console.log(`Canary error rate: ${errorRate.toFixed(2)}%`);

    if (errorRate > ERROR_THRESHOLD_PCT) {
      console.error(`Error rate ${errorRate}% exceeds threshold ${ERROR_THRESHOLD_PCT}%. Rolling back.`);
      await setCanaryPct(0);
      process.exit(1);
    }
  }
  console.log("Migration complete. Canary is now at 100%.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

### Automated rollback trigger via Cloudflare Alerting

Configure a Worker error-rate alert in the Cloudflare dashboard (Notifications → Worker Alerts) to call a webhook:

```typescript
// src/rollback-webhook.ts  — separate Worker handling CF alert webhooks
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const secret = <redacted-secret>"CF-Webhook-Auth");
    if (secret !== env.WEBHOOK_SECRET) return new Response("Unauthorized", { status: 401 });

    const body = (await request.json()) as { data: { worker: string; metric: string } };
    if (body.data.worker === "api-worker-canary") {
      await env.MIGRATION_KV.put("migration:canary_pct", "0");
      console.log("Auto-rollback triggered by Cloudflare alert");
    }

    return new Response("OK");
  },
};
```

### Migration completion validation

```typescript
// scripts/validate-migration.ts
async function validateMigration(): Promise<void> {
  const checks = [
    { path: "/healthz", expectedStatus: 200 },
    { path: "/api/v2/ping", expectedStatus: 200 },
    { path: "/api/v2/products?limit=1", expectedStatus: 200 },
  ];

  const base = "https://api.example.com";

  for (const check of checks) {
    const res = await fetch(`${base}${check.path}`);
    if (res.status !== check.expectedStatus) {
      throw new Error(`${check.path} returned ${res.status}, expected ${check.expectedStatus}`);
    }
    const version = res.headers.get("X-Worker-Version");
    if (version !== "canary") {
      throw new Error(`${check.path} served by wrong version: ${version}`);
    }
  }

  console.log("All validation checks passed. Migration validated.");
}

validateMigration().catch((err) => {
  console.error("Validation failed:", err.message);
  process.exit(1);
});
```

## Implementation Details

- The KV read adds ~1 ms latency per request. For latency-sensitive APIs, bake the current percentage as a constant at deploy time and redeploy the canary Worker at each ramp step instead of reading from KV.
- Service Bindings are zero-latency (same data center, no HTTP overhead) — ideal for forwarding to the stable Worker.
- Tag both Workers in your observability with `version: canary` or `version: stable` via the `X-Worker-Version` response header to allow dimension filtering in Analytics Engine.
- Use `ctx.waitUntil()` to log migration routing decisions asynchronously so they do not add to response latency.

## Anti-patterns

- **Hard cutover**: Switching DNS or swapping the primary route without a ramp means 100% of users see any regression immediately.
- **Manual KV edits**: Always use the ramp script with observability gates. Manual KV edits in the dashboard skip error-rate checks.
- **Too-short observation windows**: Waiting less than 5 minutes per step misses slow errors that ramp up under sustained load.
- **Not pinning the stable Worker**: If the stable Worker is redeployed with breaking changes during a migration, rollback sends traffic to a broken target.

## Gotchas

- Routes with identical patterns and the same priority produce undefined behavior. Always use distinct priority values.
- `Math.random()` is seeded per-isolate, not per-request, so distribution is statistically correct across millions of requests but may appear clustered in low-traffic testing.
- KV is eventually consistent. A `put` may take up to 60 seconds to propagate globally. Use a 60-second ramp step delay to avoid partial propagation mid-observation window.
- Service Bindings forward the original `Request` object including headers. If your stable Worker enforces internal auth headers, ensure the canary sets them before forwarding.

## Verification

```bash
# Check current canary percentage
wrangler kv key get migration:canary_pct --namespace-id $MIGRATION_KV_ID

# Tail logs from both Workers side-by-side
wrangler tail api-worker-canary --format pretty &
wrangler tail api-worker-stable --format pretty &

# Send 20 test requests and count version distribution
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%header{x-worker-version}\n" https://api.example.com/healthz
done | sort | uniq -c
```

## Related

- `workers-environment-promotion-pipeline.md`
- `workers-deployment-verification-smoke-tests.md`
- `workers-zero-downtime-d1-migration-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/routing/routes/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/observability/logs/tail-worker/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
