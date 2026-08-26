# Cloudflare Load Balancing with Workers Health Checks

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You have multiple origin servers or regional backend pools behind Cloudflare.  Standard
HTTPS health checks tell you whether a TCP connection succeeds, but you need smarter
steering — checking application-level state (database connectivity, cache warm, queue depth)
or combining health check logic with custom routing based on device type, latency, or
request payload.  You want Workers to enrich or replace the built-in health check and pool
steering logic.

## Context

Cloudflare Load Balancing (CLB) is a paid feature (available from Pro plan) that provides:

- **Pools** — groups of origin servers with individual weights.
- **Health monitors** — scheduled probes (HTTP/HTTPS/TCP/UDP) that mark origins
  healthy or unhealthy.
- **Steering policies** — Off (round-robin), Random, Dynamic latency, Proximity,
  Least Outstanding Requests, or Custom Rules.
- **Workers integration** — a Load Balancer can be paired with a Worker that
  intercepts requests before steering, overrides the pool choice, or synthesizes
  health check responses.

CLB lives in the **Traffic** section of the Cloudflare dashboard.  Workers can interact
with CLB through:

1. A Worker sitting in front of the LB hostname that rewrites the request or selects a pool
   via `fetch()` to a specific origin.
2. A custom health-check Worker endpoint on your origin that returns rich JSON the standard
   health monitor calls.
3. The Load Balancing API to update pool membership dynamically from a Worker (advanced).

## Section 1 — Standard Health Monitor Configuration

### Create a pool and monitor via Terraform (recommended for IaC)

```hcl
resource "cloudflare_load_balancer_pool" "api_pool_us" {
  account_id  = var.account_id
  name        = "api-us-east"
  description = "US-East API servers"

  origins {
    name    = "us-east-1a"
    address = "10.0.1.10"
    weight  = 1
    enabled = true
  }

  origins {
    name    = "us-east-1b"
    address = "10.0.1.11"
    weight  = 1
    enabled = true
  }

  minimum_origins     = 1
  notification_email  = ["ops@example.com"]
}

resource "cloudflare_load_balancer_monitor" "api_health" {
  account_id      = var.account_id
  type            = "https"
  path            = "/health"
  expected_codes  = "200"
  interval        = 60   # seconds between probes
  retries         = 2
  timeout         = 5
  method          = "GET"

  header {
    header = "Host"
    values = ["api.internal.example.com"]
  }

  # Expect this JSON body substring to be present
  expected_body   = "\"status\":\"ok\""
  description     = "API deep health check"
}

resource "cloudflare_load_balancer" "api_lb" {
  zone_id          = var.zone_id
  name             = "api.example.com"
  fallback_pool_id = cloudflare_load_balancer_pool.api_pool_us.id
  default_pool_ids = [cloudflare_load_balancer_pool.api_pool_us.id]

  steering_policy  = "dynamic_latency"
  proxied          = true

  # Custom rules override steering for specific conditions
  rules {
    name      = "mobile-to-edge-pool"
    condition = "http.request.uri.path matches \"^/api/mobile\""
    fixed_response = false

    overrides {
      default_pool_ids = [cloudflare_load_balancer_pool.api_pool_eu.id]
      steering_policy  = "proximity"
    }
  }
}
```

## Section 2 — Deep Health-Check Endpoint on Origin

A "shallow" health check (HTTP 200 from `/health`) can give false positives when the DB is
down but nginx still answers.  Implement a deep health endpoint in your application:

```typescript
// Express.js origin health endpoint
import { Pool } from 'pg';
import { createClient } from 'redis';

const db = new Pool({ connectionString: process.env.DATABASE_URL });
const redis = createClient({ url: process.env.REDIS_URL });

app.get('/health/deep', async (req, res) => {
  const checks: Record<string, string> = {};
  let healthy = true;

  // Database ping
  try {
    await db.query('SELECT 1');
    checks.database = 'ok';
  } catch (e) {
    checks.database = 'error';
    healthy = false;
  }

  // Redis ping
  try {
    await redis.ping();
    checks.cache = 'ok';
  } catch (e) {
    checks.cache = 'error';
    // Degraded but still serve if redis is optional
  }

  // Queue depth check (optional; fail if backlog > threshold)
  const queueDepth = await getQueueDepth();
  checks.queue_depth = String(queueDepth);
  if (queueDepth > 10000) {
    checks.queue = 'overloaded';
    healthy = false;
  } else {
    checks.queue = 'ok';
  }

  res.status(healthy ? 200 : 503).json({
    status: healthy ? 'ok' : 'unhealthy',
    checks,
    ts: new Date().toISOString(),
  });
});
```

Update the Cloudflare monitor to probe `/health/deep` and set `expected_body` to
`"status":"ok"`.

## Section 3 — Worker-Side Pool Override Logic

For cases where CLB's built-in steering policies are insufficient — e.g. routing mobile
clients to a specific pool, or short-circuiting to a cache Worker on high load — place a
Worker in front of the LB hostname.

### wrangler.toml

```toml
name               = "lb-router"
main               = "src/router.ts"
compatibility_date = "2024-09-23"

[vars]
POOL_US_EAST = "https://us-east.origin.internal"
POOL_EU_WEST = "https://eu-west.origin.internal"
POOL_EDGE_CACHE = "https://cache.origin.internal"
```

### src/router.ts

```typescript
interface Env {
  POOL_US_EAST: string;
  POOL_EU_WEST: string;
  POOL_EDGE_CACHE: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cf = request.cf as IncomingRequestCfProperties | undefined;
    const url = new URL(request.url);

    // 1. Mobile clients on high-latency paths → edge cache pool
    const deviceType = cf?.deviceType ?? "desktop";
    const isMobile = deviceType === "mobile";

    // 2. Country-based pool selection (Proximity steering simulation)
    const country = cf?.country ?? "US";
    const euCountries = new Set(["GB","DE","FR","NL","SE","NO","DK","FI","PL","ES","IT"]);
    const targetPool = euCountries.has(country) ? env.POOL_EU_WEST : env.POOL_US_EAST;

    // 3. For read-only GET requests from mobile, try the edge cache first
    if (isMobile && request.method === "GET" && !url.pathname.startsWith("/api/write")) {
      const cacheResp = await tryPool(env.POOL_EDGE_CACHE, request, url);
      if (cacheResp && cacheResp.status !== 503) {
        const r = new Response(cacheResp.body, cacheResp);
        r.headers.set("X-Pool", "edge-cache");
        r.headers.set("X-Device", deviceType);
        return r;
      }
    }

    // 4. Route to regional pool
    const resp = await tryPool(targetPool, request, url);
    if (!resp || resp.status === 503) {
      // Failover: try the other pool
      const fallback = targetPool === env.POOL_EU_WEST ? env.POOL_US_EAST : env.POOL_EU_WEST;
      const fallbackResp = await tryPool(fallback, request, url);
      if (fallbackResp) {
        const r = new Response(fallbackResp.body, fallbackResp);
        r.headers.set("X-Pool", "fallback");
        return r;
      }
      return new Response("All pools unavailable", { status: 502 });
    }

    const r = new Response(resp.body, resp);
    r.headers.set("X-Pool", country);
    r.headers.set("X-Device", deviceType);
    return r;
  },
};

async function tryPool(
  baseUrl: string,
  request: Request,
  url: URL
): Promise<Response | null> {
  const targetUrl = baseUrl + url.pathname + url.search;
  try {
    return await fetch(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      // Bypass Cloudflare cache for origin health probes
      cf: { cacheEverything: false },
    });
  } catch {
    return null;
  }
}
```

## Section 4 — Dynamic Pool Management via API from a Worker

For advanced scenarios (auto-scaling, maintenance windows), a Worker can call the CLB API
to enable/disable origins in a pool:

```typescript
// Called from a Worker triggered by a Cloudflare Queue or Cron
async function disableOrigin(
  accountId: string,
  poolId: string,
  originAddress: string,
  apiToken: string
): Promise<void> {
  // Fetch current pool config
  const getResp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/load_balancers/pools/${poolId}`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const pool = await getResp.json() as { result: { origins: Origin[] } };

  // Patch the target origin to disabled
  const updated = pool.result.origins.map((o: Origin) =>
    o.address === originAddress ? { ...o, enabled: false } : o
  );

  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/load_balancers/pools/${poolId}`,
    {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ origins: updated }),
    }
  );
}

interface Origin {
  name: string;
  address: string;
  enabled: boolean;
  weight: number;
}
```

Store the API token in a Secret or Secrets Store; never hardcode it.

## Mobile vs Desktop Considerations

- **Device-aware pool routing** — Cloudflare exposes `request.cf.deviceType` ("mobile",
  "tablet", "desktop") in Workers.  Routing mobile clients to geographically closer or more
  cache-heavy pools reduces first-byte latency on high-latency radio links.
- **Health check probes are always "desktop"** — CLB health monitors do not carry a device
  type; your origin health endpoint should not return different content based on device.
- **TCP vs HTTP monitors for mobile-heavy APIs** — if your API uses WebSockets or long-poll
  for mobile push, an HTTP monitor may close the connection before a WebSocket upgrade
  completes.  Use TCP monitors or a dedicated `/health/http` endpoint that responds
  synchronously.
- **Proximity steering for mobile** — mobile users on carrier NAT often appear to come from
  IP ranges that do not match their physical location.  Prefer `cf.country` over IP
  geolocation for coarse pool selection; use `cf.colo` for fine-grained edge-pool matching.

## Anti-patterns

- **Probing a dynamic response body** — if `expected_body` matches a string that changes
  (e.g. a timestamp or version hash), health checks will flip-flop.  Use a stable string
  like `"status":"ok"`.
- **Setting `minimum_origins = 0`** — this causes CLB to keep routing to a pool even when
  all origins are unhealthy.  Set it to at least 1 so the pool fails over properly.
- **Doing origin failover inside the Worker without respecting CLB health state** — if both
  your Worker and CLB attempt failover independently, clients can see split-brain responses.
  Choose one layer for failover logic.
- **Short health-check intervals on origin rate-limited endpoints** — Cloudflare probes
  come from multiple PoPs; a 10-second interval across 5 PoPs is effectively 0.5 requests/s
  per PoP but can aggregate to 5+ req/s.  Use `interval = 60` for origins that rate-limit
  health probers.

## Gotchas

- **CLB is zone-scoped** — each load balancer record belongs to a specific zone.  If you
  need cross-zone routing, use a Worker on a generic hostname that forwards to
  zone-specific CLB endpoints.
- **Proxied vs DNS-only** — CLB with `proxied = true` sends traffic through the Cloudflare
  network (enabling Workers, WAF, etc.).  DNS-only mode returns origin IPs directly; no
  Workers, no WAF.
- **Pool order matters for "Off" steering** — when steering_policy is "off", traffic goes
  to the first healthy pool in the `default_pool_ids` list in order.  Reorder to simulate
  active/passive failover.
- **Health monitor billing** — each monitor probe counts as a request.  High-frequency
  monitors across many pools and PoPs can add up; review usage in the Analytics dashboard.
- **Worker CPU budget and LB** — a Worker placed in front of a CLB LB hostname has the
  same 30 ms CPU limit as any other Worker.  Do not perform expensive sync operations
  (large KV reads, complex crypto) before forwarding to the pool.

## Verification

```bash
# 1. List pools and check health status
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/load_balancers/pools" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.[].result[] | {name, healthy}'

# 2. Preview which pool a request would hit (without traffic)
curl -s \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/load_balancers/preview/${LB_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"

# 3. Tail the router Worker
npx wrangler tail lb-router --format=pretty

# 4. Simulate a mobile request with cf-device-type
curl -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" \
     https://api.example.com/api/mobile/products

# 5. Force-fail an origin and watch failover
# Temporarily change the origin's /health endpoint to return 503
# Monitor the CLB health event stream in the dashboard → Traffic → Load Balancing → Events
```

## Related

- `waf-rate-limiting-deep-dive.md` — rate limiting on origins behind CLB
- `workers-scheduled-events.md` — cron triggers for periodic pool management
- `workers-fetch-api-patterns.md` — `fetch()` patterns used in pool routing
- `geolocation-accuracy-mobile-carrier-roaming.md` — `cf.country` accuracy on mobile
- `cloudflare-terraform-provider-iac.md` — Terraform provider for CLB resources

## Sources

- Cloudflare Load Balancing docs: https://developers.cloudflare.com/load-balancing/
- Pool configuration: https://developers.cloudflare.com/load-balancing/pools/
- Health monitors: https://developers.cloudflare.com/load-balancing/monitors/
- Steering policies: https://developers.cloudflare.com/load-balancing/understand-basics/traffic-steering/steering-policies/
- Workers + Load Balancing: https://developers.cloudflare.com/load-balancing/additional-options/load-balancing-rules/
