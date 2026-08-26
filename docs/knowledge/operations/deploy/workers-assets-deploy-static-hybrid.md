# Workers Assets Static-Hybrid Deployment Pattern

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to deploy a full-stack application where static files (HTML, JS bundles, images,
fonts) are served directly from Cloudflare's edge storage with zero compute cost, while
a subset of routes (`/api/*`, `/auth/*`, `/ws`) are handled by a Worker with dynamic
logic, bindings (KV, D1, R2, Durable Objects), and middleware. The goal is **one
deployment unit** — not two separate projects — with the Worker and assets sharing the
same custom domain.

## Context

Since 2024 Cloudflare Workers supports an **Assets binding** (`assets = {binding =
"ASSETS", directory = "..."}`) that lets a Worker serve a directory of static files
from Workers KV-backed edge storage. The Worker script decides per-request whether to
delegate to `env.ASSETS.fetch(request)` or handle the request itself. This pattern
replaces the older Workers Sites approach and competes with Cloudflare Pages for
full-stack deployments — the key difference being that the Worker has full programmatic
control over request routing.

---

## Project Structure

```
my-app/
├── wrangler.toml
├── src/
│   └── index.ts          # Worker entry point
├── dist/                 # SPA / SSG build output (vite build → dist)
│   ├── index.html
│   ├── assets/
│   └── _headers          # optional custom headers
└── package.json
```

---

## wrangler.toml Configuration

```toml
name            = "my-app"
main            = "src/index.ts"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]

# Static assets binding — serves files from ./dist at the edge
[assets]
directory = "./dist"
binding   = "ASSETS"

# Optional: configure asset routing behaviour
[assets.serve_directly]
# true  — requests to /assets/* bypass the Worker entirely (fastest)
# false — every request goes through fetch() handler first (default)
# Omit for the default (false), which lets the Worker intercept everything
serve_directly = false

[[kv_namespaces]]
binding  = "SESSIONS"
id       = "abc123"

[[d1_databases]]
binding      = "DB"
database_name = "my-app-db"
database_id  = "def456"

[env.staging]
name = "my-app-staging"
[env.staging.assets]
directory = "./dist"
binding   = "ASSETS"
[[env.staging.kv_namespaces]]
binding = "SESSIONS"
id      = "staging-kv-id"
[[env.staging.d1_databases]]
binding       = "DB"
database_name = "my-app-staging-db"
database_id   = "staging-db-id"
```

---

## Worker Entry Point — Hybrid Routing

```typescript
// src/index.ts
export interface Env {
  ASSETS: Fetcher;       // static assets binding
  SESSIONS: KVNamespace;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // --- Dynamic routes handled by the Worker ---
    if (url.pathname.startsWith("/api/")) {
      return handleApi(request, env, ctx);
    }

    if (url.pathname.startsWith("/auth/")) {
      return handleAuth(request, env, ctx);
    }

    // --- Everything else: delegate to static assets ---
    // ASSETS.fetch() serves the file from edge storage, or returns 404
    // if the file doesn't exist.
    const assetResponse = await env.ASSETS.fetch(request);

    // SPA fallback: if the asset is missing, serve index.html so the
    // client-side router can handle the path.
    if (assetResponse.status === 404 && !url.pathname.includes(".")) {
      const indexRequest = new Request(
        new URL("/index.html", url.origin),
        request
      );
      return env.ASSETS.fetch(indexRequest);
    }

    return assetResponse;
  },
};

async function handleApi(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === "/api/health") {
    return Response.json({ ok: true, ts: Date.now() });
  }

  // Example D1 query
  if (url.pathname === "/api/items" && request.method === "GET") {
    const { results } = await env.DB.prepare("SELECT id, name FROM items LIMIT 50")
      .all();
    return Response.json(results);
  }

  return new Response("Not Found", { status: 404 });
}

async function handleAuth(
  request: Request,
  env: Env,
  _ctx: ExecutionContext
): Promise<Response> {
  const sessionId = request.headers.get("Cookie")?.match(/session=([^;]+)/)?.[1];
  if (!sessionId) return new Response("Unauthorized", { status: 401 });

  const session = await env.SESSIONS.get(sessionId, "json");
  if (!session) return new Response("Session expired", { status: 401 });

  return Response.json(session);
}
```

---

## Build and Deploy Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers Static Hybrid

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: "22" }

      - run: npm ci

      - name: Build static assets
        run: npm run build          # outputs to ./dist

      - name: Verify dist exists
        run: |
          [[ -d dist ]] || { echo "dist/ missing"; exit 1; }
          echo "dist/ contains $(find dist -type f | wc -l) files"

      - name: Run D1 migrations (staging)
        if: github.ref == 'refs/heads/main'
        run: |
          npx wrangler d1 migrations apply my-app-staging-db \
            --env staging --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy to staging
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Smoke test staging
        run: |
          BASE=https://my-app-staging.example.workers.dev
          curl -sf "$BASE/api/health" | jq -e '.ok == true'
          curl -sf "$BASE/" -o /dev/null -w "%{http_code}" | grep -q 200

      - name: Run D1 migrations (production)
        run: |
          npx wrangler d1 migrations apply my-app-db --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Deploy to production
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

---

## Asset Routing Modes

| `serve_directly` | Behaviour |
|---|---|
| `false` (default) | All requests pass through the Worker's `fetch()` handler. Assets are served via `env.ASSETS.fetch()`. Worker code runs for every request, including static files. |
| `true` | Requests whose path exactly matches an asset file bypass the Worker entirely — served directly from edge storage. Only non-matching paths hit the Worker. |

Use `serve_directly = true` when:
- The Worker has non-trivial CPU work per request and you don't need to intercept static
  file responses.
- You want free CPU billing on asset requests.

Use `serve_directly = false` when:
- You need to inject headers, check auth, or add ETags on all responses including assets.
- You are running A/B tests that gate access to assets.

---

## Anti-patterns

- **Putting the `directory` path inside `src/`** — the assets directory is relative to
  `wrangler.toml`; it must point to the build output, not source files.
- **Checking for file extensions in SPA fallback** — using `.includes(".")` is brittle;
  prefer checking `Content-Type` from the 404 response or maintaining an explicit API
  prefix list.
- **Sharing a single `wrangler.toml` entry for assets across all envs without env
  overrides** — staging and production may use different D1/KV IDs; always define
  `[env.staging]` blocks explicitly.
- **Not running D1 migrations before `wrangler deploy`** — the Worker and schema must
  stay in sync; deploy the migration first, then the Worker.

## Gotchas

- Wrangler uploads the entire `directory` on each deploy. Large asset directories (>500
  MB) significantly increase deploy time. Use content-hashed filenames and a CDN cache
  layer; `wrangler assets` re-uploads only changed files.
- The `ASSETS` binding's `fetch()` method accepts only `Request` objects whose URL
  matches the Worker's own hostname. Passing an external URL throws a runtime error.
- `serve_directly = true` means the Worker's `fetch()` handler never sees those
  requests — you cannot set custom headers on directly-served assets from the Worker.
  Use `_headers` for static header rules in that case.
- There is no way to serve assets from a sub-path prefix only (e.g. `/static/*`). The
  assets binding always maps to the root of the hostname.

## Verification

```bash
# Local dev (assets + worker together)
npx wrangler dev

# Check that static assets are served
curl -I http://localhost:8787/index.html

# Check that the API route is hit (not assets)
curl http://localhost:8787/api/health

# After deploy — check asset and API headers differ
curl -sI https://my-app.example.workers.dev/assets/main.abc.js | grep cache-control
curl -sI https://my-app.example.workers.dev/api/health | grep content-type
```

## Related

- `workers-assets-binding-deploy-patterns.md`
- `workers-kv-to-r2-assets-migration.md`
- `cloudflare-pages-custom-headers-deploy.md`
- `wrangler-deploy-hooks-pre-post-script-automation.md`
- `d1-zero-downtime-schema-migration-workers-compatibility.md`

## Sources

- https://developers.cloudflare.com/workers/static-assets/
- https://developers.cloudflare.com/workers/static-assets/binding/
- https://developers.cloudflare.com/workers/wrangler/configuration/#assets
- https://developers.cloudflare.com/workers/static-assets/routing/
