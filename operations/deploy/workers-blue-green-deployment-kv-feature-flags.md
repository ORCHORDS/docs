# Blue-Green Deployment for Cloudflare Workers with KV Feature Flags

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need zero-downtime deployments with instant rollback capability for a production Worker. The canary-percentage approach is too slow when you need to cut over all traffic at once, and you want a deployment strategy that lets you pre-warm the new version and switch atomically.

---

## Context

Blue-green deployments maintain two identical Worker environments — `blue` and `green` — at all times. A lightweight router Worker reads a single KV key `{"active": "blue"}` or `{"active": "green"}` and proxies the request to the active environment via a service binding. Switching from blue to green is a single KV write that propagates in under 60 seconds with no re-deploy. Each environment exposes a `/health` endpoint so the router and external monitors can verify liveness before and after a cutover. Rollback is the same operation in reverse: flip the KV key back to the previous colour.

---

## Section 1 — Config / wrangler.toml

```toml
# router/wrangler.toml
name = "bg-router"
main = "src/router.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "BG_CONFIG"
id = "<bg-config-kv-namespace-id>"

[[services]]
binding = "BLUE"
service = "api-blue"

[[services]]
binding = "GREEN"
service = "api-green"

---

# blue/wrangler.toml
name = "api-blue"
main = "src/worker.ts"
compatibility_date = "2026-08-01"
vars = { COLOUR = "blue" }

---

# green/wrangler.toml
name = "api-green"
main = "src/worker.ts"
compatibility_date = "2026-08-01"
vars = { COLOUR = "green" }
```

---

## Section 2 — Implementation / Scripts

```typescript
// router/src/router.ts
export interface Env {
  BG_CONFIG: KVNamespace;
  BLUE: Fetcher;
  GREEN: Fetcher;
}

type Colour = "blue" | "green";

interface BgConfig {
  active: Colour;
}

const CONFIG_KEY = "active-colour";
const CACHE_TTL_MS = 5_000;

let cachedColour: Colour | null = null;
let cacheExpiresAt = 0;

async function getActiveColour(kv: KVNamespace): Promise<Colour> {
  const now = Date.now();
  if (cachedColour !== null && now < cacheExpiresAt) return cachedColour;

  const raw = await kv.get(CONFIG_KEY);
  const parsed: BgConfig = raw ? JSON.parse(raw) : { active: "blue" };
  cachedColour = parsed.active === "green" ? "green" : "blue";
  cacheExpiresAt = now + CACHE_TTL_MS;
  return cachedColour;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const colour = await getActiveColour(env.BG_CONFIG);
    const backend = colour === "green" ? env.GREEN : env.BLUE;

    const response = await backend.fetch(request);

    // Propagate the active colour in a response header for observability
    const headers = new Headers(response.headers);
    headers.set("X-BG-Active", colour);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
```

```typescript
// shared/src/worker.ts  (deployed as both api-blue and api-green)
export interface Env {
  COLOUR: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return Response.json({
        status: "ok",
        colour: env.COLOUR,
        timestamp: new Date().toISOString(),
      });
    }

    if (url.pathname === "/api/version") {
      return Response.json({ colour: env.COLOUR, version: "__VERSION__" });
    }

    // ... real application logic
    return Response.json({ hello: "world", colour: env.COLOUR });
  },
};
```

```bash
#!/usr/bin/env bash
# scripts/cutover.sh  — switch active colour
set -euo pipefail

NAMESPACE_ID="${KV_NAMESPACE_ID:?KV_NAMESPACE_ID is required}"
TARGET="${1:?Usage: cutover.sh <blue|green>}"

if [[ "$TARGET" != "blue" && "$TARGET" != "green" ]]; then
  echo "ERROR: target must be 'blue' or 'green'"
  exit 1
fi

echo "Switching active colour to: $TARGET"
wrangler kv:key put \
  --namespace-id="$NAMESPACE_ID" \
  active-colour \
  "{\"active\":\"$TARGET\"}"

echo "Waiting 10 s for KV propagation..."
sleep 10

ROUTER_URL="${ROUTER_URL:?ROUTER_URL is required}"
HEALTH=$(curl -sf "$ROUTER_URL/health" | jq -r '.colour')

if [[ "$HEALTH" != "$TARGET" ]]; then
  echo "ERROR: health check returned colour '$HEALTH', expected '$TARGET'"
  exit 1
fi

echo "Cutover complete. Active colour: $TARGET"
```

---

## Section 3 — CI / Automation

```yaml
# .github/workflows/blue-green-deploy.yml
name: Blue-Green Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      KV_NAMESPACE_ID: ${{ secrets.BG_KV_NAMESPACE_ID }}
      ROUTER_URL: ${{ vars.ROUTER_URL }}

    steps:
      - uses: actions/checkout@v4

      - name: Install wrangler
        run: npm install -g wrangler

      - name: Determine current active colour
        id: current
        run: |
          ACTIVE=$(wrangler kv:key get \
            --namespace-id=$KV_NAMESPACE_ID \
            active-colour | jq -r '.active // "blue"')
          echo "colour=$ACTIVE" >> $GITHUB_OUTPUT
          echo "Current active: $ACTIVE"

      - name: Determine target colour (opposite of current)
        id: target
        run: |
          if [[ "${{ steps.current.outputs.colour }}" == "blue" ]]; then
            echo "colour=green" >> $GITHUB_OUTPUT
          else
            echo "colour=blue" >> $GITHUB_OUTPUT
          fi

      - name: Deploy to inactive colour
        run: |
          TARGET=${{ steps.target.outputs.colour }}
          echo "Deploying to: api-$TARGET"
          # wrangler.toml name is api-blue or api-green
          cd worker
          COLOUR=$TARGET wrangler deploy --name "api-$TARGET"

      - name: Health-check the newly deployed colour (direct)
        run: |
          TARGET=${{ steps.target.outputs.colour }}
          HEALTH=$(curl -sf "$ROUTER_URL/health?force=$TARGET" | jq -r '.status')
          [[ "$HEALTH" == "ok" ]] || (echo "Health check failed"; exit 1)

      - name: Atomic cutover
        run: bash scripts/cutover.sh ${{ steps.target.outputs.colour }}

      - name: Rollback on failure
        if: failure()
        run: |
          PREV=${{ steps.current.outputs.colour }}
          echo "Rolling back to $PREV"
          wrangler kv:key put \
            --namespace-id=$KV_NAMESPACE_ID \
            active-colour "{\"active\":\"$PREV\"}"
```

---

## Anti-patterns

- **Deploying the router before the new colour Worker is live** — the service binding will fail with a 503 if `api-green` has not been deployed yet; always deploy the inactive colour first, then cut over.
- **Relying solely on KV for health-check state** — KV is for routing config, not for recording application health; use an external uptime monitor or Analytics Engine for health signals.
- **Sharing state between blue and green via a common KV namespace** — if blue and green write different schema versions to shared KV, a rollback may leave corrupted keys; treat all shared state as append-only or use D1 schema migrations with backwards compatibility.
- **Forgetting to pre-warm the inactive colour** — a cold Worker start on cutover adds latency spikes visible to users; deploy and send a warm-up request before flipping the KV key.

---

## Gotchas

- KV eventual consistency means the cutover is not instant globally; allow 10–60 seconds before declaring success.
- Service binding latency adds ~1 ms overhead per hop. Two hops (router → colour Worker) is negligible but measure it.
- The module-level `cachedColour` variable in the router resets on Worker cold start. Under very low traffic the cache provides no benefit.
- Wrangler deploys using `--name` override require the API token to have `Workers Scripts:Edit` permission on the account, not just the zone.
- Both `api-blue` and `api-green` must be deployed at all times; if one is deleted, the service binding panics and the router returns 500.

---

## Verification

```bash
# Check current active colour
wrangler kv:key get --namespace-id=<id> active-colour

# Health-check the router
curl -i https://your-router.example.com/health
# Expect: X-BG-Active: blue (or green)

# Manual cutover to green
bash scripts/cutover.sh green

# Verify cutover
curl -s https://your-router.example.com/api/version | jq .colour

# Instant rollback to blue
wrangler kv:key put --namespace-id=<id> active-colour '{"active":"blue"}'

# Confirm rollback
curl -s https://your-router.example.com/health | jq .colour
```

---

## Related

- `wrangler-deploy-canary-percentage-routing.md`
- `workers-rollback-wrangler-versions.md`
- `workers-deployment-smoke-test-health-check.md`

---

## Sources

- Cloudflare Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Wrangler deploy reference — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
