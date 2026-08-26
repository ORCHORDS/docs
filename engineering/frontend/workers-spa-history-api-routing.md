# SPA Routing Support (HTML5 History API) Served from Workers + R2

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A React/Vue/Svelte SPA is deployed to R2 + Workers. Direct navigation to `/app/dashboard` or `/settings/profile` returns a 404 because R2 only serves exact file paths. The Worker must intercept 404s and return `index.html`, allowing the client-side router to take over.

## Context

HTML5 History API routing (`pushState`) means the browser URL changes without a real page navigation, but if the user bookmarks `/app/dashboard` and opens it fresh, the browser makes a real HTTP GET to that path. R2 has no object at that key, so it returns 404. The Worker must:

1. Serve exact asset paths (JS, CSS, fonts, images) from R2 with long `max-age`.
2. Serve `index.html` for any path that doesn't match a real asset — with `no-cache` so the SPA shell always re-validates.
3. Inject preload `Link` headers for critical assets to start resource discovery before HTML is parsed.
4. Handle `ETag`-based conditional requests for `index.html` to avoid sending the full response when unchanged.

---

## Solution

### 1. Worker — SPA Routing Handler

```typescript
// worker/src/index.ts

export interface Env {
  ASSETS_BUCKET: R2Bucket;
  INDEX_HTML_KEY: string; // e.g. 'index.html'
}

/** Paths that look like file references (have an extension). */
const ASSET_EXTENSION_RE = /\.([a-z0-9]{1,8})$/i;

/**
 * Assets with content-addressed hashes in their filenames can be cached
 * indefinitely. Vite/CRA/webpack output these by default.
 * Example: /assets/main.a1b2c3d4.js
 */
const IMMUTABLE_ASSET_RE = /\/assets\/[^/]+\.[0-9a-f]{8,}\.[a-z]+$/;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const pathname = url.pathname;

    // Normalise double slashes
    if (pathname.includes('//')) {
      return Response.redirect(url.origin + pathname.replace(/\/+/g, '/'), 301);
    }

    // 1. Check if the path looks like a real asset (has a file extension)
    if (ASSET_EXTENSION_RE.test(pathname)) {
      return serveR2Asset(request, env, pathname.slice(1));
    }

    // 2. SPA fallback — serve index.html for all extension-less paths
    return serveIndex(request, env);
  },
};

/**
 * Serve a specific asset from R2.
 * Uses conditional request headers (If-None-Match, If-Modified-Since).
 */
async function serveR2Asset(request: Request, env: Env, key: string): Promise<Response> {
  const ifNoneMatch = request.headers.get('If-None-Match');
  const ifModifiedSince = request.headers.get('If-Modified-Since');

  const r2Options: R2GetOptions = {};

  // Pass ETag to R2 for conditional fetch — avoids full object download
  if (ifNoneMatch) {
    // R2 ETags include quotes; strip them for the conditional option
    r2Options.onlyIf = { etagDoesNotMatch: ifNoneMatch.replace(/"/g, '') };
  }

  const object = await env.ASSETS_BUCKET.get(key, r2Options);

  // 304 Not Modified
  if (object === null && ifNoneMatch) {
    return new Response(null, { status: 304 });
  }

  if (object === null) {
    return new Response('Not Found', { status: 404 });
  }

  const isImmutable = IMMUTABLE_ASSET_RE.test('/' + key);

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('ETag', `"${object.etag}"`);
  headers.set(
    'Cache-Control',
    isImmutable
      ? 'public, max-age=31536000, immutable'
      : 'public, max-age=3600'
  );
  // Security headers for JS/CSS
  headers.set('X-Content-Type-Options', 'nosniff');

  return new Response(object.body, {
    status: 200,
    headers,
  });
}

/**
 * Serve index.html for SPA routes.
 * Uses ETag-based conditional caching so unchanged shells return 304.
 */
async function serveIndex(request: Request, env: Env): Promise<Response> {
  const ifNoneMatch = request.headers.get('If-None-Match');
  const indexKey = env.INDEX_HTML_KEY || 'index.html';

  const r2Options: R2GetOptions = {};
  if (ifNoneMatch) {
    r2Options.onlyIf = { etagDoesNotMatch: ifNoneMatch.replace(/"/g, '') };
  }

  const object = await env.ASSETS_BUCKET.get(indexKey, r2Options);

  if (object === null && ifNoneMatch) {
    return new Response(null, { status: 304 });
  }

  if (object === null) {
    return new Response('Service Unavailable — index.html missing', { status: 503 });
  }

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('Content-Type', 'text/html; charset=utf-8');
  headers.set('ETag', `"${object.etag}"`);
  // index.html must NOT be cached immutably — SPA shell changes on deploy
  headers.set('Cache-Control', 'public, no-cache');
  // Inject preload Link headers for critical assets
  headers.set(
    'Link',
    [
      '</assets/main.js>; rel=preload; as=script',
      '</assets/main.css>; rel=preload; as=style',
      '</assets/inter.woff2>; rel=preload; as=font; crossorigin',
    ].join(', ')
  );

  return new Response(object.body, {
    status: 200,
    headers,
  });
}
```

### 2. R2 Upload Script — Deploy SPA Build Artifacts

```typescript
// scripts/deploy-spa.ts
import { readdir, readFile, stat } from 'node:fs/promises';
import { join, relative, extname } from 'node:path';

const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const R2_BUCKET = 'spa-assets';
const BUILD_DIR = './dist';

const CONTENT_TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
};

async function uploadFile(localPath: string, key: string): Promise<void> {
  const body = await readFile(localPath);
  const ext = extname(localPath);
  const contentType = CONTENT_TYPES[ext] ?? 'application/octet-stream';

  const url = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/r2/buckets/${R2_BUCKET}/objects/${encodeURIComponent(key)}`;

  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      'Content-Type': contentType,
    },
    body,
  });

  if (!res.ok) throw new Error(`Upload failed for ${key}: ${res.status} ${await res.text()}`);
  console.log(`Uploaded: ${key} (${body.byteLength} bytes)`);
}

async function* walkDir(dir: string): AsyncGenerator<string> {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) yield* walkDir(fullPath);
    else yield fullPath;
  }
}

// Upload all build artifacts
for await (const filePath of walkDir(BUILD_DIR)) {
  const key = relative(BUILD_DIR, filePath);
  await uploadFile(filePath, key);
}
console.log('Deploy complete.');
```

### 3. wrangler.toml

```toml
name = "spa-router"
main = "worker/src/index.ts"
compatibility_date = "2024-09-23"

[vars]
INDEX_HTML_KEY = "index.html"

[[r2_buckets]]
binding = "ASSETS_BUCKET"
bucket_name = "spa-assets"

[env.production]
[[env.production.r2_buckets]]
binding = "ASSETS_BUCKET"
bucket_name = "spa-assets-prod"
```

### 4. Cache Strategy Summary

```typescript
// worker/src/cache-headers.ts

export type CacheStrategy = 'immutable' | 'revalidate' | 'nocache';

export function cacheHeaders(strategy: CacheStrategy): HeadersInit {
  switch (strategy) {
    case 'immutable':
      // Content-addressed assets: cache forever, never revalidate
      return { 'Cache-Control': 'public, max-age=31536000, immutable' };
    case 'revalidate':
      // index.html: must revalidate, but a 304 is cheap
      return { 'Cache-Control': 'public, no-cache' };
    case 'nocache':
      // API responses, dynamic data
      return { 'Cache-Control': 'no-store' };
  }
}

/**
 * Map file paths to cache strategies.
 * Call this in the Worker to decide headers per asset.
 */
export function strategyForPath(pathname: string): CacheStrategy {
  if (pathname === '/' || pathname.endsWith('.html')) return 'revalidate';
  if (IMMUTABLE_ASSET_RE.test(pathname)) return 'immutable';
  return 'revalidate';
}

const IMMUTABLE_ASSET_RE = /\/assets\/[^/]+\.[0-9a-f]{8,}\.[a-z0-9]+$/i;
```

---

## Implementation Details

- **Extension heuristic**: Paths without a known file extension are treated as SPA routes and fall through to `index.html`. This handles `/app/dashboard`, `/settings`, `/user/123`, etc. Paths like `/favicon.ico` or `/robots.txt` are served from R2 directly.
- **R2 conditional fetch with `onlyIf`**: Passing `etagDoesNotMatch` to `R2Bucket.get()` instructs R2 to return `null` if the ETag has not changed, letting the Worker return `304 Not Modified` without downloading the object. This is critical for `index.html` which is fetched on every page load.
- **`Cache-Control: public, no-cache` for index.html**: This means browsers and CDNs cache the file but must revalidate before using it. Combined with ETag, this means only a single tiny `304` response is sent if the SPA shell hasn't changed.
- **`immutable` flag for hashed assets**: Browsers that support the `immutable` extension (Firefox, Chrome) will never revalidate these assets — even on hard reload — because they know the URL encodes the content hash.
- **`Link` preload headers**: Injected at the Worker level, these fire before the browser has parsed `index.html`. Critical JS and CSS start downloading immediately, reducing Time-to-Interactive by 100–400 ms on fast connections.

---

## Anti-patterns

- **Serving `index.html` for paths with extensions**: A request for `/favicon.ico` should not return `index.html`. Always check for file extensions before falling through.
- **`Cache-Control: max-age=86400` on `index.html`**: Users will get stale SPA shells for up to a day after a deploy. Use `no-cache` + ETag instead.
- **Uploading `index.html` to R2 without setting `Content-Type: text/html`**: R2 will serve it as `application/octet-stream`, causing the browser to download rather than render it.
- **Not deleting old hashed assets after a deploy**: Old assets from a previous deploy remain in R2 forever if not cleaned. Set up a cleanup script or R2 lifecycle rules.
- **Not setting `X-Content-Type-Options: nosniff`**: Without this, some browsers may sniff JavaScript files and misidentify them, opening XSS vectors.

---

## Gotchas

- R2 `etagDoesNotMatch` comparison is **case-sensitive** and excludes the surrounding quotes. Strip the quotes from the `If-None-Match` header before passing to the option, as shown in the code.
- R2 ETags for the same object change when the object is re-uploaded, even with identical content. Your deploy pipeline must upload only changed files, or every `index.html` deploy will bust the cache for all users.
- When `object.writeHttpMetadata(headers)` is called, it sets `Content-Type` and `Content-Encoding` from the R2 object's stored metadata. If you forgot to set `Content-Type` on upload, this returns no content-type header and the response defaults to `application/octet-stream`.
- The `Link` preload header for fonts requires `crossorigin` (even when same-origin) because fonts are fetched with CORS. Omitting it results in the font being fetched twice.
- Workers in front of R2 count R2 Class A operations (writes) and Class B operations (reads). Each `ASSETS_BUCKET.get()` is a Class B op — free tier is 10 million/month. High-traffic sites should add Cloudflare Cache API caching in front of R2.

---

## Verification

```bash
# Deploy Worker
npx wrangler deploy

# Direct navigation to SPA route — must return index.html, not 404
curl -sI https://your-worker.workers.dev/app/dashboard \
  | grep -E 'HTTP|content-type|cache-control|etag'
# Expected:
# HTTP/2 200
# content-type: text/html; charset=utf-8
# cache-control: public, no-cache
# etag: "<hash>"

# Second request with ETag — must return 304
ETAG=$(curl -sI https://your-worker.workers.dev/ | grep etag | awk '{print $2}' | tr -d '\r')
curl -sI https://your-worker.workers.dev/ -H "If-None-Match: $ETAG" | head -1
# Expected: HTTP/2 304

# Hashed asset — must be immutable
curl -sI https://your-worker.workers.dev/assets/main.a1b2c3d4.js \
  | grep cache-control
# Expected: cache-control: public, max-age=31536000, immutable

# 404 for truly missing file
curl -sI https://your-worker.workers.dev/missing-file.xyz | head -1
# Expected: HTTP/2 404
```

---

## Related

- `documentation/categories/frontend/workers-view-transitions-api-edge.md`
- `documentation/categories/frontend/workers-font-subsetting-r2.md`
- `documentation/categories/frontend/workers-static-form-handler-d1.md`

---

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/workers/runtime-apis/request/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Link
- https://web.dev/articles/http-cache
