# Enabling Brotli Compression on Workers Responses

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

JSON API responses and HTML payloads served from a Cloudflare Worker are larger than necessary, inflating bandwidth costs and increasing time-to-first-byte on slow connections. The Cloudflare edge does not automatically compress Worker responses unless the Worker explicitly sets the correct headers and compresses the body itself.

## Context

- Runtime: Cloudflare Workers (V8 isolates)
- APIs used: `CompressionStream`, `Response`, `Headers`
- Trigger: HTTP fetch handler
- Content types worth compressing: JSON, HTML, plain text, SVG
- Content types to skip: images (JPEG/PNG/WebP/AVIF), video, audio, pre-compressed archives (gzip, br, zip)

---

## Section 1 — Detecting Client Support and Compressing with CompressionStream

Brotli (`br`) offers 15-25% better ratios than gzip at comparable CPU cost in Workers. Use `deflate-raw` (raw DEFLATE) when you need a lighter alternative, but prefer `br` when the client advertises it.

```typescript
export interface Env {}

const COMPRESSIBLE_TYPES = [
  'application/json',
  'text/html',
  'text/plain',
  'text/css',
  'application/javascript',
  'image/svg+xml',
];

function isCompressible(contentType: string | null): boolean {
  if (!contentType) return false;
  return COMPRESSIBLE_TYPES.some((t) => contentType.includes(t));
}

function acceptedEncoding(request: Request): 'br' | 'gzip' | 'deflate-raw' | null {
  const accept = request.headers.get('Accept-Encoding') ?? '';
  if (accept.includes('br')) return 'br';
  if (accept.includes('gzip')) return 'gzip';
  if (accept.includes('deflate')) return 'deflate-raw';
  return null;
}

async function compressBody(
  body: ReadableStream<Uint8Array>,
  encoding: 'br' | 'gzip' | 'deflate-raw',
): Promise<ReadableStream<Uint8Array>> {
  // CompressionStream is available in Workers since 2023
  // 'br' maps to Brotli; 'gzip' maps to GZIP; 'deflate-raw' maps to raw DEFLATE
  const cs = new CompressionStream(encoding as CompressionFormat);
  body.pipeTo(cs.writable); // fire-and-forget pipe; compression is streamed
  return cs.readable as ReadableStream<Uint8Array>;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Build or fetch your payload
    const payload = JSON.stringify({ hello: 'world', timestamp: Date.now() });
    const encoder = new TextEncoder();
    const bytes = encoder.encode(payload);

    const contentType = 'application/json; charset=utf-8';
    const encoding = acceptedEncoding(request);

    if (encoding && isCompressible(contentType)) {
      // Convert Uint8Array → ReadableStream
      const sourceStream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(bytes);
          controller.close();
        },
      });

      const compressed = await compressBody(sourceStream, encoding);

      const headers = new Headers({
        'Content-Type': contentType,
        'Content-Encoding': encoding === 'deflate-raw' ? 'deflate' : encoding,
        'Vary': 'Accept-Encoding',
        'Cache-Control': 'public, max-age=60, stale-while-revalidate=300',
      });

      return new Response(compressed, { status: 200, headers });
    }

    // Fallback: no compression
    return new Response(bytes, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=60',
      },
    });
  },
};
```

---

## Section 2 — Cache-Control Headers for Compressed Responses

Always emit `Vary: Accept-Encoding` so Cloudflare's cache stores separate copies per encoding. Without it, a Brotli-compressed copy may be served to a client that only supports gzip, resulting in a broken response.

```typescript
// Correct cache headers for a compressed, publicly-cacheable API response
function buildCacheHeaders(encoding: string | null): HeadersInit {
  return {
    // Tell downstream caches (including CF edge) to key on encoding
    'Vary': 'Accept-Encoding',
    // Cache at edge for 5 minutes; serve stale for up to 1 hour while revalidating
    'Cache-Control': 'public, max-age=300, stale-while-revalidate=3600',
    // Optional: expose the encoding in a custom header for observability
    ...(encoding ? { 'X-Content-Encoding': encoding } : {}),
  };
}

// For private (authenticated) responses — never cache at edge:
function buildPrivateCacheHeaders(): HeadersInit {
  return {
    'Cache-Control': 'private, no-store',
    'Vary': 'Accept-Encoding, Authorization',
  };
}
```

---

## Section 3 — Skipping Compression for Already-Compressed Content

Compressing already-compressed data (JPEG, WebP, gzip, zip) wastes CPU and can slightly *increase* payload size.

```typescript
const SKIP_COMPRESSION_EXTENSIONS = new Set([
  '.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif',
  '.mp4', '.webm', '.mp3', '.ogg',
  '.gz', '.br', '.zip', '.zst', '.7z',
  '.woff', '.woff2', // fonts are pre-compressed
]);

const SKIP_COMPRESSION_TYPES = new Set([
  'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/avif',
  'video/mp4', 'video/webm',
  'audio/mpeg', 'audio/ogg',
  'application/zip', 'application/gzip', 'application/x-brotli',
  'font/woff', 'font/woff2',
]);

function shouldSkipCompression(request: Request, contentType: string | null): boolean {
  // Check content-type
  const baseType = contentType?.split(';')[0].trim() ?? '';
  if (SKIP_COMPRESSION_TYPES.has(baseType)) return true;

  // Check URL extension as a fallback
  const url = new URL(request.url);
  const ext = url.pathname.slice(url.pathname.lastIndexOf('.')).toLowerCase();
  if (SKIP_COMPRESSION_EXTENSIONS.has(ext)) return true;

  // Skip if response is tiny — compression overhead not worth it under ~860 bytes
  return false;
}

// Usage inside fetch handler:
// const skip = shouldSkipCompression(request, upstreamResponse.headers.get('Content-Type'));
// if (skip) return upstreamResponse; // pass through as-is
```

---

## Anti-patterns

- Omitting `Vary: Accept-Encoding` — causes the CF cache to serve a Brotli body to gzip-only clients
- Compressing responses smaller than ~860 bytes — the compressed output is often larger than the input
- Using `deflate` (zlib wrapper) instead of `deflate-raw` — browser support for raw zlib in HTTP is inconsistent; prefer `gzip` or `br`
- Double-compressing: calling `compressBody` on a response that already has `Content-Encoding` set
- Setting `Content-Length` on a streamed compressed response — length changes after compression; let Cloudflare use chunked transfer

## Gotchas

- `CompressionStream('br')` is available in Workers but NOT in the browser `CompressionStream` polyfill — test in `wrangler dev` not in a browser console
- `pipeTo` is fire-and-forget; errors in the compression stream won't surface unless you attach a `catch` to the promise it returns
- Cloudflare's automatic compression (Rocket Loader / Minify) is disabled for Worker responses — the Worker owns compression entirely
- `deflate-raw` sets `Content-Encoding: deflate` in the response header (the HTTP spec uses `deflate` to mean raw DEFLATE)

## Verification

```bash
# Deploy and probe encoding negotiation
wrangler deploy

CURL_WORKER_URL="https://your-worker.workers.dev"

# Request Brotli
curl -s -o /dev/null -w "%{http_code} | CE: %header{content-encoding} | Size: %{size_download}\n" \
  -H 'Accept-Encoding: br, gzip, deflate' \
  "$CURL_WORKER_URL"

# Request gzip only
curl -s -o /dev/null -w "%{http_code} | CE: %header{content-encoding} | Size: %{size_download}\n" \
  -H 'Accept-Encoding: gzip' \
  "$CURL_WORKER_URL"

# No compression
curl -s -o /dev/null -w "%{http_code} | CE: %header{content-encoding} | Size: %{size_download}\n" \
  "$CURL_WORKER_URL"

# Verify Vary header is present
curl -sI -H 'Accept-Encoding: br' "$CURL_WORKER_URL" | grep -i 'vary\|content-encoding'
```

## Related

- `documentation/categories/performance/workers-cache-ttl-tiered-kv-strategy.md`
- `documentation/categories/performance/workers-connection-keep-alive-upstream-fetch.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/streams/compression-stream/
- https://developers.cloudflare.com/cache/concepts/cache-control/
- https://developer.mozilla.org/en-US/docs/Web/API/CompressionStream
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
