# Strangler Fig Migration Pattern Using Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a legacy monolith (Rails app, PHP server, old Node service) that you cannot rewrite all at once. Every attempt at a big-bang migration has stalled. You need to incrementally extract routes and features into Workers without downtime, with the ability to roll back any single route if the new implementation is buggy, and with a clear view of migration progress.

---

## Context

The **Strangler Fig pattern** (coined by Martin Fowler) migrates a legacy system by incrementally routing new paths to the replacement while proxying everything else to the origin. The legacy system is gradually "strangled" as more routes migrate.

Cloudflare Workers sit in front of your origin at the CDN edge, making them an ideal interception layer:

- Zero changes to the legacy origin during migration.
- Route decisions are stored in KV, enabling runtime toggling without redeployment.
- Traffic percentage splits let you canary-test new implementations.
- A KV-backed checklist tracks feature parity status.

---

## Solution

```typescript
// ============================================================
// types.ts
// ============================================================
export type MigrationStatus = 'legacy' | 'canary' | 'migrated' | 'rollback';

export interface RouteConfig {
  /** Regex pattern to match the request path */
  pattern: string;
  status: MigrationStatus;
  /** 0–100: percentage of requests sent to the new handler */
  canaryPercent: number;
  /** Human-readable note on migration progress */
  featureParity: string;
}

export interface TrafficDecision {
  target: 'new' | 'legacy';
  routeKey: string;
  matchedPattern: string;
}

// ============================================================
// route-registry.ts — KV-backed route table
// ============================================================
const ROUTE_TABLE_KEY = 'strangler:routes';
const DEFAULT_TTL = 60; // seconds — short TTL so toggles propagate fast

export class KVRouteRegistry {
  constructor(private kv: KVNamespace) {}

  async getAll(): Promise<Record<string, RouteConfig>> {
    const raw = await this.kv.get(ROUTE_TABLE_KEY, { cacheTtl: DEFAULT_TTL });
    if (!raw) return {};
    return JSON.parse(raw) as Record<string, RouteConfig>;
  }

  async upsert(key: string, config: RouteConfig): Promise<void> {
    const table = await this.getAll();
    table[key] = config;
    await this.kv.put(ROUTE_TABLE_KEY, JSON.stringify(table));
  }

  async setStatus(key: string, status: MigrationStatus): Promise<void> {
    const table = await this.getAll();
    if (!table[key]) throw new Error(`Route ${key} not found`);
    table[key].status = status;
    await this.kv.put(ROUTE_TABLE_KEY, JSON.stringify(table));
  }

  async delete(key: string): Promise<void> {
    const table = await this.getAll();
    delete table[key];
    await this.kv.put(ROUTE_TABLE_KEY, JSON.stringify(table));
  }
}

// ============================================================
// traffic-router.ts — decides new vs legacy per request
// ============================================================
export class TrafficRouter {
  constructor(private registry: KVRouteRegistry) {}

  async decide(pathname: string): Promise<TrafficDecision> {
    const routes = await this.registry.getAll();

    for (const [key, config] of Object.entries(routes)) {
      const regex = new RegExp(config.pattern);
      if (!regex.test(pathname)) continue;

      if (config.status === 'migrated') {
        return { target: 'new', routeKey: key, matchedPattern: config.pattern };
      }
      if (config.status === 'legacy' || config.status === 'rollback') {
        return { target: 'legacy', routeKey: key, matchedPattern: config.pattern };
      }
      if (config.status === 'canary') {
        const roll = Math.random() * 100;
        return {
          target: roll < config.canaryPercent ? 'new' : 'legacy',
          routeKey: key,
          matchedPattern: config.pattern,
        };
      }
    }

    // No matching route → proxy to legacy by default
    return { target: 'legacy', routeKey: 'default', matchedPattern: '*' };
  }
}

// ============================================================
// proxy.ts — forward to legacy origin
// ============================================================
export async function proxyToLegacy(
  request: Request,
  legacyOrigin: string,
): Promise<Response> {
  const url = new URL(request.url);
  url.hostname = new URL(legacyOrigin).hostname;
  url.protocol = new URL(legacyOrigin).protocol;
  url.port = new URL(legacyOrigin).port;

  const proxied = new Request(url.toString(), {
    method: request.method,
    headers: request.headers,
    body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
    redirect: 'manual',
  });

  // Tag the request so the legacy server can identify it came via Workers
  proxied.headers.set('X-Forwarded-Via', 'cloudflare-strangler');

  return fetch(proxied);
}

// ============================================================
// new-handlers/users.ts — example migrated route
// ============================================================
export async function handleUsersRoute(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);

  if (request.method === 'GET' && url.pathname === '/api/users/me') {
    const authHeader = request.headers.get('Authorization');
    if (!authHeader) return Response.json({ error: 'unauthorized' }, { status: 401 });
    // ... new implementation using Workers KV / D1
    return Response.json({ id: 'user-123', name: 'Test User', source: 'workers' });
  }

  // Fall through to legacy for anything else under /api/users
  return proxyToLegacy(request, env.LEGACY_ORIGIN);
}

// ============================================================
// migration-tracker.ts — feature parity checklist in KV
// ============================================================
export interface ParityItem {
  feature: string;
  implemented: boolean;
  testedInProduction: boolean;
  note: string;
}

export class MigrationTracker {
  constructor(private kv: KVNamespace) {}

  private key(routeKey: string) { return `parity:${routeKey}`; }

  async getChecklist(routeKey: string): Promise<ParityItem[]> {
    const raw = await this.kv.get(this.key(routeKey));
    return raw ? (JSON.parse(raw) as ParityItem[]) : [];
  }

  async updateItem(
    routeKey: string,
    feature: string,
    updates: Partial<ParityItem>,
  ): Promise<void> {
    const list = await this.getChecklist(routeKey);
    const idx = list.findIndex((i) => i.feature === feature);
    if (idx === -1) {
      list.push({ feature, implemented: false, testedInProduction: false, note: '', ...updates });
    } else {
      list[idx] = { ...list[idx], ...updates };
    }
    await this.kv.put(this.key(routeKey), JSON.stringify(list));
  }

  isReadyToMigrate(checklist: ParityItem[]): boolean {
    return checklist.length > 0 && checklist.every((i) => i.implemented && i.testedInProduction);
  }
}

// ============================================================
// worker.ts — main entry point
// ============================================================
interface Env {
  MIGRATION_KV: KVNamespace;
  LEGACY_ORIGIN: string; // e.g. "https://legacy.internal.example.com"
  ADMIN_TOKEN: string;
}

const newHandlers: Record<string, (req: Request, env: Env) => Promise<Response>> = {
  'users-api': handleUsersRoute,
  // register more migrated route handlers here
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const registry = new KVRouteRegistry(env.MIGRATION_KV);
    const router = new TrafficRouter(registry);

    // ---- Admin API ----
    if (url.pathname.startsWith('/admin/migration')) {
      if (request.headers.get('Authorization') !== `Bearer ${env.ADMIN_TOKEN}`) {
        return new Response('Forbidden', { status: 403 });
      }
      return handleAdminRequest(request, env, registry);
    }

    // ---- Traffic decision ----
    const decision = await router.decide(url.pathname);

    // Attach decision metadata to response for observability
    let response: Response;

    if (decision.target === 'new' && newHandlers[decision.routeKey]) {
      response = await newHandlersdecision.routeKey;
    } else {
      response = await proxyToLegacy(request, env.LEGACY_ORIGIN);
    }

    const mutable = new Response(response.body, response);
    mutable.headers.set('X-Strangler-Target', decision.target);
    mutable.headers.set('X-Strangler-Route', decision.routeKey);
    return mutable;
  },
};

async function handleAdminRequest(
  request: Request,
  env: Env,
  registry: KVRouteRegistry,
): Promise<Response> {
  const url = new URL(request.url);
  const method = request.method;

  // GET /admin/migration/routes — list all routes
  if (method === 'GET' && url.pathname === '/admin/migration/routes') {
    return Response.json(await registry.getAll());
  }

  // PUT /admin/migration/routes/:key — upsert route config
  if (method === 'PUT' && url.pathname.startsWith('/admin/migration/routes/')) {
    const key = url.pathname.split('/').pop()!;
    const config: RouteConfig = await request.json();
    await registry.upsert(key, config);
    return Response.json({ ok: true });
  }

  // PATCH /admin/migration/routes/:key/status — quick status toggle
  if (method === 'PATCH' && url.pathname.includes('/status')) {
    const key = url.pathname.split('/')[4];
    const { status } = await request.json<{ status: MigrationStatus }>();
    await registry.setStatus(key, status);
    return Response.json({ ok: true });
  }

  // GET /admin/migration/progress — show parity checklist summary
  if (method === 'GET' && url.pathname === '/admin/migration/progress') {
    const routes = await registry.getAll();
    const tracker = new MigrationTracker(env.MIGRATION_KV);
    const summary: Record<string, { status: MigrationStatus; ready: boolean; items: ParityItem[] }> = {};
    for (const [key, config] of Object.entries(routes)) {
      const checklist = await tracker.getChecklist(key);
      summary[key] = {
        status: config.status,
        ready: tracker.isReadyToMigrate(checklist),
        items: checklist,
      };
    }
    return Response.json(summary);
  }

  return new Response('Not found', { status: 404 });
}
```

---

## Implementation Details

**Bootstrapping the route table**

```bash
# Register the /api/users/* route at 0% canary initially
curl -X PUT https://worker.example.com/admin/migration/routes/users-api \
  -H 'Authorization: Bearer <ADMIN_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"pattern":"/api/users","status":"legacy","canaryPercent":0,"featureParity":"auth, profile, preferences"}'

# Ramp up canary to 10%
curl -X PATCH https://worker.example.com/admin/migration/routes/users-api/status \
  -H 'Authorization: Bearer <ADMIN_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"status":"canary"}'
```

**wrangler.toml**

```toml
[[kv_namespaces]]
binding = "MIGRATION_KV"
id      = "<kv-id>"

[vars]
LEGACY_ORIGIN = "https://legacy.internal.example.com"
```

---

## Anti-patterns

- **One giant Worker fetch handler** that handles both new and legacy logic inline. Keep new handlers in separate modules keyed by route name.
- **Hardcoding route status** in `wrangler.toml` vars. Use KV so you can toggle without redeployment.
- **Forgetting to handle redirects from the legacy origin**. Set `redirect: 'manual'` on the proxied request and forward `3xx` responses as-is.
- **Toggling to `migrated` before checking parity**. Always run the `isReadyToMigrate` check against the feature parity checklist.

---

## Gotchas

- The legacy origin must be reachable from the Cloudflare network (not `localhost`). Use a Cloudflare Tunnel or an internal hostname resolvable via Cloudflare.
- Workers `fetch()` does not support `http://` on non-Cloudflare origins by default in production. Use `https://` for the legacy origin.
- The `X-Forwarded-For` header is set by Cloudflare automatically; do not strip it from proxied requests or your legacy access logs lose client IPs.
- KV `cacheTtl` on reads means a route toggle propagates within 60 seconds, not instantly. For emergency rollbacks, also store the route table in a Durable Object for zero-latency reads.

---

## Verification

```bash
# Confirm routing decision header
curl -I https://worker.example.com/api/users/me
# Response headers should include:
# X-Strangler-Target: new | legacy
# X-Strangler-Route: users-api

# View migration progress dashboard
curl https://worker.example.com/admin/migration/progress \
  -H 'Authorization: Bearer <ADMIN_TOKEN>'
```

---

## Related

- `workers-anti-corruption-layer.md` — translate legacy response shapes in the proxy layer
- `backends-for-frontends-pattern.md` — BFF layer after migration is complete
- `sidecar-pattern-service-binding.md` — run legacy adapter as a separate Worker bound via Service Binding

---

## Sources

- [Cloudflare Workers documentation](https://developers.cloudflare.com/workers/)
- Martin Fowler, *Strangler Fig Application* — https://martinfowler.com/bliki/StranglerFigApplication.html
- Sam Newman, *Monolith to Microservices*, Chapter 3
