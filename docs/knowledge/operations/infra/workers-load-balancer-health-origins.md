# Cloudflare Load Balancer Health Checks and Origin Management via API

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You run multiple origin servers (regional backends, canary deployments, third-party API endpoints) behind Cloudflare and need to route traffic intelligently: healthy-only origins, geographic affinity, weighted splits, and automatic failover — all managed programmatically from a Worker or CI pipeline instead of the dashboard.

## Context

Cloudflare Load Balancing is available on Pro+ plans. The data plane sits in front of your Workers and origins. Key resources:

- **Health Check** — periodic HTTP/TCP probe; marks origins UP or DOWN
- **Origin Pool** — group of origins with weights; references a health check
- **Load Balancer** — attached to a hostname/zone; orders pools with geo-steering

All resources are managed via the Cloudflare API (`/accounts/{account_id}/load_balancers/*`).

## Solution

### 1. TypeScript API client

```typescript
const CF_API = "https://api.cloudflare.com/client/v4";

async function cfRequest<T>(
  method: string,
  path: string,
  token: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${CF_API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json<{ result: T; success: boolean; errors: unknown[] }>();
  if (!json.success) throw new Error(`CF API error: ${JSON.stringify(json.errors)}`);
  return json.result;
}
```

### 2. Create a health check

```typescript
interface HealthCheck {
  id: string;
  name: string;
  type: "HTTPS" | "HTTP" | "TCP";
  port: number;
  path: string;
  interval: number;  // seconds
  retries: number;
  timeout: number;
  expected_codes: string;
  follow_redirects: boolean;
  allow_insecure: boolean;
}

async function createHealthCheck(
  accountId: string,
  token: string,
): Promise<HealthCheck> {
  return cfRequest<HealthCheck>(
    "POST",
    `/accounts/${accountId}/load_balancers/monitors`,
    token,
    {
      type: "HTTPS",
      description: "example project-api health",
      method: "GET",
      path: "/healthz",
      port: 443,
      expected_codes: "2xx",
      expected_body: "{\"ok\":true}",
      interval: 60,       // probe every 60 s
      retries: 2,
      timeout: 5,
      follow_redirects: true,
      allow_insecure: false,
      header: {
        "Host": ["api.example.com"],
      },
    },
  );
}
```

### 3. Origin pool creation

```typescript
interface Pool {
  id: string;
  name: string;
  origins: Origin[];
  monitor: string;      // health check ID
  notification_email: string;
  healthy_origins_threshold: number;
}

interface Origin {
  name: string;
  address: string;
  weight: number;      // 0.01 – 1.0; relative weight
  enabled: boolean;
  header?: Record<string, string[]>;
}

async function createOriginPool(
  accountId: string,
  token: string,
  monitorId: string,
): Promise<Pool> {
  return cfRequest<Pool>(
    "POST",
    `/accounts/${accountId}/load_balancers/pools`,
    token,
    {
      name: "example project-primary-pool",
      description: "Primary US-East origins",
      enabled: true,
      minimum_origins: 1,
      monitor: monitorId,
      notification_email: "ops@example.com",
      notification_filter: {
        origin: { healthy: false, unhealthy: true },
        pool:   { healthy: true,  unhealthy: true },
      },
      origins: [
        { name: "us-east-1a", address: "10.0.1.10", weight: 0.5, enabled: true },
        { name: "us-east-1b", address: "10.0.1.11", weight: 0.5, enabled: true },
      ],
    },
  );
}
```

### 4. Geo-steering configuration

```typescript
interface LoadBalancer {
  id: string;
  name: string;           // hostname
  default_pools: string[];
  fallback_pool: string;
  region_pools: Record<string, string[]>;  // region code -> pool IDs
  steering_policy: "off" | "geo" | "random" | "dynamic_latency" | "proximity";
  session_affinity: "none" | "cookie" | "ip_cookie";
  session_affinity_ttl: number;
  ttl: number;
}

async function createLoadBalancer(
  zoneId: string,
  token: string,
  primaryPoolId: string,
  euPoolId: string,
  fallbackPoolId: string,
): Promise<LoadBalancer> {
  return cfRequest<LoadBalancer>(
    "POST",
    `/zones/${zoneId}/load_balancers`,
    token,
    {
      name: "api.example.com",
      default_pools: [primaryPoolId],
      fallback_pool: fallbackPoolId,
      steering_policy: "geo",
      region_pools: {
        // Cloudflare region codes: WNAM, ENAM, WEU, EEU, NSAM, SSAM, OC, ME, NAF, SAF, SAS, SEAS, NEAS
        WNAM: [primaryPoolId],
        ENAM: [primaryPoolId],
        WEU:  [euPoolId],
        EEU:  [euPoolId],
      },
      ttl: 30,
      proxied: true,
    },
  );
}
```

### 5. Session affinity

```typescript
// Add to load balancer creation payload:
session_affinity: "cookie",
session_affinity_ttl: 1800,           // 30 min sticky session
session_affinity_attributes: {
  samesite: "Auto",
  secure: "Auto",
  drain_duration: 60,                 // allow 60 s for draining on origin removal
  zero_downtime_failover: "sticky",  // keep sticky unless origin is DOWN
},
```

### 6. Adjust origin weight at runtime

```typescript
async function setOriginWeight(
  accountId: string,
  token: string,
  poolId: string,
  originName: string,
  newWeight: number,
): Promise<void> {
  // Fetch current pool state
  const pool = await cfRequest<Pool>(
    "GET",
    `/accounts/${accountId}/load_balancers/pools/${poolId}`,
    token,
  );

  const updatedOrigins = pool.origins.map(o =>
    o.name === originName ? { ...o, weight: newWeight } : o,
  );

  await cfRequest(
    "PATCH",
    `/accounts/${accountId}/load_balancers/pools/${poolId}`,
    token,
    { origins: updatedOrigins },
  );
}

// Canary: send 5% traffic to new origin
await setOriginWeight(accountId, token, poolId, "us-east-canary", 0.05);
```

### 7. Monitor pool health from a Worker

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const pools = await cfRequest<Pool[]>(
      "GET",
      `/accounts/${env.CF_ACCOUNT_ID}/load_balancers/pools`,
      env.CF_TOKEN,
    );

    for (const pool of pools) {
      const health = await cfRequest<{ healthy: boolean; origins: Record<string, { healthy: boolean }> }>(
        "GET",
        `/accounts/${env.CF_ACCOUNT_ID}/load_balancers/pools/${pool.id}/health`,
        env.CF_TOKEN,
      );

      if (!health.healthy) {
        await notifyOps(env, `Pool ${pool.name} is UNHEALTHY`, health);
      }

      const unhealthyOrigins = Object.entries(health.origins)
        .filter(([, o]) => !o.healthy)
        .map(([name]) => name);

      if (unhealthyOrigins.length > 0) {
        await notifyOps(env, `Origins DOWN in ${pool.name}: ${unhealthyOrigins.join(", ")}`, health);
      }
    }
  },
};
```

### 8. Fallback pool

The fallback pool is the last resort when all pools in the steering policy are unhealthy. Point it at a static "maintenance" page Worker or an out-of-band CDN:

```typescript
// Create a minimal fallback pool pointing at a maintenance Worker
const fallback = await createOriginPool(accountId, token, /* no monitor */ "");
// Then reference fallback.id as fallback_pool in the LB
```

## Implementation Details

- Pool health is checked from multiple Cloudflare data centers simultaneously. `minimum_origins` controls when a pool is considered unhealthy.
- `steering_policy: "proximity"` uses the GPS coordinates of origins (`latitude`/`longitude` fields) instead of region codes.
- `dynamic_latency` steering requires Cloudflare to observe real latency data; it may not be available immediately after pool creation.
- Pool changes (weight, enabled flag) take effect within 60 s across all PoPs.
- Notifications fire via email and optionally Webhook (`notification_filter`).

## Anti-patterns

- Do not set `minimum_origins: 0` — Cloudflare will route to a pool with no healthy origins.
- Do not use `weight: 0` to disable an origin; use `enabled: false` instead.
- Do not configure health checks with `interval < 60` unless on an Enterprise plan — short intervals are throttled silently.
- Do not share a monitor (health check config) across pools with different expected responses — create separate monitors.
- Do not omit `fallback_pool` — without it, a fully-degraded LB serves errors instead of a maintenance page.

## Gotchas

- Cloudflare load balancer requires the hostname to be **proxied** (orange-cloud). DNS-only records cannot be used.
- Region codes are Cloudflare-specific and do not match AWS regions or ISO country codes.
- `session_affinity: "cookie"` sets a `__cflb` cookie on the browser. Ensure your cookie consent banner accounts for it.
- Weight is relative, not absolute: two origins at weight `0.5` each receive equal traffic; not 50% each of some total.
- The health check `expected_body` is a substring match, not a regex. Keep it short and stable.

## Verification

```bash
# List all pools and health
curl -sS -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/load_balancers/pools" \
  | jq '.["result"][].name'

# Check pool health directly
curl -sS -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/load_balancers/pools/$POOL_ID/health" \
  | jq .

# Confirm geo-steering from EU
curl -si --resolve api.example.com:443:<EU_ORIGIN_IP> https://api.example.com/healthz
```

## Related

- `documentation/docs/policies/infra/workers-pulumi-cloudflare-iac.md`
- `documentation/docs/policies/infra/workers-log-drain-r2-archival.md`

## Sources

- https://developers.cloudflare.com/load-balancing/
- https://developers.cloudflare.com/api/operations/load-balancer-pools-create-pool
- https://developers.cloudflare.com/load-balancing/understand-basics/health-details/
