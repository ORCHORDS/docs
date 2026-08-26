# Deploying a Static Site with Workers Assets

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to host a static site (React SPA, Next.js export, plain HTML) on Cloudflare Workers without using Cloudflare Pages, leveraging the new Workers Assets binding that replaces Pages static hosting. The site must support custom headers, redirect rules, and client-side routing fallback so that direct URL navigation and hard refreshes return the correct `index.html`.

---

## Context

Workers Assets is the successor to Cloudflare Pages static hosting, available through the Worker runtime starting mid-2024. Instead of a separate Pages project, you declare an `assets` binding in `wrangler.toml` pointing at your build output directory; Wrangler uploads the files and serves them through the Workers edge network with automatic content-type negotiation and cache headers. The `_headers` and `_redirects` files at the root of the asset directory are parsed by the runtime and applied before the Worker script executes, preserving feature parity with Pages. SPA fallback routing is controlled by `not_found_handling = "single-page-application"`, which returns `index.html` with a 200 status for any path that does not resolve to a known asset. This approach collapses the Pages + Worker split into a single deployable unit that shares KV, D1, and other bindings.

---

## Section 1 — wrangler.toml Configuration

```toml
# wrangler.toml
name = "my-static-site"
main = "src/worker.ts"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]

[assets]
binding = "ASSETS"
directory = "./dist"
not_found_handling = "single-page-application"
html_handling = "auto-trailing-slash"

[[d1_databases]]
binding = "DB"
database_name = "site-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
ENVIRONMENT = "production"

[env.staging]
name = "my-static-site-staging"

[env.staging.vars]
ENVIRONMENT = "staging"

[env.staging.assets]
binding = "ASSETS"
directory = "./dist"
not_found_handling = "single-page-application"
```

---

## Section 2 — Custom Headers, Redirects, and Worker Script

```
# dist/_headers
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), camera=(), microphone=()

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/index.html
  Cache-Control: no-cache, no-store, must-revalidate
```

```
# dist/_redirects
/old-path  /new-path  301
/legacy/*  /new/:splat  302
/api/*     https://api.example.com/:splat  200
```

```typescript
// src/worker.ts
import type { Fetcher } from '@cloudflare/workers-types';

export interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
  ENVIRONMENT: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Serve API routes from the Worker, everything else from assets
    if (url.pathname.startsWith('/api/internal/')) {
      return handleInternalApi(request, env);
    }

    // Let the ASSETS binding handle static files and SPA fallback
    return env.ASSETS.fetch(request);
  },
};

async function handleInternalApi(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'GET') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  const { pathname } = new URL(request.url);

  if (pathname === '/api/internal/health') {
    const result = await env.DB.prepare('SELECT 1 AS ok').first<{ ok: number }>();
    return Response.json({ status: 'ok', db: result?.ok === 1, env: env.ENVIRONMENT });
  }

  return new Response('Not Found', { status: 404 });
}
```

---

## Section 3 — Build Pipeline and Deploy Commands

```bash
#!/usr/bin/env bash
# scripts/deploy-static.sh
set -euo pipefail

ENV="${1:-production}"

echo "==> Building for $ENV"
npm run build  # produces ./dist

echo "==> Checking dist exists"
[ -d ./dist ] || { echo "ERROR: dist directory missing after build"; exit 1; }

echo "==> Copying headers and redirects"
cp public/_headers ./dist/_headers
cp public/_redirects ./dist/_redirects

if [ "$ENV" = "staging" ]; then
  echo "==> Deploying to staging"
  npx wrangler deploy --env staging
else
  echo "==> Deploying to production"
  npx wrangler deploy
fi

echo "==> Deployment complete"
npx wrangler deployments list | head -5
```

```yaml
# .github/workflows/deploy-static.yml
name: Deploy Static Site

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
      - run: npm ci
      - run: npm run build
      - name: Copy asset control files
        run: |
          cp public/_headers dist/_headers
          cp public/_redirects dist/_redirects
      - name: Deploy Workers Assets
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

---

## Anti-patterns
- **Omitting `not_found_handling`** — without it, 404 responses from the asset store bubble up as actual 404s, breaking client-side routing in SPAs.
- **Using Pages and Workers Assets simultaneously for the same domain** — pick one deployment model per project to avoid routing conflicts.
- **Placing `_headers` / `_redirects` outside the `directory` root** — they must live at the root of the served asset tree, not in the project root.
- **Hardcoding cache headers only in the Worker** — for static assets, the `_headers` file is evaluated before the Worker script; duplicating logic causes race conditions.

---

## Gotchas
- `html_handling = "auto-trailing-slash"` rewrites `/about` → `/about/` and serves `about/index.html`; set to `"none"` if your framework already handles this.
- The `ASSETS` binding's `fetch()` always returns a `Response` — it never throws — so there is no need to wrap it in try/catch.
- Asset upload limits: 20,000 files per deployment, 25 MB per file, 1 GB total. Exceed these and `wrangler deploy` fails with a descriptive error.
- Environment-specific `[env.X.assets]` blocks must redeclare both `binding` and `directory`; they do not inherit from the top-level `[assets]` block.

---

## Verification

```bash
# Local preview with asset serving
npx wrangler dev --local

# Verify SPA fallback (should return 200 with index.html content)
curl -s -o /dev/null -w "%{http_code}" https://my-static-site.example.com/some/deep/route

# Check deployed assets
npx wrangler deployments list

# Inspect headers on a cached asset
curl -I https://my-static-site.example.com/assets/main.abc123.js
```

---

## Related
- `cloudflare-pages-direct-upload-ci.md`
- `wrangler-deploy-dry-run-schema-validation.md`

---

## Sources
- Workers Assets documentation — https://developers.cloudflare.com/workers/static-assets/
- Workers Assets binding — https://developers.cloudflare.com/workers/static-assets/binding/
- _headers and _redirects support — https://developers.cloudflare.com/workers/static-assets/headers-and-redirects/
- SPA routing — https://developers.cloudflare.com/workers/static-assets/routing/
