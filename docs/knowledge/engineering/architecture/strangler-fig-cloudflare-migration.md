# Strangler Fig Migration Pattern on Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project started as a Node.js Express API deployed on a VPS. As anonymous-post volume grew, cold-start latency and single-origin failures caused p99 spikes above 4 seconds on mobile. A full rewrite risks breaking mobile clients on older app versions that hard-code legacy route signatures. Strangler Fig lets the team migrate route-by-route, keeping the legacy API alive as a safety net, while new Workers handle increasing traffic share.

## Context

The Strangler Fig pattern (named after the strangler fig tree that grows around a host until the host dies) wraps a legacy system with a new facade. Traffic is progressively shifted to new implementations one endpoint at a time. Old code continues running in parallel until the new path is stable, then the legacy route is removed. On Cloudflare, a Worker placed in front of the legacy origin acts as both the new implementation host and the traffic-shifting router.

## Migration Architecture Overview

```
Mobile Client
     │
     ▼
Cloudflare Worker (Router / Strangler)
     │
     ├── NEW: /api/v2/*   ──► Worker handler (native)
     ├── NEW: /api/v1/posts ─► Worker handler (migrated)
     │
     └── LEGACY: /api/v1/* ──► fetch() ──► VPS Origin
                                            (Node.js Express)
```

The Worker is the single ingress point. Routes that have been migrated execute locally; unmigrated routes proxy through to the origin via `fetch()`.

## Phase 0 — Transparent Proxy (Day 0)

Before migrating any route, deploy the Worker as a pure pass-through to establish the ingress pattern and validate that origin calls succeed.

```typescript
// router-worker/src/index.ts  — phase 0
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = new URL(request.url);
    origin.hostname = env.LEGACY_ORIGIN_HOST; // e.g. "api-origin.example.com"
    return fetch(new Request(origin.toString(), request));
  },
};
```

Traffic impact: zero. All requests forwarded. Latency delta: < 5 ms (Worker overhead only).

## Phase 1 — Route-by-Route Migration

Add a route registry. Each entry declares whether a path is handled natively or forwarded.

```typescript
// router-worker/src/routes.ts
export const MIGRATED_ROUTES: Record<string, boolean> = {
  'GET /api/v1/posts':    true,   // migrated
  'POST /api/v1/posts':   true,   // migrated
  'GET /api/v1/feed':     false,  // legacy
  'GET /api/v1/profiles': false,  // legacy
};

// router-worker/src/index.ts  — phase 1
import { MIGRATED_ROUTES } from './routes';
import { handlePosts } from './handlers/posts';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = `${request.method} ${url.pathname}`;

    if (MIGRATED_ROUTES[key]) {
      return handlePosts(request, env);
    }

    // Forward legacy routes
    const originUrl = new URL(request.url);
    originUrl.hostname = env.LEGACY_ORIGIN_HOST;
    return fetch(new Request(originUrl.toString(), request));
  },
};
```

## Phase 2 — D1 Dual-Write for Data Parity

During migration, write operations must land in both the legacy MySQL database (via origin) and the new D1 database to allow rollback at any time.

```typescript
// handlers/posts.ts — dual-write on POST
export async function handlePosts(request: Request, env: Env): Promise<Response> {
  if (request.method === 'POST') {
    const body = await request.json<CreatePostDto>();

    // Primary write: new D1
    const id = crypto.randomUUID();
    await env.DB.prepare(
      'INSERT INTO posts (id, author_hash, body, created_at) VALUES (?,?,?,?)'
    ).bind(id, body.authorHash, body.body, Date.now()).run();

    // Shadow write: legacy origin (fire-and-forget with timeout)
    const legacyUrl = new URL(request.url);
    legacyUrl.hostname = env.LEGACY_ORIGIN_HOST;
    const legacyWrite = fetch(new Request(legacyUrl.toString(), {
      method: 'POST',
      headers: request.headers,
      body: JSON.stringify(body),
    })).catch(() => {}); // non-blocking

    // Use waitUntil to avoid killing the shadow write after response
    env.CTX.waitUntil(legacyWrite);

    return Response.json({ id }, { status: 201 });
  }

  // GET handled by D1 native read
  const { results } = await env.DB.prepare(
    'SELECT * FROM posts ORDER BY created_at DESC LIMIT 50'
  ).all();
  return Response.json({ items: results });
}
```

Dual-write checklist:

| Step                       | Owner         | Verification                          |
|----------------------------|---------------|---------------------------------------|
| D1 schema mirrors MySQL    | DBA + Dev     | Row counts match after 24 h           |
| Shadow write error rate    | Observability | Alert if > 0.1 % failures             |
| Read from D1 matches origin | QA            | Response diff test (see Verification) |
| Legacy write disabled      | Release gate  | Feature flag `DUAL_WRITE_ENABLED`     |

## Phase 3 — Traffic Shifting with KV Feature Flag

Instead of code-level flags, use KV to shift traffic percentage dynamically without redeploying.

```typescript
// Read shift percentage from KV (cached in-memory per isolate)
const shiftJson = await env.KV.get('migration:posts:shift', 'json') as { pct: number } | null;
const shiftPct = shiftJson?.pct ?? 0;

const useNew = Math.random() * 100 < shiftPct;
```

KV key `migration:posts:shift` is updated by ops tooling:

```bash
# Shift 10% of /api/v1/posts reads to Workers
wrangler kv key put --namespace-id=<NS_ID> "migration:posts:shift" '{"pct":10}'
# Increase to 50%
wrangler kv key put --namespace-id=<NS_ID> "migration:posts:shift" '{"pct":50}'
# Full cut-over
wrangler kv key put --namespace-id=<NS_ID> "migration:posts:shift" '{"pct":100}'
```

## Mobile Backward Compatibility

Older app versions (pre-2.0) send `Accept: application/vnd.example project.v1+json` and expect snake_case field names. The Worker detects the Accept header and transforms responses before returning them.

```typescript
function toSnakeCase(obj: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(obj).map(([k, v]) => [
      k.replace(/[A-Z]/g, c => `_${c.toLowerCase()}`), v,
    ])
  );
}

const isLegacyClient = request.headers.get('Accept')?.includes('vnd.example project.v1') ?? false;
const payload = isLegacyClient ? toSnakeCase(data) : data;
```

Legacy header compatibility matrix:

| Header                              | Action                           |
|-------------------------------------|----------------------------------|
| `Accept: application/vnd.example project.v1+json` | Transform response to snake_case |
| `X-App-Version: 1.*`                | Apply v1 pagination envelope     |
| `Authorization: Bearer <token>`     | Forward to legacy auth validator  |
| `X-Device-Hint: mobile`             | Compress feed payload             |

## Anti-patterns

- **Big-bang cut-over on a Friday** — even with Strangler Fig, shift no more than 25 % per day; observe error rate before advancing.
- **Dual-write without divergence detection** — shadow writes that fail silently leave D1 and MySQL out of sync; run a nightly diff job.
- **Removing the legacy route before mobile clients have auto-updated** — mobile apps on 30-day update cycles still target legacy paths; keep the proxy alive for at least 60 days post-cut-over.
- **Storing shift percentages in Worker code** — requires a deploy to change; KV-backed flags change in under 60 seconds.
- **Treating `waitUntil` as guaranteed** — `waitUntil` extends execution but is not a durable queue; use Workers Queue for writes that must not be lost.

## Gotchas

- `fetch()` inside a Worker to an external origin counts against subrequest limits (1 000 per request on paid plans).
- Cloudflare caches responses from origin by default if the origin sends `Cache-Control: public`; set `cf: { cacheEverything: false }` on legacy proxy fetches to avoid serving cached legacy responses after cut-over.
- D1 column names are case-insensitive but JavaScript object keys are not; explicitly alias SQL columns to camelCase in SELECT statements.
- KV reads have ~60 ms eventual consistency lag after a write; the first request after a shift percentage update may still use the old value.

## Verification

```bash
# Response diff between legacy and new for the same endpoint
LEGACY=$(curl -s https://legacy-api.example.com/api/v1/posts)
NEW=$(curl -s https://api.example.com/api/v1/posts)
diff <(echo "$LEGACY" | jq -S .) <(echo "$NEW" | jq -S .)
# Expect: empty diff or only timestamp variance

# Check D1 row count matches legacy MySQL
wrangler d1 execute example project-db --command="SELECT COUNT(*) FROM posts"
# Compare with: mysql -e "SELECT COUNT(*) FROM posts" legacy_db
```

## Related

- `strangler-fig.md`
- `strangler-fig-migration-pattern.md`
- `blue-green-architecture.md`
- `feature-flag-cloudflare-workers-kv.md`
- `backward-compatibility-design.md`
- `api-versioning-strategies.md`

## Sources

- Martin Fowler, "Strangler Fig Application" (martinfowler.com/bliki/StranglerFigApplication.html)
- Cloudflare Workers documentation — subrequest limits, waitUntil semantics
- Cloudflare KV documentation — eventual consistency guarantees
