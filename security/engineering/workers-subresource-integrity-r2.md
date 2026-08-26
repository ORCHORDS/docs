# Subresource Integrity (SRI) Hash Generation and Validation for R2-Served Assets

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your application serves JavaScript bundles and CSS files from Cloudflare R2 via a Worker. You need to guarantee that the content retrieved from R2 matches what was uploaded — defending against storage-layer tampering — and that browsers reject any modified asset via Subresource Integrity (SRI) attributes. Integrity failures must be audited.

## Context

Subresource Integrity is a W3C browser security feature: when a `<script>` or `<link>` element carries an `integrity` attribute containing a base64-encoded cryptographic hash, the browser refuses to execute or apply the resource if the fetched content does not match. Cloudflare Workers + R2 handle both sides: the Worker computes SHA-384 hashes at upload time, stores them in R2 object metadata, and injects `integrity` attributes via `HTMLRewriter` when serving HTML. On direct asset requests, the Worker re-verifies the hash before serving.

## Solution

### Step 1 — SHA-384 Hash Generation on Upload

```typescript
// lib/sri.ts
export async function computeSha384(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-384', data);
  return 'sha384-' + arrayBufferToBase64(digest);
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export async function computeContentHash(data: ArrayBuffer): Promise<string> {
  // SHA-256 hex hash used as the content-addressable URL segment
  const digest = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
```

### Step 2 — Upload Handler with SRI Metadata

```typescript
// handlers/upload.ts
import { computeSha384, computeContentHash } from '../lib/sri';

export async function handleAssetUpload(
  request: Request,
  bucket: R2Bucket,
  db: D1Database
): Promise<Response> {
  if (request.method !== 'PUT') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  const url = new URL(request.url);
  const originalPath = url.searchParams.get('path');
  if (!originalPath) {
    return new Response('Missing ?path parameter', { status: 400 });
  }

  const body = await request.arrayBuffer();
  const sriHash = await computeSha384(body);
  const contentHash = await computeContentHash(body);
  const contentType = request.headers.get('Content-Type') ?? 'application/octet-stream';

  // Content-addressable path: assets/<sha256-hex>/<original-filename>
  const fileName = originalPath.split('/').pop() ?? 'asset';
  const r2Key = `assets/${contentHash}/${fileName}`;

  await bucket.put(r2Key, body, {
    httpMetadata: { contentType },
    customMetadata: {
      sriHash,
      originalPath,
      uploadedAt: new Date().toISOString(),
    },
  });

  // Record in D1 for HTML injection lookup by original path
  await db.prepare(
    `INSERT INTO asset_hashes (original_path, r2_key, sri_hash, content_hash, uploaded_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(original_path) DO UPDATE SET
       r2_key = excluded.r2_key,
       sri_hash = excluded.sri_hash,
       content_hash = excluded.content_hash,
       uploaded_at = excluded.uploaded_at`
  ).bind(originalPath, r2Key, sriHash, contentHash, new Date().toISOString()).run();

  return Response.json({ r2Key, sriHash, contentHash });
}
```

### Step 3 — D1 Schema for Asset Hash Registry

```sql
-- migrations/002_asset_hashes.sql
CREATE TABLE IF NOT EXISTS asset_hashes (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  original_path TEXT    NOT NULL UNIQUE,
  r2_key        TEXT    NOT NULL,
  sri_hash      TEXT    NOT NULL,
  content_hash  TEXT    NOT NULL,
  uploaded_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sri_integrity_failures (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  r2_key        TEXT    NOT NULL,
  expected_hash TEXT    NOT NULL,
  actual_hash   TEXT    NOT NULL,
  timestamp     INTEGER NOT NULL,
  request_url   TEXT    NOT NULL
);

CREATE INDEX idx_asset_hashes_path ON asset_hashes (original_path);
CREATE INDEX idx_sri_failures_ts   ON sri_integrity_failures (timestamp);
```

### Step 4 — Integrity Verification on Asset Retrieval

```typescript
// handlers/serveAsset.ts
import { computeSha384 } from '../lib/sri';

export async function serveAsset(
  request: Request,
  bucket: R2Bucket,
  db: D1Database
): Promise<Response> {
  const url = new URL(request.url);
  // URL pattern: /assets/<contentHash>/<filename>
  const r2Key = url.pathname.replace(/^\//, '');

  const object = await bucket.get(r2Key);
  if (!object) {
    return new Response('Not Found', { status: 404 });
  }

  const body = await object.arrayBuffer();
  const expectedHash = object.customMetadata?.sriHash;

  if (expectedHash) {
    const actualHash = await computeSha384(body);
    if (actualHash !== expectedHash) {
      // Audit the failure
      await db.prepare(
        `INSERT INTO sri_integrity_failures
           (r2_key, expected_hash, actual_hash, timestamp, request_url)
         VALUES (?, ?, ?, ?, ?)`
      ).bind(r2Key, expectedHash, actualHash, Date.now(), request.url).run();

      // Serve a 500 rather than corrupted content
      return new Response('Asset integrity check failed', { status: 500 });
    }
  }

  const contentType = object.httpMetadata?.contentType ?? 'application/octet-stream';
  const cacheControl = 'public, max-age=31536000, immutable'; // safe: content-hash in URL

  return new Response(body, {
    headers: {
      'Content-Type': contentType,
      'Cache-Control': cacheControl,
      'X-Content-Type-Options': 'nosniff',
    },
  });
}
```

### Step 5 — SRI Attribute Injection via HTMLRewriter

```typescript
// lib/sriInjector.ts
interface AssetHashRow {
  original_path: string;
  r2_key: string;
  sri_hash: string;
  content_hash: string;
}

class SriInjector implements HTMLRewriterElementContentHandlers {
  constructor(
    private hashMap: Map<string, AssetHashRow>,
    private assetBase: string
  ) {}

  element(element: Element): void {
    const src = element.getAttribute('src') ?? element.getAttribute('href');
    if (!src) return;

    const record = this.hashMap.get(src);
    if (!record) return;

    // Rewrite src/href to content-addressable URL
    const newUrl = `${this.assetBase}/${record.r2_key}`;
    if (element.tagName === 'script') {
      element.setAttribute('src', newUrl);
      element.setAttribute('integrity', record.sri_hash);
      element.setAttribute('crossorigin', 'anonymous');
    } else if (element.tagName === 'link') {
      element.setAttribute('href', newUrl);
      element.setAttribute('integrity', record.sri_hash);
      element.setAttribute('crossorigin', 'anonymous');
    }
  }
}

export async function injectSriAttributes(
  response: Response,
  db: D1Database,
  assetBase: string
): Promise<Response> {
  // Bulk-fetch all known asset hashes to avoid per-element DB queries
  const { results } = await db.prepare(
    'SELECT original_path, r2_key, sri_hash, content_hash FROM asset_hashes'
  ).all<AssetHashRow>();

  const hashMap = new Map<string, AssetHashRow>();
  for (const row of results) {
    hashMap.set(row.original_path, row);
  }

  const injector = new SriInjector(hashMap, assetBase);
  return new HTMLRewriter()
    .on('script[src]', injector)
    .on('link[rel="stylesheet"]', injector)
    .transform(response);
}
```

### Step 6 — Worker Integration

```typescript
// worker.ts
import { handleAssetUpload } from './handlers/upload';
import { serveAsset } from './handlers/serveAsset';
import { injectSriAttributes } from './lib/sriInjector';

interface Env {
  ASSETS: R2Bucket;
  DB: D1Database;
  ASSET_BASE: string;   // e.g. https://assets.example.com
  UPLOAD_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Upload endpoint (authenticated)
    if (url.pathname === '/upload') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.UPLOAD_SECRET}`) {
        return new Response('Unauthorized', { status: 401 });
      }
      return handleAssetUpload(request, env.ASSETS, env.DB);
    }

    // Asset serving with integrity verification
    if (url.pathname.startsWith('/assets/')) {
      return serveAsset(request, env.ASSETS, env.DB);
    }

    // HTML serving with SRI injection
    const originResponse = await fetch(request);
    const contentType = originResponse.headers.get('content-type') ?? '';
    if (contentType.includes('text/html')) {
      return injectSriAttributes(originResponse, env.DB, env.ASSET_BASE);
    }

    return originResponse;
  },
};
```

## Implementation Details

- **SHA-384**: The W3C SRI specification recommends SHA-384 as the primary algorithm; it provides 192-bit security and is supported in all modern browsers.
- **Content-addressable URLs**: Embedding the SHA-256 hex digest in the asset URL (`/assets/<hash>/<name>`) makes cache-busting automatic — any content change produces a new URL — and allows aggressive `max-age=31536000, immutable` caching.
- **D1 as hash registry**: Storing `original_path → r2_key + sri_hash` in D1 allows `HTMLRewriter` to bulk-fetch all mappings once per HTML response rather than making per-element R2 metadata calls.
- **R2 custom metadata**: Storing `sriHash` in R2 object custom metadata provides a fast path for verification without a D1 lookup on every asset fetch.
- **Integrity failure logging**: Writing to `sri_integrity_failures` and returning `500` prevents serving tampered content while creating a durable audit trail.

## Anti-patterns

- Do not generate the SRI hash in the browser — it must be generated server-side at upload time from the authoritative file.
- Do not use SHA-1 or SHA-256 for SRI attributes — browsers require SHA-256 minimum, but SHA-384 is the recommended baseline for new deployments.
- Do not skip `crossorigin="anonymous"` on SRI-protected elements — without it the browser performs a non-CORS fetch and cannot validate the integrity hash for cross-origin resources.
- Do not use mutable R2 keys (like `/assets/main.js`) with long-lived caches — a content change updates the file but CDN caches may serve stale content with an incorrect hash.
- Do not silently swallow integrity failures — always log them and return an error rather than serving potentially tampered content.

## Gotchas

- R2 `customMetadata` values are stored as strings and must be serialized/deserialized manually.
- `HTMLRewriter` processes elements as a stream; the D1 bulk query must complete before the `transform` call so that the hash map is populated — await `injectSriAttributes` fully before returning.
- Browsers enforce SRI only for resources loaded via `<script>` and `<link rel="stylesheet">` elements; `fetch()` calls in JavaScript require manual hash verification.
- If the origin HTML is served with `Cache-Control: public`, the browser may cache HTML with old SRI hashes after an asset update. Set `no-cache` on HTML responses (revalidate on each request) while keeping `immutable` on content-addressed asset URLs.
- `crypto.subtle.digest` returns an `ArrayBuffer`; the base64 encoding must use the standard alphabet (not URL-safe) for SRI attributes.

## Verification

1. Upload an asset via `PUT /upload?path=/js/app.js` — response should include `sriHash` starting with `sha384-`.
2. Fetch the returned `r2_key` URL — expect `200` with `Cache-Control: immutable`.
3. Manually alter a byte in R2 (via wrangler or S3-compatible client); re-fetch the asset — expect `500` and a row in `sri_integrity_failures`.
4. Load the application HTML — inspect `<script>` elements for `integrity` and `crossorigin` attributes matching the uploaded `sriHash`.
5. Rename a CSS file and re-upload — confirm the HTML now references the new content-addressable URL with the updated SRI hash.

## Related

- `workers-content-security-policy-dynamic.md` — CSP `require-sri-for` directive complements SRI attribute enforcement
- `workers-request-signing-hmac.md` — signing upload requests from CI/CD pipelines to the `/upload` endpoint

## Sources

- W3C Subresource Integrity: https://www.w3.org/TR/SRI/
- MDN SRI: https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
- Cloudflare R2: https://developers.cloudflare.com/r2/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
