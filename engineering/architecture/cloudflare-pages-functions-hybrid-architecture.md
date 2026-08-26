# cloudflare-pages-functions-hybrid-architecture

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

A team ships a Next.js app with `output: "export"` on Cloudflare Pages
for static delivery. They need a handful of authenticated API endpoints
and a server-side redirect for OAuth callbacks. They debate whether to
add Pages Functions alongside the static output or deploy a separate
Worker. Route conflicts between the static export and function files
cause 404s or wrong handler execution. Mobile API clients receive HTML
error pages instead of JSON because routing is ambiguous.

## Context

Cloudflare Pages can serve static assets and run Pages Functions
(a subset of Workers) from the same deployment. A Next.js
`output: "export"` generates a flat `out/` directory with no server
code. Pages Functions live in a `functions/` sibling directory and
are bundled separately at deploy time. This hybrid lets you colocate
lightweight dynamic endpoints with a fully static frontend without
standing up a separate Worker service—but route precedence rules
and mobile API routing require deliberate design.

## 1. Repository Layout

```
my-app/
├── next.config.ts          ← output: "export"
├── out/                    ← static export (gitignored, built)
├── functions/
│   ├── api/
│   │   ├── auth/
│   │   │   └── callback.ts ← /api/auth/callback Pages Function
│   │   └── me.ts           ← /api/me Pages Function
│   └── _middleware.ts      ← runs before every request
├── public/                 ← copied verbatim into out/
└── wrangler.toml           ← if deploying via Wrangler CLI
```

`next.config.ts` for static export:

```typescript
const config: NextConfig = {
  output: "export",
  distDir: "out",
  // Trailing slash required for Pages static routing
  trailingSlash: true,
};
export default config;
```

## 2. Route Precedence Rules

Cloudflare Pages evaluates routes in this fixed order:

```
1. Exact static asset match   (out/api/me/index.html if it exists)
2. Pages Function match        (functions/api/me.ts)
3. _middleware.ts interception (wraps 1 and 2)
4. 404 fallback                (out/404.html or Functions 404)
```

Key implication: if `next export` accidentally emits
`out/api/me/index.html` (e.g., a page at `pages/api/me.tsx`), it
will shadow your Pages Function silently.

Verify no static file shadows a function:

```bash
# After build, confirm no /api/* HTML files
find out/ -path "*/api*" -name "*.html"
# Should print nothing
```

If you have a Next.js `pages/api/` directory, move all API routes to
Pages Functions and remove them from Next.js before exporting.

## 3. Pages Functions vs Separate Worker

| Criterion                  | Pages Function           | Separate Worker            |
|----------------------------|--------------------------|----------------------------|
| Deployment coupling        | Same deploy as frontend  | Independent deploys        |
| Cold-start isolation       | Shared with Pages        | Isolated                   |
| Bindings (KV, DO, D1)      | Full support             | Full support               |
| CPU limit                  | 10 ms (default plan)     | 10 ms / 30 s (paid)        |
| Cron triggers              | Not available            | Available                  |
| Wrangler tail / debug      | Via `pages deployment`   | Via `wrangler tail`        |
| Recommended for            | Auth, user APIs, BFF     | Heavy compute, cron, queues|

Use Pages Functions when the endpoint is tightly coupled to the UI
deployment (A/B redirects, auth callbacks, SSR-adjacent BFF calls).
Use a separate Worker when the endpoint needs cron, Queues consumer,
or must deploy independently of the frontend.

## 4. Pages Function Implementation Pattern

```typescript
// functions/api/me.ts
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
  SESSION_KV: KVNamespace;
}

export const onRequestGet: PagesFunction<Env> = async (ctx) => {
  const sessionId = getCookie(ctx.request, "sid");
  if (!sessionId) {
    return new Response(JSON.stringify({ error: "unauthenticated" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const userId = await ctx.env.SESSION_KV.get(`session:${sessionId}`);
  if (!userId) {
    return new Response(JSON.stringify({ error: "session_expired" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const user = await ctx.env.DB
    .prepare("SELECT id, email, name FROM users WHERE id = ?")
    .bind(userId)
    .first();

  return new Response(JSON.stringify(user), {
    headers: { "Content-Type": "application/json" },
  });
};
```

## 5. Mobile API Routing Decisions

Mobile apps (iOS, Android) call `/api/*` endpoints directly. They
must always receive JSON, never HTML. Three patterns to enforce this:

**Pattern A — Middleware content-type guard**

```typescript
// functions/_middleware.ts
export const onRequest: PagesFunction = async (ctx) => {
  const url = new URL(ctx.request.url);
  if (url.pathname.startsWith("/api/")) {
    const res = await ctx.next();
    // If a static HTML fallback leaked through, return JSON error
    const ct = res.headers.get("Content-Type") ?? "";
    if (ct.includes("text/html")) {
      return new Response(JSON.stringify({ error: "not_found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }
    return res;
  }
  return ctx.next();
};
```

**Pattern B — Dedicated API subdomain on a separate Worker**

Route `api.example.com` to a Worker; route `www.example.com` to
Pages. Mobile apps target `api.example.com` exclusively. No routing
ambiguity. Drawback: CORS must be configured explicitly.

**Pattern C — `Accept: application/json` detection in middleware**

Detect mobile API callers by `Accept` header and route accordingly.
Less reliable than pattern A or B; avoid.

## 6. Wrangler / Pages Deployment Config

```toml
# wrangler.toml (used with `wrangler pages deploy out/`)
name = "my-app"
pages_build_output_dir = "out"

[[kv_namespaces]]
binding = "SESSION_KV"
id = "..."

[[d1_databases]]
binding = "DB"
database_name = "myapp-prod"
database_id = "..."

[vars]
ENVIRONMENT = "production"
```

Build pipeline:

```bash
npm run build          # next build → out/
wrangler pages deploy out/ --project-name my-app
```

## Anti-Patterns

- **Using `next start` or SSR mode** on Pages — Pages does not run
  a Node.js server; only `output: "export"` is fully supported.
- **Putting API logic in `public/`** — files in public/ are served as
  static assets; they cannot execute.
- **Using `next/image` default loader** with static export — it
  requires a server; use `unoptimized: true` or a custom loader.
- **Returning `text/html` from an API Function** — breaks mobile
  clients that parse JSON unconditionally.
- **Deploying Pages Functions and a separate Worker to the same
  route** — leads to undefined winner; use custom domains to segment.

## Gotchas

- Pages Functions are limited to the `_worker.js` advanced mode for
  complex bundling; standard Functions cannot use `wrangler.toml`
  module syntax without the `_worker.js` entrypoint.
- Bindings declared in `wrangler.toml` must also be declared in the
  Pages project dashboard for production; `wrangler.toml` only applies
  to `wrangler pages dev`.
- `ctx.next()` in middleware calls the next handler in the chain,
  including static asset lookup; it is NOT equivalent to `fetch`.
- Trailing-slash mismatches between Next.js config and Pages routing
  cause double 301 redirects on mobile clients sensitive to redirect
  loops.

## Verification

```bash
# Local dev with functions and static together
wrangler pages dev out/ --binding SESSION_KV=...

# Confirm function handles /api/me
curl http://localhost:8788/api/me
# Expected: {"error":"unauthenticated"} with 401

# Confirm static page still served
curl http://localhost:8788/
# Expected: HTML of index page

# Confirm no HTML bleeds through API paths
curl -H "Accept: application/json" http://localhost:8788/api/nonexistent
# Expected: {"error":"not_found"} JSON, NOT HTML 404 page
```

## Related

- `documentation/categories/architecture/backend-for-frontend-pattern.md`
- `documentation/categories/architecture/api-versioning-strategy.md`
- `documentation/categories/architecture/rate-limiting-architecture-workers.md`
- `documentation/categories/architecture/cdn-architecture.md`
- `documentation/categories/architecture/function-as-a-service-patterns.md`

## Source URLs

- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/pages/framework-guides/nextjs/deploy-a-static-nextjs-site/
- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/functions/bindings/
