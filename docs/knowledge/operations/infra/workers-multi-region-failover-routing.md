# Multi-Region Failover Routing with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your backend runs in multiple regions (e.g., `us-east-1`, `eu-west-1`, `ap-southeast-1`). When one region degrades, traffic should automatically reroute to the healthiest alternative without operator intervention. You also want latency-based routing to direct users to their nearest healthy origin by default, with sticky sessions for operations that require affinity.

## Context

Cloudflare Workers run at the edge in 300+ PoPs worldwide. A Worker executes geographically close to the user and is the ideal place to implement origin selection logic: health probe results are cached in KV, origin scoring accounts for both health and measured latency, and the routing decision happens in microseconds before the first byte leaves the edge.

This guide implements:
1. Periodic health probes writing results to KV
2. Origin scoring (health + latency) on every request
3. Sticky sessions using a KV-backed session map
4. Fallback to nearest healthy origin when the preferred origin is unhealthy

## Solution

### Types and configuration

```typescript
// src/types.ts
export interface Origin {
  id: string;
  url: string;
  region: string;
  weight: number; // 1–100, higher = preferred
}

export interface HealthRecord {
  healthy: boolean;
  latencyMs: number;
  checkedAt: number; // Unix ms
  consecutiveFailures: number;
}

export interface Env {
  HEALTH_KV: KVNamespace;
  SESSION_KV: KVNamespace;
  ORIGINS: string; // JSON-encoded Origin[]
}

export const ORIGINS: Origin[] = [
  { id: "us-east",  url: "https://us-east.api.example.com",  region: "ENAM", weight: 100 },
  { id: "eu-west",  url: "https://eu-west.api.example.com",  region: "WEUR", weight: 100 },
  { id: "ap-south", url: "https://ap-south.api.example.com", region: "APAC", weight: 100 },
];

export const HEALTH_TTL_SECONDS = 30;
export const PROBE_TIMEOUT_MS   = 5_000;
export const MAX_FAILURES_BEFORE_UNHEALTHY = 2;
export const SESSION_TTL_SECONDS = 300;
```

### Health probe cron Worker

```typescript
// src/health-probe.ts
import { ORIGINS, PROBE_TIMEOUT_MS, MAX_FAILURES_BEFORE_UNHEALTHY, HEALTH_TTL_SECONDS } from "./types";
import type { Env, HealthRecord } from "./types";

async function probeOrigin(origin: { id: string; url: string }): Promise<HealthRecord> {
  const start = Date.now();
  let healthy = false;
  let latencyMs = PROBE_TIMEOUT_MS;
  let prev: HealthRecord | null = null;

  try {
    const resp = await fetch(`${origin.url}/health`, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
      cf: { cacheTtl: 0 },
    });
    latencyMs = Date.now() - start;
    healthy = resp.ok;
  } catch {
    latencyMs = PROBE_TIMEOUT_MS;
    healthy = false;
  }

  return {
    healthy,
    latencyMs,
    checkedAt: Date.now(),
    consecutiveFailures: healthy ? 0 : (prev?.consecutiveFailures ?? 0) + 1,
  };
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await Promise.allSettled(
      ORIGINS.map(async (origin) => {
        const record = await probeOrigin(origin);
        // Mark unhealthy only after N consecutive failures
        const existing = await env.HEALTH_KV.get<HealthRecord>(origin.id, "json");
        const consecutive = record.healthy
          ? 0
          : (existing?.consecutiveFailures ?? 0) + 1;
        const effectiveHealth: HealthRecord = {
          ...record,
          healthy: record.healthy || consecutive < MAX_FAILURES_BEFORE_UNHEALTHY,
          consecutiveFailures: consecutive,
        };
        await env.HEALTH_KV.put(
          origin.id,
          JSON.stringify(effectiveHealth),
          { expirationTtl: HEALTH_TTL_SECONDS * 4 } // keep stale data if probe fails
        );
      })
    );
  },
};
```

### Origin scoring and selection

```typescript
// src/router.ts
import type { Origin, HealthRecord, Env } from "./types";
import { ORIGINS, SESSION_TTL_SECONDS } from "./types";

/** Lower score = better. Score = latency penalised by weight. */
function score(health: HealthRecord, origin: Origin): number {
  if (!health.healthy) return Infinity;
  return (health.latencyMs / origin.weight) * 100;
}

/** Cloudflare colo region to origin region affinity */
const REGION_AFFINITY: Record<string, string> = {
  ENAM: "us-east",
  WNAM: "us-east",
  WEUR: "eu-west",
  EEUR: "eu-west",
  APAC: "ap-south",
  ME:   "ap-south",
  AFR:  "eu-west",
};

export async function selectOrigin(
  request: Request,
  env: Env
): Promise<Origin> {
  // Load all health records in parallel
  const healthEntries = await Promise.all(
    ORIGINS.map(async (o) => ({
      origin: o,
      health: await env.HEALTH_KV.get<HealthRecord>(o.id, "json"),
    }))
  );

  const healthy = healthEntries.filter(
    (e) => e.health?.healthy !== false // treat missing record as healthy (cold start)
  );

  if (healthy.length === 0) {
    // Last resort: return the origin with fewest consecutive failures
    const fallback = [...healthEntries].sort(
      (a, b) => (a.health?.consecutiveFailures ?? 0) - (b.health?.consecutiveFailures ?? 0)
    );
    return fallback[0].origin;
  }

  // Prefer region-affinity origin if healthy
  const coloRegion: string =
    (request as any).cf?.region ?? "ENAM";
  const affinityId = REGION_AFFINITY[coloRegion];
  const affinityEntry = healthy.find((e) => e.origin.id === affinityId);
  if (affinityEntry) return affinityEntry.origin;

  // Fall back to lowest-score healthy origin
  healthy.sort((a, b) => {
    const sa = score(a.health!, a.origin);
    const sb = score(b.health!, b.origin);
    return sa - sb;
  });
  return healthy[0].origin;
}
```

### Sticky sessions via KV

```typescript
// src/sticky.ts
import type { Env, Origin } from "./types";
import { ORIGINS, SESSION_TTL_SECONDS } from "./types";

function sessionId(request: Request): string | null {
  const cookie = request.headers.get("Cookie") ?? "";
  const match = cookie.match(/session_id=([^;]+)/);
  return match ? match[1] : null;
}

export async function getStickyOrigin(
  request: Request,
  env: Env
): Promise<Origin | null> {
  const sid = sessionId(request);
  if (!sid) return null;
  const originId = await env.SESSION_KV.get(`sticky:${sid}`);
  if (!originId) return null;
  return ORIGINS.find((o) => o.id === originId) ?? null;
}

export async function setStickyOrigin(
  request: Request,
  env: Env,
  origin: Origin
): Promise<void> {
  const sid = sessionId(request);
  if (!sid) return;
  await env.SESSION_KV.put(`sticky:${sid}`, origin.id, {
    expirationTtl: SESSION_TTL_SECONDS,
  });
}
```

### Main routing Worker

```typescript
// src/index.ts
import type { Env } from "./types";
import { selectOrigin } from "./router";
import { getStickyOrigin, setStickyOrigin } from "./sticky";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // 1. Check sticky session
    let origin = await getStickyOrigin(request, env);

    // 2. If no sticky or sticky origin is unhealthy, select best origin
    if (!origin) {
      origin = await selectOrigin(request, env);
    }

    // 3. Proxy the request
    const upstreamUrl = new URL(url.pathname + url.search, origin.url);
    const upstreamRequest = new Request(upstreamUrl.toString(), {
      method: request.method,
      headers: request.headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "follow",
    });

    let response: Response;
    try {
      response = await fetch(upstreamRequest);
    } catch (err) {
      // Hard failure: retry with next best origin
      const fallback = await selectOrigin(request, env);
      if (fallback.id === origin.id) {
        return new Response("All origins unavailable", { status: 503 });
      }
      response = await fetch(
        new Request(new URL(url.pathname + url.search, fallback.url).toString(), upstreamRequest)
      );
      origin = fallback;
    }

    // 4. Pin session to selected origin
    ctx.waitUntil(setStickyOrigin(request, env, origin));

    // 5. Add debug header (remove in production or gate behind an admin flag)
    const mutable = new Response(response.body, response);
    mutable.headers.set("X-Origin-Id", origin.id);
    return mutable;
  },
};
```

### wrangler.toml

```toml
name = "example project-router"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[kv_namespaces]]
binding = "HEALTH_KV"
id = "<health_kv_namespace_id>"

[[kv_namespaces]]
binding = "SESSION_KV"
id = "<session_kv_namespace_id>"

[triggers]
crons = ["*/1 * * * *"]  # health probe every minute
```

## Implementation Details

### Health record staleness

KV TTL is set to `4 × HEALTH_TTL_SECONDS` so stale health data persists through probe outages. A missing key is treated as healthy (cold start assumption) to avoid routing all traffic away from a new origin that hasn't been probed yet.

### Latency measurement accuracy

The probe Worker measures round-trip time from the edge PoP running the cron trigger, which may not match the latency experienced by users at other PoPs. For higher accuracy, run probes from a set of representative PoPs using Durable Objects placed in specific jurisdictions.

### Avoiding thundering herd on failover

When an origin goes unhealthy, all edge PoPs will simultaneously reroute traffic to the next best origin. Add jitter to origin selection when multiple origins have similar scores:

```typescript
function jitteredScore(health: HealthRecord, origin: Origin): number {
  const base = score(health, origin);
  return base + Math.random() * 0.05 * base; // ±5% jitter
}
```

## Anti-patterns

- **Reading health state on every request from KV without caching** — KV has ~50 ms read latency. Cache health state in the Worker's in-memory module scope with a short TTL (e.g., 5 s) to avoid adding latency to every proxied request.
- **Failover without circuit breaking** — retrying a degraded origin on every request amplifies load. Track failure counts per origin and skip origins that have failed recently.
- **Using `cf.colo` instead of `cf.region` for affinity** — colo codes are 3-letter IATA codes; region codes (`ENAM`, `WEUR`, etc.) are more stable for mapping to backend regions.
- **Sticky sessions without health awareness** — a user stuck to an unhealthy origin gets repeated failures. Always validate the sticky origin against the current health record.

## Gotchas

- Cron triggers require the Worker to be deployed with `[triggers] crons` in `wrangler.toml`. The scheduled handler and the fetch handler can coexist in the same Worker.
- KV reads inside a cron trigger count against your KV read quota. With 3 origins probed every minute, that's 4,320 reads/day — well within free tier limits but worth monitoring at scale.
- `AbortSignal.timeout()` is available in Workers runtime v2024-02-01+. Pin your `compatibility_date` to at least that date.
- The `request.cf.region` property is only available in production; in local dev with `wrangler dev`, it returns `undefined`. Default to `"ENAM"` or read it from a header set by your CI environment.

## Verification

```bash
# Trigger an immediate health probe
wrangler triggers fire example project-router

# Check health state for each origin
wrangler kv key get --namespace-id=<health_kv_id> "us-east"
wrangler kv key get --namespace-id=<health_kv_id> "eu-west"
wrangler kv key get --namespace-id=<health_kv_id> "ap-south"

# Simulate origin failure: mark us-east as unhealthy in KV
wrangler kv key put --namespace-id=<health_kv_id> "us-east" \
  '{"healthy":false,"latencyMs":5000,"checkedAt":0,"consecutiveFailures":5}'

# Confirm routing switches to next best origin
curl -I https://api.example.com/v1/health | grep X-Origin-Id
# Expected: eu-west or ap-south

# Restore
wrangler kv key delete --namespace-id=<health_kv_id> "us-east"
```

## Related

- `documentation/docs/policies/infra/workers-terraform-cloudflare-provider.md`
- `documentation/docs/policies/infra/workers-dns-record-management-api.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- https://developers.cloudflare.com/workers/configuration/routing/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
