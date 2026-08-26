# Health-Check Sidecar Pattern with Workers Fetch Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your routing Worker or service-binding fan-out code needs to know — continuously and
with low latency — which downstream services are healthy before it routes a real user
request to them. Checking health inline (on the hot path) adds latency to every user
request and amplifies load on already-struggling backends.

The sidecar pattern extracts health-checking into a dedicated "sidecar" Worker
(or Cron Trigger) that runs independently, writes results to KV, and lets the router
read a cached boolean without paying any probe latency.

---

## Context

In containerised systems a sidecar is a helper container in the same Pod as the
primary container. In Cloudflare Workers the analogue is:

- A **probe Worker** invoked by a Cron Trigger (every 30 s or 1 min) that performs
  health probes and writes pass/fail state to Workers KV.
- A **router Worker** that reads health state from KV (possibly from an in-memory
  module-scope cache to avoid KV latency on the hot path) before routing a request.

This separates concerns cleanly: the router is fast and stateless; the sidecar is
slow but offline.

---

## Architecture

```
Cron Trigger (30 s)
      │
      ▼
┌─────────────────┐
│  Probe Worker   │  ── fetch each backend's /healthz ──► backends
│  (sidecar)      │
│                 │  ── write KV "health:{name}" ──────► Workers KV
└─────────────────┘

User Request
      │
      ▼
┌─────────────────┐
│  Router Worker  │  ── read KV "health:{name}" (module cache) ──► KV
│                 │
│                 │  ── route to healthy backend ──────► service binding
└─────────────────┘
```

---

## Implementation

### 1. `wrangler.toml` for the Probe Worker

```toml
name = "health-probe"

[[kv_namespaces]]
binding  = "HEALTH_KV"
id       = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[triggers]
crons = ["*/1 * * * *"]   # every minute; use */30 * * * * * for 30-second Cron (paid plan)

[[services]]
binding = "BACKEND_A"
service  = "stable-api"

[[services]]
binding = "BACKEND_B"
service  = "canary-api"
```

### 2. Probe Worker

```typescript
// probe/index.ts
interface Env {
  HEALTH_KV: KVNamespace;
  BACKEND_A: Fetcher;
  BACKEND_B: Fetcher;
}

interface BackendProbeConfig {
  name: string;
  binding: Fetcher;
  path: string;
  timeoutMs: number;
  expectedStatus: number;
}

interface HealthRecord {
  healthy: boolean;
  checkedAt: number;   // epoch ms
  latencyMs: number;
  statusCode: number | null;
  error: string | null;
}

async function probe(cfg: BackendProbeConfig): Promise<HealthRecord> {
  const start = Date.now();
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), cfg.timeoutMs);
    const res = await cfg.binding.fetch(`https://internal${cfg.path}`, {
      signal: controller.signal,
      method: "GET",
    });
    clearTimeout(timer);
    const latencyMs = Date.now() - start;
    return {
      healthy:   res.status === cfg.expectedStatus,
      checkedAt: Date.now(),
      latencyMs,
      statusCode: res.status,
      error: null,
    };
  } catch (err) {
    return {
      healthy:    false,
      checkedAt:  Date.now(),
      latencyMs:  Date.now() - start,
      statusCode: null,
      error:      String(err),
    };
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const configs: BackendProbeConfig[] = [
      { name: "stable",  binding: env.BACKEND_A, path: "/healthz", timeoutMs: 3000, expectedStatus: 200 },
      { name: "canary",  binding: env.BACKEND_B, path: "/healthz", timeoutMs: 3000, expectedStatus: 200 },
    ];

    // Run all probes in parallel — don't let one slow probe block others
    const results = await Promise.allSettled(configs.map(probe));

    const writes = configs.map((cfg, i) => {
      const record: HealthRecord =
        results[i].status === "fulfilled"
          ? results[i].value
          : { healthy: false, checkedAt: Date.now(), latencyMs: 0, statusCode: null, error: "probe threw" };

      return env.HEALTH_KV.put(
        `health:${cfg.name}`,
        JSON.stringify(record),
        { expirationTtl: 300 }, // expire after 5 min so stale state doesn't linger
      );
    });

    ctx.waitUntil(Promise.all(writes));
  },
};
```

### 3. Shared health reader (imported by the Router Worker)

```typescript
// shared/health.ts
interface Env {
  HEALTH_KV: KVNamespace;
}

interface HealthRecord {
  healthy: boolean;
  checkedAt: number;
  latencyMs: number;
  statusCode: number | null;
  error: string | null;
}

// Module-scope in-process cache — lives for the lifetime of the isolate (minutes)
const healthCache = new Map<string, { record: HealthRecord; cachedAt: number }>();
const CACHE_TTL_MS = 10_000; // 10 s — router checks KV at most this often

export async function isHealthy(name: string, env: Env): Promise<boolean> {
  const now = Date.now();
  const cached = healthCache.get(name);
  if (cached && now - cached.cachedAt < CACHE_TTL_MS) {
    return cached.record.healthy;
  }

  const raw = await env.HEALTH_KV.get<HealthRecord>(`health:${name}`, "json");
  if (!raw) {
    // No record yet — treat as healthy to avoid blocking traffic on cold start
    return true;
  }

  healthCache.set(name, { record: raw, cachedAt: now });
  return raw.healthy;
}

export async function getHealthSummary(
  names: string[],
  env: Env,
): Promise<Record<string, HealthRecord | null>> {
  const entries = await Promise.all(
    names.map(async n => [n, await env.HEALTH_KV.get<HealthRecord>(`health:${n}`, "json")] as const),
  );
  return Object.fromEntries(entries);
}
```

### 4. Router Worker reading health state

```typescript
// router/index.ts
import { isHealthy } from "../shared/health";

interface Env {
  HEALTH_KV: KVNamespace;
  BACKEND_A: Fetcher;
  BACKEND_B: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Admin endpoint — expose health summary without probing live
    if (new URL(request.url).pathname === "/_health") {
      const { getHealthSummary } = await import("../shared/health");
      const summary = await getHealthSummary(["stable", "canary"], env);
      return Response.json(summary);
    }

    const stableOk = await isHealthy("stable", env);
    const canaryOk = await isHealthy("canary", env);

    if (stableOk) {
      return env.BACKEND_A.fetch(request);
    } else if (canaryOk) {
      // Fallback to canary if stable is down
      return env.BACKEND_B.fetch(request);
    } else {
      return new Response(
        JSON.stringify({ error: "All backends unhealthy", code: "SERVICE_UNAVAILABLE" }),
        { status: 503, headers: { "Content-Type": "application/json" } },
      );
    }
  },
};
```

---

## Health Endpoint Contract

Each backend Worker should expose a lightweight `/healthz` that:

1. Returns `200 OK` with body `{"status":"ok"}` when ready.
2. Returns `503` when the backend cannot serve traffic (e.g., D1 unreachable).
3. Completes in < 500 ms under normal conditions.

```typescript
// In any backend Worker
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname === "/healthz") {
      try {
        // Lightweight liveness check — e.g., query D1 with a no-op
        await env.DB.prepare("SELECT 1").first();
        return Response.json({ status: "ok" }, { status: 200 });
      } catch {
        return Response.json({ status: "error", detail: "db unreachable" }, { status: 503 });
      }
    }
    // … normal handler
  },
};
```

---

## Anti-patterns

- **Probing on the hot path** — inline `fetch` to `/healthz` inside the router adds
  100–500 ms to every user request. Always use the async sidecar model.
- **Never expiring KV health keys** — if the probe Worker is misconfigured or disabled,
  stale `healthy: true` records live forever. Always set `expirationTtl`.
- **Single probe per interval** — one request is a noisy signal. Consider running
  3 consecutive probes and requiring 2/3 to pass before marking healthy.
- **Treating absence of a KV record as unhealthy** — this causes all traffic to drop
  during initial deployment before the first probe runs. Default to `true` when no
  record exists and log a warning.

---

## Gotchas

- Cron Triggers on the free plan have a minimum interval of 1 minute. For 30-second
  probes you need the paid (Workers Paid) plan and a `*/30 * * * * *` expression.
- `AbortController` in Workers uses the same API as browsers, but the signal is only
  respected by `fetch`, not by service-binding calls in all runtime versions. Pin your
  compatibility date to 2024-09-23 or later for full signal support.
- Module-scope cache lives per isolate. A PoP with many isolates will make independent
  KV reads for each. This is acceptable — KV reads are cheap and the TTL bounds them.
- If a backend is behind a Cloudflare-proxied domain, probing via the public URL goes
  through the edge twice. Probe via service binding (`binding.fetch(...)`) to keep
  probes internal and accurate.

---

## Verification

```bash
# Manually trigger a probe run (wrangler dev, scheduled endpoint)
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# Read health state directly from KV
wrangler kv get --namespace-id=<ID> "health:stable"
# Expected: {"healthy":true,"checkedAt":1724400000000,"latencyMs":12,"statusCode":200,"error":null}

# Simulate backend failure: return 503 from /healthz, wait 90 s, check router returns 503
```

---

## Related

- `weighted-round-robin-workers-service-bindings.md` — consuming health state to select backends
- `circuit-breaker-workers-d1-fetch.md` — reactive failure detection vs. proactive sidecar
- `health-check-endpoint.md` — `/healthz` endpoint design reference
- `stale-while-revalidate-workers-kv.md` — KV cache freshness patterns

---

## Sources

- Cloudflare Cron Triggers — developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare KV — developers.cloudflare.com/kv/
- "Sidecar pattern" — learn.microsoft.com/en-us/azure/architecture/patterns/sidecar
