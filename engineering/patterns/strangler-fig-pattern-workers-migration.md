# Strangler Fig Migration from Legacy API to Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a running legacy API (Node.js monolith, Rails app, etc.) and need to migrate it to Cloudflare Workers incrementally without a risky big-bang cutover. Deployments to production must be safe and reversible, with the ability to compare legacy and Workers responses in real time to detect behavioral divergence.

---

## Context

The Strangler Fig pattern wraps the legacy system with a new facade that intercepts traffic and progressively handles more routes itself. A Cloudflare Worker acts as the traffic router: it reads a `migrated_routes` key from KV Workers to determine whether a given route is owned by Workers or the legacy origin, then proxies accordingly. Per-route feature flags in KV make rollout and rollback instant (a KV write). A shadow comparison mode logs both responses to Analytics Engine, enabling divergence detection before switching production traffic.

---

## Config — wrangler.toml

```toml
name        = "strangler-router"
main        = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
LEGACY_ORIGIN = "https://legacy-api.internal.example.com"
SHADOW_COMPARE = "true"   # set to "false" to disable shadow logging

[[kv_namespaces]]
binding   = "ROUTE_FLAGS"
id        = "<your-kv-id>"
preview_id = "<your-preview-kv-id>"

[[analytics_engine_datasets]]
binding = "DIVERGENCE_LOG"
dataset = "route-divergence"
```

---

## Implementation — Route Flag Schema in KV

```typescript
// Stored in KV as key: `route:<METHOD>:<path-pattern>`
// e.g.  "route:GET:/api/v2/products"  => { migrated: true, shadow: false }
//        "route:POST:/api/v1/orders"   => { migrated: false, shadow: true }

export interface RouteFlag {
  migrated: boolean; // true = handle in Workers
  shadow: boolean;   // true = also call legacy and compare
  rolloutPct?: number; // 0-100 for gradual percentage rollout
}
```

---

## Implementation — Strangler Router Worker

```typescript
// src/index.ts
import { Env } from './types';
import { handleMigratedRoute } from './handlers';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const flagKey = `route:${request.method}:${normalizePath(url.pathname)}`;

    const flagRaw = await env.ROUTE_FLAGS.get(flagKey);
    const flag = flagRaw ? (JSON.parse(flagRaw) as RouteFlag) : null;

    // Gradual percentage rollout
    const migrated = flag?.migrated && isInRollout(request, flag.rolloutPct ?? 100);

    if (migrated) {
      const workersResponse = await handleMigratedRoute(request.clone(), env);

      if (flag?.shadow && env.SHADOW_COMPARE === 'true') {
        ctx.waitUntil(
          shadowCompare(request.clone(), workersResponse.clone(), env, flagKey),
        );
      }

      return workersResponse;
    }

    // Not yet migrated — proxy to legacy
    const legacyResponse = await proxyToLegacy(request.clone(), env);

    if (flag?.shadow && env.SHADOW_COMPARE === 'true') {
      ctx.waitUntil(
        shadowCompare(request.clone(), legacyResponse.clone(), env, flagKey),
      );
    }

    return legacyResponse;
  },
};

function normalizePath(pathname: string): string {
  // Strip trailing slash and normalize dynamic segments to param tokens
  return pathname.replace(/\/$/, '').replace(/\/[0-9a-f-]{36}/g, '/:id');
}

function isInRollout(request: Request, pct: number): boolean {
  if (pct >= 100) return true;
  if (pct <= 0) return false;
  // Deterministic per-request bucketing via CF ray ID
  const ray = request.headers.get('CF-Ray') ?? Math.random().toString();
  const bucket = parseInt(ray.slice(-2), 16) % 100;
  return bucket < pct;
}

async function proxyToLegacy(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const legacyUrl = `${env.LEGACY_ORIGIN}${url.pathname}${url.search}`;
  return fetch(legacyUrl, {
    method: request.method,
    headers: request.headers,
    body: request.body,
    redirect: 'manual',
  });
}

async function shadowCompare(
  request: Request,
  primaryResponse: Response,
  env: Env,
  routeKey: string,
): Promise<void> {
  try {
    const url = new URL(request.url);
    const legacyUrl = `${env.LEGACY_ORIGIN}${url.pathname}${url.search}`;
    const legacyResponse = await fetch(legacyUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });

    const [primaryBody, legacyBody] = await Promise.all([
      primaryResponse.text(),
      legacyResponse.text(),
    ]);

    const diverged = primaryBody !== legacyBody ||
      primaryResponse.status !== legacyResponse.status;

    env.DIVERGENCE_LOG.writeDataPoint({
      blobs: [
        routeKey,
        request.method,
        url.pathname,
        diverged ? 'diverged' : 'match',
        diverged ? primaryBody.slice(0, 512) : '',
        diverged ? legacyBody.slice(0, 512) : '',
      ],
      doubles: [
        primaryResponse.status,
        legacyResponse.status,
        diverged ? 1 : 0,
      ],
      indexes: [routeKey],
    });
  } catch (err) {
    console.error('[shadow-compare] error:', err);
  }
}

interface RouteFlag {
  migrated: boolean;
  shadow: boolean;
  rolloutPct?: number;
}
```

---

## Integration — Managing Route Flags

```bash
# Mark a route as migrated (Workers handles it)
wrangler kv key put \
  --binding ROUTE_FLAGS \
  --remote \
  "route:GET:/api/v2/products" \
  '{"migrated":true,"shadow":false}'

# Enable shadow mode for a route (Workers + legacy, compare responses)
wrangler kv key put \
  --binding ROUTE_FLAGS \
  --remote \
  "route:POST:/api/v1/orders" \
  '{"migrated":false,"shadow":true}'

# 10 % gradual rollout
wrangler kv key put \
  --binding ROUTE_FLAGS \
  --remote \
  "route:GET:/api/v1/catalog" \
  '{"migrated":true,"shadow":true,"rolloutPct":10}'

# Roll back a route instantly
wrangler kv key put \
  --binding ROUTE_FLAGS \
  --remote \
  "route:GET:/api/v2/products" \
  '{"migrated":false,"shadow":false}'

# Query divergence log (Analytics Engine SQL API)
curl 'https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql' \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT blob4 AS result, count() AS cnt FROM route_divergence WHERE timestamp > NOW() - INTERVAL '1' HOUR GROUP BY result"
```

---

## Anti-patterns

- **Hard-coding route flags in Worker source** — a code deploy is required to change flags; always use KV so rollout/rollback is a single API call with zero downtime.
- **Forwarding `Host` header to legacy unchanged** — the legacy server may reject requests if the `Host` header does not match its vhost config; rewrite it to `LEGACY_ORIGIN`'s hostname.
- **Running shadow compare synchronously** — doubles response latency for every request; always use `ctx.waitUntil()` so it runs after the response is sent.
- **Comparing raw response bytes** — timestamps, trace IDs, and session tokens cause false divergence; normalize or compare only semantically meaningful fields.

---

## Gotchas

- KV reads have eventual consistency; a flag change may take up to 60 seconds to propagate globally. Use KV metadata for instant invalidation or accept the brief overlap window.
- Streaming responses (chunked transfer, SSE) cannot be cloned for shadow comparison without buffering; disable shadow mode for streaming routes.
- The `CF-Ray` header is injected by Cloudflare edge nodes; it is not present in local `wrangler dev` runs — add a fallback to `Math.random()` for local testing.
- Do not proxy WebSocket upgrade requests to the legacy origin through a standard `fetch()` — use Cloudflare's WebSocket proxy APIs or keep WebSocket routes on the legacy origin until separately migrated.

---

## Verification

```bash
# Confirm a migrated route is handled by Workers (look for a custom header)
curl -I https://my-app.example.com/api/v2/products
# Expect: X-Served-By: workers

# Confirm legacy proxy still works for unmigrated routes
curl -I https://my-app.example.com/api/v1/legacy-endpoint

# Check KV flag contents
wrangler kv key get --binding ROUTE_FLAGS --remote "route:GET:/api/v2/products"

# Tail router logs
wrangler tail strangler-router --format pretty
```

---

## Related

- `bulkhead-pattern-workers-concurrency-limit.md`
- `retry-with-jitter-pattern-workers.md`

---

## Sources

- Martin Fowler — Strangler Fig Application — https://martinfowler.com/bliki/StranglerFigApplication.html
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
