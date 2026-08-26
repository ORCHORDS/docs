# Strangler Fig Pattern: Incrementally Migrating a Legacy API to Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You have a legacy API (Express, Rails, Django, etc.) running on a VPS or container. You want to move it to Cloudflare Workers incrementally — route by route — without a big-bang rewrite or a maintenance window. You need per-route rollback and traffic-shift controls without a code deployment per change.

## Context

The Strangler Fig pattern (Martin Fowler, 2004) wraps the legacy system with a new facade. New routes are implemented in the facade; legacy routes are proxied through. Over time the facade strangles the legacy system until it can be decommissioned.

In a Workers topology:

- A **proxy Worker** sits in front of all traffic.
- Route ownership is stored in **KV** (`migration:route:<path>` → `{ owner: 'workers' | 'legacy', workerPercent: 0-100 }`).
- Migrated routes are handled by the Worker itself (or a Service Binding to a specialised Worker).
- Unmigrated routes are proxied to the legacy origin.

## Solution

### 1. KV schema for migration state

```typescript
// Each key: migration:route:<normalised-path>
// Value:
export interface RouteConfig {
  owner: 'legacy' | 'workers';
  // 0 = all traffic to legacy, 100 = all traffic to workers
  workerPercent: number;
  migratedAt?: number;     // unix ms, set when owner first set to 'workers'
  decommissioned?: boolean;
}

// Global fallback (applies when no specific route key exists)
// Key: migration:default
export interface MigrationDefault {
  owner: 'legacy';
}
```

### 2. Route normalisation helper

```typescript
// src/routing/normalise.ts

// Collapse dynamic segments to a canonical form so /users/123 and /users/456
// both map to the same KV key.
export function normaliseRoute(pathname: string): string {
  return pathname
    .replace(/\/[0-9a-f]{8}-[0-9a-f-]{27}/gi, '/:uuid') // UUIDs
    .replace(/\/\d+/g, '/:id')                           // numeric IDs
    .replace(/\/+$/, '')                                  // trailing slash
    || '/';
}
```

### 3. Traffic-split decision

```typescript
// src/routing/decision.ts
import type { RouteConfig } from './types';

export async function routeDecision(
  pathname: string,
  kv: KVNamespace,
): Promise<'workers' | 'legacy'> {
  const key = `migration:route:${normaliseRoute(pathname)}`;
  const config = await kv.get<RouteConfig>(key, 'json');

  // Unknown route → send to legacy
  if (!config) return 'legacy';
  if (config.owner === 'legacy') return 'legacy';

  // Gradual traffic shift: use a random roll
  const roll = Math.random() * 100;
  return roll < config.workerPercent ? 'workers' : 'legacy';
}

function normaliseRoute(pathname: string): string {
  return pathname
    .replace(/\/[0-9a-f]{8}-[0-9a-f-]{27}/gi, '/:uuid')
    .replace(/\/\d+/g, '/:id')
    .replace(/\/+$/, '')
    || '/';
}
```

### 4. Proxy Worker (the strangler facade)

```typescript
// src/worker.ts
import { routeDecision } from './routing/decision';
import { handleMigratedRequest } from './handlers';

export interface Env {
  MIGRATION: KVNamespace;      // route ownership config
  LEGACY_ORIGIN: string;       // e.g. https://api.legacy.internal
  MIGRATION_LOG: KVNamespace;  // optional: per-request logging
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url      = new URL(request.url);
    const decision = await routeDecision(url.pathname, env.MIGRATION);

    // Fire-and-forget: log decision without blocking response
    ctx.waitUntil(logDecision(url.pathname, decision, env.MIGRATION_LOG));

    if (decision === 'workers') {
      return handleMigratedRequest(request, env);
    }

    // Call-through to legacy
    return proxyToLegacy(request, env.LEGACY_ORIGIN);
  },
};

async function proxyToLegacy(request: Request, origin: string): Promise<Response> {
  const url    = new URL(request.url);
  url.hostname = new URL(origin).hostname;
  url.protocol = new URL(origin).protocol;
  url.port     = new URL(origin).port;

  const upstream = new Request(url.toString(), {
    method:  request.method,
    headers: request.headers,
    body:    ['GET', 'HEAD'].includes(request.method) ? null : request.body,
  });

  const response = await fetch(upstream);

  // Preserve original headers but mark the path taken for observability
  const headers = new Headers(response.headers);
  headers.set('X-Served-By', 'legacy');
  return new Response(response.body, { status: response.status, headers });
}

async function logDecision(
  pathname: string,
  decision: 'workers' | 'legacy',
  log: KVNamespace,
): Promise<void> {
  const date = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const key  = `log:${date}:${normaliseRoute(pathname)}:${decision}`;
  const raw  = await log.get(key);
  const count = parseInt(raw ?? '0', 10) + 1;
  await log.put(key, String(count), { expirationTtl: 7 * 86400 }); // keep 7 days
}

function normaliseRoute(p: string): string {
  return p.replace(/\/[0-9a-f]{8}-[0-9a-f-]{27}/gi, '/:uuid')
          .replace(/\/\d+/g, '/:id')
          .replace(/\/+$/, '') || '/';
}
```

### 5. Migration admin API (control plane)

```typescript
// src/admin.ts  — protected by a secret header, mounted at /admin/migration/*

export async function handleAdminRequest(request: Request, kv: KVNamespace): Promise<Response> {
  const url  = new URL(request.url);
  const path = url.pathname.replace('/admin/migration', '');

  // GET /admin/migration/routes  — list all route configs
  if (request.method === 'GET' && path === '/routes') {
    const list = await kv.list({ prefix: 'migration:route:' });
    const routes = await Promise.all(
      list.keys.map(async k => ({
        route: k.name.replace('migration:route:', ''),
        config: await kv.get<RouteConfig>(k.name, 'json'),
      })),
    );
    return Response.json(routes);
  }

  // PUT /admin/migration/routes/:encodedPath
  if (request.method === 'PUT' && path.startsWith('/routes/')) {
    const route  = decodeURIComponent(path.replace('/routes/', ''));
    const body   = await request.json<Partial<RouteConfig>>();
    const key    = `migration:route:${route}`;
    const existing = (await kv.get<RouteConfig>(key, 'json')) ?? {
      owner: 'legacy',
      workerPercent: 0,
    };
    const updated: RouteConfig = {
      ...existing,
      ...body,
      migratedAt: body.owner === 'workers' && existing.owner !== 'workers'
        ? Date.now()
        : existing.migratedAt,
    };
    await kv.put(key, JSON.stringify(updated));
    return Response.json(updated);
  }

  // DELETE /admin/migration/routes/:encodedPath  — rollback: return to legacy
  if (request.method === 'DELETE' && path.startsWith('/routes/')) {
    const route = decodeURIComponent(path.replace('/routes/', ''));
    const key   = `migration:route:${route}`;
    await kv.put(key, JSON.stringify({ owner: 'legacy', workerPercent: 0 }));
    return new Response(null, { status: 204 });
  }

  return new Response('Not Found', { status: 404 });
}

interface RouteConfig {
  owner: 'legacy' | 'workers';
  workerPercent: number;
  migratedAt?: number;
  decommissioned?: boolean;
}
```

### 6. Migration progress tracker

```typescript
// src/migration-report.ts
export async function getMigrationReport(kv: KVNamespace): Promise<{
  total: number;
  fullyMigrated: number;
  inProgress: number;
  onLegacy: number;
  percentComplete: number;
}> {
  const list = await kv.list({ prefix: 'migration:route:' });

  let fullyMigrated = 0;
  let inProgress = 0;
  let onLegacy = 0;

  for (const key of list.keys) {
    const config = await kv.get<{ owner: string; workerPercent: number }>(key.name, 'json');
    if (!config) continue;
    if (config.owner === 'workers' && config.workerPercent === 100) fullyMigrated++;
    else if (config.owner === 'workers') inProgress++;
    else onLegacy++;
  }

  const total = list.keys.length;
  return {
    total,
    fullyMigrated,
    inProgress,
    onLegacy,
    percentComplete: total ? Math.round((fullyMigrated / total) * 100) : 0,
  };
}
```

## Implementation Details

**Gradual traffic shift sequence** per route:

| Step | `owner`    | `workerPercent` | Effect                        |
|------|-----------|-----------------|-------------------------------|
| 0    | `legacy`  | 0               | 100 % legacy                  |
| 1    | `workers` | 5               | 5 % canary to Workers         |
| 2    | `workers` | 50              | 50 % shadow traffic           |
| 3    | `workers` | 100             | 100 % Workers, legacy cold    |
| 4    | `workers` | 100             | `decommissioned: true`, remove legacy handler |

**Rollback**: call `DELETE /admin/migration/routes/<path>` to instantly return any route to 100 % legacy — no deployment required.

**Decommission checklist**:
1. All routes at `workerPercent: 100` for ≥ 7 days with no legacy-path log entries.
2. Set `decommissioned: true` on each route config.
3. Remove `proxyToLegacy` call from the Worker (make it return 404 for unmigrated routes).
4. Shut down the legacy origin.
5. Remove `LEGACY_ORIGIN` binding from `wrangler.toml`.

## Anti-patterns

- **Big-bang cutover** — defeats the purpose; if something breaks you must roll back the entire API.
- **Hardcoding route ownership in Worker code** — requires a deployment for every traffic shift. Always use KV.
- **Forgetting to forward request body for POST/PUT/PATCH** — `request.body` is a `ReadableStream`; pass it only when method is not `GET`/`HEAD`.
- **Normalising too aggressively** — `/users/:id` and `/users/me` might need separate KV keys; test your normaliser against all real paths before deploying.

## Gotchas

- KV reads have eventual consistency (up to 60 s globally). A config change may not be visible everywhere instantly. Use `kv.get(key, { cacheTtl: 0 })` for the control plane endpoints if you need strong read-after-write guarantees in the same region.
- `ctx.waitUntil()` extends the Worker's lifetime for the log write. Without it the Worker may terminate before the log KV write completes.
- Cloudflare's `fetch()` to `LEGACY_ORIGIN` counts against your subrequest limit (1000/request). Proxy Workers should not fan out.

## Verification

```bash
# Seed a route at 0 %
curl -X PUT https://api.example.com/admin/migration/routes/%2Fusers \
  -H 'X-Admin-Secret: <secret>' \
  -H 'Content-Type: application/json' \
  -d '{"owner":"workers","workerPercent":5}'

# Check migration report
curl https://api.example.com/admin/migration/routes

# Roll back instantly
curl -X DELETE https://api.example.com/admin/migration/routes/%2Fusers \
  -H 'X-Admin-Secret: <secret>'
```

## Related

- `workers-hexagonal-architecture-ports-adapters.md`
- `workers-multi-tenant-isolation-durable-objects.md`

## Sources

- Martin Fowler, "Strangler Fig Application" — https://martinfowler.com/bliki/StranglerFigApplication.html
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Cloudflare Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
