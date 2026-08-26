# Workers Sites vs Cloudflare Pages — Migration and Feature Parity

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You have a project deployed with **Workers Sites** (the original pattern where static assets
are bundled into a Worker via `[site]` in `wrangler.toml`) and you want to know whether to
migrate to **Cloudflare Pages** or **Workers Static Assets** (the newer `assets` binding
introduced in 2024), what features you gain or lose, and how to execute the migration
without breaking production.

## Context

### Three static-serving paradigms in the Cloudflare ecosystem

| Paradigm | Release | How assets are served | Edge functions | Recommended for |
|---|---|---|---|---|
| **Workers Sites** | 2019 | Assets bundled into Worker KV via `wrangler.toml [site]` | Yes (same Worker) | Legacy; no new features |
| **Cloudflare Pages** | 2021 | Git-connected CI, assets on Cloudflare CDN, Functions in `/functions/` | Yes (`/functions/*.ts`) | Full-stack JAMstack with CI/CD |
| **Workers + Assets binding** | 2024 | `assets = { directory = "./dist" }` in `wrangler.toml` | Yes (same Worker) | Programmatic asset serving from a Worker |

Cloudflare has **not** officially deprecated Workers Sites but actively steers new projects
toward Pages (for CI/CD-driven workflows) or the `assets` binding (for programmatic
control).  Workers Sites uses KV internally; assets are uploaded as KV values on deploy,
which has size and performance implications at scale.

## Section 1 — Feature Comparison

| Feature | Workers Sites | Cloudflare Pages | Workers + Assets |
|---|---|---|---|
| Static asset hosting | KV-backed | CDN-native | CDN-native |
| Edge functions | Worker script | `/functions/` directory | Worker script |
| Git-connected CI | No (wrangler deploy) | Yes (GitHub/GitLab) | No |
| Preview deployments | No | Yes (per-branch URL) | No |
| Custom domains | Worker route | Pages custom domain | Worker route |
| `_headers` / `_redirects` | Manual in Worker | Auto-parsed | Partial (via `wrangler.toml`) |
| KV usage for assets | Yes (billable) | No | No |
| Asset file limit | ~20,000 files | 20,000 files | 20,000 files |
| Single file size limit | 25 MB | 25 MB | 25 MB |
| Deploy size limit | No hard limit | 1 GB total | No hard limit |
| Environment variables | `wrangler.toml [vars]` | Dashboard + `wrangler.toml` | `wrangler.toml [vars]` |
| Bindings (KV, D1, R2…) | Yes | Yes (via `wrangler.toml`) | Yes |
| Access / Zero Trust integration | Via WAF | Native Pages Access | Via WAF |
| Build plugins | No | Yes (Pages Build Plugins) | No |

## Section 2 — Workers Sites wrangler.toml (Legacy Pattern)

```toml
# Legacy Workers Sites — DO NOT use for new projects
name = "my-static-site"
main = "workers-site/index.js"          # auto-generated shim
compatibility_date = "2022-01-01"

[site]
bucket = "./public"                       # local build output directory
entry-point = "workers-site"             # auto-generated Worker shim directory
```

The auto-generated `workers-site/index.js` shim uses `@cloudflare/kv-asset-handler` to
serve assets.  When you run `wrangler deploy`, Wrangler uploads every file in `./public`
to a KV namespace named `__STATIC_CONTENT` and binds it to the Worker.

## Section 3 — Migrating to Workers + Assets Binding

This is the recommended migration path for projects that need programmatic logic alongside
assets (i.e. not purely content-first) and do not need Pages CI/CD.

### New wrangler.toml

```toml
name               = "my-static-site"
main               = "src/worker.ts"      # your actual Worker entry (can be minimal)
compatibility_date = "2024-09-23"

# Assets replaces [site] entirely
assets = { directory = "./public", binding = "ASSETS" }

# Any bindings your old Worker used continue to work
[[kv_namespaces]]
binding = "MY_DATA"
id      = "abc123..."
```

### Minimal src/worker.ts (pass-through + custom logic)

```typescript
interface Env {
  ASSETS: Fetcher;        // asset binding — typed as Fetcher
  MY_DATA: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Custom API routes handled by the Worker
    if (url.pathname.startsWith("/api/")) {
      return handleApi(request, env);
    }

    // All other requests: serve from assets (replaces kv-asset-handler)
    return env.ASSETS.fetch(request);
  },
};

async function handleApi(request: Request, env: Env): Promise<Response> {
  const data = await env.MY_DATA.get("config", "json");
  return Response.json({ config: data });
}
```

### Deploy

```bash
npm run build           # generate ./public
npx wrangler deploy     # uploads assets + deploys Worker
```

No more `kv-asset-handler` dependency, no separate KV namespace for assets.

## Section 4 — Migrating to Cloudflare Pages

Prefer Pages when you want:
- Git-triggered deployments with preview URLs per branch.
- The Pages CI build system (Node, Python, Hugo, etc.).
- Native Access integration for staging environments.
- Automatic `_headers` and `_redirects` file parsing.

### Step-by-step migration

**1. Connect the repository in the Dashboard**

Dashboard → Workers & Pages → Create → Pages → Connect to Git → select repo.

Set the build command and output directory to match your framework:

| Framework | Build command | Output dir |
|---|---|---|
| Next.js (static export) | `next build` | `out/` |
| Vite / React | `vite build` | `dist/` |
| Hugo | `hugo --minify` | `public/` |
| Astro | `astro build` | `dist/` |

**2. Migrate environment variables**

Pages environment variables are set in the Dashboard under Settings → Environment
Variables, or declared in `wrangler.toml` under `[env.production.vars]`.  Pages reads
`wrangler.toml` at the project root if present.

```toml
# wrangler.toml for a Pages project
name = "my-pages-site"
pages_build_output_dir = "./dist"

[vars]
API_BASE = "https://api.example.com"

[[kv_namespaces]]
binding = "MY_DATA"
id      = "abc123..."

[[d1_databases]]
binding    = "DB"
database_id = "def456..."
database_name = "mydb"
```

**3. Migrate edge logic to /functions/**

Workers Sites puts all logic in a single Worker.  Pages uses a file-system routing
convention:

```
functions/
  api/
    users.ts           →  GET/POST /api/users
    users/[id].ts      →  /api/users/:id
  _middleware.ts       →  runs on every request
```

```typescript
// functions/api/users.ts
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
}

export const onRequestGet: PagesFunction<Env> = async ({ env, request }) => {
  const users = await env.DB.prepare("SELECT id, name FROM users LIMIT 50").all();
  return Response.json(users.results);
};
```

**4. `_headers` and `_redirects` files**

Place these at the root of your output directory.  Pages parses them automatically.

```
# public/_headers
/api/*
  Cache-Control: no-store
  Access-Control-Allow-Origin: *

/*.js
  Cache-Control: public, max-age=31536000, immutable
```

```
# public/_redirects
/old-path  /new-path  301
/app/*     /app/index.html  200     # SPA fallback
```

**5. Cutover DNS**

After confirming the Pages deployment works on the `*.pages.dev` preview URL:

```bash
# Add custom domain via Dashboard → Pages project → Custom Domains
# or via API:
curl -X POST \
  "https://api.cloudflare.com/client/v4/pages/projects/my-pages-site/domains" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "www.example.com"}'
```

Cloudflare updates DNS automatically if the zone is in your account.

**6. Decommission the old Workers Site**

```bash
# Delete the old Worker (removes the KV asset namespace too after a few days)
npx wrangler delete my-static-site
```

## Mobile vs Desktop Considerations

- **`_headers` Cache-Control on Pages** — set appropriate `Vary: Accept` for images if you
  serve mobile-optimized assets from different paths; Pages does not auto-detect device type
  at the `_headers` level.
- **Pages Functions access to `request.cf.deviceType`** — available the same as in any
  Worker.  A `_middleware.ts` can read device type and rewrite the request to a
  mobile-specific asset path before Pages serves the file.
- **Preview deployment URLs** — Pages generates `*.pages.dev` preview URLs for every push.
  These are great for mobile QA testing via real device browser without DNS changes.
- **Workers Sites KV latency on first mobile request** — KV is eventually consistent and
  may miss cache on the first request to a new PoP after a deploy.  CDN-native Pages asset
  serving avoids this; the first mobile user in a region gets a CDN edge hit, not a KV
  lookup.

## Anti-patterns

- **Leaving Workers Sites in place "for now"** — `kv-asset-handler` has not received new
  features since 2023.  The KV namespace accumulates stale files on every deploy; old
  versions are not automatically purged.
- **Using Pages for purely API-only Workers** — Pages adds unnecessary CI overhead for a
  Worker that returns JSON with no static assets.  Use the standard `wrangler deploy` flow.
- **Mixing `[site]` and `assets` in the same `wrangler.toml`** — they are mutually
  exclusive; Wrangler will error.
- **Custom `kv-asset-handler` logic that duplicates Pages `_headers` behavior** — if
  migrating to Pages, delete the custom handler and let Pages process `_headers` natively.

## Gotchas

- **`__STATIC_CONTENT` KV namespace lingers** — after deleting a Workers Sites deployment,
  the auto-created `__STATIC_CONTENT` KV namespace stays in your account.  Delete it
  manually in the Dashboard to avoid confusion and any residual storage cost.
- **Pages does not support non-module-format Workers** — any `addEventListener('fetch')`
  style Service Worker syntax in `functions/` files will fail.  Use ES module `export
  default` / named export (`onRequestGet`) syntax.
- **Workers + Assets does not parse `_headers`** — unlike Pages, the `assets` binding does
  not read a `_headers` file.  Set response headers in your Worker code manually.
- **Build output directory case sensitivity** — Pages build systems run on Linux; a `./Dist`
  directory configured as `./dist` will fail silently on macOS CI but break in production.
- **Pages Functions have a 1 MB compressed script size limit per function file** — split
  large functions into multiple files or use a shared module pattern.

## Verification

```bash
# Workers Sites: confirm KV asset count before migration
npx wrangler kv key list --binding __STATIC_CONTENT --preview false | wc -l

# Workers + Assets: verify assets are recognized
npx wrangler deploy --dry-run --outdir ./wrangler-out
ls ./wrangler-out/   # should include asset manifest

# Pages: check deployment status
npx wrangler pages deployment list --project-name my-pages-site

# Pages: tail function logs
npx wrangler pages deployment tail --project-name my-pages-site

# Smoke-test redirects after migration
curl -I https://www.example.com/old-path  # expect 301
curl -I https://www.example.com/api/users # expect 200 + CORS headers
```

## Related

- `pages-best-practices.md` — general Pages patterns
- `pages-functions-routing.md` — Pages Functions routing details
- `workers-static-assets.md` — `assets` binding patterns
- `kv-best-practices.md` — managing the `__STATIC_CONTENT` KV namespace
- `pages-headers-config.md` — `_headers` file syntax
- `pages-redirects-config.md` — `_redirects` file syntax

## Sources

- Workers Sites docs: https://developers.cloudflare.com/workers/configuration/sites/
- Workers Assets (new): https://developers.cloudflare.com/workers/static-assets/
- Cloudflare Pages: https://developers.cloudflare.com/pages/
- Pages Functions: https://developers.cloudflare.com/pages/functions/
- Pages wrangler.toml: https://developers.cloudflare.com/pages/functions/wrangler-configuration/
- kv-asset-handler: https://github.com/cloudflare/workers-sdk/tree/main/packages/kv-asset-handler
