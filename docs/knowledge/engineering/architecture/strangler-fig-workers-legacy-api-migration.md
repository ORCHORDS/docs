# Strangler Fig Pattern for Migrating a Legacy API Behind a Workers Proxy

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A legacy API running on an origin server needs to be migrated to Cloudflare Workers incrementally. A hard cutover is too risky — the legacy system handles thousands of endpoints and a complete rewrite cannot be tested safely in one shot. The team needs to migrate one endpoint at a time, with the ability to roll back individual routes without touching others.

## Context

The Strangler Fig pattern (named after the fig tree that gradually envelops and replaces its host) lets you route traffic to a new implementation for the endpoints you have migrated, while transparently proxying everything else to the legacy origin. Over time, the new implementation grows until the legacy system can be decommissioned.

The Cloudflare Workers proxy sits in front of the legacy origin. A KV namespace stores a migration status map (`migration:status:<path>`) indicating whether each route is `new`, `legacy`, `canary:<pct>`, or `deprecated`. The Worker reads this map on each request, routes accordingly, and tracks cutover progress via Analytics Engine.

## Workers Router with KV-Driven Migration Map

```typescript
// proxy-worker.ts
type RouteStatus = 'legacy' | 'new' | `canary:${number}` | 'deprecated';

async function getRouteStatus(path: string, env: Env): Promise<RouteStatus> {
  // Normalise path — strip query string, lowercase
  const normalised = path.split('?')[0].toLowerCase();
  const key = `migration:status:${normalised}`;
  const status = await env.MIGRATION_MAP.get(key);
  return (status as RouteStatus) ?? 'legacy';
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const status = await getRouteStatus(url.pathname, env);

    env.ANALYTICS.writeDataPoint({
      blobs: [url.pathname, status],
      doubles: [1],
      indexes: ['migration'],
    });

    if (status === 'deprecated') {
      return Response.json(
        { error: 'this endpoint has been removed', docs: 'https://docs.example.com/migration' },
        { status: 410 }
      );
    }

    if (status === 'new') {
      return routeToNewImplementation(request, url, env);
    }

    if (status.startsWith('canary:')) {
      const pct = Number(status.split(':')[1]);
      if (Math.random() * 100 < pct) {
        return routeToNewImplementation(request, url, env);
      }
    }

    // Default: proxy to legacy origin
    return proxyToLegacy(request, env, ctx);
  },
};

async function routeToNewImplementation(
  request: Request,
  url: URL,
  env: Env
): Promise<Response> {
  // Dispatch to the appropriate new Worker handler based on path
  if (url.pathname.startsWith('/v2/orders')) {
    return handleOrdersV2(request, env);
  }
  if (url.pathname.startsWith('/v2/products')) {
    return handleProductsV2(request, env);
  }
  if (url.pathname.startsWith('/v2/customers')) {
    return handleCustomersV2(request, env);
  }
  // Fallback: path is marked 'new' in KV but handler is missing — treat as legacy
  console.warn(`No handler for ${url.pathname} — falling back to legacy`);
  return proxyToLegacy(request, env, null);
}

async function proxyToLegacy(
  request: Request,
  env: Env,
  ctx: ExecutionContext | null
): Promise<Response> {
  const legacyUrl = new URL(request.url);
  legacyUrl.hostname = env.LEGACY_ORIGIN_HOSTNAME;

  const upstreamRequest = new Request(legacyUrl.toString(), {
    method: request.method,
    headers: request.headers,
    body: request.body,
  });

  const response = await fetch(upstreamRequest);
  // Clone so we can both return and cache
  const cloned = response.clone();

  if (ctx) {
    ctx.waitUntil(cacheResponse(request, cloned, env));
  }

  return response;
}

async function cacheResponse(request: Request, response: Response, env: Env): Promise<void> {
  const cacheKey = request.url;
  const cache = await caches.open('legacy-proxy');
  if (response.ok && request.method === 'GET') {
    await cache.put(cacheKey, response);
  }
}
```

## New Endpoint Handlers

```typescript
// handlers.ts
export async function handleOrdersV2(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (request.method === 'GET' && url.pathname === '/v2/orders') {
    const rows = await env.DB.prepare(
      `SELECT order_id, customer_id, status, total_cents FROM order_aggregate LIMIT 50`
    ).all();
    return Response.json({ orders: rows.results });
  }

  const match = url.pathname.match(/^\/v2\/orders\/([\w-]+)$/);
  if (match && request.method === 'GET') {
    const row = await env.DB.prepare(
      `SELECT * FROM order_aggregate WHERE order_id = ?`
    ).bind(match[1]).first();
    if (!row) return Response.json({ error: 'not found' }, { status: 404 });
    return Response.json(row);
  }

  return new Response('method not allowed', { status: 405 });
}

export async function handleProductsV2(request: Request, env: Env): Promise<Response> {
  return Response.json({ message: 'products v2 — stub' });
}

export async function handleCustomersV2(request: Request, env: Env): Promise<Response> {
  return Response.json({ message: 'customers v2 — stub' });
}
```

## Managing the Migration Map in KV

```typescript
// migration-admin.ts — a separate admin Worker or wrangler script
export async function setRouteStatus(
  path: string,
  status: 'legacy' | 'new' | `canary:${number}` | 'deprecated',
  env: Env
): Promise<void> {
  const key = `migration:status:${path.toLowerCase()}`;
  await env.MIGRATION_MAP.put(key, status);
  console.log(`Set ${key} = ${status}`);
}

export async function listMigrationStatus(env: Env): Promise<Record<string, string>> {
  const list = await env.MIGRATION_MAP.list({ prefix: 'migration:status:' });
  const result: Record<string, string> = {};
  for (const key of list.keys) {
    const value = await env.MIGRATION_MAP.get(key.name);
    result[key.name.replace('migration:status:', '')] = value ?? 'legacy';
  }
  return result;
}

export async function migrateAll(
  paths: string[],
  targetStatus: 'new' | 'deprecated',
  env: Env
): Promise<void> {
  for (const path of paths) {
    await setRouteStatus(path, targetStatus, env);
  }
}
```

## Cutover Strategy

When 100% of paths in the KV map are set to `new` or `deprecated`, the legacy origin receives zero traffic and can be decommissioned.

```typescript
export async function checkCutoverReady(env: Env): Promise<{ ready: boolean; remaining: string[] }> {
  const list = await env.MIGRATION_MAP.list({ prefix: 'migration:status:' });
  const remaining: string[] = [];

  for (const key of list.keys) {
    const status = await env.MIGRATION_MAP.get(key.name);
    if (status === 'legacy' || (status?.startsWith('canary:') && Number(status.split(':')[1]) < 100)) {
      remaining.push(key.name.replace('migration:status:', ''));
    }
  }

  return { ready: remaining.length === 0, remaining };
}
```

## Anti-patterns

- **Storing the migration map in Worker code** — hardcoding route statuses in source code requires a deployment to change routing. KV gives you runtime control without redeploys.
- **Using the same KV namespace for migration state and application data** — keep the migration map in a dedicated namespace (`MIGRATION_MAP`) to make it easy to audit, back up, and wipe at cutover.
- **Jumping straight to `new` without a canary phase** — for high-traffic endpoints, use `canary:5` then `canary:25` then `canary:100` before setting `new`. This limits blast radius if the new implementation has a bug.
- **Not cleaning up the KV map after cutover** — stale KV reads add latency. After decommissioning the legacy origin, remove the migration map entries or set a KV TTL.

## Gotchas

- KV reads have eventual consistency. A route status change may take up to 60 seconds to propagate globally. During this window, some edge nodes will still route to the legacy origin even after you set the status to `new`.
- The `Math.random()` canary split is not sticky — the same user may get the new implementation on one request and the legacy on the next. For sticky routing, hash the user ID or use a cookie.
- The `LEGACY_ORIGIN_HOSTNAME` must be set in `wrangler.toml` as a secret or environment variable. Never hardcode origin hostnames in Worker code.
- If the legacy origin uses IP-allowlisting, add Cloudflare's egress IP ranges to its allowlist before routing traffic through the Workers proxy.

## Verification

```bash
# Set a route to canary at 10%
npx wrangler kv:key put --namespace-id=<NS_ID> \
  'migration:status:/v2/orders' 'canary:10'

# Verify routing (run multiple times; ~10% should return new implementation response)
for i in $(seq 1 20); do
  curl -s https://<worker>.workers.dev/v2/orders | jq -r '.orders // .message // "legacy"'
done

# Promote to 100%
npx wrangler kv:key put --namespace-id=<NS_ID> \
  'migration:status:/v2/orders' 'new'

# Check cutover readiness
curl https://admin.<worker>.workers.dev/cutover-check
# Expected: {"ready":false,"remaining":["/v2/products","/v2/customers"]}
```

## Related

- `bulkhead-pattern-workers-concurrency-isolation.md`
- `cqrs-workers-d1-read-write-separation.md`

## Sources

- Martin Fowler, *Strangler Fig Application* — https://martinfowler.com/bliki/StranglerFigApplication.html
- Cloudflare Workers KV documentation — https://developers.cloudflare.com/kv/
- Cloudflare Workers routing documentation — https://developers.cloudflare.com/workers/configuration/routing/
