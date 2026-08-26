# Response Compression with Brotli/gzip in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker returns large JSON payloads, HTML documents, or text assets and you
want to minimise bytes-on-the-wire without delegating to Cloudflare's automatic
compression (which only applies to cacheable responses served from edge cache,
not dynamic Worker responses).

Common signals:
- `Content-Encoding` header absent on dynamic API responses.
- Lighthouse reports large network payloads for Worker-served routes.
- Akamai / CDN bypass tests show uncompressed bodies despite `Accept-Encoding: br, gzip` in the request.

---

## Context

Cloudflare Workers run in the V8 isolate environment. The Web Streams API is
available, including `CompressionStream` (gzip and deflate). Brotli encoding is
not available natively via `CompressionStream` in Workers (as of mid-2026); it
requires either a WASM brotli encoder or Cloudflare Workers AI (text generation
overkill) — the practical choice is a tiny WASM module compiled from the
reference brotli encoder.

Gzip via `CompressionStream` is zero-dependency, low-latency, and works today.
Use brotli only when the marginal compression gain matters (typically ≥ 20 KB
payloads, repeated structure such as API JSON).

---

## Solution

```typescript
// worker.ts
import type { ExecutionContext } from '@cloudflare/workers-types';

export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

// Content types that benefit from compression
const COMPRESSIBLE_TYPES = new Set([
  'application/json',
  'application/javascript',
  'application/xml',
  'text/html',
  'text/plain',
  'text/css',
  'text/javascript',
  'text/xml',
  'image/svg+xml',
]);

// Content types that are already compressed — skip encoding
const ALREADY_COMPRESSED = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/avif',
  'image/gif',
  'audio/mpeg',
  'video/mp4',
  'application/zip',
  'application/gzip',
  'application/br',
  'font/woff2',
]);

type SupportedEncoding = 'br' | 'gzip' | 'deflate' | 'identity';

/**
 * Parse Accept-Encoding header and return the best supported encoding.
 * Returns 'identity' when the client does not advertise compression support.
 */
function negotiateEncoding(acceptEncoding: string | null): SupportedEncoding {
  if (!acceptEncoding) return 'identity';

  // Parse q-values: "br;q=1.0, gzip;q=0.8, deflate;q=0.6"
  const directives = acceptEncoding
    .split(',')
    .map((part) => {
      const [enc, q] = part.trim().split(';q=');
      return { enc: enc.trim().toLowerCase(), q: q ? parseFloat(q) : 1.0 };
    })
    .filter((d) => d.q > 0)
    .sort((a, b) => b.q - a.q);

  for (const { enc } of directives) {
    // Workers support gzip natively; brotli requires WASM (checked at runtime)
    if (enc === 'gzip' || enc === 'deflate') return enc as SupportedEncoding;
    // 'br' returned only if WASM brotli is loaded (handled by caller)
  }
  return 'identity';
}

/**
 * Compress a ReadableStream using the platform's CompressionStream.
 * format: 'gzip' | 'deflate'
 */
function compressStream(
  stream: ReadableStream,
  format: 'gzip' | 'deflate'
): ReadableStream {
  const cs = new CompressionStream(format);
  stream.pipeTo(cs.writable);
  return cs.readable;
}

/**
 * Compress an ArrayBuffer using CompressionStream (fully materialised).
 * Use for payloads under ~4 MB where you also need to measure the ratio.
 */
async function compressBuffer(
  input: ArrayBuffer,
  format: 'gzip' | 'deflate'
): Promise<ArrayBuffer> {
  const cs = new CompressionStream(format);
  const writer = cs.writable.getWriter();
  writer.write(new Uint8Array(input));
  writer.close();

  const chunks: Uint8Array[] = [];
  const reader = cs.readable.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }

  const totalLength = chunks.reduce((s, c) => s + c.byteLength, 0);
  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result.buffer;
}

/**
 * Determine whether to compress and at what level of materialisation.
 *
 * Strategy:
 * - Streaming compression (CompressionStream piped) for responses that
 *   already have a body stream and whose size is unknown.
 * - Buffered compression when we need the final size for Analytics Engine.
 */
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const upstreamResponse = await fetch(request);

    const contentType = (upstreamResponse.headers.get('content-type') ?? '').split(';')[0].trim();
    const contentEncoding = upstreamResponse.headers.get('content-encoding');

    // Skip if already encoded or not a compressible type
    const shouldCompress =
      !contentEncoding &&
      COMPRESSIBLE_TYPES.has(contentType) &&
      !ALREADY_COMPRESSED.has(contentType) &&
      upstreamResponse.body !== null;

    if (!shouldCompress) {
      return upstreamResponse;
    }

    const encoding = negotiateEncoding(request.headers.get('accept-encoding'));
    if (encoding === 'identity') {
      return upstreamResponse;
    }

    // For analytics we materialise small responses (< 512 KB hint)
    const contentLengthHint = upstreamResponse.headers.get('content-length');
    const knownSmall = contentLengthHint ? parseInt(contentLengthHint, 10) < 524_288 : false;

    const newHeaders = new Headers(upstreamResponse.headers);
    newHeaders.set('content-encoding', encoding);
    newHeaders.delete('content-length'); // length changes after compression
    newHeaders.set('vary', 'Accept-Encoding');

    if (knownSmall && encoding === 'gzip') {
      // Buffered path: lets us record compression ratio
      const rawBuffer = await upstreamResponse.arrayBuffer();
      const compressedBuffer = await compressBuffer(rawBuffer, 'gzip');

      const ratio = rawBuffer.byteLength > 0
        ? compressedBuffer.byteLength / rawBuffer.byteLength
        : 1;

      // Record to Analytics Engine (non-blocking)
      ctx.waitUntil(
        recordCompressionMetric(env.ANALYTICS, {
          url: request.url,
          encoding,
          originalBytes: rawBuffer.byteLength,
          compressedBytes: compressedBuffer.byteLength,
          ratio,
        })
      );

      newHeaders.set('content-length', String(compressedBuffer.byteLength));
      return new Response(compressedBuffer, {
        status: upstreamResponse.status,
        headers: newHeaders,
      });
    }

    // Streaming path: no materialisation, lower TTFB
    const compressedStream = compressStream(
      upstreamResponse.body!,
      encoding === 'deflate' ? 'deflate' : 'gzip'
    );

    return new Response(compressedStream, {
      status: upstreamResponse.status,
      headers: newHeaders,
    });
  },
};

// ---------------------------------------------------------------------------
// Analytics Engine helper
// ---------------------------------------------------------------------------

interface CompressionMetric {
  url: string;
  encoding: string;
  originalBytes: number;
  compressedBytes: number;
  ratio: number;
}

async function recordCompressionMetric(
  dataset: AnalyticsEngineDataset,
  metric: CompressionMetric
): Promise<void> {
  try {
    dataset.writeDataPoint({
      blobs: [metric.url, metric.encoding],
      doubles: [metric.originalBytes, metric.compressedBytes, metric.ratio],
      indexes: [new URL(metric.url).pathname],
    });
  } catch {
    // Analytics Engine write failure must never fail the request
  }
}
```

---

## Implementation Details

**CompressionStream API** is part of the Encoding Living Standard and available
in all Workers runtimes from 2023+. It uses the platform's native zlib (C)
implementation, so it is fast and does not count against CPU time the way a
pure-JS compressor would.

**Vary header** is mandatory. Without `Vary: Accept-Encoding` a downstream CDN
may serve a gzip response to a client that only accepts identity, causing
corruption.

**Content-Length stripping** is required because the compressed body length
differs from the raw length. Clients that rely on `Content-Length` for progress
bars receive an accurate value only on the buffered path where it is re-set.

**Streaming vs buffered**: The streaming path yields the first byte sooner
(lower TTFB) but precludes recording byte counts. Use the buffered path only
for known-small responses where the analytics value justifies the latency cost.

**Brotli**: Until `CompressionStream` gains `'br'` support in Workers, use the
`@nicolo-ribaudo/brotli-wasm` package or compile
[google/brotli](https://github.com/google/brotli) to WASM. Import the `.wasm`
binary as a module-scope constant (see `workers-wasm-compute-offload.md`).

---

## Anti-patterns

- **Double-compressing**: Forwarding a response that already has
  `Content-Encoding: gzip` through another `CompressionStream` produces a
  corrupt double-wrapped body. Always check the upstream `Content-Encoding`
  header before compressing.
- **Compressing images/video**: JPEG, WebP, AVIF, MP4, WOFF2 are already
  compressed. Applying gzip adds CPU overhead and typically inflates the payload
  by 1–4 %.
- **Ignoring `q=0` directives**: `Accept-Encoding: gzip;q=0` means the client
  explicitly refuses gzip. The `negotiateEncoding` helper above filters these
  out via `filter(d => d.q > 0)`.
- **Forgetting `Vary`**: Omitting `Vary: Accept-Encoding` causes CDNs to serve
  a cached compressed response to clients that did not request compression.

---

## Gotchas

- `CompressionStream` in Workers uses the default zlib compression level (6).
  There is no API to tune it. If you need level 1 (fastest) vs level 9
  (smallest), you must use a WASM compressor.
- `DecompressionStream` exists too — use it if your Worker needs to decompress
  upstream responses (e.g., an origin that always gzips).
- `pipeTo` does not return a value in the streaming path; errors propagate via
  the stream's error channel, not a rejected Promise. Wrap the outer fetch in a
  try/catch on the writable side if upstream abort handling matters.
- Analytics Engine `writeDataPoint` is eventually consistent; allow up to 60 s
  for data to appear in GraphQL queries.

---

## Verification

```bash
# Confirm gzip encoding is returned
curl -sI -H 'Accept-Encoding: gzip' https://api.example.com/v1/tracks \
  | grep -i content-encoding
# expected: content-encoding: gzip

# Measure payload size with and without compression
curl -so /dev/null -w '%{size_download}' https://api.example.com/v1/tracks
curl -so /dev/null -w '%{size_download}' \
  -H 'Accept-Encoding: gzip' https://api.example.com/v1/tracks

# Query compression ratio via Analytics Engine GraphQL
# avg(doubles[2]) < 0.5 means > 50% size reduction on average
```

---

## Related

- `workers-wasm-compute-offload.md` — Loading WASM modules for brotli encoding
- `workers-ttfb-optimization.md` — Streaming HTML to reduce TTFB
- `workers-cache-warming-strategy.md` — Pre-warming compressed responses in Cache API

---

## Sources

- [CompressionStream — WHATWG Encoding spec](https://encoding.spec.whatwg.org/#compression-stream)
- [Cloudflare Workers Runtime APIs — Encoding](https://developers.cloudflare.com/workers/runtime-apis/encoding/)
- [Analytics Engine — writeDataPoint](https://developers.cloudflare.com/analytics/analytics-engine/)
- [google/brotli — reference encoder](https://github.com/google/brotli)
