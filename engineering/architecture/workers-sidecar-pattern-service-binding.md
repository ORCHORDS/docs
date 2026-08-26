# Sidecar Pattern with Service Bindings in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Cross-cutting concerns (authentication, rate limiting, structured logging, request signing, distributed tracing) are copy-pasted into every Worker. A change to the auth scheme requires touching a dozen services. Integration tests duplicate mock setups. You need a way to extract these concerns into a single, independently deployable unit while keeping request latency low.

## Context

In container-based microservices, the Sidecar pattern co-locates a helper process in the same pod/VM as the primary service. The sidecar intercepts or augments traffic without network overhead because both processes share localhost.

Cloudflare Workers implement this via **Service Bindings**: a zero-latency, in-process call from one Worker to another within the same datacenter. The primary Worker calls the sidecar Worker as if it were a local function, but the sidecar is a separately versioned, deployable Worker with its own `wrangler.toml`, secrets, and release cycle.

Key properties:
- No HTTP round-trip overhead — Service Binding calls are handled in the same isolate group.
- Independent deployment: sidecar can be updated without redeploying primary Workers.
- Standard `Request`/`Response` interface — the same code works in tests with `fetch()`.

## Solution

### 1. Sidecar Worker — Auth + Rate Limiting + Logging

```typescript
// sidecar-worker/src/index.ts
import { verifyJwt } from './auth';
import { checkRateLimit } from './ratelimit';
import { structuredLog } from './logging';

export interface SidecarEnv {
  JWT_SECRET: string;
  RATE_LIMITER: RateLimiter; // Workers Rate Limiting binding
  LOG_SINK: Queue;           // Workers Queue for async log delivery
}

interface SidecarRequest {
  path: string;      // e.g. '/auth', '/ratelimit', '/log'
}

export default {
  async fetch(request: Request, env: SidecarEnv): Promise<Response> {
    const url = new URL(request.url);

    switch (url.pathname) {
      case '/auth':      return handleAuth(request, env);
      case '/ratelimit': return handleRateLimit(request, env);
      case '/log':       return handleLog(request, env);
      default:
        return new Response('Unknown sidecar operation', { status: 400 });
    }
  },
};

// --- Auth ---
async function handleAuth(request: Request, env: SidecarEnv): Promise<Response> {
  const authHeader = request.headers.get('Authorization') ?? '';
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : '';

  if (!token) {
    return Response.json({ ok: false, reason: 'missing_token' }, { status: 401 });
  }

  try {
    const claims = await verifyJwt(token, env.JWT_SECRET);
    // Pass verified claims back as headers so primary Worker can use them
    return Response.json({ ok: true, claims }, {
      headers: {
        'X-Auth-UserId':   claims.sub,
        'X-Auth-TenantId': claims.tenantId,
        'X-Auth-Role':     claims.role,
      },
    });
  } catch (err) {
    return Response.json({ ok: false, reason: 'invalid_token' }, { status: 401 });
  }
}

// --- Rate Limiting ---
async function handleRateLimit(request: Request, env: SidecarEnv): Promise<Response> {
  const key = request.headers.get('X-RateLimit-Key') ?? '';
  if (!key) return Response.json({ ok: false, reason: 'missing_key' }, { status: 400 });

  const { success } = await env.RATE_LIMITER.limit({ key });
  if (!success) {
    return Response.json({ ok: false, reason: 'rate_limited' }, {
      status: 429,
      headers: { 'Retry-After': '1' },
    });
  }
  return Response.json({ ok: true });
}

// --- Structured Logging ---
async function handleLog(request: Request, env: SidecarEnv): Promise<Response> {
  const entry = await request.json<Record<string, unknown>>();
  const enriched = {
    ...entry,
    ts: new Date().toISOString(),
    cf: {
      colo: request.cf?.colo,
      country: request.cf?.country,
    },
  };
  // Best-effort async delivery via Queue
  await env.LOG_SINK.send(enriched).catch(() => {});
  return new Response(null, { status: 204 });
}
```

```toml
# sidecar-worker/wrangler.toml
name = "sidecar-worker"
main = "src/index.ts"

[[queues.producers]]
binding = "LOG_SINK"
queue   = "structured-logs"

[vars]
# JWT_SECRET set via secret: wrangler secret put JWT_SECRET

[[rate_limiting]]
binding     = "RATE_LIMITER"
namespace_id = "<your-namespace-id>"
simple      = { limit = 100, period = 60 }
```

### 2. Primary Worker — calling the sidecar via Service Binding

```typescript
// primary-worker/src/index.ts
export interface PrimaryEnv {
  SIDECAR: Fetcher; // Service Binding
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: PrimaryEnv, ctx: ExecutionContext): Promise<Response> {
    // 1. Auth check via sidecar
    const authRes = await env.SIDECAR.fetch(
      new Request('https://sidecar/auth', { headers: request.headers })
    );

    if (!authRes.ok) {
      // Forward the 401/403 directly from sidecar
      return authRes;
    }

    const { claims } = await authRes.json<{ claims: Record<string, string> }>();

    // 2. Rate limit check via sidecar
    const rlRes = await env.SIDECAR.fetch(
      new Request('https://sidecar/ratelimit', {
        headers: { 'X-RateLimit-Key': `${claims.tenantId}:${claims.sub}` },
      })
    );

    if (!rlRes.ok) return rlRes; // 429

    // 3. Business logic
    const url = new URL(request.url);
    const result = await handleBusinessLogic(url, claims, env);

    // 4. Async log via sidecar (fire-and-forget)
    ctx.waitUntil(
      env.SIDECAR.fetch(
        new Request('https://sidecar/log', {
          method: 'POST',
          body: JSON.stringify({
            type: 'request',
            path: url.pathname,
            userId: claims.sub,
            tenantId: claims.tenantId,
            status: result.status,
          }),
        })
      ).catch(() => {})
    );

    return result;
  },
};

async function handleBusinessLogic(
  url: URL,
  claims: Record<string, string>,
  env: PrimaryEnv
): Promise<Response> {
  // Tenant-scoped D1 query
  const { results } = await env.DB.prepare(
    'SELECT * FROM orders WHERE tenant_id = ? LIMIT 20'
  ).bind(claims.tenantId).all();
  return Response.json(results);
}
```

```toml
# primary-worker/wrangler.toml
name = "primary-worker"
main = "src/index.ts"

[[services]]
binding = "SIDECAR"
service = "sidecar-worker"

[[d1_databases]]
binding  = "DB"
database_name = "my-db"
database_id   = "<db-id>"
```

### 3. Sidecar Versioning — independent rollout

```bash
# Deploy a new sidecar version (primary Workers are unaffected)
cd sidecar-worker
npx wrangler deploy

# Verify sidecar health without touching primaries
curl -X POST https://sidecar-worker.example.workers.dev/auth \
  -H 'Authorization: Bearer <test-token>'
```

### 4. Local Development with Multiple Workers

```toml
# wrangler.toml for the primary (local dev override)
[[services]]
binding = "SIDECAR"
service = "sidecar-worker"
local_only = true  # uses wrangler dev for sidecar
```

```bash
# Terminal 1 — start sidecar on port 8788
cd sidecar-worker && npx wrangler dev --port 8788

# Terminal 2 — start primary; wrangler routes SIDECAR binding to localhost:8788
cd primary-worker && npx wrangler dev --port 8787
```

### 5. Passing Sidecar Results Back via Headers

When the sidecar enriches a request (e.g., auth claims), return data as response headers in addition to a JSON body. This lets the primary Worker avoid a second JSON parse if it only needs one field:

```typescript
// In primary Worker — reading auth claims from headers (fast path)
const userId   = authRes.headers.get('X-Auth-UserId')   ?? '';
const tenantId = authRes.headers.get('X-Auth-TenantId') ?? '';
const role     = authRes.headers.get('X-Auth-Role')     ?? 'viewer';
// No JSON parse needed for simple cases
```

## Implementation Details

- **Zero-latency binding**: Service Binding calls do not cross a network boundary — they are V8 isolate-to-isolate calls within the same Cloudflare PoP. Typical overhead is sub-millisecond.
- **Request forwarding**: The primary Worker constructs a synthetic `Request` to the sidecar. The URL host (`https://sidecar/`) is arbitrary — only the pathname is routed by the sidecar.
- **Separate secret management**: The sidecar owns secrets (`JWT_SECRET`, API keys) the primary Worker never sees. This is a security boundary improvement over a shared-secret monolith.
- **`ctx.waitUntil()` for logging**: Logging must not block the response. Fire-and-forget with `waitUntil` keeps the sidecar call alive after the response is sent.
- **Sidecar as a pure function**: The sidecar should have no side effects on the primary Worker's response except via its returned `Response`. Avoid the sidecar mutating shared state the primary Worker reads in the same request cycle.

## Anti-patterns

- **Sidecar as an API gateway**: The sidecar should handle cross-cutting concerns, not business routing. Routing logic belongs in the primary Worker or a dedicated router Worker.
- **Awaiting sidecar for every log line**: Buffer logs in memory, flush once at the end of the request via `waitUntil`.
- **Single monolithic sidecar doing too much**: Split auth, rate limiting, and logging into separate sidecars if they have different SLAs or deployment cadences.
- **Using the sidecar for data access**: Data access (D1, KV, R2) belongs in the primary Worker or a dedicated data-layer Worker, not the sidecar.

## Gotchas

- Service Bindings require both Workers to be deployed to the same Cloudflare account. Cross-account bindings are not supported.
- A sidecar crash (unhandled exception) surfaces as a 500 to the primary Worker. The primary must handle this defensively.
- Service Binding calls count toward the primary Worker's CPU time budget, not a separate budget.
- `wrangler dev` Service Binding routing between local Workers requires Wrangler 3.x or later.
- When deploying a breaking change to the sidecar interface, use Cloudflare's gradual rollout (Worker versions + traffic splitting) to avoid breaking in-flight primary requests.

## Verification

```bash
# Unit test the sidecar in isolation
cd sidecar-worker
npx vitest run

# Integration test: primary calls sidecar
npx wrangler dev --port 8787 &
SIDECAR_PID=$!

curl -s http://localhost:8787/ \
  -H 'Authorization: Bearer invalid-token' | jq .reason
# Expected: "invalid_token"

curl -s http://localhost:8787/ \
  -H "Authorization: Bearer $(node gen-test-jwt.js)" | jq .length
# Expected: number of orders

kill $SIDECAR_PID
```

## Related

- `workers-hexagonal-architecture-ports-adapters.md`
- `anti-corruption-layer-legacy.md`
- `workers-backends-for-frontends-pattern.md`
- `workers-graceful-degradation-feature-tiers.md`

## Sources

- Burns, B. & Oppenheimer, D. (2016). "Design patterns for container-based distributed systems". USENIX HotCloud.
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Rate Limiting: https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- Cloudflare Workers Queues: https://developers.cloudflare.com/queues/
