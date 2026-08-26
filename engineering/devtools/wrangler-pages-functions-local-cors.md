# Wrangler Pages Functions Dev Local CORS Configuration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Pages Functions API returns CORS errors when called from the local Vite/Next.js dev server running on `localhost:3000`. `wrangler pages dev` starts on `localhost:8788` and the browser blocks cross-origin requests because the Function does not return `Access-Control-Allow-Origin` headers. Preflight `OPTIONS` requests return 404.

## Context

Cloudflare Pages Functions are TypeScript files placed under `functions/` at the repo root (or a custom path configured in `wrangler.toml`). `wrangler pages dev` serves them locally on port 8788 by default. When a front-end dev server on a different port fetches the Functions API, the browser enforces CORS. Unlike Workers deployed with a single `wrangler.toml`, Pages Functions share their origin with the Pages site in production, so CORS headers are often unnecessary there but required during local dev where different ports create different origins.

The standard solution is to add a reusable CORS middleware to `functions/` that handles `OPTIONS` preflight and injects response headers. For local dev only, `wrangler pages dev` also supports a `--compatibility-flags` flag and proxy integration with Vite.

---

## CORS Middleware for Pages Functions

```typescript
// functions/_middleware.ts
import type { PagesFunction, EventContext } from "@cloudflare/workers-types";

const ALLOWED_ORIGINS_DEV = [
  "http://localhost:3000",
  "http://localhost:5173",
  "http://127.0.0.1:3000",
];

const CORS_HEADERS_COMMON: Record<string, string> = {
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
  "Access-Control-Max-Age": "86400",
};

function getCorsOrigin(request: Request): string | null {
  const origin = request.headers.get("Origin");
  if (!origin) return null;
  // In production the Pages site shares the origin so this is not reached.
  // In dev the front-end is on a different port — allow configured origins.
  const isDev = origin.startsWith("http://localhost") ||
                origin.startsWith("http://127.0.0.1");
  if (isDev && ALLOWED_ORIGINS_DEV.includes(origin)) return origin;
  return null;
}

export const onRequest: PagesFunction = async (context) => {
  const { request, next } = context;
  const corsOrigin = getCorsOrigin(request);

  // Handle preflight
  if (request.method === "OPTIONS" && corsOrigin) {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": corsOrigin,
        ...CORS_HEADERS_COMMON,
      },
    });
  }

  const response = await next();

  if (corsOrigin) {
    const mutable = new Response(response.body, response);
    mutable.headers.set("Access-Control-Allow-Origin", corsOrigin);
    mutable.headers.set("Vary", "Origin");
    Object.entries(CORS_HEADERS_COMMON).forEach(([k, v]) =>
      mutable.headers.set(k, v)
    );
    return mutable;
  }

  return response;
};
```

`_middleware.ts` at the `functions/` root runs before every Function. The `next()` call invokes the matched route Function; the middleware then wraps its response.

---

## Individual Function with CORS Helper

```typescript
// functions/api/users.ts
import type { PagesFunction } from "@cloudflare/workers-types";

// Reusable helper for JSON responses
function json<T>(data: T, status = 200, corsOrigin?: string): Response {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (corsOrigin) {
    headers["Access-Control-Allow-Origin"] = corsOrigin;
    headers["Vary"] = "Origin";
  }
  return new Response(JSON.stringify(data), { status, headers });
}

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const origin = request.headers.get("Origin") ?? undefined;
  const users = await env.DB.prepare("SELECT id, email FROM users").all();
  return json(users.results, 200, origin);
};
```

For routes that do not use the middleware (e.g. in sub-directories with their own `_middleware.ts`), pass the `Origin` header through to the helper explicitly.

---

## Running wrangler pages dev with a Proxy Front-end

```bash
# Start the front-end dev server first
pnpm --filter ./apps/web dev   # runs on localhost:3000

# Start Pages Functions dev server
pnpm wrangler pages dev ./public \
  --port 8788 \
  --proxy 3000 \
  --compatibility-date 2025-01-01
```

`--proxy 3000` tells Wrangler to proxy non-Function requests to `localhost:3000`. This means you can point your browser at `localhost:8788` and have both the front-end and Functions served from the same origin, eliminating CORS entirely in local dev. CORS middleware is then only needed for tools (like Postman or Bruno) that call the Functions directly.

---

## wrangler.toml Configuration for Pages Dev

```toml
# wrangler.toml
name = "my-pages-app"
pages_build_output_dir = "./dist"
compatibility_date = "2025-01-01"

[dev]
port = 8788
local_protocol = "http"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

The `[dev]` section sets defaults that `wrangler pages dev` respects, removing the need to pass `--port` on every invocation.

---

## Testing CORS Locally with curl

```bash
# Test a simple GET — confirm header is returned
curl -v \
  -H "Origin: http://localhost:3000" \
  http://localhost:8788/api/users \
  2>&1 | grep -i "access-control"
# Expected: access-control-allow-origin: http://localhost:3000

# Test OPTIONS preflight
curl -v -X OPTIONS \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  http://localhost:8788/api/users \
  2>&1 | grep -E "HTTP/|access-control"
# Expected: HTTP/1.1 204, access-control-allow-origin: http://localhost:3000
```

---

## Anti-patterns

- **Returning `Access-Control-Allow-Origin: *` in the middleware** — wildcard origins block `credentials: "include"` requests. Use explicit origin reflection from the allowed list.
- **Adding CORS headers to the preflight `OPTIONS` response but not the actual response** — browsers check both; missing headers on the non-preflight response still causes CORS failures.
- **Hardcoding the production domain in the dev middleware** — keep dev-only origins (localhost) in the middleware and configure production-allowed origins via an environment variable or separate deployment config.
- **Forgetting to add `Vary: Origin`** — without it, CDN caches (including Cloudflare) may serve a response with the wrong `Access-Control-Allow-Origin` to a different origin.

---

## Gotchas

- `_middleware.ts` files are scoped to the directory they live in and all sub-directories. A `functions/api/_middleware.ts` does not cover `functions/auth/`.
- `wrangler pages dev` does not support hot-reloading `_middleware.ts` changes on some versions; restart the process after editing the middleware.
- When using `--proxy`, requests served by the proxy front-end do not pass through Pages Functions middleware. Only requests to paths matched by `functions/` files are routed through Wrangler.
- The `Env` type for Pages Functions bindings must be generated by `wrangler types` targeting the Pages project, not a Workers `wrangler.toml`. The generated interface may differ.
- In production on Cloudflare Pages, the Functions and the static site share the same `pages.dev` domain, so CORS headers are not needed for same-origin fetches. Only custom domain deployments serving the API from a different subdomain require production CORS headers.

---

## Verification

```bash
# Confirm middleware file is picked up
pnpm wrangler pages dev ./public --port 8788 2>&1 | grep "_middleware"
# Expected: something like "Serving worker at functions/_middleware.ts"

# Confirm preflight returns 204
curl -s -o /dev/null -w "%{http_code}" -X OPTIONS \
  -H "Origin: http://localhost:3000" \
  http://localhost:8788/api/users
# Expected: 204

# Confirm credential requests are not broken
curl -v \
  -H "Origin: http://localhost:3000" \
  -H "Cookie: session=test" \
  http://localhost:8788/api/users \
  2>&1 | grep "access-control-allow-origin"
```

---

## Related

- `wrangler-dev-local-d1-r2-kv.md` — full local binding configuration for Pages dev
- `local-https-dev-proxy-wrangler.md` — HTTPS proxy setup for local wrangler dev
- `hono-openapi-spec-generation.md` — typed routing layer that handles CORS via middleware
- `playwright-e2e-workers-wrangler-dev.md` — end-to-end testing against wrangler pages dev

---

## Sources

- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/workers/runtime-apis/response/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
