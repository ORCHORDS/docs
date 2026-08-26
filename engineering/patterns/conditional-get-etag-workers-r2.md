# Conditional GET with ETag and Last-Modified for R2-Served Assets

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker serves assets from R2 (PDFs, images, generated reports, audio files).
Clients — browsers, mobile apps, API consumers — repeatedly download the same
unchanged byte stream because the Worker returns 200 with a full body on every
request. Bandwidth costs climb, client-side caches are bypassed, and perceived
latency is higher than necessary. You need the Worker to honour HTTP conditional
requests (`If-None-Match`, `If-Modified-Since`) and return `304 Not Modified` when
the resource has not changed, eliminating redundant transfers.

---

## Context

HTTP conditional GET is specified in RFC 7232. A client that received a response
with an `ETag` or `Last-Modified` header re-sends the value on the next request:

```
Client                                       Worker
  │                                              │
  │── GET /files/report.pdf ──────────────────►  │
  │◄─ 200 + ETag: "abc123" + body ─────────────  │
  │                                              │
  │── GET /files/report.pdf                      │
  │   If-None-Match: "abc123" ───────────────►   │
  │◄─ 304 Not Modified (no body) ─────────────   │
```

Cloudflare R2 objects carry an `etag` field (MD5 of the object content) and an
`uploaded` timestamp. The Worker reads these metadata fields and performs the
conditional check without re-reading the object body unless necessary.

---

## Section 1 — ETag Validation

```typescript
// lib/conditional.ts

/**
 * Evaluates If-None-Match against a resource ETag.
 * Returns true when the client's cached version matches and a 304 can be sent.
 */
export function etagMatches(request: Request, etag: string): boolean {
  const clientEtags = request.headers.get('If-None-Match');
  if (!clientEtags) return false;

  // The header may contain a comma-separated list or the wildcard "*"
  if (clientEtags.trim() === '*') return true;

  const quoted = `"${etag}"`;   // R2 etags are bare hex; HTTP ETags must be quoted
  return clientEtags
    .split(',')
    .map((e) => e.trim())
    .some((e) => e === quoted || e === `W/${quoted}`);
}

/**
 * Evaluates If-Modified-Since against a resource's last-modified timestamp.
 * Returns true when the client's cached version is still current.
 */
export function notModifiedSince(request: Request, lastModified: Date): boolean {
  const ifModSince = request.headers.get('If-Modified-Since');
  if (!ifModSince) return false;

  const clientDate = new Date(ifModSince);
  if (isNaN(clientDate.getTime())) return false;

  // Truncate to second precision (HTTP dates have 1-second granularity)
  return Math.floor(lastModified.getTime() / 1000) <= Math.floor(clientDate.getTime() / 1000);
}

/** Build the standard caching response headers for a resource. */
export function buildCacheHeaders(etag: string, lastModified: Date, maxAge: number): Headers {
  const headers = new Headers();
  headers.set('ETag',           `"${etag}"`);
  headers.set('Last-Modified',  lastModified.toUTCString());
  headers.set('Cache-Control',  `public, max-age=${maxAge}, must-revalidate`);
  headers.set('Vary',           'Accept-Encoding');
  return headers;
}
```

---

## Section 2 — R2 Object Serving with Conditional Check

```typescript
// handlers/serve-file.ts
import { etagMatches, notModifiedSince, buildCacheHeaders } from '../lib/conditional';

export interface Env {
  BUCKET: R2Bucket;
}

const CACHE_MAX_AGE = 3600;   // 1 hour CDN and browser cache

export async function serveFile(request: Request, env: Env, key: string): Promise<Response> {
  // 1. HEAD the object to read metadata cheaply (no body transfer)
  const head = await env.BUCKET.head(key);

  if (!head) {
    return new Response('Not Found', { status: 404 });
  }

  const etag         = head.etag;
  const lastModified = new Date(head.uploaded);
  const cacheHeaders = buildCacheHeaders(etag, lastModified, CACHE_MAX_AGE);

  // 2. Evaluate conditional headers
  if (etagMatches(request, etag) || notModifiedSince(request, lastModified)) {
    // Resource unchanged — send 304 with no body
    return new Response(null, {
      status:  304,
      headers: cacheHeaders,
    });
  }

  // 3. Full response — stream the object body
  const object = await env.BUCKET.get(key);

  if (!object) {
    return new Response('Not Found', { status: 404 });
  }

  cacheHeaders.set('Content-Type',   head.httpMetadata?.contentType ?? 'application/octet-stream');
  cacheHeaders.set('Content-Length', String(head.size));

  if (head.httpMetadata?.contentEncoding) {
    cacheHeaders.set('Content-Encoding', head.httpMetadata.contentEncoding);
  }

  return new Response(object.body, {
    status:  200,
    headers: cacheHeaders,
  });
}
```

---

## Section 3 — Worker Entry Point with Range Request Support

```typescript
// worker.ts
import { serveFile } from './handlers/serve-file';

export interface Env {
  BUCKET: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const url = new URL(request.url);
    // Strip leading "/" from the path to use as R2 key
    const key = url.pathname.slice(1);

    if (!key) {
      return new Response('Bad Request', { status: 400 });
    }

    const response = await serveFile(request, env, key);

    // HEAD requests: identical headers but no body
    if (request.method === 'HEAD') {
      return new Response(null, {
        status:  response.status === 200 ? 200 : response.status,
        headers: response.headers,
      });
    }

    return response;
  },
};
```

---

## Section 4 — Uploading with Content Metadata

For conditional GET to work, R2 objects must be uploaded with explicit `httpMetadata`.
Without `contentType`, browsers mishandle responses:

```typescript
// upload.ts — called from an admin or pipeline Worker
export async function uploadFile(
  bucket:      R2Bucket,
  key:         string,
  body:        ReadableStream | ArrayBuffer,
  contentType: string,
): Promise<R2Object> {
  return bucket.put(key, body, {
    httpMetadata: {
      contentType,
      cacheControl: `public, max-age=${CACHE_MAX_AGE}, must-revalidate`,
    },
  });
}
```

R2's `etag` is the MD5 of the stored content and changes automatically on each
`put()`. No manual ETag management is required.

---

## Section 5 — Testing Conditional Behaviour

```bash
# 1. First request — expect 200 + ETag in response
curl -i https://files.example.com/report.pdf | grep -E "^(HTTP|ETag|Last-Modified)"

# 2. Conditional re-request using stored ETag — expect 304
ETAG=$(curl -sI https://files.example.com/report.pdf | grep -i etag | awk '{print $2}' | tr -d '\r')
curl -i https://files.example.com/report.pdf -H "If-None-Match: $ETAG"
# HTTP/2 304

# 3. Conditional with Last-Modified — expect 304 if file unchanged
LASTMOD=$(curl -sI https://files.example.com/report.pdf | grep -i last-modified | cut -d' ' -f2-)
curl -i https://files.example.com/report.pdf -H "If-Modified-Since: $LASTMOD"
# HTTP/2 304

# 4. After re-uploading the file — expect 200 with new ETag
# (re-upload via admin endpoint or wrangler r2 object put)
curl -i https://files.example.com/report.pdf -H "If-None-Match: $ETAG"
# HTTP/2 200  (ETag changed, conditional fails, full response sent)
```

---

## Anti-patterns

**Sending the full 200 body on every request regardless of conditional headers** —
the most common omission. Conditional GET support is not automatic in Workers; you
must check the headers explicitly and return 304.

**Returning 304 without copying the ETag and Cache-Control headers** — RFC 7232
requires that a 304 response contain the same headers the 200 would have sent.
Browsers that see a 304 without `Cache-Control` drop their cached copy.

**Setting `Cache-Control: no-store` on assets that are safe to cache** — this
disables the browser cache entirely, forcing a full 200 on every request. Use
`must-revalidate` combined with conditional GET instead.

**Using a derived or timestamp-based ETag instead of R2's MD5 ETag** — R2's built-in
`etag` is content-addressed and requires no management. Using a timestamp makes the
ETag volatile on metadata-only updates (renaming, setting headers) even when bytes
are unchanged.

---

## Gotchas

- **R2 `head()` is cheaper than `get()` but still counts against R2 Class A
  operations.** If the conditional hit rate is very high (most requests result in
  304), the `head()` call is paid on every request. For extreme cases, store ETags
  in KV and check KV first before touching R2.
- **R2 ETags are bare hex strings.** HTTP ETag syntax requires surrounding double
  quotes: `"abc123"`. The `buildCacheHeaders` helper adds them; do not double-wrap.
- **Cloudflare's CDN layer may intercept conditional requests before the Worker
  runs**, returning 304 from the Cloudflare cache directly if the resource is cached
  there. This is desirable but means your Worker's conditional logic is only
  exercised on CDN misses — which is correct behaviour, not a bug.
- **Range requests** (`Range: bytes=...`) interact with ETag validation: RFC 7233
  specifies `If-Range` semantics. This pattern handles only simple conditional GET;
  add `If-Range` handling before enabling video or large file byte-range serving.

---

## Verification

Unit test:

```typescript
// test/conditional.test.ts
import { describe, it, expect } from 'vitest';
import { etagMatches, notModifiedSince } from '../src/lib/conditional';

describe('etagMatches', () => {
  it('matches a single quoted ETag', () => {
    const req = new Request('https://x.com/', { headers: { 'If-None-Match': '"abc123"' } });
    expect(etagMatches(req, 'abc123')).toBe(true);
  });

  it('matches a wildcard', () => {
    const req = new Request('https://x.com/', { headers: { 'If-None-Match': '*' } });
    expect(etagMatches(req, 'any')).toBe(true);
  });

  it('does not match a different ETag', () => {
    const req = new Request('https://x.com/', { headers: { 'If-None-Match': '"abc123"' } });
    expect(etagMatches(req, 'xyz789')).toBe(false);
  });
});
```

---

## Related

- `request-coalescing-cache-stampede.md` — prevent simultaneous R2 fetches on miss
- `multi-layer-cache-workers-cache-api-kv-d1.md` — cache R2 responses in Cache API
- `stale-while-revalidate-workers-kv.md` — serve stale while refreshing
- `secure-headers.md` — complement caching headers with security headers
- `streaming-response-sse-workers.md` — streaming R2 body to client

---

## Sources

- RFC 7232 — Hypertext Transfer Protocol: Conditional Requests
- Cloudflare R2 Workers API — developers.cloudflare.com/r2/api/workers/workers-api-reference/
- MDN: HTTP conditional requests — developer.mozilla.org/en-US/docs/Web/HTTP/Conditional_requests
- Cloudflare Workers Cache API — developers.cloudflare.com/workers/runtime-apis/cache/
