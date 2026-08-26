# Wrangler Assets: Static Site + Workers Hybrid Deployment

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You want to serve a static frontend (built by Vite or any bundler) alongside a
Cloudflare Worker API from a single `wrangler deploy`. Previously this required either
Cloudflare Pages (with Pages Functions) or a split deployment: one R2-backed worker for
assets and another for the API. With Workers Assets (GA in 2025), Wrangler can bundle
both a static asset directory and a Worker script into one deployable unit — no Pages
project, no separate CDN origin, no CORS configuration between frontend and API.

## Context

Workers Assets is Wrangler's native static-site hosting feature for Workers. It is
distinct from Cloudflare Pages. Key properties:

- Static files in the configured `directory` are served automatically by the platform
  at the URL paths that mirror the directory structure.
- A Worker `main` script handles requests that do NOT match a static file, enabling
  SPA fallback, API routes, auth middleware, or server-side rendering.
- Asset serving is handled by the Cloudflare edge, not by your Worker code — zero CPU
  time consumed for static requests.
- Works with `wrangler dev --local` for fully offline development.

Stack: Wrangler 3.x, TypeScript, Vite (or any bundler), pnpm, Turborepo.

## Project Structure

```
apps/my-app/
  src/
    index.ts         <- Worker (API + fallback handler)
  frontend/
    src/             <- React/Svelte/Vue source
    dist/            <- Vite build output (git-ignored)
  wrangler.toml
  package.json
  vite.config.ts
```

## wrangler.toml Configuration

```toml
name = "my-app"
main = "src/index.ts"
compatibility_date = "2025-10-01"
compatibility_flags = ["nodejs_compat"]

# Assets configuration — the core of the hybrid setup
[assets]
directory = "frontend/dist"
# html_handling controls how the Worker vs. asset serving is split:
# "auto-trailing-slash"  (default) — redirects /foo to /foo/ if foo/index.html exists
# "force-trailing-slash" — always redirect to trailing-slash form
# "drop-trailing-slash"  — strip trailing slashes
# "none"                 — no redirects, serve exactly as named
html_handling = "auto-trailing-slash"
# not_found_handling controls what happens on a 404:
# "none"                 — return 404 with no body
# "single-page-application" — serve /index.html on any 404 (SPA fallback)
# "404-page"             — serve /404.html
not_found_handling = "single-page-application"

[[d1_databases]]
binding = "DB"
database_name = "myapp"
database_id = "your-d1-id-here"
```

**Critical**: The `[assets]` table was introduced in Wrangler 3.78+. Pinning Wrangler
version in `package.json` prevents silent breakage:

```json
{
  "devDependencies": {
    "wrangler": "^3.78.0"
  }
}
```

## Worker Entry Point (Hybrid Handler)

With `[assets]` configured, the Worker only runs for requests that do not match a static
file. Use this to implement API routes and a catch-all SPA fallback:

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  ASSETS: Fetcher; // injected automatically when [assets] is configured
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // API routes handled by the Worker
    if (url.pathname.startsWith("/api/")) {
      return handleApi(request, env);
    }

    // All other requests fall through to the asset server.
    // The `not_found_handling = "single-page-application"` setting means
    // /index.html is served for any unmatched path — enabling client-side routing.
    // You can also forward manually:
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;

async function handleApi(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === "/api/health" && request.method === "GET") {
    return Response.json({ status: "ok" });
  }

  if (url.pathname === "/api/items" && request.method === "GET") {
    const { results } = await env.DB.prepare("SELECT * FROM items LIMIT 50").all();
    return Response.json(results);
  }

  return new Response("Not Found", { status: 404 });
}
```

The `ASSETS` binding is a `Fetcher` automatically provided by the runtime when
`[assets]` is set — no explicit binding declaration needed in `wrangler.toml`.

## Vite Build Integration

`apps/my-app/vite.config.ts`:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "frontend/dist",
    emptyOutDir: true,
  },
  // In dev mode, proxy /api/* to wrangler dev
  server: {
    proxy: {
      "/api": "http://localhost:8787",
    },
  },
});
```

Build and deploy in one step:

```bash
# 1. Build the frontend
pnpm vite build

# 2. Deploy Worker + assets together
wrangler deploy
```

Wrangler reads the `frontend/dist/` directory, uploads all static files to the Workers
Assets CDN, and deploys the Worker script — one command, one deployment unit.

## Local Development with wrangler dev

```bash
# Start Worker + asset server locally (fully offline, Miniflare-backed)
wrangler dev --local

# In a separate terminal, run Vite in watch mode to rebuild on changes
pnpm vite build --watch
```

Wrangler's `--local` mode watches the `frontend/dist/` directory and serves new files
automatically as Vite rebuilds them. The asset server mirrors production routing
including `not_found_handling`.

For hot-module replacement during frontend development, use Vite's dev server with the
`/api` proxy (see above) rather than Wrangler's asset serving. Once you are done with
frontend work, switch to `wrangler dev --local` to test the full deployment-shape.

## Turborepo Pipeline

```json
// turbo.json
{
  "tasks": {
    "build:frontend": {
      "outputs": ["frontend/dist/**"],
      "inputs": ["frontend/src/**", "vite.config.ts"]
    },
    "deploy": {
      "dependsOn": ["build:frontend", "^build"],
      "cache": false,
      "env": ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]
    }
  }
}
```

`apps/my-app/package.json`:

```json
{
  "scripts": {
    "build:frontend": "vite build",
    "deploy": "wrangler deploy"
  }
}
```

CI runs `pnpm turbo deploy --filter @example-org/example-repo`, which first builds the frontend
(with cache), then deploys. If the frontend has not changed since the last successful
build, Turborepo restores `frontend/dist/` from cache and skips the Vite build.

## Caching and Cache-Control Headers

Workers Assets serves files with long-lived `Cache-Control` headers by default
(`public, max-age=31536000, immutable` for hashed filenames). For files without content
hashes (e.g., `index.html`), the platform uses shorter TTLs. To customize:

```typescript
// In the Worker fetch handler, intercept asset responses and override headers
async fetch(request: Request, env: Env): Promise<Response> {
  const response = await env.ASSETS.fetch(request);
  const url = new URL(request.url);

  if (url.pathname === "/" || url.pathname === "/index.html") {
    const newResponse = new Response(response.body, response);
    newResponse.headers.set(
      "Cache-Control",
      "public, max-age=0, must-revalidate"
    );
    return newResponse;
  }

  return response;
}
```

## Anti-patterns

- **Serving assets from Worker code using `Response` + `fetch`** — Before Workers Assets,
  a common pattern was fetching from R2 inside the Worker. With `[assets]` this is
  unnecessary and adds CPU cost and latency. Use the `ASSETS` fetcher or let the runtime
  serve them automatically.
- **Putting API logic in the `not_found_handling` fallback** — `not_found_handling =
  "single-page-application"` makes the platform serve `index.html` for unmatched paths.
  If you also have API routes, put them before the `env.ASSETS.fetch(request)` call or
  they will be shadowed by the asset server if a file with the same path exists.
- **Forgetting to build the frontend before `wrangler deploy`** — Wrangler uploads
  whatever is in the `directory` at deploy time. An empty or stale `frontend/dist/`
  produces a broken deployment with no error from Wrangler. Make the frontend build a
  hard dependency in CI.
- **Using `[assets]` with Cloudflare Pages projects** — Workers Assets is for Workers
  deployments (`wrangler deploy`), not Pages (`wrangler pages deploy`). The two are
  separate products with different routing semantics.

## Gotchas

- The `ASSETS` binding name is fixed — you cannot rename it. If your `wrangler.toml` has
  another binding named `ASSETS`, Wrangler will error at deploy time.
- `html_handling = "none"` disables all redirects and is appropriate only for fully
  custom routing. Most SPAs need `"auto-trailing-slash"` or the SPA fallback breaks for
  direct URL navigations.
- Files in the `directory` that start with `_` (e.g., `_headers`, `_redirects`) are
  treated as special configuration files and are not served as static assets — same
  behavior as Cloudflare Pages.
- `wrangler dev` in remote mode (`--remote`) serves assets via the real Cloudflare
  network and counts against your Workers Assets storage quota. Use `--local` during
  development to avoid this.

## Verification

```bash
# Check uploaded assets count after deploy
wrangler deployments list --name my-app

# Test static asset serving
curl -I https://my-app.example.workers.dev/index.html
# Expect: 200, Cache-Control header, Content-Type: text/html

# Test API route
curl https://my-app.example.workers.dev/api/health
# Expect: {"status":"ok"}

# Test SPA fallback (non-existent path should return index.html)
curl -sI https://my-app.example.workers.dev/some/client/route
# Expect: 200, Content-Type: text/html (not 404)

# Local smoke test
wrangler dev --local &
curl http://localhost:8787/api/health
curl -I http://localhost:8787/some/route
```

## Related

- `wrangler-dev-local-d1-r2-kv.md`
- `vite-cloudflare-workers-dev-mode.md`
- `wrangler-pages-dev-proxy-configuration.md`
- `wrangler-pages-functions-local-cors.md`
- `turborepo-cloudflare-workers-pipeline.md`

## Sources

- Workers Assets: https://developers.cloudflare.com/workers/static-assets/
- Wrangler assets config: https://developers.cloudflare.com/workers/wrangler/configuration/#assets
- Workers Assets routing: https://developers.cloudflare.com/workers/static-assets/routing/
