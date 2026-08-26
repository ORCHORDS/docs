# API Gateway Pattern on Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) grew to six downstream Workers: feed, posts, reactions, profiles, search, and moderation. Without a gateway layer, each Worker independently implements authentication, rate limiting, and CORS — logic that drifts apart over time and creates inconsistent client-facing error envelopes. Mobile clients hitting six distinct subdomains also pay DNS resolution costs on every cold start.

## Context

The API Gateway pattern centralises cross-cutting concerns — authentication, rate limiting, request routing, logging, and response shaping — into a single entry-point Worker. Downstream services become internal Workers bound via Service Bindings; they never receive unauthenticated or unthrottled traffic. Mobile and desktop clients are differentiated at the gateway so downstream Workers can stay device-agnostic.

## Gateway Architecture

```
Internet
   │
   ▼
Gateway Worker (api.example.com)
   │
   ├── Auth middleware  ─────────────────────────────┐
   ├── Rate-limit middleware (KV token bucket)        │ shared pipeline
   ├── Request-id injection                           │
   ├── Mobile / desktop route split                   │
   │                                                  ▼
   ├── /feed/*    ──► Service Binding ──► feed-worker
   ├── /posts/*   ──► Service Binding ──► post-worker
   ├── /reactions/*─► Service Binding ──► reaction-worker
   ├── /profiles/*──► Service Binding ──► profile-worker
   ├── /search/*  ──► Service Binding ──► search-worker
   └── /mod/*     ──► Service Binding ──► moderation-worker
```

All six downstream Workers are declared in `wrangler.toml` as service bindings; they are never publicly addressable.

## wrangler.toml Gateway Configuration

```toml
name = "gateway-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[services]]
binding = "FEED"
service = "feed-worker"

[[services]]
binding = "POSTS"
service = "post-worker"

[[services]]
binding = "REACTIONS"
service = "reaction-worker"

[[services]]
binding = "PROFILES"
service = "profile-worker"

[[services]]
binding = "SEARCH"
service = "search-worker"

[[services]]
binding = "MOD"
service = "moderation-worker"

[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id = "<namespace-id>"
```

## Auth Middleware

example project uses anonymous identity tokens — short-lived, server-signed JWTs containing a hashed device fingerprint. The gateway verifies the signature before any downstream call.

```typescript
// src/middleware/auth.ts
import { verify } from './jwt';

export async function authMiddleware(
  request: Request,
  env: Env
): Promise<{ anonId: string } | Response> {
  const token = request.headers.get('Authorization')?.replace('Bearer ', '');

  if (!token) {
    return Response.json({ error: 'missing_token' }, { status: 401 });
  }

  try {
    const payload = await verify(token, env.JWT_SECRET);
    return { anonId: payload.sub as string };
  } catch {
    return Response.json({ error: 'invalid_token' }, { status: 401 });
  }
}
```

## Rate-Limit Middleware (KV Token Bucket)

```typescript
// src/middleware/rateLimit.ts
export async function rateLimitMiddleware(
  anonId: string,
  env: Env
): Promise<Response | null> {
  const key = `rl:${anonId}`;
  const now = Date.now();
  const window = 60_000; // 1 minute
  const limit = 120;     // requests per window

  const raw = await env.RATE_LIMIT_KV.get(key, 'json') as
    { count: number; reset: number } | null;

  if (raw && now < raw.reset) {
    if (raw.count >= limit) {
      return new Response(null, {
        status: 429,
        headers: {
          'Retry-After': String(Math.ceil((raw.reset - now) / 1000)),
          'X-RateLimit-Limit': String(limit),
          'X-RateLimit-Remaining': '0',
        },
      });
    }
    await env.RATE_LIMIT_KV.put(key, JSON.stringify({ count: raw.count + 1, reset: raw.reset }),
      { expirationTtl: 60 });
  } else {
    await env.RATE_LIMIT_KV.put(key, JSON.stringify({ count: 1, reset: now + window }),
      { expirationTtl: 60 });
  }

  return null; // allow
}
```

Rate limit tiers per route:

| Route         | Requests / min | Burst allowance |
|---------------|---------------|-----------------|
| GET /feed     | 120           | +20 for mobile  |
| POST /posts   | 10            | None            |
| GET /search   | 30            | None            |
| POST /reactions | 60          | +10 for mobile  |
| GET /profiles | 60            | None            |

## Mobile vs Desktop Route Differentiation

The gateway injects a `X-Client-Tier` header before forwarding to downstream Workers so they can serve appropriately sized payloads without re-parsing the User-Agent.

```typescript
// src/middleware/deviceTier.ts
export function detectDeviceTier(request: Request): 'mobile' | 'desktop' {
  const hint = request.headers.get('X-Device-Hint');
  if (hint === 'mobile') return 'mobile';

  const ua = request.headers.get('User-Agent') ?? '';
  const mobilePattern = /Android|iPhone|iPad|Mobile/i;
  return mobilePattern.test(ua) ? 'mobile' : 'desktop';
}
```

Downstream Workers use `X-Client-Tier` to trim payload size:
- `mobile` → stripped feed cards, 280-char post previews, thumbnail URLs only
- `desktop` → full cards, full post bodies, original media URLs

## Downstream Fan-out

For composite endpoints (e.g. profile page needing both profile data and recent posts), the gateway fans out to multiple downstream Workers in parallel.

```typescript
// src/handlers/profilePage.ts
export async function handleProfilePage(
  request: Request,
  env: Env,
  anonId: string
): Promise<Response> {
  const profileId = new URL(request.url).pathname.split('/')[3];

  const [profileRes, postsRes] = await Promise.all([
    env.PROFILES.fetch(new Request(`https://internal/profiles/${profileId}`, request)),
    env.POSTS.fetch(new Request(`https://internal/posts?author=${profileId}&limit=20`, request)),
  ]);

  if (!profileRes.ok) return profileRes;

  const [profile, posts] = await Promise.all([
    profileRes.json(),
    postsRes.ok ? postsRes.json() : { items: [] },
  ]);

  return Response.json({ profile, posts });
}
```

Fan-out latency model:

```
Sequential: profile(80ms) + posts(60ms) = 140 ms
Parallel:   max(profile(80ms), posts(60ms)) = 80 ms   ← 43% reduction
```

## Gateway Main Handler

```typescript
// src/index.ts
import { authMiddleware } from './middleware/auth';
import { rateLimitMiddleware } from './middleware/rateLimit';
import { detectDeviceTier } from './middleware/deviceTier';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const requestId = crypto.randomUUID();

    // 1. Auth
    const authResult = await authMiddleware(request, env);
    if (authResult instanceof Response) return authResult;
    const { anonId } = authResult;

    // 2. Rate limit
    const rlResp = await rateLimitMiddleware(anonId, env);
    if (rlResp) return rlResp;

    // 3. Enrich request headers
    const tier = detectDeviceTier(request);
    const enriched = new Request(request, {
      headers: {
        ...Object.fromEntries(request.headers),
        'X-Request-Id': requestId,
        'X-Anon-Id': anonId,
        'X-Client-Tier': tier,
      },
    });

    // 4. Route
    const path = url.pathname;
    if (path.startsWith('/feed'))     return env.FEED.fetch(enriched);
    if (path.startsWith('/posts'))    return env.POSTS.fetch(enriched);
    if (path.startsWith('/reactions'))return env.REACTIONS.fetch(enriched);
    if (path.startsWith('/profiles')) return env.PROFILES.fetch(enriched);
    if (path.startsWith('/search'))   return env.SEARCH.fetch(enriched);
    if (path.startsWith('/mod'))      return env.MOD.fetch(enriched);

    return Response.json({ error: 'not_found' }, { status: 404 });
  },
};
```

## Anti-patterns

- **Putting business logic in the gateway** — the gateway handles cross-cutting concerns only; application logic belongs in downstream Workers.
- **Direct internet access to downstream Workers** — bind downstream Workers as services, never expose their routes publicly.
- **Synchronous fan-out over three or more services** — use `Promise.all` for two; for three or more, prefer a Queue-driven aggregation to avoid cascading latency.
- **Storing full JWT payloads in KV for validation** — Workers can verify JWTs in-process using SubtleCrypto; no KV round-trip needed.
- **One rate limit key per IP** — example project is anonymous; rate limit by `anonId` (device fingerprint hash), not by IP, to avoid punishing shared mobile NAT addresses.

## Gotchas

- Service Bindings do not traverse Cloudflare's global network; they execute in-region, so they are faster than `fetch()` to a second Worker hostname but still count as a subrequest.
- Mutating `request.headers` directly throws in the Workers runtime; construct a new `Request` with a merged headers object.
- KV reads for rate limiting add ~10–40 ms; for extreme throughput consider Durable Objects for atomic counter semantics instead.
- `Promise.all` failures are not isolated — if one downstream Worker throws, the entire fan-out rejects; add `.catch()` per binding for graceful partial responses.

## Verification

```bash
# Auth rejection
curl -i https://api.example.com/feed
# Expect: 401 {"error":"missing_token"}

# Valid token routes to feed worker
TOKEN=$(curl -s https://api.example.com/auth/token | jq -r .token)
curl -i -H "Authorization: Bearer $TOKEN" https://api.example.com/feed
# Expect: 200 with feed payload

# Rate limit enforcement (run 121+ times in 60 s)
for i in $(seq 1 125); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer $TOKEN" https://api.example.com/feed
done | sort | uniq -c
# Expect: mix of 200 and 429
```

## Related

- `cqrs-cloudflare-workers-d1.md`
- `rate-limiting-architecture-workers.md`
- `backend-for-frontend-pattern.md`
- `api-gateway-patterns-rate-limiting-routing.md`
- `oauth-architecture.md`
- `service-mesh-patterns.md`

## Sources

- Cloudflare Workers Service Bindings documentation
- Cloudflare KV documentation — TTL and read latency characteristics
- NGINX "API Gateway" pattern documentation
- Richardson, Chris — "Microservices Patterns" ch. 8 (API Gateway)
