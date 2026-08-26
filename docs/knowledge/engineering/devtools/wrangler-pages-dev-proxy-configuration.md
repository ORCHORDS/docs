# Wrangler Pages Dev Proxy Configuration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project's frontend (example.com) is served by Cloudflare Pages while its API Workers live in a separate `workers/` package. During local development, the Pages dev server and the API Workers dev server run on different ports, causing CORS errors and broken cookie flows. Configuring Wrangler Pages' built-in proxy eliminates these issues without touching production CORS headers.

## Context

`wrangler pages dev` can act as a reverse proxy that forwards selected URL paths to another local server. This mirrors the Pages project's production routing where `/_worker.js` handles API routes and static assets are served from the Pages CDN. The proxy configuration lives inside the `wrangler.toml` at the root of the Pages project (or in the CLI flags) and is entirely local — it has no effect on production deployment.

## Basic Proxy Setup

The simplest approach forwards all `/api/*` requests from the Pages dev server (`:8788`) to a Wrangler Workers dev server (`:8787`).

```bash
# Terminal 1 – run the API Workers
wrangler dev --port 8787 --local

# Terminal 2 – run Pages with proxy to the API
wrangler pages dev ./dist \
  --port 8788 \
  --proxy 8787
```

`--proxy 8787` instructs Pages dev to forward all unmatched requests (i.e., those not resolved to a static asset in `./dist`) to `localhost:8787`. The forwarded request preserves method, headers, and body.

## Selective Path Forwarding With Functions

For more granular routing, use Pages Functions. Add a `functions/api/[[path]].ts` catch-all that proxies to the Workers dev server only for API traffic, letting static assets fall through:

```typescript
// functions/api/[[path]].ts
export const onRequest: PagesFunction = async ({ request, params, env }) => {
  const workerBase = env.WORKER_ORIGIN ?? "http://localhost:8787";
  const url = new URL(request.url);
  // Reconstruct path under /api/
  const segments = (params["path"] as string[]) ?? [];
  const apiPath = "/api/" + segments.join("/") + url.search;

  const proxied = new Request(workerBase + apiPath, {
    method: request.method,
    headers: request.headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    // Required for streaming bodies
    duplex: "half",
  } as RequestInit & { duplex: string });

  return fetch(proxied);
};
```

Bind the env var in `wrangler.toml` for the Pages project:

```toml
# wrangler.toml (Pages project root)
name = "example project-pages"
compatibility_date = "2025-01-01"
pages_build_output_dir = "./dist"

[vars]
WORKER_ORIGIN = "http://localhost:8787"
```

## Cookie and Auth Header Passthrough

example project uses signed session cookies (`__Secure-session`). The proxy must preserve `Cookie` and `Set-Cookie` headers. Pages Functions inherit the request headers automatically, but verify that `Authorization` and `Cookie` are not stripped:

```typescript
// functions/api/[[path]].ts — auth-aware variant
export const onRequest: PagesFunction<Env> = async ({ request, params, env }) => {
  const workerBase = env.WORKER_ORIGIN ?? "http://localhost:8787";
  const url = new URL(request.url);
  const segments = (params["path"] as string[]) ?? [];
  const upstream = new URL("/api/" + segments.join("/") + url.search, workerBase);

  // Forward the real client IP so Workers rate-limiter works locally
  const forwardedHeaders = new Headers(request.headers);
  forwardedHeaders.set("x-forwarded-for", "127.0.0.1");
  forwardedHeaders.set("x-forwarded-host", url.host);

  const response = await fetch(upstream.toString(), {
    method: request.method,
    headers: forwardedHeaders,
    body: ["GET", "HEAD"].includes(request.method) ? null : request.body,
    redirect: "manual", // Let Pages handle redirects, not the proxy
  });

  // Copy Set-Cookie so auth flows work end-to-end
  const out = new Response(response.body, response);
  response.headers.getSetCookie().forEach((cookie) => {
    out.headers.append("Set-Cookie", cookie);
  });
  return out;
};
```

## Multi-Worker Proxy With Service Bindings

When example project runs multiple Workers locally (e.g., `feed-worker` on `:8787` and `dm-worker` on `:8789`), route per path:

```typescript
// functions/api/[[path]].ts — multi-worker routing
const ROUTE_MAP: Record<string, string> = {
  "feed": "http://localhost:8787",
  "dm": "http://localhost:8789",
  "auth": "http://localhost:8790",
};

export const onRequest: PagesFunction = async ({ request, params }) => {
  const segments = (params["path"] as string[]) ?? [];
  const service = segments[0] ?? "";
  const upstream = ROUTE_MAP[service];

  if (!upstream) {
    return new Response("Not Found", { status: 404 });
  }

  const url = new URL(request.url);
  const proxiedUrl = upstream + "/api/" + segments.join("/") + url.search;
  return fetch(proxiedUrl, {
    method: request.method,
    headers: request.headers,
    body: ["GET", "HEAD"].includes(request.method) ? null : request.body,
  });
};
```

Run the Pages dev server last, after all Workers are started:

```bash
# Start each worker
wrangler dev --config workers/feed/wrangler.toml --port 8787 --local &
wrangler dev --config workers/dm/wrangler.toml --port 8789 --local &
wrangler dev --config workers/auth/wrangler.toml --port 8790 --local &

# Start Pages dev
wrangler pages dev ./apps/web/dist --port 8788
```

## Anti-patterns

- Using `--proxy` and a `functions/` catch-all simultaneously for the same paths — they conflict; pick one approach
- Setting `Access-Control-Allow-Origin: *` on the Workers to "fix" CORS in local dev — this masks the real issue (the proxy is not configured) and will cause prod CORS misconfiguration
- Hardcoding `localhost` in the `WORKER_ORIGIN` var in the deployed Pages project — always scope this var to local dev only via `[env.local]`
- Forgetting `redirect: "manual"` in the proxy fetch — auto-followed redirects change the response origin and break cookie scoping

## Gotchas

- `wrangler pages dev` only watches the `functions/` directory for changes; changes to the proxied Workers require restarting those Workers separately
- The `--proxy` CLI flag forwards ALL unmatched requests; if your Workers have routes like `/health`, they will also be proxied through
- WebSocket upgrade requests (used by example project's live DM feature) are not proxied through `fetch()`; use `--proxy` (the CLI flag) which delegates to `miniflare`'s native proxy stack instead
- `getSetCookie()` is a newer Headers API method; ensure your runtime has it (Node 18.14+ or workerd 2024+)

## Verification

```bash
# Verify cookie round-trip
curl -c /tmp/cookies.txt -b /tmp/cookies.txt \
  -X POST http://localhost:8788/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"anon_test","password":"hunter2"}' -v

# Check Set-Cookie appears in response headers (from Workers -> Pages proxy)
# Then verify cookie is sent on subsequent request:
curl -b /tmp/cookies.txt http://localhost:8788/api/feed -v
```

## Related

- `wrangler-pages-functions-local-cors.md`
- `wrangler-service-bindings-multi-worker-local-dev.md`
- `local-https-dev-proxy-wrangler.md`
- `wrangler-dev-local-d1-r2-kv.md`

## Sources

- https://developers.cloudflare.com/pages/functions/local-development/
- https://developers.cloudflare.com/workers/wrangler/commands/#pages-dev
- https://developers.cloudflare.com/pages/configuration/routing/
