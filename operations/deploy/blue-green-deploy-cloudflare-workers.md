# Blue-Green Deploy — Cloudflare Workers Custom Domains & Traffic Routing

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Deploying a new Worker version to production causes a brief window where some
requests hit the old logic and some hit the new logic simultaneously, breaking
stateful flows (auth sessions, in-flight WebSocket upgrades, checkout carts).
Rolling back requires re-deploying the old bundle, which takes 30–90 seconds.

## Context

example project (example.com) runs on Cloudflare Workers with a custom domain
(`api.example.com`). Wrangler's default `wrangler deploy` replaces the active
Worker in-place. This article describes a blue-green pattern using two named
Worker scripts, a KV version flag, and Cloudflare Custom Domains to achieve
zero-downtime swaps with instant rollback capability.

Key constraints:
- Two live Worker scripts must exist simultaneously (`example project-blue`, `example project-green`)
- Traffic must be 100% on one color at all times (no split during swap)
- Mobile clients (iOS/Android native) hold long-lived sessions; mid-deploy
  session invalidation causes silent 401 loops until the user force-quits

---

## Worker Script Naming Convention

Use a stable pair of script names in `wrangler.toml`. Each color has its own
config file that overrides only the `name` field.

```toml
# wrangler.blue.toml
name = "example project-blue"
main = "dist/worker.js"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
COLOR = "blue"
```

```toml
# wrangler.green.toml
name = "example project-green"
main = "dist/worker.js"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
COLOR = "green"
```

Deploy the inactive color without touching live traffic:

```bash
# Determine inactive color from KV flag, then deploy only that script
ACTIVE=$(wrangler kv:key get --namespace-id=$NS_ID active_color)
INACTIVE=$([[ $ACTIVE == "blue" ]] && echo "green" || echo "blue")

wrangler deploy --config wrangler.${INACTIVE}.toml
```

---

## KV Version Flag Schema

Store the active color in KV so every Worker instance reads a single source of
truth without a DNS round-trip.

```
KV key: "deploy:active_color"   value: "blue" | "green"
KV key: "deploy:last_swap_ts"   value: "2026-08-22T14:30:00Z"
KV key: "deploy:last_swap_by"   value: "ci-pipeline / manual"
```

```typescript
// src/router.ts — executed on every request
export async function routeRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const activeColor = await env.KV.get("deploy:active_color");
  const myColor = env.COLOR; // injected by wrangler.toml [vars]

  if (activeColor && activeColor !== myColor) {
    // This script is the inactive color; return 503 so the
    // Custom Domain router can fail-open to the active script.
    return new Response("inactive", { status: 503 });
  }

  return handleRequest(request, env);
}
```

### Custom Domain Router Worker

A thin dispatcher Worker sits behind the custom domain and proxies to the
active script by fetching the KV flag.

```typescript
// dispatch-worker/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const color = (await env.KV.get("deploy:active_color")) ?? "blue";
    const target = `https://example project-${color}.workers.dev${new URL(request.url).pathname}`;

    return fetch(target, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });
  },
};
```

---

## Zero-Downtime Swap Sequence

| Step | Action                                   | Rollback cost |
|------|------------------------------------------|---------------|
| 1    | Deploy new bundle to inactive color      | None — live traffic unchanged |
| 2    | Run smoke tests against inactive script  | Abort; live traffic unchanged |
| 3    | Write new color to `deploy:active_color` | Instant KV write (~50 ms TTL flush) |
| 4    | Tail logs on both scripts for 5 min      | Rewrite KV to old color in < 1 s |
| 5    | Delete old script after confidence window| None — old script already idle |

```bash
# swap.sh
set -euo pipefail
NEW_COLOR=$1  # "blue" or "green"

# Step 2: smoke test inactive before swap
SMOKE_URL="https://example project-${NEW_COLOR}.workers.dev/health"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SMOKE_URL")
[[ "$STATUS" == "200" ]] || { echo "Smoke failed: $STATUS"; exit 1; }

# Step 3: atomic swap
wrangler kv:key put --namespace-id="$NS_ID" "deploy:active_color" "$NEW_COLOR"
wrangler kv:key put --namespace-id="$NS_ID" "deploy:last_swap_ts" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Swapped to $NEW_COLOR"
```

---

## Mobile Session Continuity

Mobile native clients (iOS/Android) authenticate once and store a JWT. A
Worker swap must not invalidate in-flight tokens.

Checklist:

| Risk                                | Mitigation |
|-------------------------------------|------------|
| JWT signing key differs per color   | Store signing key in KV / Workers Secrets, not in `[vars]` |
| KV session store uses color-scoped keys | Use a shared namespace for both colors (same `id`) |
| WebSocket connections mid-flight    | Drain: accept no new WS on inactive script; finish existing after swap |
| Cookie `Path` / `Domain` mismatch   | Both scripts write identical cookie headers |

WebSocket drain example in the inactive color's request handler:

```typescript
if (request.headers.get("Upgrade") === "websocket" && myColor !== activeColor) {
  return new Response("Service switching; retry in 2s", {
    status: 503,
    headers: { "Retry-After": "2" },
  });
}
```

---

## Anti-patterns

- **Deploying both colors simultaneously and using DNS weight** — Cloudflare
  DNS propagation is not instantaneous; some edge nodes may split traffic
  during propagation, violating the "100% one color" invariant.
- **Using `wrangler deploy --env production` for both colors** — env overrides
  share the same script name; you lose the separate deployable.
- **Storing the active color in D1** — D1 read latency (1–5 ms per query)
  adds to every request. KV reads are served from edge cache in < 1 ms.
- **Not setting a KV TTL** — stale reads can persist up to 60 s after a swap.
  Use `wrangler kv:namespace update --cache-ttl 30` or write with `expirationTtl`.

---

## Gotchas

- `wrangler kv:key put` propagates globally but edge caches may serve stale
  values for up to 60 seconds. Issue a cache purge or accept a short overlap
  window — not a correctness problem if the inactive script returns 503.
- Custom Domain binding a Workers script requires the domain to be proxied
  (orange-cloud) in Cloudflare DNS. Bypassing the proxy (grey-cloud) routes
  around the dispatch worker.
- Worker `[vars]` values are visible in Wrangler output and the dashboard.
  Do not store secrets there; use `wrangler secret put` instead.
- Two scripts in the same account share the same KV namespace when you use the
  same `id`. Confirm this in the dashboard under Workers & Pages > KV.

---

## Verification

```bash
# Confirm active color
wrangler kv:key get --namespace-id=$NS_ID "deploy:active_color"

# Hit health endpoint on each color directly
curl -I https://example project-blue.workers.dev/health
curl -I https://example project-green.workers.dev/health

# Confirm custom domain routes to active color
curl -s https://api.example.com/health | jq .color

# Watch real-time logs for 60 s after swap
wrangler tail example project-blue  --format=pretty &
wrangler tail example project-green --format=pretty &
sleep 60
kill %1 %2
```

---

## Related

- `rollback-strategies-workers-pages.md`
- `canary-workers-gradual-traffic-split.md`
- `blue-green-vs-canary-decision-matrix.md`
- `workers-secrets-rotation-zero-downtime.md`
- `env-binding-precedence.md`

## Sources

- Cloudflare Workers Custom Domains docs — https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
- Wrangler CLI reference — https://developers.cloudflare.com/workers/wrangler/commands/
- Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare blog: Zero-downtime deploys with Workers — https://blog.cloudflare.com/workers-zero-downtime-deploys/
