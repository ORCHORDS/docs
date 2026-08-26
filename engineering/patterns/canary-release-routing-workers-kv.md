# Canary Release Routing with Cloudflare Workers and KV

2026-08-24 / example.com / production

---

## Symptom / Use-case

You are deploying a new version of a backend service or API route and want to expose it to a controlled percentage of production traffic before fully rolling it out. If the canary version shows elevated error rates or latency, you need to roll back traffic to the stable version within seconds—without redeploying any Workers.

Unlike a blue-green switch (all-or-nothing), a canary release requires:
- Configurable traffic split percentage, changeable at runtime without a deployment.
- Sticky routing for a given user or request (same user always hits the same version during a session).
- Observability: logging which version handled each request.
- Emergency rollback that takes effect globally in under 60 seconds.

---

## Context

Cloudflare Workers are the ideal canary routing layer because they run at the edge before any origin is reached. The routing decision is stored in KV so it can be updated from a control plane API without a Worker deployment.

Architecture:
- A **router Worker** reads canary configuration from KV on each request (served from edge cache with a short TTL).
- The request is forwarded to either the **stable** or **canary** service binding based on the percentage and a deterministic hash of the user or session identifier.
- A **control plane Worker** allows authorised operators to update the KV config (percentage, enabled state, allowlist).
- Optional: Cloudflare Analytics Engine tracks per-version error rates in real time.

---

## Code sections

### 1. KV config schema

```typescript
// types/canary-config.ts

export interface CanaryConfig {
  enabled: boolean;
  percentage: number;
  canaryVersion: string;
  stableVersion: string;
  forcedCanaryUsers: string[];
  forcedStableUsers: string[];
  updatedAt: string;
}

export const CANARY_CONFIG_KV_KEY = 'canary:router:config';
```

### 2. Router Worker – deterministic traffic split

```typescript
// workers/router/src/index.ts
import type { CanaryConfig } from '../../types/canary-config';
import { CANARY_CONFIG_KV_KEY } from '../../types/canary-config';

interface Env {
  CONFIG: KVNamespace;
  STABLE_SERVICE: Fetcher;
  CANARY_SERVICE: Fetcher;
  ANALYTICS: AnalyticsEngineDataset;
}

let cachedConfig: CanaryConfig | null = null;
let cacheExpiresAt = 0;
const CONFIG_CACHE_TTL_MS = 10_000;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const config = await getCanaryConfig(env);
    const userId = extractUserId(request);
    const useCanary = shouldUseCanary(config, userId);

    const version = useCanary ? config.canaryVersion : config.stableVersion;
    const targetService = useCanary ? env.CANARY_SERVICE : env.STABLE_SERVICE;

    const upstreamRequest = new Request(request);
    upstreamRequest.headers.set('X-Deploy-Version', version);
    upstreamRequest.headers.set('X-Canary', useCanary ? '1' : '0');

    let response: Response;
    try {
      response = await targetService.fetch(upstreamRequest);
    } catch (err) {
      console.error('router: upstream fetch failed', { version, err });
      response = new Response('Bad Gateway', { status: 502 });
    }

    ctx.waitUntil(
      logRequestToAnalytics(env.ANALYTICS, {
        version,
        status: response.status,
        isCanary: useCanary,
        path: new URL(request.url).pathname,
      })
    );

    return response;
  },
};

async function getCanaryConfig(env: Env): Promise<CanaryConfig> {
  if (cachedConfig && Date.now() < cacheExpiresAt) return cachedConfig;

  const raw = await env.CONFIG.get(CANARY_CONFIG_KV_KEY, { type: 'json' });
  const defaults: CanaryConfig = {
    enabled: false, percentage: 0, canaryVersion: 'unknown', stableVersion: 'stable',
    forcedCanaryUsers: [], forcedStableUsers: [], updatedAt: new Date().toISOString(),
  };

  cachedConfig = raw ? (raw as CanaryConfig) : defaults;
  cacheExpiresAt = Date.now() + CONFIG_CACHE_TTL_MS;
  return cachedConfig;
}

function extractUserId(request: Request): string {
  return request.headers.get('X-User-Id') ?? request.headers.get('CF-Connecting-IP') ?? 'anonymous';
}

function shouldUseCanary(config: CanaryConfig, userId: string): boolean {
  if (!config.enabled || config.percentage === 0) return false;
  if (config.forcedStableUsers.includes(userId)) return false;
  if (config.forcedCanaryUsers.includes(userId)) return true;
  const hash = simpleHash(`${userId}:${config.canaryVersion}`);
  return (hash % 100) < config.percentage;
}

function simpleHash(input: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = (h * 0x01000193) >>> 0;
  }
  return h;
}

async function logRequestToAnalytics(
  dataset: AnalyticsEngineDataset,
  data: { version: string; status: number; isCanary: boolean; path: string }
): Promise<void> {
  dataset.writeDataPoint({
    indexes: [data.version],
    blobs: [data.path, data.isCanary ? 'canary' : 'stable'],
    doubles: [data.status, data.isCanary ? 1 : 0],
  });
}
```

### 3. Control plane Worker – updating canary config

```typescript
// workers/control-plane/src/index.ts
import type { CanaryConfig } from '../../types/canary-config';
import { CANARY_CONFIG_KV_KEY } from '../../types/canary-config';

interface Env {
  CONFIG: KVNamespace;
  OPERATOR_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.headers.get('Authorization') !== `Bearer ${env.OPERATOR_SECRET}`) {
      return new Response('Unauthorized', { status: 401 });
    }

    const url = new URL(request.url);

    if (url.pathname === '/canary/config' && request.method === 'GET') {
      const raw = await env.CONFIG.get(CANARY_CONFIG_KV_KEY, { type: 'json' });
      return Response.json(raw ?? { enabled: false });
    }

    if (url.pathname === '/canary/config' && request.method === 'PATCH') {
      const patch = await request.json<Partial<CanaryConfig>>();
      const existing = (await env.CONFIG.get(CANARY_CONFIG_KV_KEY, { type: 'json' })) as CanaryConfig | null;
      const updated: CanaryConfig = {
        enabled: false, percentage: 0, canaryVersion: 'unknown', stableVersion: 'stable',
        forcedCanaryUsers: [], forcedStableUsers: [],
        ...(existing ?? {}), ...patch, updatedAt: new Date().toISOString(),
      };
      if (updated.percentage < 0 || updated.percentage > 100) {
        return new Response('percentage must be 0–100', { status: 400 });
      }
      await env.CONFIG.put(CANARY_CONFIG_KV_KEY, JSON.stringify(updated), {
        metadata: { updatedAt: updated.updatedAt },
      });
      return Response.json(updated);
    }

    if (url.pathname === '/canary/rollback' && request.method === 'POST') {
      const existing = (await env.CONFIG.get(CANARY_CONFIG_KV_KEY, { type: 'json' })) as CanaryConfig | null;
      const rolled: CanaryConfig = {
        ...(existing ?? ({} as CanaryConfig)),
        enabled: false, percentage: 0, updatedAt: new Date().toISOString(),
      };
      await env.CONFIG.put(CANARY_CONFIG_KV_KEY, JSON.stringify(rolled));
      return Response.json({ rolledBack: true, config: rolled });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

### 4. wrangler.toml – router with service bindings and KV

```toml
name = "api-router"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[kv_namespaces]]
binding = "CONFIG"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[[services]]
binding = "STABLE_SERVICE"
service = "api-v2"

[[services]]
binding = "CANARY_SERVICE"
service = "api-v3-canary"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "router_requests"
```

### 5. Progressive roll-out script

```bash
#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE_URL="https://control-plane.example.com"
TOKEN="${OPERATOR_SECRET:?}"

if [[ "${1:-}" == "--rollback" ]]; then
  curl -s -X POST "$CONTROL_PLANE_URL/canary/rollback" -H "Authorization: Bearer $TOKEN" | jq .
  exit 0
fi

steps=(5 10 25 50 100)
for pct in "${steps[@]}"; do
  echo ">>> Shifting $pct% of traffic to canary"
  curl -s -X PATCH "$CONTROL_PLANE_URL/canary/config" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"enabled\": true, \"percentage\": $pct, \"canaryVersion\": \"v3.1.0\"}" | jq .
  sleep 180
done
```

### 6. Querying canary error rates via Analytics Engine GraphQL

```graphql
{
  viewer {
    accounts(filter: { accountTag: "YOUR_ACCOUNT_TAG" }) {
      router_requestsAdaptiveGroups(
        filter: { datetimegeq: "2026-08-24T00:00:00Z" datetimeleq: "2026-08-24T23:59:59Z" }
        limit: 10
        orderBy: [count_DESC]
      ) {
        count
        avg { doubles }
        dimensions { blob2 }
      }
    }
  }
}
```

---

## Anti-patterns

- **Using `Math.random()` for the traffic split.** Random is not deterministic—same user will hit different versions on consecutive requests.
- **Storing canary config in Worker environment variables.** Env vars require a deployment to change. KV updates propagate globally within seconds.
- **Setting a long KV cache TTL.** A 60-second in-memory TTL means rollback takes up to 60 seconds to take effect.
- **Routing on client-side flags alone.** If the backend is not aware of which version is running, error attribution is impossible.
- **Skipping forced stable / forced canary lists.** Without these escape hatches, you cannot test the canary yourself without being subject to the percentage roll.

---

## Gotchas

- **KV global consistency lag.** KV changes propagate within ~60 seconds to all edge nodes. During a rollback, some requests may still hit the canary for up to 60 seconds.
- **Module-scope config cache survives across requests on the same isolate.** The `CONFIG_CACHE_TTL_MS` constant controls how stale the config can be.
- **Service bindings are resolved at deploy time.** If you rename the canary Worker, you must redeploy the router to update the binding.
- **Analytics Engine data is not real-time.** There is a ~1-minute ingestion lag. Use `wrangler tail` for immediate canary error detection.
- **FNV hash modulo bias.** For very small percentages (< 1%), the modulo-100 bucketing introduces minor statistical bias.

---

## Verification

```bash
# 1. Enable canary at 10%
curl -s -X PATCH https://control-plane.example.com/canary/config \
  -H "Authorization: Bearer $OPERATOR_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "percentage": 10, "canaryVersion": "v3.1.0", "stableVersion": "v2.9.1"}'

# 2. Send 20 requests and count version distribution
for i in $(seq 1 20); do
  curl -s -o /dev/null -D - https://my-api.example.com/health \
    -H "X-User-Id: user-$i" | grep X-Deploy-Version
done | sort | uniq -c

# 3. Emergency rollback
curl -s -X POST https://control-plane.example.com/canary/rollback \
  -H "Authorization: Bearer $OPERATOR_SECRET"
```

---

## Related

- `feature-flags-implementations.md`
- `strategy-pattern-workers-kv.md`
- `weighted-round-robin-workers-service-bindings.md`
- `strangler-fig-workers-migration.md`
- `geo-aware-routing-workers.md`

---

## Sources

- Cloudflare KV – https://developers.cloudflare.com/kv/
- Cloudflare Service Bindings – https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Analytics Engine – https://developers.cloudflare.com/analytics/analytics-engine/
- Martin Fowler – Canary Release – https://martinfowler.com/bliki/CanaryRelease.html
