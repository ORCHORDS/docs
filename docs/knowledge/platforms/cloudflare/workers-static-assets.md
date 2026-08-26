# workers-static-assets

**Issue:** Serving static assets from Cloudflare Workers — the new Assets binding replaces Sites
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context

You want to serve a frontend SPA or static files alongside your Workers API.
The old `@cloudflare/kv-asset-handler` + Workers Sites approach is deprecated.
The new `assets` binding in `wrangler.toml` is the current recommended pattern.

## Pattern / Solution

### wrangler.toml

```toml
name = "my-app"
compatibility_date = "2024-09-23"

[assets]
directory = "./dist"
binding = "ASSETS"
```

### Serving assets from a Worker

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // API routes handled by Worker
    if (url.pathname.startsWith('/api/')) {
      return handleApi(request, env);
    }

    // All other requests served from static assets
    return env.ASSETS.fetch(request);
  },
};
```

### SPA fallback (serve index.html for unknown paths)

```typescript
async fetch(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname.startsWith('/api/')) {
    return handleApi(request, env);
  }

  // Try to serve the asset
  const assetResponse = await env.ASSETS.fetch(request);

  // If 404 (SPA route), serve index.html
  if (assetResponse.status === 404) {
    return env.ASSETS.fetch(new Request(new URL('/', request.url)));
  }

  return assetResponse;
},
```

### Env interface

```typescript
interface Env {
  ASSETS: Fetcher;  // from @cloudflare/workers-types
  DB?: D1Database;
}
```

### Build pipeline

```bash
# Build frontend
npm run build  # outputs to ./dist

# Deploy (Worker + assets together)
wrangler deploy
```

## Gotchas

- **`ASSETS` type is `Fetcher`**, not `R2Bucket` or `KVNamespace`. It has a `.fetch(request)` method.
- **Not for Pages**: This pattern is for standalone Workers. Pages has its own static asset pipeline — don't mix them.
- **Cache headers**: Assets are served with `Cache-Control` based on the file extension. Set custom headers in `_headers` file in your dist directory.
- **Workers Sites is deprecated**: `@cloudflare/kv-asset-handler` and `[site]` in wrangler.toml are legacy. Migrate to `[assets]`.
- **`directory` path is relative to wrangler.toml**: Use `./dist` not `/dist`.
- **404 handling**: Without the SPA fallback, a direct navigation to `/dashboard` returns a 404. Always add the index.html fallback for SPAs.

## Related

- `wrangler-toml-reference.md`
- `pages-static-vs-functions.md`
- `workers-best-practices.md`
- `pages-functions-routing.md`
