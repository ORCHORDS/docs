# Cloudflare Pages Functions: Routing and Rewrite Rules

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Pages project handles SPA client-side routing, API proxying, and static assets all from one deployment. Without explicit routing configuration, Pages Functions intercept every request — including static asset fetches — causing latency spikes and unexpected 404s. You need deterministic control over which paths invoke a Function and which are served directly from the asset CDN.

## Context

Cloudflare Pages uses two complementary mechanisms for routing:

- **`_routes.json`** — a static manifest that declares which URL patterns should invoke Functions versus be served as assets. Evaluated before the Function executes.
- **`_headers` and `_redirects`** — flat-file rules for response headers and HTTP redirects, evaluated after asset resolution.
- **`onRequest` middleware in `functions/`** — TypeScript handlers that run when a path matches the Functions layer.

The order of precedence is: `_redirects` → `_routes.json` Function invocation decision → asset lookup → Function handler. Understanding this chain prevents double-invocation bugs and ensures static assets are never accidentally funnelled through a Function.

## Declaring Explicit Invoke and Exclude Paths

The `_routes.json` file lives at the project root and ships with each deployment. Without it, Pages falls back to automatically including all paths that have a corresponding `functions/` file and excluding none.

```json
// _routes.json
{
  "version": 1,
  "include": ["/api/*", "/auth/*", "/_worker.js"],
  "exclude": ["/assets/*", "/*.js", "/*.css", "/*.woff2", "/favicon.ico"]
}
```

The `exclude` list is evaluated first. A path matching `exclude` is always served as an asset, even if it also matches `include`. Use this to explicitly protect static file patterns from ever hitting your Function budget.

## TypeScript Function Handler with Routing Context

```typescript
// functions/api/[[path]].ts
interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  ASSETS: Fetcher;
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env, params } = context;
  const url = new URL(request.url);
  const path = (params.path as string[]) ?? [];

  // Rewrite: strip /api prefix and forward to a backend binding
  if (path[0] === 'health') {
    return new Response(JSON.stringify({ status: 'ok', ts: Date.now() }), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Forward unrecognised API paths to a Service Binding rather than 404
  if (path[0] === 'v2') {
    const upstreamUrl = new URL(request.url);
    upstreamUrl.pathname = '/' + path.slice(1).join('/');
    return env.ASSETS.fetch(new Request(upstreamUrl.toString(), request));
  }

  return new Response('Not found', { status: 404 });
};
```

## Internal Rewrites via the ASSETS Binding

Pages exposes a special `ASSETS` Fetcher binding inside Functions. Use it to serve a specific asset in response to a URL that does not map to that asset on disk — the canonical SPA fallback pattern.

```typescript
// functions/[[catchall]].ts
interface Env {
  ASSETS: Fetcher;
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env } = context;
  const url = new URL(request.url);

  // Let static files pass through unchanged
  const hasExtension = /\.[a-zA-Z0-9]+$/.test(url.pathname);
  if (hasExtension) {
    return env.ASSETS.fetch(request);
  }

  // For all extensionless paths (SPA routes), serve index.html
  const indexUrl = new URL('/index.html', url.origin);
  const indexRequest = new Request(indexUrl.toString(), {
    method: 'GET',
    headers: request.headers,
  });
  const response = await env.ASSETS.fetch(indexRequest);

  // Strip cache headers so the SPA shell is always fresh
  const mutable = new Response(response.body, response);
  mutable.headers.set('Cache-Control', 'no-store');
  return mutable;
};
```

## Redirect and Header Rules

The `_redirects` and `_headers` files are deployed as static assets and evaluated by the Pages CDN layer before your Function ever runs.

```
# _redirects
/old-product/:slug  /products/:slug  301
/blog/*             /news/:splat     302
/legacy-api/*       /api/:splat      200  # proxy rewrite (status 200 = pass-through)
```

```
# _headers
/api/*
  Access-Control-Allow-Origin: *
  X-Robots-Tag: noindex

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/*
  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
  X-Content-Type-Options: nosniff
```

A `200` status in `_redirects` is a transparent rewrite — the client sees the original URL but receives the content of the target path. This is evaluated without spinning up a Function, so it is cheaper than doing the same rewrite in TypeScript.

## CI Validation of Routing Rules

Validate `_routes.json` structure and catch accidental wildcard conflicts before deployment:

```typescript
// scripts/validate-routes.ts
import { readFileSync } from 'fs';

interface RoutesManifest {
  version: number;
  include: string[];
  exclude: string[];
}

function validateRoutes(filePath: string): void {
  const raw = readFileSync(filePath, 'utf8');
  const manifest: RoutesManifest = JSON.parse(raw);

  if (manifest.version !== 1) {
    throw new Error(`Unsupported _routes.json version: ${manifest.version}`);
  }

  const dangerousIncludes = manifest.include.filter((p) => p === '/*' || p === '*');
  if (dangerousIncludes.length > 0) {
    throw new Error(
      `_routes.json include contains catch-all "${dangerousIncludes[0]}" — ` +
        'this routes every request through Functions and bypasses asset serving.'
    );
  }

  // Warn if no excludes for known static extensions
  const staticExclude = manifest.exclude.find((p) => p.includes('.js') || p.includes('.css'));
  if (!staticExclude) {
    console.warn('WARNING: _routes.json has no static-asset exclude rules. Asset fetches may hit Function budget.');
  }

  console.log(`✓ _routes.json valid: ${manifest.include.length} includes, ${manifest.exclude.length} excludes`);
}

validateRoutes(process.argv[2] ?? '_routes.json');
```

Add this to your CI pipeline before `wrangler pages deploy`:

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Validate routing rules
  run: npx tsx scripts/validate-routes.ts public/_routes.json

- name: Deploy to Pages
  run: npx wrangler pages deploy public --project-name my-app
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Anti-patterns

- **No `_routes.json` with a catch-all Function** — every request, including JS and CSS files, invokes the Function, consuming your daily invocation budget and adding cold-start latency to static asset fetches.
- **Serving the SPA fallback from `_redirects` with status 200 while also having a `[[catchall]]` Function** — both mechanisms fire; the `_redirects` layer wins, but the Function still executes and its result is discarded.
- **Mutating the `ASSETS` fetch request body** — the ASSETS binding only accepts GET and HEAD. Passing a POST request directly to it silently returns a 405.
- **Putting auth middleware in `functions/[[catchall]].ts` without excluding static assets** — unauthenticated users cannot load your CSS or JS.

## Gotchas

- Pages limits `_routes.json` to 100 rules total (include + exclude combined). Exceeding this causes deployment to fail with a validation error.
- The `ASSETS` binding is not available in Workers deployed via `wrangler deploy` — it is Pages-exclusive.
- `_redirects` rules are case-sensitive on path matching; `_routes.json` is also case-sensitive.
- Functions in subdirectories (`functions/api/users.ts`) automatically generate include patterns for their path. If you also provide a `_routes.json`, your explicit list replaces the auto-generated one entirely — you must re-declare any paths you still want to route.
- The Pages build system strips the `functions/` directory from the output served as assets, so a file at `functions/api/hello.ts` does not collide with a static file at `public/api/hello.html`.

## Verification

```bash
# Deploy to a preview branch and smoke-test routing behaviour
wrangler pages deploy public --project-name my-app --branch routing-test

PREVIEW_URL=$(wrangler pages deployment list --project-name my-app \
  --format json | jq -r '.[0].url')

# Static asset should not invoke Function (check for missing x-function-invoked header)
curl -si "$PREVIEW_URL/assets/main.js" | grep -i "x-function"

# API path should reach Function
curl -si "$PREVIEW_URL/api/health" | grep "200 OK"

# SPA route should return index.html content
curl -s "$PREVIEW_URL/some/deep/route" | grep '<div id="root">'
```

## Related

- `cloudflare-pages-build-watch-paths-optimization.md`
- `cloudflare-pages-branch-deploy-preview-d1-seeding.md`
- `workers-assets-binding-deploy-patterns.md`
- `deploy-gate-e2e-tests-playwright-pages.md`

## Sources

- Cloudflare Pages Functions routing documentation: https://developers.cloudflare.com/pages/functions/routing/
- `_routes.json` reference: https://developers.cloudflare.com/pages/functions/routing/#functions-invocation-routes
- Pages `_redirects` syntax: https://developers.cloudflare.com/pages/configuration/redirects/
- Pages `_headers` syntax: https://developers.cloudflare.com/pages/configuration/headers/
