# Dynamic CORS Policy Management with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A multi-tenant SaaS product needs to allow different origins for different API routes — the public widget endpoint accepts `https://*.customer.com`, the admin API accepts only `https://app.example.com`, and WebSocket upgrade paths have their own allowlist. A static `Access-Control-Allow-Origin: *` is too broad, but hard-coding every origin in Worker source is inflexible. The origin allowlist must be hot-updatable without redeployment.

---

## Context

CORS is enforced by browsers, not servers. The server's job is to echo the correct headers on every response — including errors — and to respond correctly to preflight `OPTIONS` requests. Common mistakes:

- Reflecting the request `Origin` without checking it against an allowlist (CORS bypass).
- Returning `Access-Control-Allow-Credentials: true` with `Access-Control-Allow-Origin: *` (browser blocks this).
- Omitting `Vary: Origin` when reflecting a specific origin (CDN caches the wrong origin).
- Forgetting CORS headers on error responses (browser sees CORS failure, hides the real error).

KV is the right store for the origin allowlist: reads are ~1 ms at the edge, the list is small, and updates propagate globally within ~60 s without a Worker redeploy.

---

## Solution

### KV Namespace Setup

```toml
# wrangler.toml
[[kv_namespaces]]
binding  = "CORS_CONFIG"
id       = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
preview_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

Store the config as a JSON document keyed by route prefix:

```jsonc
// KV key: "cors:config"
{
  "/api/v1/widget": {
    "origins": ["https://app.customer.com", "https://staging.customer.com"],
    "methods": ["GET", "POST"],
    "headers": ["Content-Type", "X-Widget-Token"],
    "credentials": false,
    "maxAge": 86400
  },
  "/api/v1/admin": {
    "origins": ["https://app.example.com"],
    "methods": ["GET", "POST", "PUT", "DELETE", "PATCH"],
    "headers": ["Content-Type", "Authorization"],
    "credentials": true,
    "maxAge": 3600
  },
  "*": {
    "origins": [],
    "methods": ["GET"],
    "headers": ["Content-Type"],
    "credentials": false,
    "maxAge": 0
  }
}
```

### CORS Middleware

```typescript
// src/lib/cors.ts
export interface CorsRouteConfig {
  origins: string[];
  methods: string[];
  headers: string[];
  credentials: boolean;
  maxAge: number;
}

type CorsConfig = Record<string, CorsRouteConfig>;

interface Env {
  CORS_CONFIG: KVNamespace;
}

const CONFIG_CACHE_KEY = 'cors:config';
const CONFIG_TTL_SECONDS = 60;

let _configCache: { config: CorsConfig; fetchedAt: number } | null = null;

async function getCorsConfig(env: Env): Promise<CorsConfig> {
  const now = Date.now();
  if (_configCache && now - _configCache.fetchedAt < CONFIG_TTL_SECONDS * 1000) {
    return _configCache.config;
  }

  const raw = await env.CORS_CONFIG.get(CONFIG_CACHE_KEY);
  if (!raw) {
    // Default deny-all if KV is empty
    return { '*': { origins: [], methods: ['GET'], headers: [], credentials: false, maxAge: 0 } };
  }

  const config: CorsConfig = JSON.parse(raw);
  _configCache = { config, fetchedAt: now };
  return config;
}

function findRouteConfig(config: CorsConfig, pathname: string): CorsRouteConfig {
  // Longest prefix match
  const prefixes = Object.keys(config).filter(k => k !== '*');
  prefixes.sort((a, b) => b.length - a.length);

  for (const prefix of prefixes) {
    if (pathname.startsWith(prefix)) return config[prefix];
  }

  return config['*'] ?? { origins: [], methods: ['GET'], headers: [], credentials: false, maxAge: 0 };
}

function isOriginAllowed(routeConfig: CorsRouteConfig, origin: string): boolean {
  return routeConfig.origins.some(allowed => {
    if (allowed === origin) return true;
    // Wildcard subdomain: "https://*.customer.com"
    if (allowed.startsWith('https://*.')) {
      const suffix = allowed.slice('https://*.'.length);
      return origin.startsWith('https://') && origin.endsWith(suffix);
    }
    return false;
  });
}

export function buildCorsHeaders(
  routeConfig: CorsRouteConfig,
  requestOrigin: string | null,
  isPreflight: boolean
): HeadersInit {
  const headers: Record<string, string> = {};

  if (!requestOrigin) return headers;

  const allowed = isOriginAllowed(routeConfig, requestOrigin);
  if (!allowed) {
    // Return Vary but NOT Allow-Origin — browser will block
    headers['Vary'] = 'Origin';
    return headers;
  }

  // Reflect the specific origin (never wildcard with credentials)
  headers['Access-Control-Allow-Origin'] = requestOrigin;
  headers['Vary'] = 'Origin';

  if (routeConfig.credentials) {
    headers['Access-Control-Allow-Credentials'] = 'true';
  }

  if (isPreflight) {
    headers['Access-Control-Allow-Methods'] = routeConfig.methods.join(', ');
    headers['Access-Control-Allow-Headers'] = routeConfig.headers.join(', ');
    if (routeConfig.maxAge > 0) {
      headers['Access-Control-Max-Age'] = String(routeConfig.maxAge);
    }
  }

  return headers;
}

export async function handleCors(
  request: Request,
  env: Env,
  next: () => Promise<Response>
): Promise<Response> {
  const config = await getCorsConfig(env);
  const url = new URL(request.url);
  const routeConfig = findRouteConfig(config, url.pathname);
  const origin = request.headers.get('Origin');
  const isPreflight = request.method === 'OPTIONS';

  if (isPreflight) {
    const corsHeaders = buildCorsHeaders(routeConfig, origin, true);
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  const response = await next();
  const corsHeaders = buildCorsHeaders(routeConfig, origin, false);

  const newResponse = new Response(response.body, response);
  for (const [key, value] of Object.entries(corsHeaders)) {
    newResponse.headers.set(key, value);
  }
  return newResponse;
}
```

### Worker Entry Point

```typescript
// src/index.ts
import { handleCors } from './lib/cors';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    return handleCors(request, env, async () => {
      // Your application handler
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/v1/widget')) {
        return new Response(JSON.stringify({ data: 'widget payload' }), {
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('Not Found', { status: 404 });
    });
  },
};
```

### CORS Violation Logging

```typescript
// src/lib/cors.ts (extended)
export async function handleCors(
  request: Request,
  env: Env,
  next: () => Promise<Response>
): Promise<Response> {
  const config = await getCorsConfig(env);
  const url = new URL(request.url);
  const routeConfig = findRouteConfig(config, url.pathname);
  const origin = request.headers.get('Origin');
  const isPreflight = request.method === 'OPTIONS';

  // Log rejected origins for security monitoring
  if (origin && !isOriginAllowed(routeConfig, origin)) {
    console.warn(JSON.stringify({
      event: 'cors_rejection',
      origin,
      pathname: url.pathname,
      method: request.method,
      ts: Date.now(),
    }));
  }

  // ... rest of handler
}
```

---

## Implementation Details

- **In-memory cache**: The `_configCache` pattern avoids one KV read per request. The 60-second TTL balances freshness with performance. For instant propagation needs, use KV metadata TTL or a Durable Object.
- **Vary header**: Without `Vary: Origin`, a CDN (or Cloudflare's own cache) may serve a cached response with one origin's CORS headers to a different origin. Always set `Vary: Origin` on any response that includes CORS headers.
- **Wildcard subdomain matching**: The `https://*.customer.com` pattern must validate that the suffix matches exactly — a naive `includes` check can be bypassed with `https://evil.com?x=.customer.com`.
- **Preflight caching**: `Access-Control-Max-Age: 86400` tells browsers to cache the preflight result for 24 hours. Lower values mean more OPTIONS requests; higher values mean slower allowlist updates reach clients.
- **Error responses**: Apply CORS headers in error paths too. The `handleCors` wrapper above handles this because `next()` is called and its response is always augmented.

---

## Anti-patterns

- **`Access-Control-Allow-Origin: *` with `credentials: true`** — browsers reject this combination. If you need credentials, you must reflect the specific origin.
- **Not checking the allowlist before reflecting** — echoing `request.headers.get('Origin')` without validation is a CORS bypass.
- **Setting CORS headers only in the happy path** — 4xx and 5xx responses need CORS headers too, otherwise browsers hide the status code from JavaScript.
- **Storing the full allowlist in source code** — makes it impossible to update without redeployment.
- **Using `*` for `Access-Control-Allow-Headers`** — not all browsers honour this; enumerate explicitly.

---

## Gotchas

- The in-memory `_configCache` is per-isolate. Cloudflare may spawn many isolates; cache invalidation is eventual, not instantaneous.
- `OPTIONS` requests do not carry an `Authorization` header — preflight responses must not require authentication.
- Safari has historically been stricter about CORS than Chrome; test with Safari when using `credentials: true`.
- If the Worker sits behind a Cloudflare Cache rule, ensure CORS-varying responses are not cached globally (use `Cache-Control: private` or bypass cache for authenticated routes).

---

## Verification

```bash
# 1. Allowed origin — expect ACAO header in response
curl -si -H 'Origin: https://app.example.com' \
  -X OPTIONS https://api.example.com/api/v1/admin \
  | grep -i 'access-control'

# 2. Disallowed origin — expect Vary but NO ACAO header
curl -si -H 'Origin: https://evil.com' \
  -X OPTIONS https://api.example.com/api/v1/admin \
  | grep -i 'access-control'

# 3. Wildcard subdomain
curl -si -H 'Origin: https://tenant123.customer.com' \
  -X OPTIONS https://api.example.com/api/v1/widget \
  | grep -i 'access-control-allow-origin'

# 4. Confirm Vary header present
curl -si https://api.example.com/api/v1/widget | grep -i vary

# 5. Update allowlist in KV and verify change propagates within 60s
wrangler kv key put --binding CORS_CONFIG 'cors:config' "$(cat cors-config-updated.json)"
```

---

## Related

- `documentation/docs/policies/security/workers-content-security-policy-dynamic.md`
- `documentation/docs/policies/security/workers-ip-allowlist-kv-middleware.md`
- MDN CORS documentation: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS

---

## Sources

- Fetch Living Standard — CORS protocol: https://fetch.spec.whatwg.org/#http-cors-protocol
- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- OWASP CORS Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
