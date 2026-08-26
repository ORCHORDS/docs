# Workers Response Compression: Brotli and Zstd

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker that serves JSON API responses or HTML over the Cloudflare network is transferring uncompressed payloads because Cloudflare's automatic compression pass does not apply to responses generated inside the Worker's `Response` constructor. Transfer sizes exceed 50 KB per response, and mobile users on congested networks report slow perceived load times. Adding Brotli or Zstd compression in the Worker itself cuts transfer size by 60–80 % with negligible CPU overhead relative to typical Worker CPU budgets.

## Context

Cloudflare applies gzip compression automatically to cacheable HTML responses served from origin, but Worker-generated `Response` objects bypass this pass by default — the Worker is the origin as far as Cloudflare is concerned. The `CompressionStream` Web API is available in the Workers runtime and supports `gzip`, `deflate`, and `deflate-raw`; Brotli (`br`) is available via the `BrotliCompress` WASM module bundled in the runtime as of mid-2026. Zstd support (`zstd`) landed in Workers runtime v2025.1 via `CompressionStream("zstd")`.

The correct approach: inspect `Accept-Encoding`, negotiate the best available algorithm, stream-compress the response body, and set the appropriate `Content-Encoding` and `Vary` headers.

## 1. Encoding Negotiation Helper

```typescript
// lib/encoding.ts
export type Encoding = "zstd" | "br" | "gzip" | "identity";

const PRIORITY: Encoding[] = ["zstd", "br", "gzip", "identity"];

/**
 * Parses Accept-Encoding and returns the best mutually supported algorithm.
 * Respects quality values (q=) per RFC 9110 §12.5.3.
 */
export function negotiateEncoding(acceptEncoding: string | null): Encoding {
  if (!acceptEncoding) return "identity";

  const supported = new Set<string>(PRIORITY);
  let best: Encoding = "identity";
  let bestQ = 0;

  for (const part of acceptEncoding.split(",")) {
    const [rawToken, rawQ] = part.trim().split(";q=");
    const token = rawToken.trim().toLowerCase();
    const q     = rawQ ? parseFloat(rawQ) : 1.0;

    if (supported.has(token) && q > bestQ) {
      bestQ = q;
      best  = token as Encoding;
    }
  }

  return best;
}
```

## 2. Streaming Compression Wrapper

```typescript
// lib/compress.ts
import { negotiateEncoding, Encoding } from "./encoding";

export interface CompressOptions {
  /** Minimum body length in bytes to compress. Below this, skip compression. */
  minSize?: number;
}

/**
 * Returns a new Response with the body stream-compressed according to the
 * best encoding the client advertises. Adds Content-Encoding + Vary headers.
 * Passes through if the payload is smaller than minSize.
 */
export async function compressResponse(
  response: Response,
  request: Request,
  options: CompressOptions = {}
): Promise<Response> {
  const { minSize = 1024 } = options;

  // Don't compress already-encoded responses
  if (response.headers.get("Content-Encoding")) return response;

  // Don't compress non-compressible content types
  const ct = response.headers.get("Content-Type") ?? "";
  if (/^(image|audio|video|application\/(zip|gzip|zstd|brotli|pdf))/.test(ct)) {
    return response;
  }

  const encoding = negotiateEncoding(request.headers.get("Accept-Encoding"));
  if (encoding === "identity") return response;

  // Buffer to check size threshold (only read the body once via tee)
  const [sizeCheck, toCompress] = response.body!.tee();
  const reader  = sizeCheck.getReader();
  let byteCount = 0;

  while (byteCount < minSize) {
    const { done, value } = await reader.read();
    if (done) break;
    byteCount += value.byteLength;
  }
  reader.cancel();

  if (byteCount < minSize) {
    // Too small — return with original stream
    return new Response(toCompress, response);
  }

  // Stream-compress
  const compressionAlgo = encoding === "zstd" ? "zstd"
    : encoding === "br"   ? "deflate"  // fallback: native br lands runtime ≥2025.4
    : "gzip";

  const cs             = new CompressionStream(compressionAlgo as CompressionFormat);
  const compressedBody = toCompress.pipeThrough(cs);

  const headers = new Headers(response.headers);
  headers.set("Content-Encoding", encoding);
  headers.delete("Content-Length"); // compressed length differs
  headers.append("Vary", "Accept-Encoding");

  return new Response(compressedBody, {
    status:     response.status,
    statusText: response.statusText,
    headers,
  });
}
```

## 3. Integration in the Worker Fetch Handler

```typescript
// worker.ts
import { compressResponse } from "./lib/compress";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const data = await buildResponsePayload(env);

    const raw = Response.json(data, {
      headers: { "Cache-Control": "public, max-age=60, stale-while-revalidate=300" },
    });

    return compressResponse(raw, request, { minSize: 512 });
  },
};
```

## 4. Brotli via Native Runtime Support (runtime ≥ 2025.4)

When the Workers runtime exposes `"br"` as a valid `CompressionFormat`, swap the fallback in the `compressionAlgo` mapping:

```typescript
// Feature-detect native Brotli support at module scope (evaluated once per isolate)
const NATIVE_BROTLI: boolean = (() => {
  try {
    new CompressionStream("br");
    return true;
  } catch {
    return false;
  }
})();

function selectCompressionAlgo(encoding: string): CompressionFormat {
  if (encoding === "zstd") return "zstd";
  if (encoding === "br")   return NATIVE_BROTLI ? "br" : "gzip";
  return "gzip";
}
```

## 5. Caching Compressed Variants with the Cache API

```typescript
// Serve compressed responses from the Cache API to avoid re-compressing on each hit
async function serveWithCompressionCache(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const cache      = caches.default;
  // Cache key includes encoding so each variant is stored separately
  const cacheKey   = new Request(
    `${request.url}?__enc=${request.headers.get("Accept-Encoding") ?? "identity"}`,
    { headers: request.headers }
  );
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const raw        = Response.json(await buildResponsePayload(env));
  const compressed = await compressResponse(raw, request, { minSize: 512 });

  ctx.waitUntil(cache.put(cacheKey, compressed.clone()));
  return compressed;
}
```

## 6. Verification via Wrangler Dev

```bash
# Test encoding negotiation locally
curl -s -o /dev/null -w "%{size_download} %{content_type}\n" \
  -H "Accept-Encoding: zstd, br, gzip" \
  http://localhost:8787/api/data

# Confirm Content-Encoding header
curl -I -H "Accept-Encoding: br" http://localhost:8787/api/data | grep content-encoding
```

## Anti-patterns

- **Setting `Content-Encoding: br` while using `deflate` internally** — the browser will reject the response with a decoding error; always keep the algorithm and the header in sync.
- **Compressing small responses** — below ~512 bytes, compression headers add overhead that can exceed the space saved. Guard with `minSize`.
- **Re-compressing already-compressed content** — images, video, and zip files will inflate rather than shrink; check `Content-Type` before compressing.
- **Forgetting `Vary: Accept-Encoding`** — a cache that ignores `Vary` will serve a Brotli response to a client that only accepts gzip, producing a decode failure.
- **Buffering the entire body before compressing** — use `pipeThrough(new CompressionStream(...))` to keep the response streaming and TTFB low.

## Gotchas

- `CompressionStream("zstd")` is not available in Workers runtime < 2025.1; feature-detect or pin `compatibility_date` to a known-good date.
- Brotli native support in `CompressionStream` (`"br"`) may not be available on all runtime versions; the feature-detection pattern above is the safest fallback.
- The `Content-Length` header must be removed after compression — the compressed size is unknown at stream start. Failing to remove it causes HTTP clients to truncate the body.
- `Vary: Accept-Encoding` must be set; without it, Cloudflare's cache layer may serve a compressed response to a client that sent no `Accept-Encoding`.

## Verification

Compare transfer sizes before and after with the `cf-cache-status` and `content-encoding` response headers. Use `wrk` or `k6` to measure p95 TTFB at load:

```typescript
// Smoke test — assert Content-Encoding is set for large payloads
const res = await fetch("https://worker.example.com/api/large", {
  headers: { "Accept-Encoding": "br, gzip" },
});
console.assert(res.headers.get("content-encoding") !== null, "No compression applied");
console.assert(res.headers.get("vary")?.includes("Accept-Encoding"), "Vary header missing");
```

## Related

- `workers-response-streaming-ttfb-optimization.md`
- `workers-cache-api-stale-while-revalidate.md`
- `compression-gzip-brotli.md`
- `http-zstd-content-coding-window-bounds.md`
- `workers-streaming-large-payloads.md`

## Sources

- WHATWG Compression Streams API — compression.spec.whatwg.org
- Cloudflare Workers Compression Streams — developers.cloudflare.com/workers/runtime-apis/streams/compression-streams
- RFC 9110 §12.5.3 Accept-Encoding quality values — rfc-editor.org/rfc/rfc9110#section-12.5.3
- Cloudflare Workers compatibility dates — developers.cloudflare.com/workers/configuration/compatibility-dates
