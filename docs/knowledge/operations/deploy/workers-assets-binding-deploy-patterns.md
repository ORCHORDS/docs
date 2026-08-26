# Workers Assets Binding Deploy Patterns

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You want to serve static assets (HTML, JS, CSS, images) directly from a Cloudflare Worker — without a separate Pages project — so the Worker script can intercept requests, modify responses, inject headers, or implement authentication before serving files. The legacy `[site]` binding is deprecated; the current `assets` binding provides a first-class, fetch-compatible interface for asset serving within the Workers runtime.

## Context

The Workers Assets binding (`[assets]` in `wrangler.toml`) uploads static files alongside the Worker script and exposes them through a typed `env.ASSETS.fetch()` interface. The Worker receives all requests first; it can decide to pass through to assets, modify the response, or return a custom response entirely. This pattern unifies API and static asset serving in a single Worker deployment, eliminates the need for a Pages project for simple SPA or static-plus-API workloads, and supports custom caching, auth, and header injection at deploy time.

---

## 1. Basic Assets Binding Configuration

Configure the `[assets]` block in `wrangler.toml` to upload a local directory alongside the Worker.

```toml
# wrangler.toml
name = "my-full-stack-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]

[assets]
directory = "./public"
binding = "ASSETS"
```

The `directory` path is relative to `wrangler.toml`. All files under `./public` are hashed, uploaded, and served from Cloudflare's global network.

---

## 2. Typed Asset Fetch in Worker Script

Use the `ASSETS` binding to fall through to static files after handling API routes.

```typescript
// src/index.ts
interface Env {
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Intercept API routes
    if (url.pathname.startsWith('/api/')) {
      return handleApi(request, env);
    }

    // Serve static assets for all other paths
    const assetResponse = await env.ASSETS.fetch(request);

    // Inject security headers on all asset responses
    const headers = new Headers(assetResponse.headers);
    headers.set('X-Frame-Options', 'DENY');
    headers.set('X-Content-Type-Options', 'nosniff');
    headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

    return new Response(assetResponse.body, {
      status: assetResponse.status,
      headers,
    });
  },
};

async function handleApi(request: Request, env: Env): Promise<Response> {
  return Response.json({ ok: true, path: new URL(request.url).pathname });
}
```

---

## 3. SPA Fallback Pattern

For single-page applications, any unmatched path should serve `index.html` rather than returning a 404 from the asset binding.

```typescript
// src/index.ts — SPA fallback
interface Env {
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // API routes bypass asset serving
    if (url.pathname.startsWith('/api/')) {
      return handleApi(request, env);
    }

    // Attempt to serve the exact asset
    const assetResponse = await env.ASSETS.fetch(request);

    // If asset not found, serve index.html for SPA client-side routing
    if (assetResponse.status === 404) {
      const indexRequest = new Request(new URL('/index.html', request.url).toString(), request);
      return env.ASSETS.fetch(indexRequest);
    }

    return assetResponse;
  },
};
```

---

## 4. Authentication Gate Before Asset Serving

Require a valid session cookie before serving any static asset, enabling private content distribution.

```typescript
// src/index.ts — authenticated static serving
interface Env {
  ASSETS: Fetcher;
  SESSIONS: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Allow public paths unconditionally
    const PUBLIC_PATHS = ['/login', '/assets/logo.png', '/favicon.ico'];
    if (PUBLIC_PATHS.some((p) => url.pathname === p)) {
      return env.ASSETS.fetch(request);
    }

    // Validate session
    const sessionId = getCookie(request, 'session_id');
    if (!sessionId) {
      return Response.redirect(new URL('/login', request.url).toString(), 302);
    }

    const session = await env.SESSIONS.get(sessionId);
    if (!session) {
      return Response.redirect(new URL('/login', request.url).toString(), 302);
    }

    return env.ASSETS.fetch(request);
  },
};

function getCookie(request: Request, name: string): string | null {
  const cookie = request.headers.get('Cookie') ?? '';
  const match  = cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}
```

---

## 5. Per-Environment Asset Directories

Use `wrangler.toml` environment overrides to serve different asset builds per environment, enabling staging and production to have independent asset sets.

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[assets]
directory = "./dist"
binding = "ASSETS"

[env.staging]
name = "my-worker-staging"

[env.staging.assets]
directory = "./dist-staging"
binding = "ASSETS"

[env.production]
name = "my-worker-prod"

[env.production.assets]
directory = "./dist"
binding = "ASSETS"
```

CI deploy script:

```typescript
// scripts/deploy-with-assets.ts
import { execSync } from 'child_process';

const ENV    = process.env.DEPLOY_ENV ?? 'staging';
const BUILD  = ENV === 'production' ? 'build:prod' : 'build:staging';

// Build the correct asset set
execSync(`npm run ${BUILD}`, { stdio: 'inherit' });

// Deploy with environment-specific asset directory
execSync(`npx wrangler deploy --env ${ENV}`, { stdio: 'inherit' });
```

---

## 6. Cache-Control Header Override for Hashed Assets

Hashed static assets (fingerprinted by build tools) can be served with long-lived cache headers. Non-fingerprinted files like `index.html` need short TTLs.

```typescript
// src/index.ts — selective cache-control
const IMMUTABLE_EXT = /\.(js|css|woff2?|png|jpg|webp|svg)$/;
const HASHED_PATH   = /\.[0-9a-f]{8,}\./; // matches fingerprinted filenames

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const assetResponse = await env.ASSETS.fetch(request);
    if (!assetResponse.ok) return assetResponse;

    const url      = new URL(request.url);
    const headers  = new Headers(assetResponse.headers);
    const isHashed = IMMUTABLE_EXT.test(url.pathname) && HASHED_PATH.test(url.pathname);

    headers.set(
      'Cache-Control',
      isHashed
        ? 'public, max-age=31536000, immutable'
        : 'public, max-age=0, must-revalidate'
    );

    return new Response(assetResponse.body, { status: assetResponse.status, headers });
  },
};
```

---

## Anti-Patterns

- **Using legacy `[site]` binding** — deprecated; `[site]` does not support the typed `Fetcher` interface and has different routing semantics. Migrate to `[assets]`.
- **Placing large binary assets in the `directory`** — Worker bundles have a 25 MB uncompressed limit for the script; while assets are stored separately, extremely large individual files may cause upload failures.
- **Not setting a fallback for SPAs** — without the 404 → index.html fallback, hard refreshes on deep routes return a 404 from the asset binding.
- **Serving the same asset binding path in multiple workers** — only one Worker can own a given route; asset routes conflict if two workers are deployed to the same pattern.

## Gotchas

- `env.ASSETS.fetch()` only accepts `GET` and `HEAD` requests. Passing a `POST` request directly to `ASSETS` returns a 405; handle non-GET methods before falling through to assets.
- The `[assets]` binding directory is hashed at deploy time; updating a file and redeploying the Worker script without the `--assets` step will continue serving the old file.
- `wrangler dev` serves assets from the local filesystem during development; the production upload path may differ from local resolution for index-fallback behavior.
- Asset responses from the binding do not include a `CF-Cache-Status` header — cache-control headers must be set by the Worker itself to influence edge caching behavior.

## Verification

1. Run `wrangler deploy` and check the output for "Uploading N assets" to confirm the directory was included.
2. `curl -I https://your-worker.workers.dev/static/main.js` and verify the expected `Cache-Control` and `Content-Type` headers.
3. Request a non-existent path and confirm the SPA fallback returns `index.html` with status 200.
4. Confirm authentication gate by making an unauthenticated request to a protected path and verifying a `302` redirect to `/login`.

## Related

- `cloudflare-pages-custom-build-config.md`
- `wrangler-environments-promotion-pipeline.md`
- `deploy-cold-start-prewarming.md`
- `env-binding-precedence.md`
- `workers-binding-version-management.md`

## Sources

- https://developers.cloudflare.com/workers/static-assets/
- https://developers.cloudflare.com/workers/static-assets/binding/
- https://developers.cloudflare.com/workers/wrangler/configuration/#assets
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
