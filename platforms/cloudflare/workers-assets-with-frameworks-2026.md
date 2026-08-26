# workers-assets-with-frameworks-2026

Deploying modern JS frameworks (Next.js, Remix, Astro, Nuxt, SvelteKit) to
Cloudflare Workers using the Workers Static Assets binding — the 2026 successor
to Pages Functions. Covers the migration path and the gotchas that break
frameworks that assume Node.js.

## Symptom

You followed a framework's Cloudflare deploy guide and got one of:

```text
Error: The module "node:fs" could not be found
Error: Request context is not available
TypeError: process.env is undefined
Error: Static asset <path> not found in manifest
```

Or: the deploy succeeds, the homepage loads, but client-side routing 404s on
refresh, or API routes return `text/html` instead of JSON.

## Background: Workers Static Assets

In 2026, Cloudflare unified Pages and Workers. The `assets` binding in
`wrangler.toml` lets a Worker serve static files (your built frontend) AND
server-side code from the same deployment. This replaces Pages Functions.

```toml
# wrangler.toml — modern framework deploy
name = "my-app"
main = "./worker/index.ts"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

# Serve built frontend assets
[assets]
directory = "./dist"
binding = "ASSETS"
not_found_handling = "single-page-application"  # SPA fallback
```

```typescript
// worker/index.ts — minimal pass-through for SPA
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return env.ASSETS.fetch(request);
  },
};
```

## Solution: Per-framework setup

### Next.js (App Router, 2026 recommended config)

```toml
# wrangler.toml
name = "next-app"
main = ".open-next/worker.js"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

[assets]
directory = ".open-next/assets"
binding = "ASSETS"
```

Build with OpenNext (the maintained Cloudflare adapter for Next.js):

```bash
npx @opennextjs/cloudflare build
npx wrangler deploy
```

### Astro

```bash
npx astro add cloudflare
```

```astro
// astro.config.mjs
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';

export default defineConfig({
  output: 'server',
  adapter: cloudflare({
    platformProxy: { enabled: true },
  }),
});
```

```toml
# wrangler.toml
name = "astro-app"
main = "./dist/_worker.js"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

[assets]
directory = "./dist"
binding = "ASSETS"
```

### Remix

```bash
npx create-remix@latest --template cloudflare
```

```typescript
// worker/index.ts
import { createRequestHandler } from "@remix-run/cloudflare";
import * as build from "../build/server";

export default {
  async fetch(request, env, ctx) {
    const handler = createRequestHandler(build, "production");
    return handler(request, { env, ctx });
  },
};
```

## Common errors and fixes

### `node:fs` / `node:path` / `node:crypto` not found

```toml
# You MUST add this flag
compatibility_flags = ["nodejs_compat"]
```

`nodejs_compat` enables Node.js built-in module shims. Without it, any
framework code touching `fs`, `path`, `crypto`, etc. crashes at runtime.

### Static assets 404 on direct navigation (client-side routing)

```toml
[assets]
directory = "./dist"
binding = "ASSETS"
not_found_handling = "single-page-application"
```

The `single-page-application` setting serves `index.html` for any path not
matching a static file — essential for React Router / Vue Router apps.

### API routes return HTML

Your framework's API routes are being caught by the SPA fallback. Fix:

```toml
[assets]
directory = "./dist"
binding = "ASSETS"
run_worker_first = true   # Worker handles ALL requests first; only falls
                          # through to assets if Worker doesn't respond
```

With `run_worker_first = true`, the Worker processes every request. The
Worker must explicitly serve assets for non-API routes:

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // API routes → handled here
    if (url.pathname.startsWith("/api/")) {
      return handleApi(request);
    }

    // Everything else → serve static assets
    return env.ASSETS.fetch(request);
  },
};
```

### `process.env` is undefined

Workers don't have `process.env`. Frameworks that read `process.env` at module
scope break. Two fixes:

```typescript
// Fix 1: shim process.env from the env binding (top of worker)
globalThis.process = { env: {} } as any;
```

Or configure the framework to use Cloudflare's env:

```typescript
// Remix example — pass env to loader context
export default {
  async fetch(request, env, ctx) {
    const handler = createRequestHandler(build, "production");
    return handler(request, {
      env,
      ctx,
      // Make env available as process.env for framework code
      process: { env },
    });
  },
};
```

## Gotchas

- **`nodejs_compat` does NOT give you real Node.js.** It shims ~40 common
  modules. Anything using native addons, `child_process`, `cluster`, or deep
  Node internals will still fail. Check the compat docs for the full list.
- **`run_worker_first` changes asset caching behavior.** When the Worker
  intercepts every request, Cloudflare's automatic static asset CDN caching
  no longer applies unless your Worker sets proper `Cache-Control` headers.
- **Hot module reload (HMR) doesn't work with `wrangler dev` for assets.**
  Use the framework's own dev server (`npm run dev`) for development, and
  only use `wrangler dev` to test the production build.
- **`_routes.json` (from Pages) is gone.** In Workers + Assets, routing
  control is via `run_worker_first` and your Worker code. There's no
  file-based exclude list anymore.
- **Large asset directories slow deploys.** If `./dist` has 10,000+ files
  (common with Next.js image optimization), deploys take minutes. Use R2
  for user-uploaded media; keep `[assets]` directory to build output only.
- **Migrating from Pages? The URL changes.** `my-app.pages.dev` becomes
  `my-app.<subdomain>.workers.dev` (or your custom domain). Plan a DNS
  cutover — there's no automatic redirect.
- **Environment variables are NOT injected at build time.** In Pages, some
  vars were available during build. In Workers, all secrets/env vars are
  runtime-only via the `env` parameter. Pre-build vars must go in
  `wrangler.toml` `[vars]` or be baked into the build via `.env` files.
- **`compatibility_date` matters more than you think.** Framework adapters
  target specific runtime features. If your framework docs say "use
  compatibility_date X", use exactly that date — newer dates can introduce
  breaking behavior changes that the adapter hasn't accounted for.

## Migration checklist (Pages → Workers + Assets)

1. [ ] Add `[assets]` block to `wrangler.toml` pointing to build output
2. [ ] Set `compatibility_flags = ["nodejs_compat"]`
3. [ ] Convert Pages Functions (`functions/` dir) to a Worker entry point
4. [ ] Move `_routes.json` logic into `run_worker_first` + Worker code
5. [ ] Test API routes separately from static assets
6. [ ] Update CI/CD: `wrangler pages deploy` → `wrangler deploy`
7. [ ] Update DNS: `*.pages.dev` → `*.workers.dev` (or custom domain)
8. [ ] Verify client-side routing works on hard refresh
