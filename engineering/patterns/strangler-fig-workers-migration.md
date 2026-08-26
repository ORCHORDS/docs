# Strangler Fig Pattern: Migrating Legacy REST Endpoints to Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You have a monolithic or legacy API (Express, Rails, FastAPI, etc.) deployed on a VPS, container, or traditional cloud instance. Teams want the latency, scalability, and cost benefits of Cloudflare Workers but cannot afford a big-bang rewrite. Routes break in production during large migrations. You need incremental, reversible migration of individual endpoints.

## Context

The **Strangler Fig** pattern (Martin Fowler, 2004) wraps the old system so that new functionality can be incrementally added alongside it. Over time the new system strangles the old one. On Cloudflare the Workers layer is the ideal strangler: it sits at the network edge, intercepts every HTTP request, and can proxy selectively to the legacy origin while serving migrated routes natively.

```
                         ┌────────────────────────────────────────────────┐
  Client                 │           Cloudflare Worker (Router)           │
  ──────►  CF Edge  ───► │                                                │
                         │  migrated route?  ──YES──► Workers handler     │
                         │       │                                         │
                         │      NO                                         │
                         │       ▼                                         │
                         │  proxy to legacy origin ──► Legacy API server  │
                         └────────────────────────────────────────────────┘
```

The Worker acts as both router and migration feature-flag: new code runs at the edge, old code remains on the origin until fully replaced.

## Section 1 — Route Registry

Keep a registry of migrated routes so the router stays declarative. Store it in KV for dynamic updates or hardcode it in code for simplicity.

```typescript
// types.ts
export interface RouteEntry {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | '*';
  pattern: URLPattern;
  handler: (req: Request, env: Env, ctx: ExecutionContext, match: URLPatternResult) => Promise<Response>;
}
```

```typescript
// registry.ts
import { getUsersHandler }   from './handlers/users';
import { getProductHandler } from './handlers/products';
import type { RouteEntry }   from './types';

export const MIGRATED_ROUTES: RouteEntry[] = [
  {
    method:  'GET',
    pattern: new URLPattern({ pathname: '/api/v2/users/:id' }),
    handler: getUsersHandler,
  },
  {
    method:  'GET',
    pattern: new URLPattern({ pathname: '/api/v2/products/:slug' }),
    handler: getProductHandler,
  },
];
```

## Section 2 — The Worker Router

```typescript
// worker.ts
import { MIGRATED_ROUTES } from './registry';

export interface Env {
  LEGACY_ORIGIN: string; // e.g. "https://api.legacy.example.com"
  MIGRATION_LOG: KVNamespace;
  ENVIRONMENT: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Try each migrated route in order
    for (const route of MIGRATED_ROUTES) {
      if (route.method !== '*' && route.method !== request.method) continue;

      const match = route.pattern.exec(url);
      if (!match) continue;

      // Found a migrated route — log it and serve from Workers
      ctx.waitUntil(
        logMigrationHit(env.MIGRATION_LOG, url.pathname, 'workers')
      );
      return route.handler(request, env, ctx, match);
    }

    // Unmigrated route — proxy to legacy origin
    ctx.waitUntil(
      logMigrationHit(env.MIGRATION_LOG, url.pathname, 'legacy')
    );
    return proxyToLegacy(request, env.LEGACY_ORIGIN);
  },
};

async function proxyToLegacy(request: Request, origin: string): Promise<Response> {
  const url      = new URL(request.url);
  const upstream = new URL(url.pathname + url.search, origin);

  const proxied = new Request(upstream.toString(), {
    method:  request.method,
    headers: stripHopByHopHeaders(request.headers),
    body:    ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
    // Prevent Workers from following redirects silently
    redirect: 'manual',
  });

  const response = await fetch(proxied);

  // Clone and rewrite any Location headers that point to the legacy origin
  const newHeaders = new Headers(response.headers);
  const location   = response.headers.get('Location');
  if (location && location.startsWith(origin)) {
    newHeaders.set('Location', location.replace(origin, url.origin));
  }
  newHeaders.set('X-Served-By', 'legacy-origin');

  return new Response(response.body, {
    status:  response.status,
    headers: newHeaders,
  });
}

function stripHopByHopHeaders(headers: Headers): Headers {
  const HOP_BY_HOP = [
    'connection', 'keep-alive', 'proxy-authenticate',
    'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade',
  ];
  const out = new Headers(headers);
  for (const h of HOP_BY_HOP) out.delete(h);
  return out;
}

async function logMigrationHit(kv: KVNamespace, path: string, target: 'workers' | 'legacy'): Promise<void> {
  const key   = `hit:${target}:${new Date().toISOString().slice(0, 10)}:${path}`;
  const prev  = await kv.get(key);
  const count = prev ? parseInt(prev, 10) + 1 : 1;
  await kv.put(key, String(count), { expirationTtl: 30 * 86_400 }); // 30-day rolling window
}
```

## Section 3 — Migrated Handler Example

```typescript
// handlers/users.ts
import type { Env }         from '../worker';
import type { RouteEntry }  from '../types';

export const getUsersHandler: RouteEntry['handler'] = async (
  request, env, ctx, match
): Promise<Response> => {
  const userId = match.pathname.groups['id'];
  if (!userId) {
    return Response.json({ error: 'Missing user id' }, { status: 400 });
  }

  // Use D1 instead of the legacy MySQL/PostgreSQL on the origin
  const stmt  = env.DB.prepare('SELECT id, email, name, created_at FROM users WHERE id = ?');
  const user  = await stmt.bind(userId).first<{ id: string; email: string; name: string; created_at: string }>();

  if (!user) {
    return Response.json({ error: 'User not found' }, { status: 404 });
  }

  return Response.json(user, {
    headers: { 'X-Served-By': 'workers-edge' },
  });
};
```

## Section 4 — Canary / Shadow Mode

Before cutting over fully, run in shadow mode to compare responses:

```typescript
// shadow.ts
export async function shadowCompare(
  request: Request,
  workerResponse: Response,
  legacyOrigin: string,
  ctx: ExecutionContext
): Promise<void> {
  // Clone worker response for comparison (we'll still return it)
  const [workerBody1, workerBody2] = workerResponse.body
    ? workerResponse.body.tee()
    : [null, null];

  ctx.waitUntil(
    (async () => {
      try {
        const legacyReq  = new Request(request.url.replace(new URL(request.url).origin, legacyOrigin), {
          method:  request.method,
          headers: request.headers,
        });
        const legacyResp = await fetch(legacyReq);

        const [wJson, lJson] = await Promise.all([
          workerBody2 ? new Response(workerBody2).json() : null,
          legacyResp.json(),
        ]);

        const match = JSON.stringify(wJson) === JSON.stringify(lJson);
        if (!match) {
          console.error(JSON.stringify({
            level:   'warn',
            event:   'shadow_mismatch',
            path:    new URL(request.url).pathname,
            workers: wJson,
            legacy:  lJson,
          }));
        }
      } catch (err) {
        console.error('Shadow comparison failed:', err);
      }
    })()
  );
}
```

## Anti-patterns

**Big-bang route migration.** Moving 50 routes at once defeats the incremental safety of the strangler fig. Migrate one route, observe for 48 hours, then proceed.

**Hardcoding origin credentials in the Worker.** Use `wrangler secret put LEGACY_ORIGIN_TOKEN` and pull from `env`; never embed API keys in source.

**Not stripping hop-by-hop headers.** Forwarding `Connection: keep-alive` or `Transfer-Encoding: chunked` to the legacy origin causes subtle failures or doubled encoding.

**Infinite redirect loops.** If the legacy server issues a 301 pointing back to the same hostname, the Worker will re-intercept it and loop. Rewrite `Location` headers as shown in `proxyToLegacy`.

**Using `request.body` on GET/HEAD.** `fetch()` rejects a body on a GET; guard with a method check before forwarding the body stream.

## Gotchas

- **URLPattern is order-sensitive** — more-specific patterns must appear before wildcards in the registry array.
- **`response.body` is a `ReadableStream`** and can only be consumed once. If you need to inspect the body (e.g., shadow mode) use `.tee()`.
- **Timeouts differ** — Workers have a 30-second CPU time limit per request; legacy endpoints may have been written assuming longer timeouts. Enforce `AbortSignal.timeout(25_000)` on the upstream fetch.
- **Authentication headers** — If the legacy origin uses IP allowlisting, add your Workers egress IPs (available in Cloudflare dashboard) to the allowlist rather than passing credentials in headers.
- **Cloudflare does not guarantee fixed egress IPs** for standard Workers. Use a Cloudflare Tunnel (cloudflared) from the legacy origin side for secure private connectivity.

## Verification

```bash
# Check migration hit counts for a given date
wrangler kv:key list --namespace-id=<MIGRATION_LOG_ID> --prefix "hit:workers:$(date +%Y-%m-%d)"

# Smoke-test migrated endpoint vs legacy
curl -s https://api.example.com/api/v2/users/123 | jq .
curl -s https://api.legacy.example.com/api/v2/users/123 | jq .

# Confirm X-Served-By header
curl -I https://api.example.com/api/v2/users/123 | grep X-Served-By
```

Integration test to verify routing:

```typescript
// test/routing.test.ts
import { describe, it, expect, vi } from 'vitest';
import worker from '../src/worker';

describe('strangler router', () => {
  it('serves migrated route from workers', async () => {
    const req = new Request('https://api.example.com/api/v2/users/42');
    const res = await worker.fetch(req, mockEnv, mockCtx);
    expect(res.headers.get('X-Served-By')).toBe('workers-edge');
  });

  it('proxies unmigrated route to legacy', async () => {
    const req = new Request('https://api.example.com/api/v1/old-endpoint');
    const res = await worker.fetch(req, mockEnv, mockCtx);
    expect(res.headers.get('X-Served-By')).toBe('legacy-origin');
  });
});
```

## Related

- `api-gateway-routing.md` — general routing patterns
- `feature-cookbook-traffic-shifting.md` — canary and blue-green deployments
- `feature-flags.md` — route-level feature flags for progressive rollout
- `circuit-breaker-workers-d1-fetch.md` — protect the legacy origin from overload during migration

## Sources

- Martin Fowler, "StranglerFigApplication" — martinfowler.com/bliki/StranglerFigApplication.html
- Cloudflare Workers documentation — developers.cloudflare.com/workers/
- URLPattern API — developer.mozilla.org/en-US/docs/Web/API/URLPattern
- Cloudflare Tunnel docs — developers.cloudflare.com/cloudflare-one/connections/connect-networks/
