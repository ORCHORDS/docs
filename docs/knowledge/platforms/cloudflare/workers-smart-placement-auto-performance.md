# Workers Smart Placement — Auto Performance Optimization

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker that proxies requests to an origin server or queries a D1 database experiences higher-than-expected latency because it runs at the PoP closest to the *end user*, not closest to the *backend*. Smart Placement automatically relocates the Worker to the PoP that minimizes total round-trip time.

## Context

- Runtime: Cloudflare Workers (ES modules or Service Worker syntax)
- Feature: Smart Placement (GA as of 2024)
- Relevant backends: D1, origin HTTP server, external APIs with a fixed region
- Tooling: wrangler v3+

---

## Section 1 — How Smart Placement Works

By default, Workers run at the edge PoP nearest to the client. This is optimal for pure-compute tasks but suboptimal when the Worker must make one or more round-trips to a single-region backend (e.g., a D1 database hosted in `us-east-1` or an origin in Frankfurt).

With Smart Placement enabled, Cloudflare's control plane:

1. Observes the Worker's outbound connections over time (subrequests, D1 calls).
2. Identifies the PoP that minimizes `client→Worker` + `Worker→backend` latency.
3. Routes future requests to that PoP transparently — no code changes required.

The algorithm re-evaluates placement periodically and as traffic patterns shift.

---

## Section 2 — Enabling Smart Placement in wrangler.toml

```toml
# wrangler.toml
name = "smart-api"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[placement]
mode = "smart"

[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

No code changes are required. Deploy with:

```bash
wrangler deploy
```

Verify placement is active:

```bash
wrangler deployments list
# The deployment detail will show placement: smart
```

---

## Section 3 — Measuring Latency Before and After

Add timing headers to your Worker so you can benchmark the effect.

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const t0 = Date.now();

    // Simulate a typical D1 read
    const stmt = env.DB.prepare('SELECT id, name FROM products LIMIT 10');
    const t1 = Date.now();
    const { results } = await stmt.all();
    const t2 = Date.now();

    const workerColo = (request.cf as any)?.colo ?? 'unknown';
    const dbMs = t2 - t1;
    const totalMs = t2 - t0;

    return new Response(JSON.stringify({ results }), {
      headers: {
        'Content-Type': 'application/json',
        'X-Worker-Colo': workerColo,
        'X-DB-Latency-Ms': String(dbMs),
        'X-Total-Latency-Ms': String(totalMs),
        'X-Placement-Mode': 'smart',
      },
    });
  },
};
```

Capture latency metrics:

```bash
# Before enabling smart placement
curl -s -o /dev/null -w "%{time_total}" https://smart-api.example.com/

# After enabling smart placement (allow ~5 minutes for placement to settle)
curl -s -o /dev/null -w "%{time_total}" https://smart-api.example.com/

# Inspect Worker colo and DB latency
curl -I https://smart-api.example.com/ 2>&1 | grep -i 'x-worker\|x-db\|x-total'
```

---

## Section 4 — Understanding Placement Relative to D1 and Origins

```typescript
// src/placement-debug.ts — diagnostic endpoint, disable in production
export async function handleDebug(
  request: Request,
  env: { DB: D1Database }
): Promise<Response> {
  const cf = request.cf as any;

  // D1 exposes its region via the HTTP response headers internally;
  // we surface what we can from the Workers runtime.
  const info = {
    workerColo: cf?.colo,
    country: cf?.country,
    region: cf?.region,
    latitude: cf?.latitude,
    longitude: cf?.longitude,
    // D1 region is fixed at database creation time — check the dashboard.
    // Smart Placement moves the Worker toward the D1 colo.
    hint: 'Worker should be placed near your D1 database region.',
  };

  // Measure subrequest latency to origin
  const originUrl = 'https://httpbin.org/get'; // replace with your origin
  const t0 = Date.now();
  await fetch(originUrl);
  const originMs = Date.now() - t0;

  return new Response(
    JSON.stringify({ placement: info, originLatencyMs: originMs }, null, 2),
    { headers: { 'Content-Type': 'application/json' } }
  );
}
```

---

## Section 5 — Opting Out Per-Request

Smart Placement is applied at the Worker level. If you need to override for a specific request (e.g., a latency-sensitive streaming response), you cannot opt out per-request — consider splitting that path into a separate Worker without `placement.mode = "smart"`.

```toml
# wrangler.toml — separate streaming worker without smart placement
name = "streaming-worker"
main = "src/stream.ts"
compatibility_date = "2025-01-01"
# No [placement] block = default edge-closest behavior
```

---

## Anti-patterns

- Enabling Smart Placement on a pure-compute Worker with no backend subrequests — it adds no benefit and Cloudflare may not move the Worker anyway.
- Expecting instant placement — the algorithm needs traffic to learn; allow 5–15 minutes after deployment.
- Mixing D1 databases in different regions in the same Worker — the algorithm can only optimize for one dominant backend.
- Using Smart Placement for WebSocket Workers — latency for the initial handshake improves but the persistent connection locks the colo.
- Benchmarking with a single request — use a load test to get a statistically valid latency distribution.

## Gotchas

- Smart Placement is currently not supported for Workers behind `wrangler dev` or `wrangler dev --remote`.
- The `cf.colo` field in the request reflects the *entry* PoP (closest to the user), not the PoP where the Worker ran — use `X-Worker-Colo` response headers for verification.
- Placement decisions are not surfaced in real-time logs; check the Workers Analytics dashboard.
- D1 is currently single-region — Smart Placement is most impactful when your D1 database and origin are in the same region.
- Workers with very low traffic (< ~10 req/min) may not accumulate enough signal for placement to activate.

## Verification

```bash
# Deploy with smart placement
wrangler deploy

# Generate load to let the placement algorithm learn
for i in $(seq 1 100); do
  curl -s https://smart-api.example.com/ > /dev/null
done

# Measure p50/p99 with hey (https://github.com/rakyll/hey)
hey -n 500 -c 20 https://smart-api.example.com/

# Compare DB latency header across multiple edge PoPs using a global ping tool
# e.g., https://check-host.net or curl from different regions via SSH

# Confirm placement mode in wrangler
wrangler deployments list --name smart-api
```

## Related

- `documentation/docs/policies/cloudflare/workers-d1-alarms-scheduled-mutations.md`
- `documentation/docs/policies/cloudflare/workers-mutual-tls-client-certificate-auth.md`
- `documentation/docs/policies/cloudflare/cloudflare-pages-functions-middleware-chain.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/smart-placement/
- https://developers.cloudflare.com/d1/
- https://blog.cloudflare.com/smart-placement/
