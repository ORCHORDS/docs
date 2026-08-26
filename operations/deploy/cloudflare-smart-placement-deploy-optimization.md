# Cloudflare Smart Placement Deploy Optimization

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Workers that make frequent calls to a single-region database (D1, Hyperdrive, or external Postgres) suffer unnecessary latency when Cloudflare routes the Worker to an edge PoP far from the data source, negating the benefit of a globally distributed edge.

## Context
Cloudflare Smart Placement automatically relocates a Worker invocation closer to the backend services it calls, based on observed request routing patterns. When enabled, Cloudflare samples outbound subrequest destinations and moves execution to a PoP that minimises round-trip time to those backends. This is particularly effective for Workers wrapping a single-region database: rather than a user in Tokyo hitting a Worker that then makes a 200ms TCP trip to a US database, Smart Placement co-locates the Worker with the database and serves the user from the closest egress point after the DB round-trip.

## Enabling Smart Placement in wrangler.toml

```toml
name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[placement]
mode = "smart"
```

To opt out for a specific deployment (e.g., debug or rollback):
```toml
[placement]
mode = "off"
```

## TypeScript Worker Designed for Smart Placement

Smart Placement works best when the Worker makes deterministic outbound calls to a consistent backend host. Avoid fanning out to multiple origins within one Worker if they reside in different regions.

```typescript
export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  UPSTREAM_HOST: string;
}

async function fetchUserRecord(
  userId: string,
  env: Env
): Promise<Record<string, unknown> | null> {
  // D1 call — Smart Placement will co-locate Worker near D1's region
  const row = await env.DB.prepare(
    "SELECT id, name, plan, created_at FROM users WHERE id = ? LIMIT 1"
  )
    .bind(userId)
    .first<{ id: string; name: string; plan: string; created_at: string }>();

  return row ?? null;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const userId = url.searchParams.get("user_id");

    if (!userId) {
      return new Response("Missing user_id", { status: 400 });
    }

    const cacheKey = `user:${userId}`;
    const cached = await env.CACHE.get(cacheKey, "json");
    if (cached) {
      return Response.json(cached, { headers: { "X-Placement": "cache-hit" } });
    }

    const user = await fetchUserRecord(userId, env);
    if (!user) {
      return new Response("Not found", { status: 404 });
    }

    ctx.waitUntil(env.CACHE.put(cacheKey, JSON.stringify(user), { expirationTtl: 60 }));
    return Response.json(user, {
      headers: {
        "X-Placement": "db-hit",
        "Cache-Control": "private, max-age=60",
      },
    });
  },
};
```

## Validating Smart Placement is Active

After deploying, check that the `CF-Worker-Placement-Mode` response header reflects `smart`. Cloudflare injects this header on Workers that have Smart Placement enabled and active.

```typescript
// scripts/validate-smart-placement.ts
const WORKER_URL = process.env.WORKER_URL ?? "https://orchords-api.orchords-api.workers.dev";
const PROBE_PATH = "/health";
const SAMPLE_COUNT = 10;

interface PlacementResult {
  iteration: number;
  cfRay: string;
  placementMode: string;
  responseTimeMs: number;
}

async function probe(i: number): Promise<PlacementResult> {
  const start = Date.now();
  const resp = await fetch(`${WORKER_URL}${PROBE_PATH}`);
  const elapsed = Date.now() - start;

  return {
    iteration: i,
    cfRay: resp.headers.get("CF-RAY") ?? "unknown",
    placementMode: resp.headers.get("CF-Worker-Placement-Mode") ?? "none",
    responseTimeMs: elapsed,
  };
}

async function main(): Promise<void> {
  const results: PlacementResult[] = [];
  for (let i = 0; i < SAMPLE_COUNT; i++) {
    results.push(await probe(i));
    await new Promise((r) => setTimeout(r, 500));
  }

  const smartCount = results.filter((r) => r.placementMode === "smart").length;
  const avgMs = results.reduce((s, r) => s + r.responseTimeMs, 0) / results.length;

  console.table(results);
  console.log(`Smart placement active on ${smartCount}/${SAMPLE_COUNT} requests`);
  console.log(`Average response time: ${avgMs.toFixed(1)}ms`);

  if (smartCount === 0) {
    console.warn("Smart Placement not observed — check wrangler.toml [placement] block");
    process.exit(1);
  }
}

main();
```

## CI Pipeline Integration

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Deploying Worker with Smart Placement..."
npx wrangler deploy

echo "Allowing 30s for placement telemetry to initialize..."
sleep 30

echo "Validating Smart Placement headers..."
npx tsx scripts/validate-smart-placement.ts

echo "Recording baseline P50/P95 latencies for regression tracking..."
npx tsx scripts/record-latency-baseline.ts --tag "post-deploy-$(date +%Y%m%d%H%M)"
```

```typescript
// scripts/record-latency-baseline.ts
import { writeFileSync } from "fs";

const TAG = process.argv.find((a) => a.startsWith("--tag="))?.split("=")[1] ?? "unknown";
const WORKER_URL = process.env.WORKER_URL!;
const SAMPLES = 50;

async function sample(): Promise<number> {
  const t = Date.now();
  await fetch(`${WORKER_URL}/health`);
  return Date.now() - t;
}

async function main(): Promise<void> {
  const times: number[] = [];
  for (let i = 0; i < SAMPLES; i++) {
    times.push(await sample());
    await new Promise((r) => setTimeout(r, 200));
  }
  times.sort((a, b) => a - b);
  const p50 = times[Math.floor(SAMPLES * 0.5)];
  const p95 = times[Math.floor(SAMPLES * 0.95)];
  const result = { tag: TAG, p50, p95, samples: SAMPLES, ts: new Date().toISOString() };
  writeFileSync(`baselines/${TAG}.json`, JSON.stringify(result, null, 2));
  console.log(result);
}

main();
```

## Anti-patterns
- Enabling Smart Placement on a Worker that calls multiple geographically dispersed backends — Cloudflare can only optimise for one dominant backend
- Disabling Smart Placement in staging but enabling it in production — latency characteristics between environments will diverge
- Using Smart Placement alongside a `D1_BETA` binding that has no fixed region — placement may oscillate
- Assuming Smart Placement will activate immediately after first deploy — it requires a sampling period (~30 minutes of real traffic)
- Testing Smart Placement effectiveness with `wrangler dev` — local dev bypasses placement entirely

## Gotchas
- Smart Placement can increase latency for users geographically close to the Worker but far from the database — it optimises for database round-trip, not user proximity
- The `CF-Worker-Placement-Mode` header is only present in production; it does not appear in `wrangler dev` or preview URLs
- Smart Placement is re-evaluated on each deployment; a new deploy resets the sampling window
- Workers using `caches.default` may see cache miss rates increase if placement relocates the Worker to a different PoP than where cache entries were stored
- Smart Placement is currently unavailable for Workers using the `nodejs_compat` flag with certain Node APIs

## Verification
```bash
# Confirm placement mode header is returned
curl -s -I "https://orchords-api.orchords-api.workers.dev/health" \
  | grep -i "cf-worker-placement-mode"

# Compare P95 latency before and after enabling Smart Placement
diff baselines/pre-placement.json baselines/post-placement.json
```

## Related
- `cloudflare-worker-cpu-time-limits-optimization.md`
- `deploy-cold-start-prewarming.md`
- `multi-region-deployment.md`
- `workers-d1-pre-deploy-migration-safety.md`

## Sources
- https://developers.cloudflare.com/workers/configuration/smart-placement/
- https://developers.cloudflare.com/workers/platform/limits/
- https://blog.cloudflare.com/introducing-worker-smart-placement/
